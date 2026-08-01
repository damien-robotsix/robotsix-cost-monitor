"""Service layer: cross-project cost aggregation with a small TTL cache.

Wraps the per-project :class:`LangfuseClient`s, caches each ``(project, window)``
trace fetch for ``cache_ttl_seconds``, and exposes the aggregations the
dashboard needs — per-project and aggregated across all projects.

The :class:`TTLCache` supports stale-while-revalidate (SWR) semantics:
- Entries are *fresh* for ``ttl`` seconds and served immediately.
- After ``ttl`` seconds the entry is *stale* — still served, but a background
  refresh is triggered so the next request gets fresh data.
- On cold cache (no entry at all) the fetch blocks the caller.
"""

from __future__ import annotations

import asyncio
import time
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
    _trace_cost,
    aggregate_by_name,
    aggregate_by_name_backend,
    aggregate_by_name_split,
    backend_cost_series,
    cost_trend,
    merge_model_costs,
    most_expensive_session,
    most_expensive_trace,
)
from .clients.langfuse import LangfuseClient
from .clients.models import LangfuseTrace
from .config import Config, ProjectConfig
from .exceptions import (
    CacheError,
    ProjectConfigError,
)

_T = TypeVar("_T")
logger = structlog.get_logger(__name__)
K = TypeVar("K")
V = TypeVar("V")


class TTLCache[K, V]:
    """Generic TTL cache with stale-while-revalidate (SWR) semantics.

    Each value is paired with a freshness deadline and a last-updated
    monotonic timestamp.  ``get_or_fetch`` returns the cached value while
    fresh; when stale it still returns the cached value but triggers a
    background refresh (non-blocking).  On a cold miss it blocks on the
    fetch.

    The ``on_refresh`` callback (if set) is called after each successful
    background refresh so the owning service can update its global
    ``last_updated`` timestamp.
    """

    def __init__(
        self,
        ttl: float,
        *,
        on_refresh: Callable[[], None] | None = None,
    ) -> None:
        """Create a cache where every entry is fresh for *ttl* seconds.

        After *ttl* seconds the entry becomes stale but is still served;
        a background refresh is scheduled when the first caller hits the
        stale entry.
        """
        self._ttl = ttl
        self._on_refresh = on_refresh
        # (value, freshness_deadline, last_updated_monotonic)
        self._store: dict[K, tuple[V, float, float]] = {}
        self._pending: set[K] = set()

    @property
    def last_updated(self) -> float | None:
        """Most recent ``time.monotonic()`` when any entry was refreshed.

        ``None`` when the cache has never been populated.
        """
        if not self._store:
            return None
        return max(entry[2] for entry in self._store.values())

    async def get_or_fetch(self, key: K, fetch_fn: Callable[[], Awaitable[V]]) -> V:
        """Fresh → serve, stale → serve + bg refresh, cold → block."""
        now = time.monotonic()
        hit = self._store.get(key)
        if hit is not None:
            _value, deadline, _updated = hit
            if deadline > now:
                return _value  # fresh — serve immediately
            # Stale — serve immediately, refresh in background
            if key not in self._pending:
                self._pending.add(key)
                asyncio.create_task(self._background_refresh(key, fetch_fn))
            return _value
        # Cold miss — block on fetch
        result = await fetch_fn()
        now = time.monotonic()
        self._store[key] = (result, now + self._ttl, now)
        if self._on_refresh is not None:
            self._on_refresh()
        return result

    async def _background_refresh(
        self, key: K, fetch_fn: Callable[[], Awaitable[V]]
    ) -> None:
        """Fetch a fresh value for *key* in the background, updating the store."""
        try:
            result = await fetch_fn()
            now = time.monotonic()
            self._store[key] = (result, now + self._ttl, now)
            if self._on_refresh is not None:
                self._on_refresh()
        except Exception:
            logger.debug("background refresh failed for key %s", key, exc_info=True)
        finally:
            self._pending.discard(key)

    def invalidate(self, key: K | None = None) -> None:
        """Remove *key* from the cache; when *key* is ``None`` clear all entries."""
        if key is None:
            self._store.clear()
            self._pending.clear()
        else:
            self._store.pop(key, None)
            self._pending.discard(key)


