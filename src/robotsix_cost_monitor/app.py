"""FastAPI app: cost dashboard + reconciliation endpoints, server-rendered UI."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import logging.config
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import structlog
from asgi_correlation_id import correlation_id
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from robotsix_cost_monitor import __version__

from .clients.registry import RegistryClient
from .config import Config, load_config
from .metrics import cache_warm_failure, cache_warm_success
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


def _configure_logging(log_format: str = "json", log_level: str = "INFO") -> None:
    """Configure structlog with ProcessorFormatter bridge + request-ID enrichment.

    Shared processors are used by structlog's own chain AND by the
    ``ProcessorFormatter`` foreign_pre_chain so that third-party / Uvicorn
    logs also receive correlation IDs, timestamps, and log levels.
    """
    fmt = log_format
    log_level = log_level.upper()

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


async def _reconcile_loop(cfg: Config, service: CostService, hours: float) -> None:
    """Reconcile all projects on a schedule until cancelled.

    Runs every *hours* hours (with an initial run so the banner has data
    immediately).
    """
    interval = max(1.0, hours) * 3600
    while True:
        try:
            await reconcile_all(cfg, service)
        except Exception:
            logger.exception("scheduled reconcile failed")
        await asyncio.sleep(interval)


async def _warm_cache(cfg: Config, service: CostService) -> None:
    """Pre-fetch aggregates for all dashboard window presets on startup.

    Every window-selector option is warmed so window switches are near-instant
    from the first page load.  Best-effort — failures are logged and discarded.
    """
    if not service._project_map:
        return
    from .service import DASHBOARD_WINDOW_PRESETS

    logger.info(
        "warming dashboard cache (%d projects, %d windows)",
        len(service._project_map),
        len(DASHBOARD_WINDOW_PRESETS),
    )
    failed = False
    for h in DASHBOARD_WINDOW_PRESETS:
        try:
            # summary() touches model_usage + trace_count per project
            await service.summary("all", h)
            # by_model() touches model_usage per project
            await service.by_model("all", h)
            # trend() touches traces per project
            await service.trend("all", h)
        except Exception:
            logger.exception("dashboard cache warm-up failed for window=%sh", h)
            failed = True
    if failed:
        cache_warm_failure.inc()
    else:
        cache_warm_success.inc()
    logger.info("dashboard cache warm complete")


async def _cache_refresh_loop(
    cfg: Config, service: CostService, interval_s: int
) -> None:
    """Periodically re-fetch dashboard aggregates so the cache stays warm.

    Runs forever until cancelled; sleeps *interval_s* between refreshes.
    """
    while True:
        await asyncio.sleep(interval_s)
        await _warm_cache(cfg, service)


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------


def create_app(config: Config | None = None) -> FastAPI:
    """Assemble the FastAPI application.

    Loads the project :class:`~robotsix_cost_monitor.config.Config` (when *config*
    is ``None``, reads from the path given by ``ROBOTSIX_CONFIG_FILE``), builds a
    :class:`~robotsix_cost_monitor.service.CostService`, wires the lifespan
    (reconciliation background loop), mounts the route handlers from
    :mod:`robotsix_cost_monitor.routes`, registers exception handlers, and serves
    the static web assets.
    """
    cfg = config or load_config()
    _configure_logging(cfg.settings.log_format, cfg.settings.log_level)
    registry = RegistryClient(
        base_url=cfg.settings.registry_base_url,
        api_key=cfg.settings.registry_api_key.get_secret_value(),
    )
    service = CostService(cfg, registry)

    @contextlib.asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        """ASGI lifespan: set up / tear down application state."""
        await service.refresh_projects()
        tasks: list[asyncio.Task[None]] = []
        rh = cfg.settings.reconcile_schedule_hours
        if rh > 0 and service._project_map:
            logger.info("starting reconcile scheduler (every %sh)", rh)
            tasks.append(asyncio.create_task(_reconcile_loop(cfg, service, rh)))
        # Periodic dashboard cache warming (keeps aggregates precomputed).
        di = cfg.settings.dashboard_refresh_interval_seconds
        if di > 0 and service._project_map:
            logger.info("starting dashboard cache-refresh loop (every %ss)", di)
            tasks.append(asyncio.create_task(_cache_refresh_loop(cfg, service, di)))
        # One-shot startup cache warm so the first page load is fast.
        tasks.append(asyncio.create_task(_warm_cache(cfg, service)))
        rpi = cfg.settings.registry_poll_interval_seconds
        if rpi > 0:

            async def _registry_poll_loop() -> None:
                while True:
                    await asyncio.sleep(rpi)
                    await service.refresh_projects()

            tasks.append(asyncio.create_task(_registry_poll_loop()))
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

    from prometheus_fastapi_instrumentator import Instrumentator

    Instrumentator().instrument(app).expose(
        app, endpoint="/metrics", include_in_schema=False
    )

    from asgi_correlation_id import CorrelationIdMiddleware

    app.add_middleware(CorrelationIdMiddleware)

    from secure import (
        ContentSecurityPolicy,
        PermissionsPolicy,
        ReferrerPolicy,
        Secure,
        Server,
        StrictTransportSecurity,
        XContentTypeOptions,
        XFrameOptions,
    )
    from secure.middleware import SecureASGIMiddleware

    csp = (
        ContentSecurityPolicy()
        .default_src("'self'")
        .script_src("'self'", "'unsafe-inline'")
        .style_src("'self'", "'unsafe-inline'")
        .img_src("'self'", "data:")
        .object_src("'none'")
        .base_uri("'self'")
        .form_action("'self'")
    )
    secure_headers = Secure(
        csp=csp,
        server=Server().set(""),
        hsts=StrictTransportSecurity().max_age(31536000).include_subdomains(),
        referrer=ReferrerPolicy().strict_origin_when_cross_origin(),
        xcto=XContentTypeOptions().nosniff(),
        xfo=XFrameOptions().sameorigin(),
        permissions=PermissionsPolicy().geolocation().microphone().camera(),
    )
    app.add_middleware(SecureASGIMiddleware, secure=secure_headers)

    # HTTP Basic auth — the dashboard has no other access control, so it must
    # be protected whenever it is reachable beyond loopback (e.g. via the
    # central-deploy gateway, which is an unauthenticated reverse proxy). When
    # unconfigured the check is a no-op (local dev / SSH tunnel). /health is
    # always exempt so the container healthcheck keeps working.
    _auth = cfg.settings.auth
    _auth_user = _auth.username
    _auth_pass = _auth.password.get_secret_value()
    if _auth_user and _auth_pass:
        import base64
        import binascii
        import hmac

        from fastapi import Request
        from fastapi.responses import PlainTextResponse

        _expected = f"{_auth_user}:{_auth_pass}"

        @app.middleware("http")
        async def _basic_auth(request: Request, call_next: Any) -> Any:
            if request.url.path in ("/health", "/metrics"):
                return await call_next(request)
            header = request.headers.get("authorization", "")
            if header.startswith("Basic "):
                try:
                    decoded = base64.b64decode(header[6:]).decode("utf-8")
                except binascii.Error, UnicodeDecodeError:
                    decoded = ""
                # Constant-time compare to avoid leaking the credential.
                if hmac.compare_digest(decoded, _expected):
                    return await call_next(request)
            return PlainTextResponse(
                "Unauthorized",
                status_code=401,
                headers={"WWW-Authenticate": 'Basic realm="cost-monitor"'},
            )

        logger.info("HTTP Basic auth enabled for the dashboard")
    else:
        logger.warning(
            "dashboard auth is DISABLED (settings.auth.username/password unset) "
            "— safe only on loopback; do not expose via the gateway"
        )

    register_exception_handlers(app)
    app.include_router(router)

    if (_WEB / "static").is_dir():
        app.mount("/static", StaticFiles(directory=_WEB / "static"), name="static")

    # robotsix-ui shared base CSS (compiled dist/style.css from @robotsix/ui)
    _ui_dist = Path("node_modules/@robotsix/ui/dist")
    if _ui_dist.is_dir():
        app.mount(
            "/static/robotsix-ui",
            StaticFiles(directory=_ui_dist),
            name="robotsix-ui",
        )

    return app
