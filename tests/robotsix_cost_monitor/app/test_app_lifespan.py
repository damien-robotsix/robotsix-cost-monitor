"""App lifespan tests: conditional task creation and teardown."""

# mypy: disable-error-code="arg-type"

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, Mock, patch

import httpx
import pytest
from fastapi.testclient import TestClient

from robotsix_cost_monitor.app import (
    create_app,
)
from robotsix_cost_monitor.clients.mill import MillClient
from robotsix_cost_monitor.config import Config, Settings

# ---------------------------------------------------------------------------
# lifespan — conditional task creation
# ---------------------------------------------------------------------------


def _make_mock_service(*, with_projects: bool = True) -> Mock:
    """Return a mock CostService that carries a non-empty ``_project_map``."""
    svc = Mock()
    svc._project_map = {"proj-a": Mock()} if with_projects else {}
    svc.refresh_projects = AsyncMock()
    svc._caches = []
    svc.summary = AsyncMock(return_value=[])
    svc.by_model = AsyncMock(return_value=[])
    svc.trend = AsyncMock(return_value=[])
    return svc


def test_lifespan_skips_background_loops_when_intervals_zero() -> None:
    """When all schedule intervals are zero only ``_warm_cache`` runs (one-shot)."""
    cfg = Config(
        settings=Settings(
            reconcile_schedule_hours=0,
            dashboard_refresh_interval_seconds=0,
            registry_poll_interval_seconds=0,
        )
    )
    mock_reconcile = AsyncMock()
    mock_cache_refresh = AsyncMock()
    mock_warm = AsyncMock()

    with (
        patch("robotsix_cost_monitor.app._reconcile_loop", mock_reconcile),
        patch("robotsix_cost_monitor.app._cache_refresh_loop", mock_cache_refresh),
        patch("robotsix_cost_monitor.app._warm_cache", mock_warm),
    ):
        app = create_app(cfg)
        with TestClient(app) as _client:
            pass

    mock_reconcile.assert_not_called()
    mock_cache_refresh.assert_not_called()
    mock_warm.assert_called_once()


def test_lifespan_starts_reconcile_loop_when_positive_and_projects() -> None:
    """A positive ``reconcile_schedule_hours`` with projects starts the reconcile loop."""
    cfg = Config(settings=Settings(reconcile_schedule_hours=24))
    mock_reconcile = AsyncMock()
    mock_service = _make_mock_service()

    with (
        patch("robotsix_cost_monitor.app.CostService", return_value=mock_service),
        patch("robotsix_cost_monitor.app._reconcile_loop", mock_reconcile),
        patch("robotsix_cost_monitor.app._cache_refresh_loop", AsyncMock()),
        patch("robotsix_cost_monitor.app._warm_cache", AsyncMock()),
    ):
        app = create_app(cfg)
        with TestClient(app) as _client:
            pass

    mock_reconcile.assert_called_once()


def test_lifespan_skips_reconcile_when_no_projects() -> None:
    """A positive ``reconcile_schedule_hours`` with an empty project map
    does NOT start the reconcile loop.
    """
    cfg = Config(settings=Settings(reconcile_schedule_hours=24))
    mock_reconcile = AsyncMock()
    mock_service = _make_mock_service(with_projects=False)

    with (
        patch("robotsix_cost_monitor.app.CostService", return_value=mock_service),
        patch("robotsix_cost_monitor.app._reconcile_loop", mock_reconcile),
        patch("robotsix_cost_monitor.app._cache_refresh_loop", AsyncMock()),
        patch("robotsix_cost_monitor.app._warm_cache", AsyncMock()),
    ):
        app = create_app(cfg)
        with TestClient(app) as _client:
            pass

    mock_reconcile.assert_not_called()


def test_lifespan_starts_cache_refresh_when_positive_and_projects() -> None:
    """A positive ``dashboard_refresh_interval_seconds`` with projects starts
    the cache-refresh loop.
    """
    cfg = Config(settings=Settings(dashboard_refresh_interval_seconds=120))
    mock_cache_refresh = AsyncMock()
    mock_service = _make_mock_service()

    with (
        patch("robotsix_cost_monitor.app.CostService", return_value=mock_service),
        patch("robotsix_cost_monitor.app._cache_refresh_loop", mock_cache_refresh),
        patch("robotsix_cost_monitor.app._reconcile_loop", AsyncMock()),
        patch("robotsix_cost_monitor.app._warm_cache", AsyncMock()),
    ):
        app = create_app(cfg)
        with TestClient(app) as _client:
            pass

    mock_cache_refresh.assert_called_once()


def test_lifespan_starts_registry_poll_when_interval_positive() -> None:
    """A positive ``registry_poll_interval_seconds`` starts a poll loop that
    calls ``service.refresh_projects``.
    """
    cfg = Config(settings=Settings(registry_poll_interval_seconds=1))
    mock_service = _make_mock_service()

    # Let the poll loop run a couple of iterations.
    _real_sleep = asyncio.sleep

    async def fast_sleep(seconds: float) -> None:
        await _real_sleep(0)

    with (
        patch("robotsix_cost_monitor.app.CostService", return_value=mock_service),
        patch("robotsix_cost_monitor.app._warm_cache", AsyncMock()),
        patch("robotsix_cost_monitor.app.asyncio.sleep", fast_sleep),
    ):
        app = create_app(cfg)
        with TestClient(app) as _client:
            pass

    # The poll loop should have called refresh_projects at least once
    # before the lifespan was torn down.
    assert mock_service.refresh_projects.call_count >= 1


