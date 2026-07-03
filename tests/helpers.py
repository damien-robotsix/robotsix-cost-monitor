"""Test helper utilities — imported explicitly, NOT auto-discovered.

These are data-builder / factory functions that test files import directly
(rather than fixtures auto-discovered by pytest).  Keeping them in a dedicated
module avoids duplication and signature drift.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, Mock

from robotsix_cost_monitor.clients.models import LangfuseTrace
from robotsix_cost_monitor.config import AnalystConfig, Config, ProjectConfig, Settings

# ---------------------------------------------------------------------------
# LangfuseTrace builder
# ---------------------------------------------------------------------------


def trace(
    cost: float = 1.0,
    name: str = "implement",
    *,
    session: str = "",
    tid: str | None = None,
    ago_h: float | None = None,
) -> LangfuseTrace:
    """Build a :class:`LangfuseTrace` instance for tests.

    Keyword Args:
        cost: ``totalCost`` value (default 1.0).
        name: trace ``name`` (default ``"implement"``).
        session: ``sessionId`` — omitted when empty/falsy.
        tid: explicit trace ``id``; if ``None``, derived from *cost* + *name*.
        ago_h: if given, a ``timestamp`` derived from ``now - ago_h hours``
            is included (ISO-8601 with ``Z`` suffix).

    """
    trace_id = tid if tid is not None else f"tr-{cost}-{name}"
    data: dict[str, str | float | None] = {
        "id": trace_id,
        "name": name,
        "totalCost": cost,
    }
    if session:
        data["sessionId"] = session
    if ago_h is not None:
        ts = (datetime.now(UTC) - timedelta(hours=ago_h)).isoformat()
        data["timestamp"] = ts.replace("+00:00", "Z")
    return LangfuseTrace.model_validate(data)


# ---------------------------------------------------------------------------
# ProjectConfig factory
# ---------------------------------------------------------------------------


def _proj(
    name: str = "demo", *, openrouter_key: str | None = "sk-demo"
) -> ProjectConfig:
    """A ProjectConfig with dummy credentials (``base_url`` never called)."""
    return ProjectConfig(
        name=name,
        public_key=f"pk-{name}",
        secret_key=f"sk-{name}",
        base_url="http://localhost",
        openrouter_key=openrouter_key,
    )


# ---------------------------------------------------------------------------
# Config factory
# ---------------------------------------------------------------------------


def _config(
    *projects: ProjectConfig,
    ttl: int = 10,
    subscription_call_cap: int = 0,
    **analyst_kwargs: Any,
) -> Config:
    """Build a ``Config`` from projects and optional Settings overrides.

    ``analyst_kwargs`` are forwarded to ``AnalystConfig`` (only when at least
    one kwarg is given).
    """
    settings_kwargs: dict[str, Any] = {
        "cache_ttl_seconds": ttl,
        "subscription_call_cap": subscription_call_cap,
    }
    if analyst_kwargs:
        settings_kwargs["analyst"] = AnalystConfig(**analyst_kwargs)
    return Config(projects=list(projects), settings=Settings(**settings_kwargs))


# ---------------------------------------------------------------------------
# LangfuseClient mock factory
# ---------------------------------------------------------------------------


def _mock_client(**overrides: object) -> Mock:
    """A ``LangfuseClient`` mock whose async fetch methods return empty results.

    Callers can override individual methods, e.g.::

        client = _mock_client()
        object.__setattr__(
            client, "fetch_traces_window", AsyncMock(return_value=[...])
        )
    """
    client = Mock()
    object.__setattr__(client, "fetch_traces_window", AsyncMock(return_value=[]))
    object.__setattr__(client, "fetch_model_usage_window", AsyncMock(return_value=[]))
    object.__setattr__(client, "fetch_backend_cost_window", AsyncMock(return_value={}))
    object.__setattr__(client, "fetch_agent_usage_window", AsyncMock(return_value=[]))
    object.__setattr__(client, "fetch_trace_detail", AsyncMock(return_value={}))
    for k, v in overrides.items():
        setattr(client, k, v)
    return client
