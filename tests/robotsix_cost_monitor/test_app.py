"""App + config tests using a zero-project config (no network)."""

# mypy: disable-error-code="arg-type"

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import pytest
import structlog
from asgi_correlation_id import correlation_id
from fastapi.testclient import TestClient
from pydantic import SecretStr

from robotsix_cost_monitor.app import (
    _cache_refresh_loop,
    _reconcile_loop,
    _warm_cache,
    add_correlation_id,
    create_app,
)
from robotsix_cost_monitor.config import Config, Settings, load_config
from robotsix_cost_monitor.metrics import cache_warm_failure, cache_warm_success


def _empty_app() -> TestClient:
    return TestClient(create_app(Config()))


def _auth_app() -> TestClient:
    from robotsix_cost_monitor.config import AuthConfig, Settings

    cfg = Config(
        settings=Settings(
            auth=AuthConfig(
                username="admin",
                password=SecretStr("s3cret"),  # pragma: allowlist secret
            )
        ),
    )
    return TestClient(create_app(cfg))


def test_auth_required_returns_401_without_credentials() -> None:
    r = _auth_app().get("/")
    assert r.status_code == 401
    assert r.headers.get("www-authenticate", "").lower().startswith("basic")


def test_auth_rejects_wrong_credentials() -> None:
    r = _auth_app().get("/", auth=("admin", "wrong"))
    assert r.status_code == 401


def test_auth_accepts_correct_credentials() -> None:
    r = _auth_app().get("/", auth=("admin", "s3cret"))
    assert r.status_code == 200


def test_auth_health_is_exempt() -> None:
    # The container healthcheck hits /health without credentials.
    r = _auth_app().get("/health")
    assert r.status_code == 200


def test_auth_readyz_is_exempt() -> None:
    # The container readiness probe hits /readyz without credentials.
    r = _auth_app().get("/readyz")
    assert r.status_code == 200


def test_auth_disabled_when_unconfigured() -> None:
    # No username/password -> dashboard is open (loopback/dev).
    r = _empty_app().get("/")
    assert r.status_code == 200


def test_health() -> None:
    r = _empty_app().get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_security_headers_on_html_page() -> None:
    """The index HTML page includes security response headers."""
    r = _empty_app().get("/")
    assert r.status_code == 200
    assert r.headers["x-content-type-options"] == "nosniff"
    assert "content-security-policy" in r.headers


def test_security_headers_on_json_api() -> None:
    """JSON API responses also include security response headers."""
    r = _empty_app().get("/health")
    assert r.status_code == 200
    assert r.headers["x-content-type-options"] == "nosniff"
    assert "content-security-policy" in r.headers


def test_summary_empty_is_zero() -> None:
    r = _empty_app().get("/api/summary?hours=24")
    assert r.status_code == 200
    body = r.json()
    assert body["total_cost"] == 0.0
    assert body["projects"] == []
    assert body["window_hours"] == 24


def test_summary_unknown_project_returns_404() -> None:
    """An unknown project slug returns 404 with PROJECT_NOT_FOUND."""
    r = _empty_app().get("/api/summary?project=nonexistent")
    assert r.status_code == 404
    body = r.json()
    assert body["error"]["code"] == "PROJECT_NOT_FOUND"


def test_summary_project_all_returns_200_when_no_projects() -> None:
    """?project=all is always valid — returns 200 even with zero projects."""
    r = _empty_app().get("/api/summary?project=all")
    assert r.status_code == 200


def test_unknown_project_across_endpoints() -> None:
    """Every project-scoped endpoint returns 404 with PROJECT_NOT_FOUND for an unknown slug."""
    c = _empty_app()
    endpoints = [
        "/api/summary?project=nope",
        "/api/by-agent?project=nope",
        "/api/by-model?project=nope",
        "/api/backend-trend?project=nope&backend=openrouter",
        "/api/trend?project=nope",
        "/api/highlights?project=nope",
        "/api/reconcile?project=nope",
    ]
    for ep in endpoints:
        r = c.get(ep)
        assert r.status_code == 404, f"{ep} returned {r.status_code}"
        body = r.json()
        assert body["error"]["code"] == "PROJECT_NOT_FOUND", f"{ep} code mismatch"


def test_by_agent_and_trend_empty() -> None:
    c = _empty_app()
    assert c.get("/api/by-agent?hours=24").json() == []
    assert len(c.get("/api/trend?hours=24&buckets=12").json()) == 12


def test_by_agent_accepts_backend_param() -> None:
    """The /api/by-agent route accepts ?backend=... and returns empty for no projects."""
    c = _empty_app()
    r = c.get("/api/by-agent?hours=24&backend=openrouter")
    assert r.status_code == 200
    assert r.json() == []


