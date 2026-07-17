"""FastAPI app: cost dashboard + reconciliation endpoints, server-rendered UI."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import logging.config
import os
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import structlog
from asgi_correlation_id import correlation_id
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from robotsix_cost_monitor import __version__

from .analyst import (
    load_proposals,
    load_targeted_analysis,
    run_analyst,
    run_stage_analyst,
    run_ticket_analyst,
)
from .config import Config, load_config
from .reconcile import reconcile_all
from .routes import register_exception_handlers, router
from .service import CostService

_WEB = Path(__file__).resolve().parent / "web"


def add_correlation_id(
    _logger: logging.Logger, _method_name: str, event_dict: dict[str, object]
) -> dict[str, object]:
    """Inject the asgi-correlation-id correlation ID into structlog events."""
    if request_id := correlation_id.get(None):
        event_dict["request_id"] = request_id
    return event_dict


def _configure_logging() -> None:
    """Configure structlog with ProcessorFormatter bridge + request-ID enrichment.

    Shared processors are used by structlog's own chain AND by the
    ``ProcessorFormatter`` foreign_pre_chain so that third-party / Uvicorn
    logs also receive correlation IDs, timestamps, and log levels.
    """
    fmt = os.environ.get("LOG_FORMAT", "json" if os.environ.get("CI") else "console")
    log_level = os.environ.get("LOG_LEVEL", "INFO").upper()

    shared_processors = [
        add_correlation_id,
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
    ]

    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            *shared_processors,  # type: ignore[list-item]
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    json_renderer = structlog.processors.JSONRenderer()
    console_renderer = structlog.dev.ConsoleRenderer()

    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "structlog": {
                    "()": structlog.stdlib.ProcessorFormatter,
                    "processors": [
                        structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                        json_renderer if fmt == "json" else console_renderer,
                    ],
                    "foreign_pre_chain": shared_processors,
                },
            },
            "handlers": {
                "default": {
                    "level": log_level,
                    "class": "logging.StreamHandler",
                    "formatter": "structlog",
                    "stream": "ext://sys.stdout",
                },
            },
            "loggers": {
                "": {
                    "handlers": ["default"],
                    "level": log_level,
                    "propagate": True,
                },
                "uvicorn": {
                    "handlers": ["default"],
                    "level": log_level,
                    "propagate": False,
                },
                "uvicorn.error": {"level": log_level},
                "uvicorn.access": {
                    "handlers": ["default"],
                    "level": "WARNING" if fmt == "console" else log_level,
                    "propagate": False,
                },
            },
        }
    )


logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Scheduler helpers (tested directly — keep in this module)
# ---------------------------------------------------------------------------


def _parse_iso(value: Any) -> datetime | None:
    """Parse a stored ISO ``generated_at`` to an aware UTC datetime, or None."""
    if not isinstance(value, str) or not value:
        return None
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def _last_analyst_run() -> datetime | None:
    """Return the most recent analyst run timestamp.

    The most recent ``generated_at`` across the persisted fleet/ticket/stage
    analyses, or ``None`` when none has run yet.

    Used to resume the analyst cadence across process restarts: the dashboard's
    scheduler lives in-process and is redeployed often (Watchtower), so a timer
    that simply sleeps a full interval on every start would keep resetting and
    the daily analysis would rarely fire.
    """
    stamps = (
        load_proposals().get("generated_at"),
        load_targeted_analysis("ticket").get("generated_at"),
        load_targeted_analysis("stage").get("generated_at"),
    )
    runs = [dt for dt in (_parse_iso(s) for s in stamps) if dt is not None]
    return max(runs) if runs else None


def _initial_analyst_delay(
    interval: float, last_run: datetime | None, now: datetime
) -> float:
    """Calculate seconds to wait before the first scheduled analysis.

    ``0`` when a full *interval* has already elapsed since *last_run* (or nothing
    has ever run), else only the remaining time — so the ~daily cadence is stable
    regardless of how often the container restarts. A *last_run* in the future
    (clock skew) falls back to a full interval rather than running immediately.
    """
    if last_run is None:
        return 0.0
    elapsed = (now - last_run).total_seconds()
    if elapsed < 0:
        return interval
    return max(0.0, interval - elapsed)


async def _analyst_loop(cfg: Config, service: CostService, hours: float) -> None:
    """Run all analyses on a schedule until cancelled.

    Analyses: fleet + most-costly ticket + most-costly stage, every *hours*
    hours. The first delay is derived from the last persisted run (not a fresh
    full sleep) so frequent redeploys don't starve the schedule: if a full
    interval has already elapsed it runs at once, otherwise it waits only the
    remainder.
    """
    interval = max(1.0, hours) * 3600
    analyses = (
        ("fleet", run_analyst),
        ("ticket", run_ticket_analyst),
        ("stage", run_stage_analyst),
    )
    delay = _initial_analyst_delay(interval, _last_analyst_run(), datetime.now(UTC))
    logger.info(
        "analyst scheduler: first run in %.0fs (interval %.0fs)", delay, interval
    )
    while True:
        await asyncio.sleep(delay)
        for label, fn in analyses:
            try:
                await fn(cfg, service)
            except Exception:
                logger.exception("scheduled %s analysis failed", label)
        delay = interval


async def _reconcile_loop(cfg: Config, hours: float) -> None:
    """Reconcile all projects on a schedule until cancelled.

    Runs every *hours* hours (with an initial run so the banner has data
    immediately).
    """
    interval = max(1.0, hours) * 3600
    while True:
        try:
            await reconcile_all(cfg)
        except Exception:
            logger.exception("scheduled reconcile failed")
        await asyncio.sleep(interval)


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------


def create_app(config: Config | None = None) -> FastAPI:
    """Assemble the FastAPI application.

    Loads the project :class:`~robotsix_cost_monitor.config.Config` (when *config*
    is ``None``, reads from the path given by ``COST_MONITOR_CONFIG``), builds a
    :class:`~robotsix_cost_monitor.service.CostService`, wires the lifespan
    (analyst and reconciliation background loops), mounts the route handlers from
    :mod:`robotsix_cost_monitor.routes`, registers exception handlers, and serves
    the static web assets.
    """
    _configure_logging()

    cfg = config or load_config()
    service = CostService(cfg)

    @contextlib.asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        """ASGI lifespan: set up / tear down application state."""
        tasks: list[asyncio.Task[None]] = []
        a = cfg.settings.analyst
        if a.enabled and a.schedule_hours > 0:
            logger.info("starting analyst scheduler (every %sh)", a.schedule_hours)
            tasks.append(
                asyncio.create_task(_analyst_loop(cfg, service, a.schedule_hours))
            )
        rh = cfg.settings.reconcile_schedule_hours
        if rh > 0 and cfg.projects:
            logger.info("starting reconcile scheduler (every %sh)", rh)
            tasks.append(asyncio.create_task(_reconcile_loop(cfg, rh)))
        try:
            yield
        finally:
            for t in tasks:
                t.cancel()
            for t in tasks:
                with contextlib.suppress(asyncio.CancelledError):
                    await t

    app = FastAPI(title="robotsix-cost-monitor", version=__version__, lifespan=lifespan)
    app.state.config = cfg
    app.state.service = service

    from asgi_correlation_id import CorrelationIdMiddleware

    app.add_middleware(CorrelationIdMiddleware)

    register_exception_handlers(app)
    app.include_router(router)

    if (_WEB / "static").is_dir():
        app.mount("/static", StaticFiles(directory=_WEB / "static"), name="static")

    return app
