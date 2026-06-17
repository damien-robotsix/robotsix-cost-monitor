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


# ---------------------------------------------------------------------------
# Pure aggregations over a list of trace dicts (no I/O).
# ---------------------------------------------------------------------------


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