class CostService:
    """Cross-project cost aggregation service with per-window TTL cache.

    All five internal caches share a single :attr:`last_updated` timestamp
    (the youngest refresh across *all* caches) so the dashboard can display
    data freshness.
    """

    def __init__(self, config: Config) -> None:
        """Initialise the service with a validated config and per-project clients."""
        self.config = config
        self._clients: dict[str, LangfuseClient] = {
            p.slug: LangfuseClient(
                public_key=p.public_key.get_secret_value(),
                secret_key=p.secret_key.get_secret_value(),
                base_url=p.base_url,
            )
            for p in config.projects
        }
        ttl = self.config.settings.cache_ttl_seconds
        self._last_updated: datetime | None = None
        self._caches: list[TTLCache[Any, Any]] = []
        on_refresh = self._touch_last_updated

        def _mk[T](
            cache_type: type[TTLCache[Any, Any]], t: type[T]
        ) -> TTLCache[Any, T]:
            c = TTLCache[Any, T](ttl, on_refresh=on_refresh)
            self._caches.append(c)
            return c

        # cache: (slug, hours) -> (traces, monotonic_deadline)
        self._cache = _mk(TTLCache, list[LangfuseTrace])
        # cache: (slug, hours) -> (per-model usage rows, monotonic_deadline)
        self._model_cache = _mk(TTLCache, list[dict[str, Any]])
        # cache: (slug, hours) -> ({time_bucket -> {backend -> cost}}, deadline)
        self._backend_cache = _mk(TTLCache, dict[str, dict[str, float]])
        # cache: (slug, hours) -> (per-(stage, backend) rows, monotonic_deadline)
        self._agent_usage_cache = _mk(TTLCache, list[dict[str, Any]])
        # cache: (slug, hours) -> (trace_count, monotonic_deadline)
        self._trace_count_cache = _mk(TTLCache, int)

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

    def _projects(self, slug: str | None) -> list[ProjectConfig]:
        if slug and slug != "all":
            p = self.config.project(slug)
            return [p] if p else []
        return list(self.config.projects)

    async def _safe_project_fetch[T](
        self,
        project: ProjectConfig,
        fetch_fn: Callable[[], Awaitable[T]],
        label: str,
        default: T,
    ) -> T:
        try:
            return await fetch_fn()
        except ExternalServiceError, ExternalRateLimitError, CacheError:
            logger.warning("project %s %s failed transiently", project.slug, label)
            return default
        except ProjectConfigError:
            logger.warning("project %s misconfigured — skipping", project.slug)
            return default
        except Exception:
            logger.exception("project %s %s failed unexpectedly", project.slug, label)
            return default

    async def _cached_fetch(
        self,
        project: ProjectConfig,
        hours: int,
        cache: TTLCache[tuple[str, int], _T],
        fetch_fn: Callable[[int], Awaitable[_T]],
    ) -> _T:
        key = (project.slug, hours)
        return await cache.get_or_fetch(key, lambda: fetch_fn(hours))

    async def _traces(self, project: ProjectConfig, hours: int) -> list[LangfuseTrace]:
        return await self._cached_fetch(
            project,
            hours,
            self._cache,
            lambda h: self._clients[project.slug].fetch_traces_window(h),
        )

    async def _trace_count(self, project: ProjectConfig, hours: int) -> int:
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
    ) -> list[tuple[ProjectConfig, list[LangfuseTrace]]]:
        out: list[tuple[ProjectConfig, list[LangfuseTrace]]] = []
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
        fetch: Callable[[ProjectConfig, int], Awaitable[list[dict[str, Any]]]],
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

    async def _build_trace_rows(
        self, slug: str | None, hours: int
    ) -> list[dict[str, Any]]:
        gathered = await self._gather(slug, hours)
        rows: list[dict[str, Any]] = []
        for p, traces in gathered:
            for t in traces:
                tid = t.id
                if not tid:
                    continue
                rows.append(
                    {
                        "trace_id": tid,
                        "project": p.slug,
                        "name": t.name or "(unnamed)",
                        "cost": round(_trace_cost(t), 6),
                    }
                )
        return rows

    async def candidate_traces(
        self, slug: str | None, hours: int, limit: int, *, per_agent: int = 1
    ) -> list[dict[str, Any]]:
        """Return the cost-analyst's drill-in candidate traces.

        Selection is deterministic and **per agent** (trace name): take the top
        ``per_agent`` most expensive traces of EACH agent — so a cheaper agent
        is still inspected instead of being crowded out by the priciest one —
        then cap the total at ``limit`` (priciest agents win if it overflows).
        Each candidate carries why it was picked (``rank``, ``pct_of_traced``,
        ``agent_pct_of_traced``, ``selection_reason``).
        """
        rows = await self._build_trace_rows(slug, hours)
        total = sum(r["cost"] for r in rows) or 1e-9

        # Group by agent (trace name) across all projects; take each agent's
        # top `per_agent` traces so every agent gets coverage.
        by_agent: dict[str, list[dict[str, Any]]] = {}
        for r in rows:
            by_agent.setdefault(r["name"], []).append(r)
        selected: list[dict[str, Any]] = []
        for traces_for_agent in by_agent.values():
            traces_for_agent.sort(key=lambda r: r["cost"], reverse=True)
            agent_pct = round(100 * sum(t["cost"] for t in traces_for_agent) / total, 1)
            for j, t in enumerate(traces_for_agent[:per_agent], 1):
                t["agent_rank"] = j
                t["agent_pct_of_traced"] = agent_pct
                selected.append(t)

        selected.sort(key=lambda r: r["cost"], reverse=True)
        selected = selected[:limit]
        for i, r in enumerate(selected, 1):
            r["rank"] = i
            r["pct_of_traced"] = round(100 * r["cost"] / total, 1)
            r["selection_reason"] = (
                f"top trace for agent '{r['name']}' (#{r['agent_rank']} of its "
                f"traces) — ${r['cost']:.2f}; agent '{r['name']}' is "
                f"{r['agent_pct_of_traced']}% of traced spend over the last "
                f"{hours}h"
            )
        return selected

    async def top_ticket(self, slug: str | None, hours: int) -> dict[str, Any] | None:
        """Return the most expensive session (= board ticket) in the window.

        Returns the session id, total cost, trace count, the per-stage cost
        breakdown (where the ticket's spend went), and its traces — the basis
        for the ticket-level (global) cost analysis. ``None`` if no sessions.
        """
        gathered = await self._gather(slug, hours)
        all_traces = [t for _, traces in gathered for t in traces]
        top = most_expensive_session(all_traces)
        if not top:
            return None
        sid = top["session_id"]
        session_traces = [t for t in all_traces if t.session_id == sid]
        traces = sorted(
            (
                {
                    "trace_id": t.id,
                    "name": t.name or "(unnamed)",
                    "cost": round(_trace_cost(t), 6),
                }
                for t in session_traces
                if t.id
            ),
            key=lambda r: float(r["cost"]),  # type: ignore[arg-type]
            reverse=True,
        )
        return {
            "session_id": sid,
            "cost": top["cost"],
            "count": top["count"],
            "by_stage": aggregate_by_name(session_traces),
            "traces": traces,
        }

    async def top_stage(
        self, slug: str | None, hours: int, sample: int = 8
    ) -> dict[str, Any] | None:
        """Return the most expensive stage (agent / trace name) in the window.

        Returns the stage, its total cost + share of traced spend, and a sample
        of its priciest traces (with project) — the basis for the stage-level
        (global) cost analysis. ``None`` if there are no traces.
        """
        rows = await self._build_trace_rows(slug, hours)
        if not rows:
            return None
        by_name: dict[str, dict[str, float]] = {}
        for r in rows:
            agg = by_name.setdefault(r["name"], {"cost": 0.0, "count": 0})
            agg["cost"] += r["cost"]
            agg["count"] += 1
        total = sum(v["cost"] for v in by_name.values()) or 1e-9
        name, agg = max(by_name.items(), key=lambda kv: kv[1]["cost"])
        stage_traces = sorted(
            (r for r in rows if r["name"] == name),
            key=lambda r: r["cost"],
            reverse=True,
        )[:sample]
        return {
            "stage": name,
            "cost": round(agg["cost"], 6),
            "count": int(agg["count"]),
            "pct_of_traced": round(100 * agg["cost"] / total, 1),
            "traces": stage_traces,
        }

    async def trace_detail(self, project_slug: str, trace_id: str) -> dict[str, Any]:
        """Fetch a single trace's full detail (observations) from its project."""
        client = self._clients.get(project_slug)
        if client is None:
            return {}
        trace = await client.fetch_trace_detail(trace_id)
        return trace.model_dump(by_alias=True)

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
        self, project: ProjectConfig, hours: int
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
        self, project: ProjectConfig, hours: int
    ) -> dict[str, dict[str, float]]:
        return await self._cached_fetch(
            project,
            hours,
            self._backend_cache,
            lambda h: self._clients[project.slug].fetch_backend_cost_window(h),
        )

    async def _agent_usage(
        self, project: ProjectConfig, hours: int
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
