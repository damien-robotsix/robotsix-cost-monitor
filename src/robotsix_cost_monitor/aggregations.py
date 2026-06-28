"""Pure cost-aggregation and transformation functions over trace dicts.

No I/O, no HTTP, no LangfuseClient dependency — only ``typing`` and
``datetime``. Trivially testable without httpx mocking.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .clients.models import LangfuseTrace

# Periodic-agent sessions: "<board> · <stage>-<YYYYMMDDTHHmmssZ>-<hash>"
# Match the stage prefix (e.g. "trace_review", "implement") so unnamed
# traces from periodic runs group under their stage rather than a per-run
# "(unnamed) …" bucket.
_PERIODIC_SESSION_RE = re.compile(
    r"(?:^|.*[·|]\s*)"  # optional board prefix ending with · or |
    r"([a-z_]+)"  # stage name (capture group 1)
    r"-\d{8}T\d{6}Z-"  # timestamp separator
)


def _trace_cost(trace: LangfuseTrace) -> float:
    """Extract a trace's total cost, tolerant of Langfuse field-name variants."""
    for key in ("total_cost", "calculated_total_cost", "cost"):
        v = getattr(trace, key, None)
        if isinstance(v, (int, float)):
            return float(v)
    return 0.0


def _utc_now() -> datetime:
    return datetime.now(UTC)


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
    """Merge per-project ``{time_bucket -> {backend -> cost}}`` maps into a cost
    series ``[{bucket_start, cost}]`` for *backend* (or the all-backends total
    when *backend* is ``"all"``), sorted by time bucket."""
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


def _trace_label(trace: LangfuseTrace) -> str:
    """Display label for a trace in the by-agent view.

    Prefers the trace name (the stage/agent). Some traces reach Langfuse
    without a name (a pydantic-ai/claude_sdk span became the trace root in a
    context where the session was lost — see robotsix-llmio's trace-name
    handling); rather than dumping their cost into one opaque "(unnamed)"
    bucket, attribute it to the session/ticket so it's still actionable.
    """
    name = trace.name
    if name:
        return str(name)
    sid = trace.session_id
    if sid and isinstance(sid, str):
        m = _PERIODIC_SESSION_RE.match(sid)
        if m:
            return m.group(1)
    return f"(unnamed) {sid}" if sid else "(unnamed)"


def aggregate_by_name(traces: list[LangfuseTrace]) -> list[dict[str, Any]]:
    """Cost + count grouped by trace name (the pipeline stage/agent)."""
    acc: dict[str, dict[str, float]] = {}
    for t in traces:
        name = _trace_label(t)
        slot = acc.setdefault(name, {"cost": 0.0, "count": 0.0})
        slot["cost"] += _trace_cost(t)
        slot["count"] += 1
    ordered = sorted(acc.items(), key=lambda kv: kv[1]["cost"], reverse=True)
    return [
        {"name": n, "cost": round(v["cost"], 6), "count": int(v["count"])}
        for n, v in ordered
    ]


def aggregate_by_session(traces: list[LangfuseTrace]) -> list[dict[str, Any]]:
    """Cost + trace-count grouped by sessionId (the ticket)."""
    acc: dict[str, dict[str, float]] = {}
    for t in traces:
        sid = t.session_id
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


def _parse_ts(trace: LangfuseTrace) -> datetime | None:
    raw = trace.timestamp
    if not isinstance(raw, str):
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


def cost_trend(
    traces: list[LangfuseTrace], hours: int, buckets: int = 48
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


def aggregate_by_name_backend(
    rows: list[dict[str, Any]], backend: str
) -> list[dict[str, Any]]:
    """Merge per-(stage, backend) observation rows for *backend* into the
    ``{"name", "cost", "count"}`` shape returned by
    :func:`aggregate_by_name`.

    ``rows`` are pre-flattened dicts (each with at least ``name``, ``backend``,
    ``cost`` and ``count``).  Rows whose ``backend`` does not match are
    silently dropped.  Multiple projects' rows can be passed together — they
    are summed by stage name.
    """
    acc: dict[str, dict[str, float]] = {}
    for r in rows:
        if r.get("backend") != backend:
            continue
        name = r["name"]
        slot = acc.setdefault(name, {"cost": 0.0, "count": 0.0})
        slot["cost"] += float(r.get("cost") or 0.0)
        slot["count"] += float(r.get("count") or 0.0)
    ordered = sorted(acc.items(), key=lambda kv: kv[1]["cost"], reverse=True)
    return [
        {"name": n, "cost": round(v["cost"], 6), "count": int(v["count"])}
        for n, v in ordered
    ]


def aggregate_by_name_split(
    rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Segment per-(stage, backend) observation rows into per-stage
    OpenRouter-marginal vs subscription-estimated pools.

    ``rows`` are pre-flattened dicts (each with at least ``name``, ``backend``,
    ``cost`` and ``count``).  Multiple projects' rows can be passed together —
    they are summed by stage name.

    Returns one dict per stage::

        {"name": str,
         "openrouter_cost": float, "subscription_cost": float, "total_cost": float,
         "openrouter_count": int, "subscription_count": int}

    where ``total_cost = openrouter_cost + subscription_cost``.  All costs are
    rounded to 6 decimals.  Sorted by ``openrouter_cost`` descending (primary),
    ``total_cost`` descending (tie-break) so stages are ranked by marginal cash.
    """
    acc: dict[str, dict[str, float]] = {}
    for r in rows:
        name = r["name"]
        backend = r.get("backend", "")
        slot = acc.setdefault(
            name,
            {
                "openrouter_cost": 0.0,
                "subscription_cost": 0.0,
                "openrouter_count": 0.0,
                "subscription_count": 0.0,
            },
        )
        cost = float(r.get("cost") or 0.0)
        count = float(r.get("count") or 0.0)
        if backend == "openrouter":
            slot["openrouter_cost"] += cost
            slot["openrouter_count"] += count
        elif backend == "claude-sdk":
            slot["subscription_cost"] += cost
            slot["subscription_count"] += count

    ordered = sorted(
        acc.items(),
        key=lambda kv: (
            kv[1]["openrouter_cost"],
            kv[1]["openrouter_cost"] + kv[1]["subscription_cost"],
        ),
        reverse=True,
    )
    return [
        {
            "name": n,
            "openrouter_cost": round(v["openrouter_cost"], 6),
            "subscription_cost": round(v["subscription_cost"], 6),
            "total_cost": round(v["openrouter_cost"] + v["subscription_cost"], 6),
            "openrouter_count": int(v["openrouter_count"]),
            "subscription_count": int(v["subscription_count"]),
        }
        for n, v in ordered
    ]


def most_expensive_trace(traces: list[LangfuseTrace]) -> dict[str, Any] | None:
    if not traces:
        return None
    top = max(traces, key=_trace_cost)
    return {
        "id": top.id,
        "name": top.name,
        "session_id": top.session_id,
        "cost": round(_trace_cost(top), 6),
        "timestamp": top.timestamp,
    }


def most_expensive_session(traces: list[LangfuseTrace]) -> dict[str, Any] | None:
    rows = aggregate_by_session(traces)
    return rows[0] if rows else None
