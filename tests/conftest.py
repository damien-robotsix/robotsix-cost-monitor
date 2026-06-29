"""Shared fixtures and factory helpers for the test suite.

Every helper here is a single-source-of-truth — no duplicated definitions
across test files.

Fixtures (auto-discovered by pytest):
  - ``event_loop`` — session-scoped loop for pytest-asyncio + xdist compat

Factories (defined in ``tests/helpers.py``, re-exported here for backward
compatibility with tests that import from ``conftest``):
  - ``_proj(name, *, openrouter_key)`` — a ProjectConfig with dummy credentials
  - ``_config(*projects, ttl, **analyst_kwargs)`` — a Config from projects + settings
  - ``_mock_client(**overrides)`` — a Mock whose async LangfuseClient fetch
    methods return empty results
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from helpers import _config, _mock_client, _proj  # noqa: F401


@pytest.fixture(scope="session")
def event_loop() -> Any:
    """Session-scoped event loop for pytest-asyncio + xdist compatibility."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()
