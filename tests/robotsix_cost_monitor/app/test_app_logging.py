"""App logging bridge, correlation-ID injection and log-level tests."""

# mypy: disable-error-code="arg-type"

from __future__ import annotations

import json
import logging

import structlog
from robotsix_llmio.logging import bind_correlation_id

from robotsix_cost_monitor.app import (
    create_app,
)
from robotsix_cost_monitor.config import Config

# ---------------------------------------------------------------------------
# Logging bridge — correlation ID injection
# ---------------------------------------------------------------------------


def test_access_log_contains_correlation_id() -> None:
    """Verify the ``robotsix_llmio.setup_structlog`` bridge renders a bound
    correlation id into formatted JSON output for foreign stdlib log records
    (e.g. uvicorn access logs).

    The test constructs a ``LogRecord`` manually and formats it through the
    ``ProcessorFormatter`` wired onto the root logger by ``create_app`` (via
    ``setup_structlog(correlation_id=True)``), simulating what happens when a
    third-party logger (like uvicorn) emits a record.
    """
    cfg = Config()
    create_app(cfg)

    # Steal the structlog ProcessorFormatter from the root logger's bridge
    # handler (ignore any handler pytest may have attached to the root logger).
    root = logging.getLogger()
    formatter = None
    for h in root.handlers:
        if isinstance(h.formatter, structlog.stdlib.ProcessorFormatter):
            formatter = h.formatter
            break
    assert formatter is not None, "ProcessorFormatter not found on root handlers"

    # Bind a correlation id so the contextvars merge processor picks it up.
    cid = "req-test-456"
    bind_correlation_id(cid)
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
        assert parsed.get("correlation_id") == cid, (
            f"missing correlation_id in {parsed}"
        )
    finally:
        bind_correlation_id(None)


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
