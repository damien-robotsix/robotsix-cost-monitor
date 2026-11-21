"""Root pytest configuration shared by the whole test suite."""

from __future__ import annotations

import faulthandler
from collections.abc import Callable

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from robotsix_cost_monitor.config import Config

# Enable faulthandler so that a native crash in a pytest-xdist worker (e.g.
# a segfault) dumps a Python traceback to stderr, and CI logs carry a fault
# trace instead of only pytest-xdist's internal ``assert not crashitem``.
# This is the in-repo stand-in for PYTHONFAULTHANDLER=1, which the reusable
# python-ci workflow cannot set from this repo.
#
# How it works: pytest imports this root conftest in every pytest process,
# including each xdist worker. Enabling faulthandler at module level
# therefore arms it in the workers too, so a native crash dumps the Python
# stack of every thread to stderr.
#
# When to remove: once the worker crash is diagnosed and fixed (or the
# python-ci workflow sets PYTHONFAULTHANDLER=1 itself), this file can be
# deleted.
faulthandler.enable()


@pytest.fixture
def app_factory() -> Callable[..., FastAPI]:
    """Single app constructor for the suite: wraps ``create_app(Config())``.

    Pass ``config=...`` to build the app from a bespoke :class:`Config` (the
    ``create_app(Config())`` override pattern the test modules already use).
    ``create_app`` is imported lazily so that modules which mock the optional
    ``robotsix_llmio`` dependency (e.g. ``test_routes.py``) can import this
    conftest without forcing that dependency in.
    """

    def _app_factory(*, config: Config | None = None) -> FastAPI:
        from robotsix_cost_monitor.app import create_app

        return create_app(config or Config())

    return _app_factory


@pytest.fixture
def make_client(app_factory: Callable[..., FastAPI]) -> Callable[..., TestClient]:
    """Return a factory that wraps a FastAPI app in a ``TestClient``.

    The single place the suite constructs HTTP test clients. By default it
    wraps ``create_app(Config())``; pass ``config=`` to build a bespoke app
    or ``app=`` to wrap an already-built or mutated app. Extra keyword
    arguments are forwarded to ``TestClient``. The client is not entered as
    a context manager, so the app lifespan does not run unless the caller
    uses ``with``.
    """

    def _make_client(
        *,
        config: Config | None = None,
        app: FastAPI | None = None,
        **kwargs: object,
    ) -> TestClient:
        return TestClient(app or app_factory(config=config), **kwargs)  # type: ignore[arg-type]

    return _make_client


@pytest.fixture
def client(make_client: Callable[..., TestClient]) -> TestClient:
    """A ``TestClient`` bound to ``create_app(Config())`` (lifespan not run)."""
    return make_client()


@pytest.fixture
def http_client() -> httpx.AsyncClient:
    """A real ``httpx.AsyncClient`` for wiring a mock service client's transport.

    Used to prove ``MillClient.close()`` releases its lazily-created
    transport; the app teardown under test is what closes it, and the test
    asserts ``is_closed`` afterwards.
    """
    return httpx.AsyncClient(timeout=30.0)
