"""Shared fixtures and factory helpers for the test suite.

Every helper here is a single-source-of-truth — no duplicated definitions
across test files.

Fixtures (auto-discovered by pytest):
  - ``event_loop`` — session-scoped loop for pytest-asyncio + xdist compat

Factories:
  - ``_proj(name, *, openrouter_key)`` — a ProjectConfig with dummy credentials
  - ``_config(*projects, ttl, **analyst_kwargs)`` — a Config from projects + settings
  - ``_mock_client(**overrides)`` — a Mock whose async LangfuseClient fetch
    methods return empty results
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, Mock

import pytest

from robotsix_cost_monitor.config import AnalystConfig, Config, ProjectConfig, Settings


@pytest.fixture(scope="session")
def event_loop() -> Any:
    """Session-scoped event loop for pytest-asyncio + xdist compatibility."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


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
    **analyst_kwargs: Any,
) -> Config:
    """Build a ``Config`` from projects and optional Settings overrides.

    ``analyst_kwargs`` are forwarded to ``AnalystConfig`` (only when at least
    one kwarg is given).
    """
    settings_kwargs: dict[str, Any] = {"cache_ttl_seconds": ttl}
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
    object.__setattr__(client, "fetch_trace_detail", AsyncMock(return_value={}))
    for k, v in overrides.items():
        setattr(client, k, v)
    return client
