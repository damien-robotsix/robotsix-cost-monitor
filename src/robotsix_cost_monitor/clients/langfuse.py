"""Langfuse read client for cost-monitor.

One :class:`LangfuseClient` per project.  Provides auth/URL construction
and async HTTP calls plus cost-monitor's domain-specific aggregation
methods (``/api/public/metrics`` queries, per-model / per-backend / per-agent
aggregation). Talks to the Langfuse public REST API (``/api/public/*``).

Pure aggregation / transformation functions live in
:mod:`robotsix_cost_monitor.aggregations`.
"""

from __future__ import annotations

import base64
import json
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from ..aggregations import (
    _empty_model_slot,
    _model_rows,
    _utc_now,
    backend_for_model,
)

__all__ = [
    "LangfuseClient",
]


class _LangfuseRESTClient:
    """Minimal vendored async REST helper for the Langfuse public API.

    Replaces the external ``AsyncLangfuseReadClient`` so that
    ``robotsix-llmio`` remains a truly optional (analyst-only) dependency.
    Provides exactly the four methods :class:`LangfuseClient` uses:
    ``url``, ``auth_header``, ``fetch_traces_window``, ``fetch_trace_detail``.
    """

    def __init__(
        self,
        *,
        public_key: str,
        secret_key: str,
        base_url: str,
        timeout: float = 30.0,
    ) -> None:
        self._public_key = public_key
        self._secret_key = secret_key
        self.base_url = base_url.rstrip("/")
        self._timeout = timeout

    def url(self, path: str) -> str:
        """Join *path* onto the project's base URL."""
        return f"{self.base_url}{path}"

    def auth_header(self) -> str:
        """Return the ``Authorization: Basic ...`` header value."""
        creds = f"{self._public_key}:{self._secret_key}"
        return f"Basic {base64.b64encode(creds.encode()).decode()}"

    async def fetch_traces_window(
        self, hours: float
    ) -> Any:  # pragma: no cover — tested via LangfuseClient delegation
        """Yield every trace with ``timestamp`` within the last *hours*.

        Paginates ``GET /api/public/traces`` automatically.
        """
        from_timestamp = (
            datetime.now(timezone.utc) - timedelta(hours=hours)  # noqa: UP017
        ).isoformat()
        page = 1
        limit = 50
        while True:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.get(
                    self.url("/api/public/traces"),
                    params={
                        "fromTimestamp": from_timestamp,
                        "page": str(page),
                        "limit": str(limit),
                    },
                    headers={"Authorization": self.auth_header()},
                )
                resp.raise_for_status()
                body: dict[str, Any] = resp.json()
                for trace in body.get("data") or []:
                    yield trace
                meta: dict[str, Any] = body.get("meta") or {}
                total_pages: int = meta.get("totalPages", 0)
                if page >= total_pages:
                    break
                page += 1

    async def fetch_trace_detail(
        self, trace_id: str
    ) -> dict[str, Any]:  # pragma: no cover — tested via LangfuseClient delegation
        """Return the full trace for *trace_id* (including observations)."""
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.get(
                self.url(f"/api/public/traces/{trace_id}"),
                headers={"Authorization": self.auth_header()},
            )
            resp.raise_for_status()
            body_data: dict[str, Any] = resp.json()
            return body_data


class LangfuseClient:
    """Read-only cost/trace client for a single Langfuse project.

    Composes :class:`_LangfuseRESTClient` for auth/URL helpers and
    async REST transport; owns its own domain aggregation.
    """

    def __init__(
        self,
        *,
        public_key: str,
        secret_key: str,
        base_url: str,
        timeout: float = 30.0,
    ) -> None:
        self._lf = _LangfuseRESTClient(
            public_key=public_key,
            secret_key=secret_key,
            base_url=base_url,
            timeout=timeout,
        )
        self._timeout = timeout

    async def fetch_traces_window(self, hours: float) -> list[dict[str, Any]]:
        """Return all traces with ``timestamp`` within the last *hours*.

        *hours* may be fractional (reconciliation passes the exact snapshot
        interval). Delegates to :meth:`_LangfuseRESTClient.fetch_traces_window`.
        """
        return [trace async for trace in self._lf.fetch_traces_window(hours)]

    async def fetch_trace_detail(self, trace_id: str) -> dict[str, Any]:
        """Return a single trace's full detail (including its observations).

        Delegates to :meth:`_LangfuseRESTClient.fetch_trace_detail`.
        """
        detail: dict[str, Any] = await self._lf.fetch_trace_detail(trace_id)
        return detail

    async def _metrics(
        self,
        hours: float,
        *,
        metrics: list[dict[str, str]],
        view: str = "observations",
        dimensions: list[dict[str, str]] | None = None,
        time_dimension: dict[str, str] | None = None,
    ) -> list[dict[str, Any]]:
        """Run a Langfuse metrics query over *view* (``observations`` or
        ``traces``) for the exact last *hours*, grouped by *dimensions* (``None``
        → group by model; pass ``[]`` for an ungrouped total). Returns the raw
        ``data`` rows.

        ``/api/public/metrics`` aggregates server-side and, unlike the
        daily-metrics endpoint, honors the exact ``from``/``to`` window (the
        daily endpoint returns whole calendar days and badly over-counts sub-day
        windows). One request per query — no pagination needed.
        """
        now = _utc_now()
        query: dict[str, Any] = {
            "view": view,
            "metrics": metrics,
            "dimensions": (
                [{"field": "providedModelName"}] if dimensions is None else dimensions
            ),
            "fromTimestamp": (now - timedelta(hours=hours))
            .isoformat()
            .replace("+00:00", "Z"),
            "toTimestamp": now.isoformat().replace("+00:00", "Z"),
        }
        if time_dimension is not None:
            query["timeDimension"] = time_dimension
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.get(
                self._lf.url("/api/public/metrics"),
                params={"query": json.dumps(query)},
                headers={"Authorization": self._lf.auth_header()},
            )
            resp.raise_for_status()
            data: dict[str, Any] = resp.json()
            return list(data.get("data") or [])

    async def fetch_trace_count_window(self, hours: float) -> int:
        """Count traces in the exact last *hours* via a server-side metrics
        query (``view=traces``, ungrouped ``count``).

        One ``/api/public/metrics`` request — O(1), vs paging every trace just to
        ``len()`` them (which is ~27s over a week of all-project data).
        """
        rows = await self._metrics(
            hours,
            view="traces",
            metrics=[{"measure": "count", "aggregation": "count"}],
            dimensions=[],
        )
        return int(rows[0].get("count_count") or 0) if rows else 0

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
