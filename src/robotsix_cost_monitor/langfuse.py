"""Langfuse read client for cost-monitor.

One :class:`LangfuseClient` per project. Composes the shared
:class:`robotsix_llmio.core.LangfuseReadClient` for auth/URL construction
and adds async HTTP calls plus cost-monitor's domain-specific aggregation
methods (``/api/public/metrics`` queries, per-model / per-backend / per-agent
aggregation). Talks to the Langfuse public REST API (``/api/public/*``).

Pure aggregation / transformation functions live in
:mod:`robotsix_cost_monitor.aggregations`.
"""

from __future__ import annotations

import json
from datetime import timedelta
from typing import Any

import httpx
from robotsix_llmio.core import LangfuseReadClient

from .aggregations import (
    _empty_model_slot,
    _model_rows,
    _utc_now,
    backend_for_model,
)

__all__ = [
    "LangfuseClient",
]

_PAGE_LIMIT = 100
_MAX_PAGES = 100  # safety cap (≤ 10k traces per query)


class LangfuseClient:
    """Read-only cost/trace client for a single Langfuse project.

    Composes :class:`LangfuseReadClient` for auth/URL helpers;
    owns its own async HTTP and domain aggregation.
    """

    def __init__(
        self,
        *,
        public_key: str,
        secret_key: str,
        base_url: str,
        timeout: float = 30.0,
    ) -> None:
        self._lf = LangfuseReadClient(
            public_key=public_key,
            secret_key=secret_key,
            base_url=base_url,
        )
        self._timeout = timeout

    async def _get(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.get(
                self._lf.url(path),
                params=params,
                headers={"Authorization": self._lf.auth_header()},
            )
            resp.raise_for_status()
            data: dict[str, Any] = resp.json()
            return data

    async def fetch_traces_window(self, hours: float) -> list[dict[str, Any]]:
        """Return all traces with ``timestamp`` within the last *hours*.

        *hours* may be fractional (reconciliation passes the exact snapshot
        interval).

        Paginates ``/api/public/traces`` newest-first using ``fromTimestamp``;
        stops at the window edge or the page cap.
        """
        since = _utc_now() - timedelta(hours=hours)
        from_ts = since.isoformat().replace("+00:00", "Z")
        out: list[dict[str, Any]] = []
        for page in range(1, _MAX_PAGES + 1):
            data = await self._get(
                "/api/public/traces",
                {
                    "fromTimestamp": from_ts,
                    "limit": _PAGE_LIMIT,
                    "page": page,
                    "orderBy": "timestamp.desc",
                },
            )
            batch = data.get("data") or []
            if not batch:
                break
            out.extend(batch)
            meta = data.get("meta") or {}
            total_pages = meta.get("totalPages")
            if total_pages is not None and page >= total_pages:
                break
            if len(batch) < _PAGE_LIMIT:
                break
        return out

    async def fetch_trace_detail(self, trace_id: str) -> dict[str, Any]:
        """Return a single trace's full detail (including its observations)."""
        return await self._get(f"/api/public/traces/{trace_id}", {})

    async def _metrics(
        self,
        hours: float,
        *,
        metrics: list[dict[str, str]],
        dimensions: list[dict[str, str]] | None = None,
        time_dimension: dict[str, str] | None = None,
    ) -> list[dict[str, Any]]:
        """Run a Langfuse metrics query over the *observations* view for the
        exact last *hours*, grouped by *dimensions* (defaults to model). Returns
        the raw ``data`` rows.

        ``/api/public/metrics`` aggregates server-side and, unlike the
        daily-metrics endpoint, honors the exact ``from``/``to`` window (the
        daily endpoint returns whole calendar days and badly over-counts sub-day
        windows). One request per query — no pagination needed.
        """
        now = _utc_now()
        query: dict[str, Any] = {
            "view": "observations",
            "metrics": metrics,
            "dimensions": dimensions or [{"field": "providedModelName"}],
            "fromTimestamp": (now - timedelta(hours=hours))
            .isoformat()
            .replace("+00:00", "Z"),
            "toTimestamp": now.isoformat().replace("+00:00", "Z"),
        }
        if time_dimension is not None:
            query["timeDimension"] = time_dimension
        data = await self._get("/api/public/metrics", {"query": json.dumps(query)})
        return list(data.get("data") or [])

    async def fetch_agent_usage_window(self, hours: int) -> list[dict[str, Any]]:
        """Per-(stage, backend) cost over the exact last *hours*.

        Groups observations by trace name AND model, then maps each model to its
        serving backend via :func:`backend_for_model`. Returns rows shaped
        ``{"name": <stage>, "backend": <backend>, "cost": <float>,
        "count": <int>}`` sorted by cost descending.

        Observations with no model name carry no cost and are skipped. Uses the
        same window-accurate metrics source as :meth:`fetch_model_usage_window`.
        """
        rows = await self._metrics(
            hours,
            metrics=[
                {"measure": "totalCost", "aggregation": "sum"},
                {"measure": "count", "aggregation": "count"},
            ],
            dimensions=[
                {"field": "traceName"},
                {"field": "providedModelName"},
            ],
        )
        acc: dict[tuple[str, str], dict[str, float]] = {}
        for row in rows:
            model = row.get("providedModelName")
            stage = row.get("traceName")
            if not model or not stage:
                continue
            backend = backend_for_model(model)
            key = (stage, backend)
            slot = acc.setdefault(key, {"cost": 0.0, "count": 0.0})
            slot["cost"] += float(row.get("sum_totalCost") or 0.0)
            slot["count"] += float(row.get("count_count") or 0.0)
        ordered = sorted(acc.items(), key=lambda kv: kv[1]["cost"], reverse=True)
        return [
            {
                "name": stage,
                "backend": backend,
                "cost": round(v["cost"], 6),
                "count": int(v["count"]),
            }
            for (stage, backend), v in ordered
        ]

    async def fetch_model_usage_window(self, hours: int) -> list[dict[str, Any]]:
        """Per-model cost + token usage over the exact last *hours*.

        Window-accurate (see :meth:`_metrics`). Observations with no model
        (non-generation spans) are skipped; they carry no cost.
        """
        rows = await self._metrics(
            hours,
            metrics=[
                {"measure": "totalCost", "aggregation": "sum"},
                {"measure": "inputTokens", "aggregation": "sum"},
                {"measure": "outputTokens", "aggregation": "sum"},
                {"measure": "totalTokens", "aggregation": "sum"},
                {"measure": "count", "aggregation": "count"},
            ],
        )
        acc: dict[str, dict[str, float]] = {}
        for row in rows:
            model = row.get("providedModelName")
            if not model:
                continue
            slot = acc.setdefault(model, _empty_model_slot())
            slot["cost"] += float(row.get("sum_totalCost") or 0.0)
            slot["input_tokens"] += float(row.get("sum_inputTokens") or 0.0)
            slot["output_tokens"] += float(row.get("sum_outputTokens") or 0.0)
            slot["total_tokens"] += float(row.get("sum_totalTokens") or 0.0)
            slot["observations"] += float(row.get("count_count") or 0.0)
        return _model_rows(acc)

    async def fetch_cost_by_backend(self, hours: float) -> dict[str, float]:
        """Total cost per serving backend over the exact last *hours*.

        ``{backend -> cost}`` (e.g. ``{"openrouter": .., "claude-sdk": ..}``).
        Used by reconciliation to compare like-for-like: OpenRouter's per-key
        spend only reconciles against the *openrouter*-backend traced cost —
        Claude-SDK traffic is traced here but billed by Anthropic, not OpenRouter.
        """
        rows = await self._metrics(
            hours, metrics=[{"measure": "totalCost", "aggregation": "sum"}]
        )
        out: dict[str, float] = {}
        for row in rows:
            model = row.get("providedModelName")
            if not model:
                continue
            backend = backend_for_model(model)
            out[backend] = out.get(backend, 0.0) + float(
                row.get("sum_totalCost") or 0.0
            )
        return out

    async def fetch_backend_cost_window(
        self, hours: int
    ) -> dict[str, dict[str, float]]:
        """``{time_bucket -> {backend -> cost}}`` over the exact last *hours*.

        Same metrics source as :meth:`fetch_model_usage_window`, bucketed over
        time (granularity scaled to the window) and folded per backend (see
        :func:`backend_for_model`) for the per-backend cost trend.
        """
        granularity = "minute" if hours <= 1 else "hour" if hours <= 72 else "day"
        rows = await self._metrics(
            hours,
            metrics=[{"measure": "totalCost", "aggregation": "sum"}],
            time_dimension={"granularity": granularity},
        )
        out: dict[str, dict[str, float]] = {}
        for row in rows:
            model = row.get("providedModelName")
            if not model:
                continue
            bucket = str(row.get("time_dimension"))
            backend = backend_for_model(model)
            slot = out.setdefault(bucket, {})
            slot[backend] = slot.get(backend, 0.0) + float(
                row.get("sum_totalCost") or 0.0
            )
        return out
