"""FastAPI app: cost dashboard + reconciliation endpoints, server-rendered UI."""

from __future__ import annotations

import asyncio
import contextlib
import os
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any, cast

import structlog
from fastapi import FastAPI, Request, Response
from fastapi.staticfiles import StaticFiles
from robotsix_http.fastapi import (
    DomainError,
    HealthCheck,
    create_health_router,
    domain_error_handler,
    register_exception_handlers,
)
from robotsix_llmio.logging import setup_structlog

from robotsix_cost_monitor import __version__

from .clients.mill import MillAPIError, MillClient
from .clients.registry import RegistryClient
from .config import Config, data_dir, load_config, resolve_registry_api_key
from .exceptions import CostMonitorError
from .metrics import cache_warm_failure, cache_warm_success
from .reconcile import reconcile_all
from .routes import router
from .routes_config import router as config_router
from .service import CostService

_WEB = Path(__file__).resolve().parent / "web"


async def _cost_monitor_error_handler(request: Request, exc: Exception) -> Response:
    """Render a typed :class:`CostMonitorError` via the canonical envelope.

    Maps the domain exception onto :class:`robotsix_http.fastapi.DomainError`
    so its ``status_code`` / ``error_code`` drive the shared
    ``{"error": {"code", "detail"}}`` envelope built by
    :func:`robotsix_http.fastapi.domain_error_handler`.
    """
    err = cast(CostMonitorError, exc)
    return await domain_error_handler(
        request,
        DomainError(err.detail, code=err.error_code, status_code=err.status_code),
    )


def register_error_handlers(app: FastAPI) -> None:
    """Wire the shared exception-handler suite plus the domain-error adapter.

    Delegates the standard handlers (validation, ``HTTPException``,
    ``ExternalHTTPError``, catch-all) to
    :func:`robotsix_http.fastapi.register_exception_handlers`, then registers
    :func:`_cost_monitor_error_handler` so the typed :class:`CostMonitorError`
    hierarchy keeps its status/code mapping.
    """
    register_exception_handlers(app)
    app.add_exception_handler(CostMonitorError, _cost_monitor_error_handler)


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


async def _stuck_ticket_loop(mill: MillClient, interval_s: int) -> None:
    """Periodically check the mill board for tickets stuck in non-terminal states.

    Each run queries ``GET /tickets`` and logs a warning for every ticket
    whose ``updated_at`` is older than ``stuck_ticket_threshold_hours``.
    When the mill API is unreachable the gauge keeps its previous value —
    a failed check must never reset ``stuck_ticket_count`` to zero,
    otherwise downstream alerting would silently clear during outages.
    """
    from .metrics import stuck_ticket_check_runs, stuck_ticket_count

    while True:
        try:
            stuck = await mill.fetch_stuck_tickets()
            stuck_ticket_check_runs.inc()
            if stuck:
                stuck_ticket_count.set(len(stuck))
                logger.warning(
                    "stuck_ticket_check: %d tickets stuck in non-terminal state",
                    len(stuck),
                    stuck_tickets=[
                        {
                            "id": t.ticket_id,
                            "title": t.title,
                            "state": t.state,
                            "stuck_for_hours": t.stuck_for_hours,
                        }
                        for t in stuck
                    ],
                )
            else:
                stuck_ticket_count.set(0)
                logger.debug("stuck_ticket_check: no stuck tickets found")
        except MillAPIError:
            # The mill board API is unreachable — keep the previous gauge
            # value so alerting does not miss real stuck tickets.  The
            # underlying cause was already logged by MillClient.
            logger.warning(
                "stuck_ticket_check: mill API unavailable; "
                "keeping previous stuck-ticket gauge value"
            )
        except Exception:
            logger.exception("stuck_ticket_check failed")
        await asyncio.sleep(interval_s)


# ---------------------------------------------------------------------------
# Readiness checks (mounted on /readyz via create_health_router)
# ---------------------------------------------------------------------------

#: Paths that bypass HTTP Basic auth: the shared liveness/readiness probes and
#: the Prometheus scrape must never be auth-gated by orchestrators/gateways.
_AUTH_EXEMPT_PATHS = ("/health", "/health/live", "/readyz", "/metrics")


def _readiness_checks(cfg: Config, service: CostService) -> dict[str, HealthCheck]:
    """Build the named readiness checks for the shared health router.

    * ``projects`` — the registry has yielded at least one Langfuse project
      (in-memory; populated by ``refresh_projects`` at startup and on poll).
      Without it every cost endpoint serves empty data.
    * ``data_dir`` — the reconciliation snapshot directory exists and is
      writable (reconcile persists snapshots there before comparing).
    """

    async def _projects() -> None:
        if not service.projects():
            raise RuntimeError("no projects discovered from the registry")

    async def _data_dir() -> None:
        d = data_dir(cfg.settings) / "reconcile"
        # The failure text is served unauthenticated: never echo the path.
        try:
            d.mkdir(parents=True, exist_ok=True)
        except OSError:
            raise RuntimeError("reconcile data directory cannot be created") from None
        if not os.access(d, os.W_OK):
            raise RuntimeError("reconcile data directory is not writable")

    return {"projects": _projects, "data_dir": _data_dir}


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
    # Fleet-standard structlog + stdlib ProcessorFormatter bridge. Includes the
    # uvicorn loggers previously wired by the hand-rolled dictConfig so their
    # records render through the same renderer; correlation-id merging is
    # enabled (bind via robotsix_llmio.logging.bind_correlation_id).
    setup_structlog(
        level=cfg.settings.log_level,
        fmt=cfg.settings.log_format,
        loggers=(
            "robotsix_cost_monitor",
            "uvicorn",
            "uvicorn.error",
            "uvicorn.access",
        ),
        correlation_id=True,
    )
    registry = RegistryClient(
        base_url=cfg.settings.registry_base_url,
        api_key=resolve_registry_api_key(cfg.settings),
    )
    service = CostService(cfg, registry)
    mill = MillClient(cfg.settings)

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
        sti = cfg.settings.stuck_ticket_check_interval_seconds
        if sti > 0 and cfg.settings.mill_base_url:
            logger.info(
                "starting stuck-ticket check loop (every %ss, threshold=%sh)",
                sti,
                cfg.settings.stuck_ticket_threshold_hours,
            )
            tasks.append(asyncio.create_task(_stuck_ticket_loop(mill, sti)))
        try:
            yield
        finally:
            for t in tasks:
                t.cancel()
            for t in tasks:
                with contextlib.suppress(asyncio.CancelledError):
                    await t
            await mill.close()

    app = FastAPI(title="robotsix-cost-monitor", version=__version__, lifespan=lifespan)
    app.state.config = cfg
    app.state.service = service
    app.state.mill = mill

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
    # unconfigured the check is a no-op (local dev / SSH tunnel). The probe
    # paths (/health, /health/live, /readyz) and /metrics are always exempt so
    # the container healthcheck and orchestrator/gateway probes keep working.
    _auth = cfg.settings.auth
    _auth_user = _auth.username
    _auth_pass = _auth.password.get_secret_value()
    if _auth_user and _auth_pass:
        import base64
        import binascii
        import hmac

        from fastapi.responses import PlainTextResponse

        _expected = f"{_auth_user}:{_auth_pass}"

        @app.middleware("http")
        async def _basic_auth(request: Request, call_next: Any) -> Any:
            if request.url.path in _AUTH_EXEMPT_PATHS:
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

    register_error_handlers(app)
    app.include_router(
        create_health_router(
            ready_path="/readyz", checks=_readiness_checks(cfg, service)
        )
    )
    app.include_router(router)
    app.include_router(config_router)

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
