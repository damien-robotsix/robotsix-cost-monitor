"""Service layer: cross-project cost aggregation with a small TTL cache.

Wraps the per-project :class:`LangfuseClient`s, caches each ``(project, window)``
trace fetch for ``cache_ttl_seconds``, and exposes the aggregations the
dashboard needs — per-project and aggregated across all projects.
"""

from __future__ import annotations

import time
from typing import Any

from . import langfuse as lf
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

    async def summary(self, slug: str | None, hours: int) -> dict[str, Any]:
        """Per-project totals + the aggregate, for the window."""
        gathered = await self._gather(slug, hours)
        per_project: list[dict[str, Any]] = []
        total = 0.0
        for p, traces in gathered:
            cost = lf.total_cost(traces)
            total += cost
            per_project.append(
                {
                    "name": p.name,
                    "slug": p.slug,
                    "cost": cost,
                    "trace_count": len(traces),
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
        return lf.aggregate_by_name(all_traces)

    async def trend(
        self, slug: str | None, hours: int, buckets: int = 48
    ) -> list[dict[str, Any]]:
        gathered = await self._gather(slug, hours)
        all_traces = [t for _, traces in gathered for t in traces]
        return lf.cost_trend(all_traces, hours, buckets)

    async def highlights(self, slug: str | None, hours: int) -> dict[str, Any]:
        gathered = await self._gather(slug, hours)
        all_traces = [t for _, traces in gathered for t in traces]
        return {
            "most_expensive_trace": lf.most_expensive_trace(all_traces),
            "most_expensive_session": lf.most_expensive_session(all_traces),
        }
