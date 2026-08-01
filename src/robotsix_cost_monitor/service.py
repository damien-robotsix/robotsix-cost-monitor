"""Service layer: cross-project cost aggregation with a small TTL cache.

Projects are discovered at runtime from the central-deploy registry (not from
hardcoded config).  The :class:`TTLCache` supports stale-while-revalidate (SWR):

- Entries are *fresh* for ``ttl`` seconds and served immediately.
- After ``ttl`` seconds the entry is *stale* — still served, but a background
  refresh is triggered so the next request gets fresh data.
- On cold cache (no entry at all) the fetch blocks the caller.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

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
            "refresh_projects: discovered %d project(s)", len(self._project_map)
        )

    def _projects(self, slug: str | None) -> list[RegistryProject]:
        if slug and slug != "all":
            p = self._project_map.get(slug)
            return [p] if p else []
        return list(self._project_map.values())

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
                    "cost": cost,
                    "trace_count": trace_count,
                }
            )
        total = round(total, 6)
        return {
            "window_hours": hours,
            "total_cost": total,
            "projects": per_project,
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

    async def candidate_traces(
        self, slug: str | None, hours: int, *, limit: int = 10, per_agent: int = 0
    ) -> list[dict[str, Any]]:
        """Return the top-*limit* most expensive traces across projects.

        When *per_agent* > 0, at most *per_agent* traces are selected from each
        agent (trace name), ensuring coverage of cheaper agents that would
        otherwise be crowded out by a single expensive agent.
        """
        gathered = await self._gather(slug, hours)
        all_traces: list[tuple[str, LangfuseTrace]] = []
        for p, traces in gathered:
            for t in traces:
                all_traces.append((p.slug, t))

        if not all_traces:
            return []

        total_cost = sum((t.total_cost or 0.0) for _, t in all_traces) or 1.0

        # Sort by cost descending
        all_traces.sort(key=lambda x: x[1].total_cost or 0.0, reverse=True)

        if per_agent > 0:
            seen: dict[str, int] = {}
            selected: list[tuple[str, LangfuseTrace]] = []
            for slug, t in all_traces:
                agent = t.name or "unknown"
                if seen.get(agent, 0) >= per_agent:
                    continue
                seen[agent] = seen.get(agent, 0) + 1
                selected.append((slug, t))
            # Re-sort by cost after per-agent capping
            selected.sort(key=lambda x: x[1].total_cost or 0.0, reverse=True)
            selected = selected[:limit]
        else:
            selected = all_traces[:limit]

        result: list[dict[str, Any]] = []
        for i, (slug, t) in enumerate(selected, 1):
            cost = round(t.total_cost or 0.0, 6)
            result.append({
                "trace_id": t.id,
                "cost": cost,
                "name": t.name,
                "project": slug,
                "rank": i,
                "pct_of_traced": round(cost / total_cost * 100, 1),
                "selection_reason": f"agent '{t.name}'",
            })
        return result

    async def trace_detail(self, slug: str, trace_id: str) -> dict[str, Any]:
        """Return full detail for a single trace, or {} for unknown projects."""
        client = self._clients.get(slug)
        if client is None:
            return {}
        try:
            detail = await client.fetch_trace_detail(trace_id)
            return detail.model_dump(by_alias=True)
        except Exception:
            logger.exception("trace_detail failed for %s/%s", slug, trace_id)
            return {}

    async def top_ticket(
        self, slug: str | None, hours: int
    ) -> dict[str, Any] | None:
        """Return the priciest session (ticket) in the window, or None."""
        gathered = await self._gather(slug, hours)
        all_traces = [t for _, traces in gathered for t in traces]

        sessions: dict[str, dict[str, Any]] = {}
        for t in all_traces:
            sid = t.session_id
            if not sid:
                continue
            if sid not in sessions:
                sessions[sid] = {"session_id": sid, "cost": 0.0, "count": 0, "by_stage": {}}  # type: ignore[assignment]
            cost = t.total_cost or 0.0
            sessions[sid]["cost"] += cost
            sessions[sid]["count"] += 1
            stage = t.name or "unknown"
            sessions[sid]["by_stage"][stage] = sessions[sid]["by_stage"].get(stage, 0.0) + cost  # type: ignore[index]

        if not sessions:
            return None

        top_sid = max(sessions, key=lambda s: sessions[s]["cost"])
        top = sessions[top_sid]
        top["cost"] = round(top["cost"], 6)
        top["by_stage"] = sorted(
            (
                {"name": k, "cost": round(v, 6)}
                for k, v in top["by_stage"].items()
            ),
            key=lambda x: x["cost"],
            reverse=True,
        )
        return top

    async def top_stage(
        self, slug: str | None, hours: int, *, sample: int = 5
    ) -> dict[str, Any] | None:
        """Return the priciest stage (trace name) in the window, or None."""
        gathered = await self._gather(slug, hours)
        all_traces = [t for _, traces in gathered for t in traces]

        if not all_traces:
            return None

        total_cost = sum((t.total_cost or 0.0) for t in all_traces) or 1.0

        stages: dict[str, dict[str, Any]] = {}
        for t in all_traces:
            name = t.name or "unknown"
            if name not in stages:
                stages[name] = {"stage": name, "cost": 0.0, "count": 0, "traces": []}
            cost = t.total_cost or 0.0
            stages[name]["cost"] += cost
            stages[name]["count"] += 1
            stages[name]["traces"].append(t)

        top_name = max(stages, key=lambda s: stages[s]["cost"])
        top = stages[top_name]
        top["cost"] = round(top["cost"], 6)
        top["pct_of_traced"] = round(top["cost"] / total_cost * 100, 1)
        top["traces"].sort(key=lambda t: t.total_cost or 0.0, reverse=True)
        top["traces"] = [{"trace_id": t.id} for t in top["traces"][:sample]]
        return top
