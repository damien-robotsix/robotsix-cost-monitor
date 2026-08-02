"""Service layer: cross-project cost aggregation with a small TTL cache.

Projects are discovered at runtime from the central-deploy registry (not from
hardcoded config).  The :class:`TTLCache` supports stale-while-revalidate (SWR):

- Entries are *fresh* for ``ttl`` seconds and served immediately.
- After ``ttl`` seconds the entry is *stale* — still served, but a background
  refresh is triggered so the next request gets fresh data.
- On cold cache (no entry at all) the fetch blocks the caller.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any, TypeVar

import structlog
from robotsix_http import (
    ExternalRateLimitError,
    ExternalServiceError,
)

from .aggregations import (
    BackendKind,
    aggregate_by_name,
    aggregate_by_name_backend,
    aggregate_by_name_split,
    backend_cost_series,
    cost_trend,
    merge_model_costs,
    most_expensive_session,
    most_expensive_trace,
)
from .cache import TTLCache
from .clients.langfuse import LangfuseClient
from .clients.models import LangfuseTrace, RegistryProject
from .clients.registry import RegistryClient
from .config import Config
from .exceptions import (
    CacheError,
)

_T = TypeVar("_T")
logger = structlog.get_logger(__name__)


#: Dashboard window presets (hours).  Pre-warmed so every selector option
#: is a cache hit from the moment the dashboard first loads.
DASHBOARD_WINDOW_PRESETS: tuple[int, ...] = (1, 6, 24, 168)


class CostService:
    """Cross-project cost aggregation service with per-window TTL cache.

    All five internal caches share a single :attr:`last_updated` timestamp
    (the youngest refresh across *all* caches) so the dashboard can display
    data freshness.
    """

    def __init__(self, config: Config, registry_client: RegistryClient) -> None:
        """Initialise the service with config and a registry client.

        Starts with an empty project/client map — call :meth:`refresh_projects`
        during startup to populate from the registry.
        """
        self.config = config
        self._registry = registry_client
        self._project_map: dict[str, RegistryProject] = {}
        self._clients: dict[str, LangfuseClient] = {}
        ttl = self.config.settings.cache_ttl_seconds
        self._last_updated: datetime | None = None
        self._caches: list[TTLCache[Any, Any]] = []
        on_refresh = self._touch_last_updated

        def _mk[T](t: type[T]) -> TTLCache[Any, T]:
            c = TTLCache[Any, T](ttl, on_refresh=on_refresh)
            self._caches.append(c)
            return c

        # cache: (slug, hours) -> (traces, monotonic_deadline)
        self._cache = _mk(list[LangfuseTrace])
        # cache: (slug, hours) -> (per-model usage rows, monotonic_deadline)
        self._model_cache = _mk(list[dict[str, Any]])
        # cache: (slug, hours) -> ({time_bucket -> {backend -> cost}}, deadline)
        self._backend_cache = _mk(dict[str, dict[str, float]])
        # cache: (slug, hours) -> (per-(stage, backend) rows, monotonic_deadline)
        self._agent_usage_cache = _mk(list[dict[str, Any]])
        # cache: (slug, hours) -> (trace_count, monotonic_deadline)
        self._trace_count_cache = _mk(int)

    def _touch_last_updated(self) -> None:
        """Record the current wall-clock time as the last cache refresh."""
        self._last_updated = datetime.now(UTC)

    @property
    def last_updated(self) -> datetime | None:
        """UTC datetime of the most recent cache refresh, or ``None`` when cold."""
        return self._last_updated

    def invalidate_all(self) -> None:
        """Clear every internal cache so the next request fetches fresh data."""
        for c in self._caches:
            c.invalidate()
        self._last_updated = None

    async def refresh_projects(self) -> None:
        """Query the registry and rebuild the project/client map.

        Best-effort: on failure the existing project list is kept unchanged.
        """
        try:
            registry_projects = await self._registry.fetch_projects()
        except Exception:
            logger.warning("refresh_projects: registry fetch failed")
            return
        if not registry_projects:
            logger.warning("refresh_projects: registry returned no projects")
            return
        self._project_map = {p.slug: p for p in registry_projects}
        self._clients = {
            p.slug: LangfuseClient(
                public_key=p.langfuse_public_key,
                secret_key=p.langfuse_secret_key,
                base_url=p.langfuse_base_url,
            )
            for p in registry_projects
        }
        self.invalidate_all()
        logger.info(
            "refresh_projects: discovered %d project(s) across %d component(s)",
            len(self._project_map),
            len(self.components()),
        )

    def projects(self) -> list[RegistryProject]:
        """Return every discovered project, in registry order."""
        return list(self._project_map.values())

    def components(self) -> dict[str, list[RegistryProject]]:
        """Return discovered projects grouped by owning component.

        Insertion order follows the registry, so the dashboard's component list
        is stable across refreshes.  Projects whose component is unknown are
        grouped under their own slug rather than dropped.
        """
        out: dict[str, list[RegistryProject]] = {}
        for p in self._project_map.values():
            out.setdefault(p.component_id or p.slug, []).append(p)
        return out

    def _projects(self, slug: str | None) -> list[RegistryProject]:
        """Resolve a selector to the projects it covers.

        Accepts ``"all"``/empty (everything), a **component id** (every project
        that component owns), or a single **project slug**.  Resolving both
        levels here is what lets every endpoint be component-aware without any
        per-endpoint or per-component code.

        Project slugs win over component ids on collision: a project is the
        more specific thing, and the single-project component case (where the
        two names coincide) resolves identically either way.
        """
        if not slug or slug == "all":
            return list(self._project_map.values())
        if (p := self._project_map.get(slug)) is not None:
            return [p]
        return [q for q in self._project_map.values() if q.component_id == slug]

    async def _safe_project_fetch[T](
        self,
        project: RegistryProject,
        fetch_fn: Callable[[], Awaitable[T]],
        label: str,
        default: T,
    ) -> T:
        try:
            return await fetch_fn()
        except ExternalServiceError, ExternalRateLimitError, CacheError:
            logger.warning("project %s %s failed transiently", project.slug, label)
            return default
        except Exception:
            logger.exception("project %s %s failed unexpectedly", project.slug, label)
            return default

    async def _cached_fetch(
        self,
        project: RegistryProject,
        hours: int,
        cache: TTLCache[tuple[str, int], _T],
        fetch_fn: Callable[[int], Awaitable[_T]],
    ) -> _T:
        key = (project.slug, hours)
        return await cache.get_or_fetch(key, lambda: fetch_fn(hours))

    async def _traces(
        self, project: RegistryProject, hours: int
    ) -> list[LangfuseTrace]:
        return await self._cached_fetch(
            project,
            hours,
            self._cache,
            lambda h: self._clients[project.slug].fetch_traces_window(h),
        )

    async def _trace_count(self, project: RegistryProject, hours: int) -> int:
        """Trace count for the window via a server-side metrics query (cached).

        Avoids paging every raw trace just to ``len()`` them — the headline
        ``summary`` only needs the count, not the trace bodies.
        """
        return await self._cached_fetch(
            project,
            hours,
            self._trace_count_cache,
            lambda h: self._clients[project.slug].fetch_trace_count_window(h),
        )

    async def _gather(
        self, slug: str | None, hours: int
    ) -> list[tuple[RegistryProject, list[LangfuseTrace]]]:
        out: list[tuple[RegistryProject, list[LangfuseTrace]]] = []
        for p in self._projects(slug):
            traces: list[LangfuseTrace] = await self._safe_project_fetch(
                p,
                lambda: self._traces(p, hours),  # noqa: B023
                "fetch traces",
                [],
            )
            out.append((p, traces))
        return out

    async def _gather_list_results(
        self,
        slug: str | None,
        hours: int,
        fetch: Callable[[RegistryProject, int], Awaitable[list[dict[str, Any]]]],
    ) -> list[dict[str, Any]]:
        parts: list[list[dict[str, Any]]] = []
        for p in self._projects(slug):
            result: list[dict[str, Any]] = await self._safe_project_fetch(
                p,
                lambda: fetch(p, hours),  # noqa: B023
                "fetch list results",
                [],
            )
            parts.append(result)
        return [r for part in parts for r in part]

    async def summary(self, slug: str | None, hours: int) -> dict[str, Any]:
        """Per-project totals + the aggregate, for the window.

        Cost is observation-based (the same window-accurate metrics source as the
        by-model / by-backend breakdowns), so the headline total, the per-model
        rows, and the per-backend totals all reconcile — a backend can never
        exceed the total. ``trace_count`` comes from a server-side ``view=traces``
        count metric (not by paging every trace), so this stays fast.
        """
        per_project: list[dict[str, Any]] = []
        total = 0.0
        for p in self._projects(slug):
            models: list[dict[str, Any]] = await self._safe_project_fetch(
                p,
                lambda: self._model_usage(p, hours),  # noqa: B023
                "model-usage",
                [],
            )
            trace_count: int = await self._safe_project_fetch(
                p,
                lambda: self._trace_count(p, hours),  # noqa: B023
                "trace-count",
                0,
            )
            cost = round(sum(m["cost"] for m in models), 6)
            total += cost
            per_project.append(
                {
                    "name": p.name,
                    "slug": p.slug,
                    "component": p.component_id,
                    "cost": cost,
                    "trace_count": trace_count,
                }
            )
        total = round(total, 6)
        by_component: dict[str, dict[str, Any]] = {}
        for row in per_project:
            agg = by_component.setdefault(
                str(row["component"] or row["slug"]),
                {
                    "component": row["component"] or row["slug"],
                    "cost": 0.0,
                    "trace_count": 0,
                    "projects": [],
                },
            )
            agg["cost"] = round(agg["cost"] + float(row["cost"]), 6)
            agg["trace_count"] += int(row["trace_count"])
            agg["projects"].append(row)
        return {
            "window_hours": hours,
            "total_cost": total,
            "projects": per_project,
            "components": sorted(
                by_component.values(), key=lambda c: float(c["cost"]), reverse=True
            ),
        }

    async def by_agent(
        self, slug: str | None, hours: int, backend: str = "all"
    ) -> list[dict[str, Any]]:
        """Cost by trace name (stage/agent), merged across selected projects.

        When ``backend`` is ``"all"`` (default), uses trace-level cost
        (``aggregate_by_name``) — unchanged from the original behavior.

        When a specific backend is selected, uses per-(stage, backend)
        observation-metrics so that each stage's cost is attributed to the
        backend(s) it actually used.
        """
        if backend == "all":
            gathered = await self._gather(slug, hours)
            all_traces = [t for _, traces in gathered for t in traces]
            return aggregate_by_name(all_traces)

        all_rows = await self._gather_list_results(slug, hours, self._agent_usage)
        return aggregate_by_name_backend(all_rows, backend)

    async def by_agent_segmented(self, slug: str | None, hours: int) -> dict[str, Any]:
        """Return cost by stage, split into OpenRouter vs subscription pools.

        Returns::

            {"window_hours": int,
             "rows": list[dict],
             "openrouter_marginal_total": float,
             "subscription_estimate_total": float,
             "subscription_count_total": int,
             "subscription_cap": int,
             "subscription_cap_pct": float | None}

        Each row in ``rows`` carries the stage name, per-pool cost + count,
        total cost, and a ``marginal_reducible`` flag.  ``subscription_cap_pct``
        is ``subscription_count_total / subscription_cap`` when the cap > 0,
        otherwise ``None``.
        """
        all_rows = await self._gather_list_results(slug, hours, self._agent_usage)
        rows = aggregate_by_name_split(all_rows)
        openrouter_marginal_total = sum(r["openrouter_cost"] for r in rows)
        subscription_estimate_total = sum(r["subscription_cost"] for r in rows)
        subscription_count_total = sum(r["subscription_count"] for r in rows)
        cap = self.config.settings.subscription_call_cap
        return {
            "window_hours": hours,
            "rows": rows,
            "openrouter_marginal_total": round(openrouter_marginal_total, 6),
            "subscription_estimate_total": round(subscription_estimate_total, 6),
            "subscription_count_total": subscription_count_total,
            "subscription_cap": cap,
            "subscription_cap_pct": (
                round(subscription_count_total / cap, 6) if cap > 0 else None
            ),
        }

    async def _model_usage(
        self, project: RegistryProject, hours: int
    ) -> list[dict[str, Any]]:
        return await self._cached_fetch(
            project,
            hours,
            self._model_cache,
            lambda h: self._clients[project.slug].fetch_model_usage_window(h),
        )

    async def by_model(self, slug: str | None, hours: int) -> list[dict[str, Any]]:
        """Cost + token usage by model, merged across selected projects.

        Window-accurate (see :meth:`LangfuseClient.fetch_model_usage_window`).
        """
        all_rows = await self._gather_list_results(slug, hours, self._model_usage)
        return merge_model_costs([all_rows])

    async def _backend_cost(
        self, project: RegistryProject, hours: int
    ) -> dict[str, dict[str, float]]:
        return await self._cached_fetch(
            project,
            hours,
            self._backend_cache,
            lambda h: self._clients[project.slug].fetch_backend_cost_window(h),
        )

    async def _agent_usage(
        self, project: RegistryProject, hours: int
    ) -> list[dict[str, Any]]:
        return await self._cached_fetch(
            project,
            hours,
            self._agent_usage_cache,
            lambda h: self._clients[project.slug].fetch_agent_usage_window(h),
        )

    async def backend_trend(
        self, slug: str | None, hours: int, backend: BackendKind
    ) -> list[dict[str, Any]]:
        """Return the cost trend for a backend, merged across selected projects.

        Window-accurate; time-bucket granularity scales with the window.
        """
        parts: list[dict[str, dict[str, float]]] = []
        for p in self._projects(slug):
            cost: dict[str, dict[str, float]] = await self._safe_project_fetch(
                p,
                lambda: self._backend_cost(p, hours),  # noqa: B023
                "backend-cost",
                {},
            )
            parts.append(cost)
        return backend_cost_series(parts, backend)

    async def trend(
        self, slug: str | None, hours: int, buckets: int = 48
    ) -> list[dict[str, Any]]:
        """Return a cost trend series across the window."""
        gathered = await self._gather(slug, hours)
        all_traces = [t for _, traces in gathered for t in traces]
        return cost_trend(all_traces, hours, buckets)

    async def highlights(
        self, slug: str | None, hours: int, backend: str = "all"
    ) -> dict[str, Any]:
        """Return dashboard highlights: top trace, session, and summary stats.

        When *backend* is not ``"all"``, traces are filtered to only those
        whose name appears in the agent-usage rows for that backend, keeping
        the highlights consistent with the backend selector.
        """
        gathered = await self._gather(slug, hours)
        all_traces = [t for _, traces in gathered for t in traces]
        if backend != "all":
            agent_rows = await self._gather_list_results(slug, hours, self._agent_usage)
            backend_names: set[str] = {
                r["name"] for r in agent_rows if r.get("backend") == backend
            }
            all_traces = [t for t in all_traces if t.name in backend_names]
        return {
            "most_expensive_trace": most_expensive_trace(all_traces),
            "most_expensive_session": most_expensive_session(all_traces),
        }
