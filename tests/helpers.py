"""Test helper utilities — imported explicitly, NOT auto-discovered.

These are data-builder / factory functions that test files import directly
(rather than fixtures auto-discovered by pytest).  Keeping them in a dedicated
module avoids duplication and signature drift.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any


def trace(
    cost: float = 1.0,
    name: str = "implement",
    *,
    session: str = "",
    tid: str | None = None,
    ago_h: float | None = None,
) -> dict[str, Any]:
    """Build a trace dict row in the shape returned by LangfuseClient.

    Keyword Args:
        cost: ``totalCost`` value (default 1.0).
        name: trace ``name`` (default ``"implement"``).
        session: ``sessionId`` — omitted when empty/falsy.
        tid: explicit trace ``id``; if ``None``, derived from *cost* + *name*.
        ago_h: if given, a ``timestamp`` derived from ``now - ago_h hours``
            is included (ISO-8601 with ``Z`` suffix).
    """
    trace_id = tid if tid is not None else f"tr-{cost}-{name}"
    t: dict[str, Any] = {"id": trace_id, "name": name, "totalCost": cost}
    if session:
        t["sessionId"] = session
    if ago_h is not None:
        ts = (datetime.now(UTC) - timedelta(hours=ago_h)).isoformat()
        t["timestamp"] = ts.replace("+00:00", "Z")
    return t
