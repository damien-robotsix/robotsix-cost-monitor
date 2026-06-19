"""Service layer: cross-project cost aggregation with a small TTL cache.

Wraps the per-project :class:`LangfuseClient`s, caches each ``(project, window)``
trace fetch for ``cache_ttl_seconds``, and exposes the aggregations the
dashboard needs — per-project and aggregated across all projects.
"""

from __future__ import annotations

import time
from typing import Any

from .aggregations import (
    _trace_cost,
    aggregate_by_name,
    backend_cost_series,
    cost_trend,
    merge_model_costs,
    most_expensive_session,
    most_expensive_trace,
)
from .config import Config, ProjectConfig
from .langfuse import LangfuseClient


class CostService:
    def __init__(self, config: Config) -> None:
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
        self._cache: dict[tuple[str, int], tuple[list[dict[str, Any]], float]] = {}
        # cache: (slug, hours) -> (per-model usage rows, monotonic_deadline)
        self._model_cache: dict[
            tuple[str, int], tuple[list[dict[str, Any]], float]
        ] = {}
        # cache: (slug, hours) -> ({time_bucket -> {backend -> cost}}, deadline)
        self._backend_cache: dict[
            tuple[str, int], tuple[dict[str, dict[str, float]], float]
        ] = {}

    def _projects(self, slug: str | None) -> list[ProjectConfig]:
        if slug and slug != "all":
            p = self.config.project(slug)
            return [p] if p else []
        return list(self.config.projects)

    async def _traces(self, project: ProjectConfig, hours: int) -> list[dict[str, Any]]:
        key = (project.slug, hours)
        hit = self._cache.get(key)
        if hit and hit[1] > time.monotonic():
            return hit[0]
        traces = await self._clients[project.slug].fetch_traces_window(hours)
        ttl = self.config.settings.cache_ttl_seconds
        self._cache[key] = (traces, time.monotonic() + ttl)
        return traces

    async def _gather(
        self, slug: str | None, hours: int
    ) -> list[tuple[ProjectConfig, list[dict[str, Any]]]]:
        out: list[tuple[ProjectConfig, list[dict[str, Any]]]] = []
        for p in self._projects(slug):
            try:
                out.append((p, await self._traces(p, hours)))
            except Exception:  # noqa: BLE001 — a dead project must not 500 the page
                out.append((p, []))
        return out

    async def candidate_traces(
        self, slug: str | None, hours: int, limit: int
    ) -> list[dict[str, Any]]:
        """Return the *limit* most expensive traces in the window, each tagged
        with its project slug — the cost-analyst's drill-in candidates."""
        gathered = await self._gather(slug, hours)
        rows: list[dict[str, Any]] = []
        for p, traces in gathered:
            for t in traces:
                tid = t.get("id")
                if not tid:
                    continue
                rows.append(
                    {
                        "trace_id": tid,
                        "project": p.slug,
                        "name": t.get("name") or "(unnamed)",
                        "cost": round(_trace_cost(t), 6),
                    }
                )
        rows.sort(key=lambda r: r["cost"], reverse=True)
        return rows[:limit]

    async def trace_detail(self, project_slug: str, trace_id: str) -> dict[str, Any]:
        """Fetch a single trace's full detail (observations) from its project."""
        client = self._clients.get(project_slug)
        if client is None:
            return {}
        return await client.fetch_trace_detail(trace_id)

    async def summary(self, slug: str | None, hours: int) -> dict[str, Any]:
        """Per-project totals + the aggregate, for the window.

        Cost is observation-based (the same window-accurate metrics source as the
        by-model / by-backend breakdowns), so the headline total, the per-model
        rows, and the per-backend totals all reconcile — a backend can never
        exceed the total. ``trace_count`` still comes from the trace list.
        """
        per_project: list[dict[str, Any]] = []
        total = 0.0
        for p in self._projects(slug):
            try:
                models = await self._model_usage(p, hours)
            except Exception:  # noqa: BLE001 — a dead project must not 500 the page
                models = []
            try:
                trace_count = len(await self._traces(p, hours))
            except Exception:  # noqa: BLE001
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

    async def by_agent(self, slug: str | None, hours: int) -> list[dict[str, Any]]:
        """Cost by trace name (stage/agent), merged across selected projects."""
        gathered = await self._gather(slug, hours)
        all_traces = [t for _, traces in gathered for t in traces]
        return aggregate_by_name(all_traces)

    async def _model_usage(
        self, project: ProjectConfig, hours: int
    ) -> list[dict[str, Any]]:
        key = (project.slug, hours)
        hit = self._model_cache.get(key)
        if hit and hit[1] > time.monotonic():
            return hit[0]
        rows = await self._clients[project.slug].fetch_model_usage_window(hours)
        ttl = self.config.settings.cache_ttl_seconds
        self._model_cache[key] = (rows, time.monotonic() + ttl)
        return rows

    async def by_model(self, slug: str | None, hours: int) -> list[dict[str, Any]]:
        """Cost + token usage by model, merged across selected projects.

        Window-accurate (see :meth:`LangfuseClient.fetch_model_usage_window`)."""
        parts: list[list[dict[str, Any]]] = []
        for p in self._projects(slug):
            try:
                parts.append(await self._model_usage(p, hours))
            except Exception:  # noqa: BLE001 — a dead project must not 500 the page
                parts.append([])
        return merge_model_costs(parts)

    async def _backend_cost(
        self, project: ProjectConfig, hours: int
    ) -> dict[str, dict[str, float]]:
        key = (project.slug, hours)
        hit = self._backend_cache.get(key)
        if hit and hit[1] > time.monotonic():
            return hit[0]
        data = await self._clients[project.slug].fetch_backend_cost_window(hours)
        ttl = self.config.settings.cache_ttl_seconds
        self._backend_cache[key] = (data, time.monotonic() + ttl)
        return data

    async def backend_trend(
        self, slug: str | None, hours: int, backend: str
    ) -> list[dict[str, Any]]:
        """Cost trend for *backend* (or all-backends total when ``all``),
        merged across selected projects. Window-accurate; time-bucket
        granularity scales with the window."""
        parts: list[dict[str, dict[str, float]]] = []
        for p in self._projects(slug):
            try:
                parts.append(await self._backend_cost(p, hours))
            except Exception:  # noqa: BLE001 — a dead project must not 500 the page
                parts.append({})
        return backend_cost_series(parts, backend)

    async def trend(
        self, slug: str | None, hours: int, buckets: int = 48
    ) -> list[dict[str, Any]]:
        gathered = await self._gather(slug, hours)
        all_traces = [t for _, traces in gathered for t in traces]
        return cost_trend(all_traces, hours, buckets)

    async def highlights(self, slug: str | None, hours: int) -> dict[str, Any]:
        gathered = await self._gather(slug, hours)
        all_traces = [t for _, traces in gathered for t in traces]
        return {
            "most_expensive_trace": most_expensive_trace(all_traces),
            "most_expensive_session": most_expensive_session(all_traces),
        }