def test_by_agent_backend_all_is_default() -> None:
    """Omitting ?backend=... is equivalent to ?backend=all."""
    c = _empty_app()
    assert (
        c.get("/api/by-agent?hours=24").json()
        == c.get("/api/by-agent?hours=24&backend=all").json()
    )


def test_by_model_empty() -> None:
    r = _empty_app().get("/api/by-model?hours=24")
    assert r.status_code == 200
    assert r.json() == []


def test_backend_trend_empty() -> None:
    r = _empty_app().get("/api/backend-trend?hours=24&backend=openrouter")
    assert r.status_code == 200
    assert r.json() == []


def test_index_served() -> None:
    r = _empty_app().get("/")
    assert r.status_code == 200
    assert "cost monitor" in r.text
    # The dashboard renders the last reconcile into this element on load.
    assert 'id="recon-when"' in r.text


def test_reconcile_last_served_from_disk(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The persisted last reconcile is served by ``/api/reconcile/last`` — this is
    what lets the dashboard show the last run after a page reload or container
    restart (the file is on the persisted data volume).
    """
    monkeypatch.setattr(
        "robotsix_cost_monitor.reconcile.data_dir", lambda settings=None: tmp_path
    )
    recon = tmp_path / "reconcile"
    recon.mkdir()
    (recon / "last.json").write_text(
        json.dumps(
            {
                "generated_at": "2026-06-19T15:37:25+00:00",
                "status": "ok",
                "results": [
                    {
                        "project": "demo",
                        "configured": True,
                        "within_tolerance": True,
                        "provider_delta_usd": 1.0,
                        "langfuse_cost_usd": 1.0,
                        "drift_usd": 0.0,
                    }
                ],
            }
        )
    )

    app = TestClient(create_app(Config(settings=Settings(data_dir=tmp_path))))

    r = app.get("/api/reconcile/last")

    assert r.status_code == 200
    body = r.json()
    assert body["generated_at"] == "2026-06-19T15:37:25+00:00"
    assert body["status"] == "ok"
    assert body["results"][0]["project"] == "demo"


def test_load_config_missing(tmp_path: Path) -> None:
    """Loading a nonexistent file returns defaults (robotsix_config behavior)."""
    config = load_config(tmp_path / "nope.json")
    assert isinstance(config, Config)


def test_load_config_roundtrip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg_file = tmp_path / "config.json"
    cfg_file.write_text(
        json.dumps(
            {
                "projects": [
                    {
                        "name": "A",
                        "public_key": "pk-lf-a",
                        "secret_key": "sk-lf-a",
                        "base_url": "http://lf",
                    }
                ],
                "settings": {"default_window_hours": 48},
            }
        )
    )
    monkeypatch.setenv("ROBOTSIX_CONFIG_FILE", str(cfg_file))
    loaded = load_config()
    assert loaded.settings.default_window_hours == 48


# ---------------------------------------------------------------------------
# _reconcile_loop — schedule + error tolerance
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reconcile_loop_continues_after_failure() -> None:
    """A failing reconcile call does not kill the loop — it sleeps and retries."""
    cfg = Config()

    reconcile_calls = 0

    async def fail_then_pass(_cfg: object, _svc: object) -> None:
        nonlocal reconcile_calls
        reconcile_calls += 1
        if reconcile_calls <= 1:
            raise RuntimeError("reconcile failed")

    sleep_args: list[float] = []
    _real_sleep = asyncio.sleep

    async def fake_sleep(seconds: float) -> None:
        sleep_args.append(seconds)
        await _real_sleep(0)

    with (
        patch("robotsix_cost_monitor.app.asyncio.sleep", fake_sleep),
        patch("robotsix_cost_monitor.app.reconcile_all", fail_then_pass),
    ):
        svc = Mock()
        task = asyncio.create_task(_reconcile_loop(cfg, svc, hours=1))
        while reconcile_calls < 2:
            await _real_sleep(0)
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    assert reconcile_calls >= 2
    assert len(sleep_args) >= 2
    assert sleep_args[0] == 3600.0
    assert sleep_args[1] == 3600.0


@pytest.mark.asyncio
async def test_reconcile_loop_clamps_interval_at_one_hour() -> None:
    """When ``hours`` < 1 the reconcile interval is clamped to 1 hour."""
    cfg = Config()
    svc = Mock()

    sleep_args: list[float] = []
    _real_sleep = asyncio.sleep

    async def fake_sleep(seconds: float) -> None:
        sleep_args.append(seconds)
        await _real_sleep(0)

    with (
        patch("robotsix_cost_monitor.app.asyncio.sleep", fake_sleep),
        patch("robotsix_cost_monitor.app.reconcile_all", AsyncMock()),
    ):
        task = asyncio.create_task(_reconcile_loop(cfg, svc, hours=0.01))
        while len(sleep_args) < 2:
            await _real_sleep(0)
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    for s in sleep_args[:2]:
        assert s == 3600.0


@pytest.mark.asyncio
async def test_reconcile_loop_cancellation() -> None:
    """Cancelling the reconcile loop task raises ``CancelledError``."""
    cfg = Config()
    svc = Mock()

    async def blocked(_cfg: object, _svc: object) -> None:
        await asyncio.Event().wait()

    with (
        patch("robotsix_cost_monitor.app.asyncio.sleep", AsyncMock()),
        patch("robotsix_cost_monitor.app.reconcile_all", blocked),
    ):
        task = asyncio.create_task(_reconcile_loop(cfg, svc, hours=1))
        await asyncio.sleep(0)  # let the loop enter reconcile_all
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task


# ---------------------------------------------------------------------------
# Logging bridge — correlation ID injection
# ---------------------------------------------------------------------------


def test_add_correlation_id_injects_request_id() -> None:
    """``add_correlation_id`` adds ``request_id`` when the asgi-correlation-id
    context variable is set.
    """
    cid = "test-req-123"
    correlation_id.set(cid)
    try:
        event = add_correlation_id(Mock(), "", {})
        assert event["request_id"] == cid
    finally:
        correlation_id.set(None)


def test_add_correlation_id_noop_when_not_set() -> None:
    """``add_correlation_id`` leaves the event dict unchanged when no
    correlation ID is active.
    """
    correlation_id.set(None)
    event = add_correlation_id(Mock(), "", {"message": "hello"})
    assert "request_id" not in event
    assert event["message"] == "hello"


def test_access_log_contains_request_id() -> None:
    """Verify the ``ProcessorFormatter`` bridge injects ``request_id`` into
    formatted JSON output for stdlib log records (e.g. uvicorn access logs).

    The test constructs a ``LogRecord`` manually and formats it through the
    ``ProcessorFormatter`` configured by ``_configure_logging``, simulating
    what happens when a third-party logger (like uvicorn) emits a record.
    """
    cfg = Config()
    create_app(cfg)

    # Steal the ProcessorFormatter from the root logger's configured handler.
    root = logging.getLogger()
    formatter = None
    for h in root.handlers:
        if hasattr(h, "formatter") and h.formatter is not None:
            formatter = h.formatter
            break
    assert formatter is not None, "ProcessorFormatter not found on root handlers"

    # Set a correlation ID so add_correlation_id can pick it up.
    cid = "req-test-456"
    correlation_id.set(cid)
    try:
        # Build a mock LogRecord as if uvicorn.access emitted it.
        record = logging.LogRecord(
            name="uvicorn.access",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="127.0.0.1:0 - GET /health 200",
            args=(),
            exc_info=None,
        )
        formatted = formatter.format(record)
        parsed = json.loads(formatted)
        assert parsed.get("request_id") == cid, f"missing request_id in {parsed}"
    finally:
        correlation_id.set(None)


def test_log_level_debug_shows_debug_events() -> None:
    """When ``LOG_LEVEL=DEBUG``, debug-level structlog events reach the
    stdlib handler (``filter_by_level`` passes them through).
    """
    from robotsix_cost_monitor.config import Settings

    cfg = Config(settings=Settings(log_level="DEBUG"))
    create_app(cfg)

    # ``dictConfig`` replaces root handlers — add a fresh capture handler.
    from _pytest.logging import LogCaptureHandler

    capture = LogCaptureHandler()
    capture.setLevel(logging.DEBUG)
    logging.getLogger().addHandler(capture)
    try:
        test_logger = structlog.get_logger("test_app_debug")
        test_logger.debug("debug-level diagnostic", extra_key="x")

        assert any(r.name == "test_app_debug" for r in capture.records), (
            "DEBUG event not found"
        )
    finally:
        logging.getLogger().removeHandler(capture)


def test_log_level_info_filters_debug_events() -> None:
    """Default ``LOG_LEVEL=INFO`` — ``filter_by_level`` drops debug events
    before they reach stdlib, so no record appears.
    """
    from robotsix_cost_monitor.config import Settings

    cfg = Config(settings=Settings(log_level="INFO"))
    create_app(cfg)

    from _pytest.logging import LogCaptureHandler

    capture = LogCaptureHandler()
    capture.setLevel(logging.DEBUG)
    logging.getLogger().addHandler(capture)
    try:
        test_logger = structlog.get_logger("test_app_info_filter")
        test_logger.debug("this-should-not-appear")

        assert not any(r.name == "test_app_info_filter" for r in capture.records), (
            "DEBUG event leaked despite LOG_LEVEL=INFO"
        )
    finally:
        logging.getLogger().removeHandler(capture)


# ---------------------------------------------------------------------------
# _warm_cache — counter logic
# ---------------------------------------------------------------------------


def _mock_service(*, with_projects: bool = True) -> Mock:
    """Return a mock CostService with controlled ``_project_map``."""
    svc = Mock()
    svc._project_map = {"proj-a": Mock()} if with_projects else {}
    svc.summary = AsyncMock(return_value=[])
    svc.by_model = AsyncMock(return_value=[])
    svc.trend = AsyncMock(return_value=[])
    return svc


@pytest.mark.asyncio
async def test_warm_cache_increments_success_when_all_windows_succeed() -> None:
    """When every window warms without error, ``cache_warm_success`` is incremented."""
    cfg = Config()
    svc = _mock_service()

    before_success = cache_warm_success._value.get()
    before_failure = cache_warm_failure._value.get()

    await _warm_cache(cfg, svc)

    assert cache_warm_success._value.get() == before_success + 1
    assert cache_warm_failure._value.get() == before_failure


@pytest.mark.asyncio
async def test_warm_cache_increments_failure_when_window_raises() -> None:
    """When any window warm-up raises, ``cache_warm_failure`` is incremented."""
    cfg = Config()
    svc = _mock_service()
    svc.by_model.side_effect = RuntimeError("simulated cache fetch failure")

    before_success = cache_warm_success._value.get()
    before_failure = cache_warm_failure._value.get()

    await _warm_cache(cfg, svc)

    assert cache_warm_success._value.get() == before_success
    assert cache_warm_failure._value.get() == before_failure + 1


@pytest.mark.asyncio
async def test_warm_cache_noop_when_no_projects() -> None:
    """When ``_project_map`` is empty the function returns immediately —
    no counters are touched and no service calls are made.
    """
    cfg = Config()
    svc = _mock_service(with_projects=False)

    before_success = cache_warm_success._value.get()
    before_failure = cache_warm_failure._value.get()

    await _warm_cache(cfg, svc)

    assert cache_warm_success._value.get() == before_success
    assert cache_warm_failure._value.get() == before_failure
    svc.summary.assert_not_called()
    svc.by_model.assert_not_called()
    svc.trend.assert_not_called()


# ---------------------------------------------------------------------------
# _cache_refresh_loop — schedule + error tolerance
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cache_refresh_loop_sleeps_and_calls_warm_cache() -> None:
    """The refresh loop sleeps for *interval_s* seconds and then calls
    ``_warm_cache`` on each iteration.
    """
    cfg = Config()
    svc = _mock_service()

    warm_calls = 0
    _real_sleep = asyncio.sleep

    async def fake_warm(_cfg: Config, _svc: object) -> None:
        nonlocal warm_calls
        warm_calls += 1

    sleep_args: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleep_args.append(seconds)
        await _real_sleep(0)

    with (
        patch("robotsix_cost_monitor.app._warm_cache", fake_warm),
        patch("robotsix_cost_monitor.app.asyncio.sleep", fake_sleep),
    ):
        task = asyncio.create_task(_cache_refresh_loop(cfg, svc, interval_s=120))
        while warm_calls < 2:
            await _real_sleep(0)
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    assert warm_calls >= 2
    assert len(sleep_args) >= 2
    assert sleep_args[0] == 120
    assert sleep_args[1] == 120


@pytest.mark.asyncio
async def test_cache_refresh_loop_cancellation() -> None:
    """Cancelling the cache-refresh loop raises ``CancelledError``."""
    cfg = Config()
    svc = Mock()

    async def blocked(_cfg: Config, _svc: object) -> None:
        await asyncio.Event().wait()

    with (
        patch("robotsix_cost_monitor.app.asyncio.sleep", AsyncMock()),
        patch("robotsix_cost_monitor.app._warm_cache", blocked),
    ):
        task = asyncio.create_task(_cache_refresh_loop(cfg, svc, interval_s=60))
        await asyncio.sleep(0)  # let loop enter _warm_cache
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task


# ---------------------------------------------------------------------------
# lifespan — conditional task creation
# ---------------------------------------------------------------------------


def _make_mock_service(*, with_projects: bool = True) -> Mock:
    """Return a mock CostService that carries a non-empty ``_project_map``."""
    svc = Mock()
    svc._project_map = {"proj-a": Mock()} if with_projects else {}
    svc.refresh_projects = AsyncMock()
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
