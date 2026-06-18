"""Self-contained async Langfuse read client + cost aggregations.

One :class:`LangfuseClient` per project. Talks to the Langfuse public REST API
(``/api/public/*``) with HTTP Basic auth (public key : secret key) and paginates
the traces endpoint. No Langfuse SDK dependency — just ``httpx``.

Cost is read from each trace's ``totalCost`` (Langfuse's span-derived cost).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

_PAGE_LIMIT = 100
_MAX_PAGES = 100  # safety cap (≤ 10k traces per query)


def _trace_cost(trace: dict[str, Any]) -> float:
    """Extract a trace's total cost, tolerant of Langfuse field-name variants."""
    for key in ("totalCost", "calculatedTotalCost", "cost"):
        v = trace.get(key)
        if isinstance(v, (int, float)):
            return float(v)
    return 0.0


def _utc_now() -> datetime:
    return datetime.now(UTC)


class LangfuseClient:
    """Read-only cost/trace client for a single Langfuse project."""

    def __init__(
        self,
        *,
        public_key: str,
        secret_key: str,
        base_url: str,
        timeout: float = 30.0,
    ) -> None:
        self._auth = (public_key, secret_key)
        self._base = base_url.rstrip("/")
        self._timeout = timeout

    async def _get(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.get(
                f"{self._base}{path}", params=params, auth=self._auth
            )
            resp.raise_for_status()
            data: dict[str, Any] = resp.json()
            return data

    async def fetch_traces_window(self, hours: int) -> list[dict[str, Any]]:
        """Return all traces with ``timestamp`` within the last *hours*.

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

    async def session_traces(self, session_id: str) -> list[dict[str, Any]]:
        """Return all traces for a session (ticket)."""
        data = await self._get(
            "/api/public/traces",
            {"sessionId": session_id, "limit": _PAGE_LIMIT},
        )
        return list(data.get("data") or [])

    async def fetch_daily_model_usage(self, hours: int) -> list[dict[str, Any]]:
        """Per-model cost + token usage over the last *hours*.

        Uses Langfuse's daily-metrics endpoint (``/api/public/metrics/daily``),
        which already aggregates cost and token usage per model server-side, and
        sums each model's daily rows across the window. This is day-granular —
        the window is effectively rounded out to whole days — but far cheaper
        than paging every generation observation. Observations with no model
        (non-generation spans) are skipped; they carry no cost.
        """
        since = _utc_now() - timedelta(hours=hours)
        from_ts = since.isoformat().replace("+00:00", "Z")
        acc: dict[str, dict[str, float]] = {}
        for page in range(1, _MAX_PAGES + 1):
            data = await self._get(
                "/api/public/metrics/daily",
                {"fromTimestamp": from_ts, "limit": _PAGE_LIMIT, "page": page},
            )
            rows = data.get("data") or []
            if not rows:
                break
            for day in rows:
                for usage in day.get("usage") or []:
                    model = usage.get("model")
                    if not model:
                        continue
                    slot = acc.setdefault(model, _empty_model_slot())
                    slot["cost"] += float(usage.get("totalCost") or 0.0)
                    slot["input_tokens"] += float(usage.get("inputUsage") or 0.0)
                    slot["output_tokens"] += float(usage.get("outputUsage") or 0.0)
                    slot["total_tokens"] += float(usage.get("totalUsage") or 0.0)
                    slot["observations"] += float(usage.get("countObservations") or 0.0)
            meta = data.get("meta") or {}
            total_pages = meta.get("totalPages")
            if total_pages is not None and page >= total_pages:
                break
            if len(rows) < _PAGE_LIMIT:
                break
        return _model_rows(acc)

    async def fetch_daily_backend_cost(self, hours: int) -> dict[str, dict[str, float]]:
        """``{date -> {backend -> cost}}`` over the window (day-granular).

        Same daily-metrics source as :meth:`fetch_daily_model_usage`, but the
        per-model rows are folded into their backend (see
        :func:`backend_for_model`) so the dashboard can show a per-backend cost
        trend and filter totals by backend.
        """
        since = _utc_now() - timedelta(hours=hours)
        from_ts = since.isoformat().replace("+00:00", "Z")
        out: dict[str, dict[str, float]] = {}
        for page in range(1, _MAX_PAGES + 1):
            data = await self._get(
                "/api/public/metrics/daily",
                {"fromTimestamp": from_ts, "limit": _PAGE_LIMIT, "page": page},
            )
            rows = data.get("data") or []
            if not rows:
                break
            for day in rows:
                slot = out.setdefault(str(day.get("date")), {})
                for usage in day.get("usage") or []:
                    model = usage.get("model")
                    if not model:
                        continue
                    backend = backend_for_model(model)
                    slot[backend] = slot.get(backend, 0.0) + float(
                        usage.get("totalCost") or 0.0
                    )
            meta = data.get("meta") or {}
            total_pages = meta.get("totalPages")
            if total_pages is not None and page >= total_pages:
                break
            if len(rows) < _PAGE_LIMIT:
                break
        return out


# ---------------------------------------------------------------------------
# Pure aggregations over a list of trace dicts (no I/O).
# ---------------------------------------------------------------------------


def backend_for_model(model: str) -> str:
    """Map a model name to its serving backend (transport).

    Keys on the model-ID *shape*, not specific names, so it survives model
    version bumps: OpenRouter model IDs are always ``vendor/model`` (contain a
    ``/``); the Claude SDK uses bare aliases (``opus``/``haiku``/``sonnet``).
    """
    return "openrouter" if "/" in model else "claude-sdk"


def _empty_model_slot() -> dict[str, float]:
    return {
        "cost": 0.0,
        "input_tokens": 0.0,
        "output_tokens": 0.0,
        "total_tokens": 0.0,
        "observations": 0.0,
    }


def _model_rows(acc: dict[str, dict[str, float]]) -> list[dict[str, Any]]:
    """Format a model→totals accumulator into rows sorted by cost desc."""
    ordered = sorted(acc.items(), key=lambda kv: kv[1]["cost"], reverse=True)
    return [
        {
            "model": model,
            "backend": backend_for_model(model),
            "cost": round(v["cost"], 6),
            "input_tokens": int(v["input_tokens"]),
            "output_tokens": int(v["output_tokens"]),
            "total_tokens": int(v["total_tokens"]),
            "observations": int(v["observations"]),
        }
        for model, v in ordered
    ]


def backend_cost_series(
    parts: list[dict[str, dict[str, float]]], backend: str
) -> list[dict[str, Any]]:
    """Merge per-project ``{date -> {backend -> cost}}`` maps into a daily cost
    series ``[{bucket_start, cost}]`` for *backend* (or the all-backends total
    when *backend* is ``"all"``), sorted by date."""
    merged: dict[str, dict[str, float]] = {}
    for part in parts:
        for date, by_backend in part.items():
            slot = merged.setdefault(date, {})
            for b, cost in by_backend.items():
                slot[b] = slot.get(b, 0.0) + cost
    series: list[dict[str, Any]] = []
    for date in sorted(merged):
        by_backend = merged[date]
        cost = (
            sum(by_backend.values())
            if backend == "all"
            else by_backend.get(backend, 0.0)
        )
        series.append({"bucket_start": date, "cost": round(cost, 6)})
    return series


def merge_model_costs(parts: list[list[dict[str, Any]]]) -> list[dict[str, Any]]:
    """Merge per-model usage rows from several projects, summing by model."""
    acc: dict[str, dict[str, float]] = {}
    for rows in parts:
        for r in rows:
            slot = acc.setdefault(r["model"], _empty_model_slot())
            slot["cost"] += float(r.get("cost") or 0.0)
            slot["input_tokens"] += float(r.get("input_tokens") or 0.0)
            slot["output_tokens"] += float(r.get("output_tokens") or 0.0)
            slot["total_tokens"] += float(r.get("total_tokens") or 0.0)
            slot["observations"] += float(r.get("observations") or 0.0)
    return _model_rows(acc)


def total_cost(traces: list[dict[str, Any]]) -> float:
    return round(sum(_trace_cost(t) for t in traces), 6)


def aggregate_by_name(traces: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Cost + count grouped by trace name (the pipeline stage/agent)."""
    acc: dict[str, dict[str, float]] = {}
    for t in traces:
        name = t.get("name") or "(unnamed)"
        slot = acc.setdefault(name, {"cost": 0.0, "count": 0.0})
        slot["cost"] += _trace_cost(t)
        slot["count"] += 1
    ordered = sorted(acc.items(), key=lambda kv: kv[1]["cost"], reverse=True)
    return [
        {"name": n, "cost": round(v["cost"], 6), "count": int(v["count"])}
        for n, v in ordered
    ]


def aggregate_by_session(traces: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Cost + trace-count grouped by sessionId (the ticket)."""
    acc: dict[str, dict[str, float]] = {}
    for t in traces:
        sid = t.get("sessionId") or t.get("session_id")
        if not sid:
            continue
        slot = acc.setdefault(sid, {"cost": 0.0, "count": 0.0})
        slot["cost"] += _trace_cost(t)
        slot["count"] += 1
    ordered = sorted(acc.items(), key=lambda kv: kv[1]["cost"], reverse=True)
    return [
        {"session_id": s, "cost": round(v["cost"], 6), "count": int(v["count"])}
        for s, v in ordered
    ]


def _parse_ts(trace: dict[str, Any]) -> datetime | None:
    raw = trace.get("timestamp")
    if not isinstance(raw, str):
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


def cost_trend(
    traces: list[dict[str, Any]], hours: int, buckets: int = 48
) -> list[dict[str, Any]]:
    """Bucket total cost over the time window into *buckets* equal slots."""
    now = _utc_now()
    start = now - timedelta(hours=hours)
    span = (now - start).total_seconds() or 1.0
    width = span / buckets
    totals = [0.0] * buckets
    for t in traces:
        ts = _parse_ts(t)
        if ts is None:
            continue
        idx = int((ts - start).total_seconds() / width)
        if idx < 0 or idx >= buckets:
            continue
        totals[idx] += _trace_cost(t)
    return [
        {
            "bucket_start": (start + timedelta(seconds=width * i)).isoformat(),
            "cost": round(totals[i], 6),
        }
        for i in range(buckets)
    ]


def most_expensive_trace(traces: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not traces:
        return None
    top = max(traces, key=_trace_cost)
    return {
        "id": top.get("id"),
        "name": top.get("name"),
        "session_id": top.get("sessionId"),
        "cost": round(_trace_cost(top), 6),
        "timestamp": top.get("timestamp"),
    }


def most_expensive_session(traces: list[dict[str, Any]]) -> dict[str, Any] | None:
    rows = aggregate_by_session(traces)
    return rows[0] if rows else None