def test_lifespan_warm_cache_always_runs() -> None:
    """``_warm_cache`` is always started even when all loops are disabled."""
    cfg = Config(
        settings=Settings(
            reconcile_schedule_hours=0,
            dashboard_refresh_interval_seconds=0,
            registry_poll_interval_seconds=0,
        )
    )
    mock_warm = AsyncMock()

    with patch("robotsix_cost_monitor.app._warm_cache", mock_warm):
        app = create_app(cfg)
        with TestClient(app) as _client:
            pass

    mock_warm.assert_called_once()


# ---------------------------------------------------------------------------
# lifespan — teardown
# ---------------------------------------------------------------------------


def test_lifespan_teardown_cancels_all_tasks() -> None:
    """After the ``TestClient`` context manager exits every background task
    has been cancelled and awaited (``task.done()`` is True).
    """
    cfg = Config(
        settings=Settings(
            reconcile_schedule_hours=24,
            dashboard_refresh_interval_seconds=120,
            registry_poll_interval_seconds=30,
        )
    )
    mock_service = _make_mock_service()

    real_create_task = asyncio.create_task
    tasks_created: list[asyncio.Task[object]] = []

    def tracking_create_task(coro: object) -> asyncio.Task[object]:
        task: asyncio.Task[object] = real_create_task(coro)
        tasks_created.append(task)
        return task

    async def _block_forever(*args: object, **kwargs: object) -> None:
        await asyncio.Event().wait()

    with (
        patch("robotsix_cost_monitor.app.CostService", return_value=mock_service),
        patch("robotsix_cost_monitor.app._reconcile_loop", _block_forever),
        patch("robotsix_cost_monitor.app._cache_refresh_loop", _block_forever),
        patch("robotsix_cost_monitor.app._warm_cache", _block_forever),
        patch("robotsix_cost_monitor.app.asyncio.create_task", tracking_create_task),
    ):
        app = create_app(cfg)
        with TestClient(app) as _client:
            pass

    # reconcile, cache_refresh, warm_cache, registry_poll → ≥ 4 tasks
    assert len(tasks_created) >= 4, f"expected ≥ 4 tasks, got {len(tasks_created)}"
    for task in tasks_created:
        assert task.done(), f"task {task.get_name()!r} was not done after teardown"


def test_lifespan_teardown_closes_mill_client() -> None:
    """The ``MillClient`` is explicitly closed during lifespan teardown so the
    underlying ``httpx.AsyncClient`` is released rather than left to the GC.
    """
    cfg = Config(settings=Settings())
    mock_service = _make_mock_service()
    mock_mill = Mock()
    mock_mill.close = AsyncMock()

    with (
        patch("robotsix_cost_monitor.app.CostService", return_value=mock_service),
        patch("robotsix_cost_monitor.app.MillClient", return_value=mock_mill),
        patch("robotsix_cost_monitor.app._warm_cache", AsyncMock()),
    ):
        app = create_app(cfg)
        with TestClient(app) as _client:
            pass

    mock_mill.close.assert_awaited_once()


def test_lifespan_teardown_closes_caches() -> None:
    """Each service cache's ``aclose()`` is awaited during lifespan teardown so
    in-flight background refreshes are cancelled rather than left untracked.
    """
    cfg = Config(settings=Settings())
    mock_service = _make_mock_service()
    caches = [Mock(aclose=AsyncMock()), Mock(aclose=AsyncMock())]
    mock_service._caches = caches

    with (
        patch("robotsix_cost_monitor.app.CostService", return_value=mock_service),
        patch("robotsix_cost_monitor.app._warm_cache", AsyncMock()),
    ):
        app = create_app(cfg)
        with TestClient(app) as _client:
            pass

    for c in caches:
        c.aclose.assert_awaited_once()


def test_lifespan_teardown_releases_real_httpx_client() -> None:
    """Integration: a *real* ``MillClient``'s underlying ``httpx.AsyncClient``
    is actually released during lifespan teardown.

    Unlike ``test_lifespan_teardown_closes_mill_client`` (which mocks the
    client), this drives the real ``MillClient.close()`` path and asserts the
    lazily-created transport is closed and the holder reset to ``None``.
    """
    cfg = Config(settings=Settings())
    mock_service = _make_mock_service()

    mill = MillClient(cfg.settings)
    # Force the lazy HTTP transport into existence so we have something to
    # observe being closed. ``httpx.AsyncClient.__init__`` needs no event loop.
    mill._http = httpx.AsyncClient(timeout=30.0)
    http = mill._http
    assert not http.is_closed

    with (
        patch("robotsix_cost_monitor.app.CostService", return_value=mock_service),
        patch("robotsix_cost_monitor.app.MillClient", return_value=mill),
        patch("robotsix_cost_monitor.app._warm_cache", AsyncMock()),
    ):
        app = create_app(cfg)
        with TestClient(app) as _client:
            pass

    assert http.is_closed, "underlying httpx.AsyncClient was not released"
    assert mill._http is None


def test_lifespan_teardown_releases_httpx_client_on_error() -> None:
    """The underlying ``httpx.AsyncClient`` is released even when the app
    context exits via an exception — cleanup lives in a ``finally`` block, so
    an error path must not leak the transport.
    """
    cfg = Config(settings=Settings())
    mock_service = _make_mock_service()

    mill = MillClient(cfg.settings)
    mill._http = httpx.AsyncClient(timeout=30.0)
    http = mill._http
    assert not http.is_closed

    with (
        patch("robotsix_cost_monitor.app.CostService", return_value=mock_service),
        patch("robotsix_cost_monitor.app.MillClient", return_value=mill),
        patch("robotsix_cost_monitor.app._warm_cache", AsyncMock()),
    ):
        app = create_app(cfg)
        with (
            pytest.raises(RuntimeError, match="boom"),
            TestClient(app) as _client,
        ):
            raise RuntimeError("boom")

    assert http.is_closed, "underlying httpx.AsyncClient leaked on error path"
    assert mill._http is None
