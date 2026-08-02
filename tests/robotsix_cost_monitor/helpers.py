"""Test helper utilities — imported explicitly, NOT auto-discovered.

Fixtures (auto-discovered by pytest when placed in ``conftest.py``, but also
accessible via direct import):
  - ``event_loop`` — session-scoped loop for pytest-asyncio + xdist compat

Data-builder / factory functions that test files import directly (rather than
fixtures auto-discovered by pytest):
  - ``trace`` — build a LangfuseTrace for tests
  - ``_proj(name, *, openrouter_key)`` — a RegistryProject with dummy credentials
  - ``_config(ttl, **settings_kwargs)`` — a Config with settings
  - ``_mock_client(**overrides)`` — a Mock whose async LangfuseClient fetch
    methods return empty results
"""

# mypy: disable-error-code="arg-type"

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, Mock

import pytest

from robotsix_cost_monitor.clients.models import LangfuseTrace, RegistryProject
from robotsix_cost_monitor.clients.registry import RegistryClient
from robotsix_cost_monitor.config import Config, Settings
from robotsix_cost_monitor.service import CostService

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
# RegistryProject factory
# ---------------------------------------------------------------------------


def _proj(
    name: str = "demo",
    *,
    openrouter_key: str | None = "sk-demo",
    component: str = "",
) -> RegistryProject:
    """A RegistryProject with dummy credentials."""
    return RegistryProject(
        name=name,
        slug=name.strip().lower().replace(" ", "-"),
        component_id=component,
        langfuse_public_key=f"pk-lf-{name}",
        langfuse_secret_key=f"sk-lf-{name}",
        langfuse_base_url="http://localhost",
        openrouter_key=openrouter_key,
    )


# ---------------------------------------------------------------------------
# Config factory
# ---------------------------------------------------------------------------


def _config(
    ttl: int = 10,
    subscription_call_cap: int = 0,
    data_dir: Path | None = None,
    registry_base_url: str = "",
    **settings_kwargs: Any,
) -> Config:
    """Build a ``Config`` with optional Settings overrides."""
    merged: dict[str, Any] = {
        "cache_ttl_seconds": ttl,
        "subscription_call_cap": subscription_call_cap,
        "registry_base_url": registry_base_url,
    }
    if data_dir is not None:
        merged["data_dir"] = data_dir
    merged.update(settings_kwargs)
    return Config(settings=Settings(**merged))


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
    object.__setattr__(client, "fetch_trace_count_window", AsyncMock(return_value=0))
    object.__setattr__(client, "fetch_trace_count_window", AsyncMock(return_value=0))
    for k, v in overrides.items():
        setattr(client, k, v)
    return client


# ---------------------------------------------------------------------------
# CostService factory (file-local to test_service.py — moved here for reuse)
# ---------------------------------------------------------------------------


def _svc(*projects: RegistryProject, **config_kwargs: Any) -> CostService:
    """CostService whose LangfuseClient instances are all mocks.

    ``config_kwargs`` are forwarded to ``_config`` (e.g. ``subscription_call_cap``).
    """
    cfg = _config(**config_kwargs)
    registry = Mock(spec=RegistryClient)
    object.__setattr__(
        registry,
        "fetch_projects",
        AsyncMock(return_value=list(projects)),
    )
    svc = CostService(cfg, registry)
    # Populate the service from the registry mock
    for p in projects:
        svc._project_map[p.slug] = p
        svc._clients[p.slug] = _mock_client()
    return svc


def _model_row(
    model: str = "opus",
    cost: float = 1.0,
    input_tokens: int = 100,
    output_tokens: int = 50,
    total_tokens: int = 150,
    observations: int = 1,
) -> dict[str, Any]:
    return {
        "model": model,
        "backend": "claude-sdk",
        "cost": cost,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
        "observations": observations,
    }


# ---------------------------------------------------------------------------
# Session-scoped event loop fixture (pytest-asyncio + xdist compat)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def event_loop() -> Any:
    """Session-scoped event loop for pytest-asyncio + xdist compatibility."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()
