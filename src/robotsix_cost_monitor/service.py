"""Service layer: cross-project cost aggregation with a small TTL cache.

Wraps the per-project :class:`LangfuseClient`s, caches each ``(project, window)``
trace fetch for ``cache_ttl_seconds``, and exposes the aggregations the
dashboard needs — per-project and aggregated across all projects.
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

import structlog

from .aggregations import (
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
    ExternalRateLimitError,
    ExternalServiceError,
    ProjectConfigError,
)

_T = TypeVar("_T")
logger = structlog.get_logger(__name__)


class CostService:
    """Cross-project cost aggregation service with per-window TTL cache."""

    def __init__(self, config: Config) -> None:
        """Initialise the service with a validated config and per-project clients."""
        self.config = config
        self._clients: dict[str, LangfuseClient] = {
            p.slug: LangfuseClient(
                public_key=p.public_key,
                secret_key=p.secret_key,
                base_url=p.base_url,
            )
            for p in config.projects
        }
        # cache: (slug, hours) -> (traces, monotonic_deadline)
        self._cache: dict[tuple[str, int], tuple[list[LangfuseTrace], float]] = {}
        # cache: (slug, hours) -> (per-model usage rows, monotonic_deadline)
        self._model_cache: dict[
            tuple[str, int], tuple[list[dict[str, Any]], float]
        ] = {}
        # cache: (slug, hours) -> ({time_bucket -> {backend -> cost}}, deadline)
        self._backend_cache: dict[
            tuple[str, int], tuple[dict[str, dict[str, float]], float]
        ] = {}
        # cache: (slug, hours) -> (per-(stage, backend) rows, monotonic_deadline)
        self._agent_usage_cache: dict[
            tuple[str, int], tuple[list[dict[str, Any]], float]
        ] = {}
        # cache: (slug, hours) -> (trace_count, monotonic_deadline)
        self._trace_count_cache: dict[tuple[str, int], tuple[int, float]] = {}

    def _projects(self, slug: str | None) -> list[ProjectConfig]:
        if slug and slug != "all":
            p = self.config.project(slug)
            return [p] if p else []
        return list(self.config.projects)

    async def _cached_fetch(
        self,
        project: ProjectConfig,
        hours: int,
        cache_dict: dict[tuple[str, int], tuple[_T, float]],
        fetch_fn: Callable[[int], Awaitable[_T]],
    ) -> _T:
        key = (project.slug, hours)
        hit = cache_dict.get(key)
        if hit and hit[1] > time.monotonic():
            return hit[0]
        result = await fetch_fn(hours)
        ttl = self.config.settings.cache_ttl_seconds
        cache_dict[key] = (result, time.monotonic() + ttl)
        return result

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
            try:
                out.append((p, await self._traces(p, hours)))
            except (ExternalServiceError, ExternalRateLimitError, CacheError):
                logger.warning(
                    "project %s failed transiently — returning empty data", p.slug
                )
                out.append((p, []))
            except ProjectConfigError:
                logger.warning("project %s misconfigured — skipping", p.slug)
                out.append((p, []))
            except Exception:
                logger.exception(
                    "project %s failed unexpectedly — returning empty data", p.slug
                )
                out.append((p, []))
        return out

    async def _gather_list_results(
        self,
        slug: str | None,
        hours: int,
        fetch: Callable[[ProjectConfig, int], Awaitable[list[dict[str, Any]]]],
    ) -> list[dict[str, Any]]:
        parts: list[list[dict[str, Any]]] = []
        for p in self._projects(slug):
            try:
                parts.append(await fetch(p, hours))
            except (ExternalServiceError, ExternalRateLimitError, CacheError):
                logger.warning(
                    "project %s failed transiently — returning empty data", p.slug
                )
                parts.append([])
            except ProjectConfigError:
                logger.warning("project %s misconfigured — skipping", p.slug)
                parts.append([])
            except Exception:
                logger.exception(
                    "project %s failed unexpectedly — returning empty data", p.slug
                )
                parts.append([])
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
            try:
                models = await self._model_usage(p, hours)
            except (ExternalServiceError, ExternalRateLimitError, CacheError):
                logger.warning(
                    "project %s model-usage fetch failed transiently", p.slug
                )
                models = []
            except ProjectConfigError:
                logger.warning("project %s misconfigured — skipping", p.slug)
                models = []
            except Exception:
                logger.exception(
                    "project %s model-usage fetch failed unexpectedly", p.slug
                )
                models = []
            try:
                trace_count = await self._trace_count(p, hours)
            except (ExternalServiceError, ExternalRateLimitError, CacheError):
                logger.warning(
                    "project %s trace-count fetch failed transiently", p.slug
                )
                trace_count = 0
            except ProjectConfigError:
                logger.warning("project %s misconfigured — skipping", p.slug)
                trace_count = 0
            except Exception:
                logger.exception(
                    "project %s trace-count fetch failed unexpectedly", p.slug
                )
                trace_count = 0
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
        self, slug: str | None, hours: int, backend: str
    ) -> list[dict[str, Any]]:
        """Return the cost trend for a backend, merged across selected projects.

        Window-accurate; time-bucket granularity scales with the window.
        """
        parts: list[dict[str, dict[str, float]]] = []
        for p in self._projects(slug):
            try:
                parts.append(await self._backend_cost(p, hours))
            except (ExternalServiceError, ExternalRateLimitError, CacheError):
                logger.warning(
                    "project %s backend-cost fetch failed transiently", p.slug
                )
                parts.append({})
            except ProjectConfigError:
                logger.warning("project %s misconfigured — skipping", p.slug)
                parts.append({})
            except Exception:
                logger.exception(
                    "project %s backend-cost fetch failed unexpectedly", p.slug
                )
                parts.append({})
        return backend_cost_series(parts, backend)

    async def trend(
        self, slug: str | None, hours: int, buckets: int = 48
    ) -> list[dict[str, Any]]:
        """Return a cost trend series across the window."""
        gathered = await self._gather(slug, hours)
        all_traces = [t for _, traces in gathered for t in traces]
        return cost_trend(all_traces, hours, buckets)

    async def highlights(self, slug: str | None, hours: int) -> dict[str, Any]:
        """Return dashboard highlights: top trace, session, and summary stats."""
        gathered = await self._gather(slug, hours)
        all_traces = [t for _, traces in gathered for t in traces]
        return {
            "most_expensive_trace": most_expensive_trace(all_traces),
            "most_expensive_session": most_expensive_session(all_traces),
        }
