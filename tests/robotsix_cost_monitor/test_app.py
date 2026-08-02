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
    _reconcile_loop,
    add_correlation_id,
    create_app,
)
from robotsix_cost_monitor.config import Config, Settings, load_config


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


def test_summary_unknown_project_returns_empty() -> None:
    """An unknown project slug returns 200 with zero totals (no validation)."""
    r = _empty_app().get("/api/summary?project=nonexistent")
    assert r.status_code == 200
    body = r.json()
    assert body["total_cost"] == 0.0
    assert body["projects"] == []


def test_summary_project_all_returns_200_when_no_projects() -> None:
    """?project=all is always valid — returns 200 even with zero projects."""
    r = _empty_app().get("/api/summary?project=all")
    assert r.status_code == 200


def test_unknown_project_across_endpoints() -> None:
    """Every project-scoped endpoint returns 200 with empty data for an unknown slug."""
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
        assert r.status_code == 200, f"{ep} returned {r.status_code}"


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
