"""HTTP route handlers (APIRouter) and exception handlers.

All route handlers that were previously inline inside ``create_app`` now live
here, using FastAPI dependency injection to obtain ``Config`` and ``CostService``
from ``app.state``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, NamedTuple, cast

import structlog
from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse
from robotsix_http import ExternalHTTPError

from .aggregations import BackendKind
from .analyst import (
    AnalystKind,
    build_digest,
    load_proposals,
    load_targeted_analysis,
    run_analyst,
    run_stage_analyst,
    run_ticket_analyst,
)
from .config import Config
from .exceptions import CostMonitorError, ProjectNotFoundError
from .reconcile import load_last_reconcile, reconcile_all, reconcile_project
from .service import CostService

_WEB = Path(__file__).resolve().parent / "web"
logger = structlog.get_logger(__name__)

router = APIRouter()

# ---------------------------------------------------------------------------
# Dependency providers
# ---------------------------------------------------------------------------


def get_config(request: Request) -> Config:
    """Return the :class:`Config` stored on ``app.state`` during startup."""
    return request.app.state.config  # type: ignore[no-any-return]


def get_service(request: Request) -> CostService:
    """Return the :class:`CostService` stored on ``app.state`` during startup."""
    return request.app.state.service  # type: ignore[no-any-return]


# ---------------------------------------------------------------------------
# Route helpers (was in app.py)
# ---------------------------------------------------------------------------


class ProjectWindow(NamedTuple):
    """Resolved project slug and effective window hours for a request."""

    project: str
    hours: int


def _require_project(project: str, cfg: Config) -> None:
    if project != "all" and not cfg.project(project):
        raise ProjectNotFoundError(f"Unknown project slug: {project}")


def _window(hours: int, config: Config) -> int:
    return hours or config.settings.default_window_hours


def resolve_project(
    project: str = Query("all"), cfg: Config = Depends(get_config)
) -> str:
    """Validate *project* slug exists in config; raise 404 if not."""
    _require_project(project, cfg)
    return project


def resolve_hours(
    hours: int = Query(0, ge=0), cfg: Config = Depends(get_config)
) -> int:
    """Return *hours* or the config default if zero."""
    return _window(hours, cfg)


def project_window(
    project: str = Depends(resolve_project),
    hours: int = Depends(resolve_hours),
) -> ProjectWindow:
    """Composite dependency: validated project slug + resolved window hours."""
    return ProjectWindow(project=project, hours=hours)


# ---------------------------------------------------------------------------
# Exception handlers
# ---------------------------------------------------------------------------


async def validation_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Return a consistent 422 envelope with field-level errors."""
    errors = [
        {
            "field": " → ".join(str(loc) for loc in e["loc"] if loc != "body"),
            "message": e["msg"],
            "code": e.get("type", "validation_error"),
        }
        for e in exc.errors()
    ]
    return JSONResponse(
        status_code=422,
        content={"error": {"code": "VALIDATION_ERROR", "details": errors}},
    )


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """Wrap HTTPException in a consistent JSON envelope."""
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": "HTTP_ERROR", "detail": exc.detail}},
    )


async def cost_monitor_error_handler(
    request: Request, exc: CostMonitorError
) -> JSONResponse:
    """Return a typed cost-monitor error in the consistent JSON envelope."""
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": exc.error_code, "detail": exc.detail}},
    )


async def external_http_error_handler(
    request: Request, exc: ExternalHTTPError
) -> JSONResponse:
    """Return a typed error for robotsix-http exceptions.

    Derives the error code from the exception type so the response
    envelope matches :func:`cost_monitor_error_handler`.
    """
    from robotsix_http import (
        ExternalAuthError,
        ExternalRateLimitError,
        ExternalServiceError,
    )

    if isinstance(exc, ExternalAuthError):
        code = "EXTERNAL_AUTH_ERROR"
    elif isinstance(exc, ExternalRateLimitError):
        code = "RATE_LIMITED"
    elif isinstance(exc, ExternalServiceError):
        code = "EXTERNAL_SERVICE_ERROR"
    else:
        code = "EXTERNAL_SERVICE_ERROR"
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": code, "detail": str(exc)}},
    )


async def unhandled_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all: log the full traceback, return sanitized 500."""
    logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={
            "error": {"code": "INTERNAL_ERROR", "detail": "Internal Server Error"}
        },
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Wire the exception handlers onto *app*."""
    app.add_exception_handler(RequestValidationError, validation_handler)  # type: ignore[arg-type]
    app.add_exception_handler(HTTPException, http_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(CostMonitorError, cost_monitor_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(ExternalHTTPError, external_http_error_handler)
    app.add_exception_handler(Exception, unhandled_handler)


# ---------------------------------------------------------------------------
# Route handlers (was inside create_app)
# ---------------------------------------------------------------------------


@router.get("/health")
def health(cfg: Config = Depends(get_config)) -> dict[str, Any]:
    """GET /health — health check returning status and project names."""
    return {"status": "ok", "projects": [p.name for p in cfg.projects]}


@router.get("/api/projects")
def projects(cfg: Config = Depends(get_config)) -> list[dict[str, str]]:
    """GET /api/projects — list all configured projects with name and slug."""
    return [{"name": p.name, "slug": p.slug} for p in cfg.projects]


@router.get("/api/summary")
async def summary(
    pw: ProjectWindow = Depends(project_window),
    service: CostService = Depends(get_service),
) -> dict[str, Any]:
    """GET /api/summary — total cost and per-project totals for the window."""
    return await service.summary(pw.project, pw.hours)


@router.get("/api/by-agent")
async def by_agent(
    backend: str = Query("all"),
    pw: ProjectWindow = Depends(project_window),
    service: CostService = Depends(get_service),
) -> list[dict[str, Any]]:
    """GET /api/by-agent — cost breakdown by agent name for a project and window."""
    return await service.by_agent(pw.project, pw.hours, backend)


@router.get("/api/by-agent-segmented")
async def by_agent_segmented(
    pw: ProjectWindow = Depends(project_window),
    service: CostService = Depends(get_service),
) -> dict[str, Any]:
    """GET /api/by-agent-segmented — agent costs segmented by model and backend."""
    return await service.by_agent_segmented(pw.project, pw.hours)


@router.get("/api/by-model")
async def by_model(
    pw: ProjectWindow = Depends(project_window),
    service: CostService = Depends(get_service),
) -> list[dict[str, Any]]:
    """GET /api/by-model — cost breakdown by model for a project and window."""
    return await service.by_model(pw.project, pw.hours)


@router.get("/api/backend-trend")
async def backend_trend(
    backend: str = Query("all"),
    pw: ProjectWindow = Depends(project_window),
    service: CostService = Depends(get_service),
) -> list[dict[str, Any]]:
    """GET /api/backend-trend — cost trend per backend for a project and window."""
    return await service.backend_trend(pw.project, pw.hours, cast(BackendKind, backend))


@router.get("/api/trend")
async def trend(
    buckets: int = Query(48, ge=1, le=200),
    pw: ProjectWindow = Depends(project_window),
    service: CostService = Depends(get_service),
) -> list[dict[str, Any]]:
    """GET /api/trend — cost trend series bucketed by time for a project and window."""
    return await service.trend(pw.project, pw.hours, buckets)


@router.get("/api/highlights")
async def highlights(
    pw: ProjectWindow = Depends(project_window),
    service: CostService = Depends(get_service),
) -> dict[str, Any]:
    """GET /api/highlights — summaries (total, change, top agents) for the window."""
    return await service.highlights(pw.project, pw.hours)


@router.get("/api/reconcile")
async def reconcile(
    project: str = Query("all"),
    cfg: Config = Depends(get_config),
) -> list[dict[str, Any]]:
    """GET /api/reconcile — reconcile OpenRouter usage against Langfuse traced costs."""
    # Running all projects persists last.json (banner + scheduler share it);
    # a single-project run is a transient check that doesn't overwrite it.
    _require_project(project, cfg)
    if project == "all":
        out = await reconcile_all(cfg)
        return cast("list[dict[str, Any]]", out["results"])
    targets = [p for p in cfg.projects if p.slug == project]
    return [await reconcile_project(p, cfg.settings) for p in targets]


@router.get("/api/reconcile/last")
def reconcile_last(cfg: Config = Depends(get_config)) -> dict[str, Any]:
    """GET /api/reconcile/last — return the most recent reconciliation result."""
    return load_last_reconcile(cfg.settings.data_dir)


@router.get("/api/analyst/digest")
async def analyst_digest(
    hours: int = Query(0, ge=0),
    cfg: Config = Depends(get_config),
    service: CostService = Depends(get_service),
) -> dict[str, Any]:
    """GET /api/analyst/digest — build a cost-analysis digest from recent trace data."""
    h = hours or cfg.settings.analyst.window_hours
    return await build_digest(service, h, cfg)


@router.get("/api/analyst/proposals")
def analyst_proposals(cfg: Config = Depends(get_config)) -> dict[str, Any]:
    """GET /api/analyst/proposals — load saved cost-reduction proposals."""
    return load_proposals(cfg.settings.data_dir)


@router.post("/api/analyst/run")
async def analyst_run(
    cfg: Config = Depends(get_config),
    service: CostService = Depends(get_service),
) -> dict[str, Any]:
    """POST /api/analyst/run — trigger a full cost-analyst analysis run."""
    return await run_analyst(cfg, service)


@router.post("/api/analyst/run/{kind}")
async def analyst_run_targeted(
    kind: AnalystKind,
    cfg: Config = Depends(get_config),
    service: CostService = Depends(get_service),
) -> dict[str, Any]:
    """POST /api/analyst/run/{kind} — run a targeted analysis (ticket or stage)."""
    if kind == "ticket":
        return await run_ticket_analyst(cfg, service)
    if kind == "stage":
        return await run_stage_analyst(cfg, service)
    raise HTTPException(status_code=404, detail=f"Unknown analyst kind: {kind}")


@router.get("/api/analyst/{kind}")
def analyst_targeted(kind: AnalystKind, cfg: Config = Depends(get_config)) -> dict[str, Any]:
    """GET /api/analyst/{kind} — load a saved targeted analysis (ticket or stage)."""
    return load_targeted_analysis(kind, cfg.settings.data_dir)


@router.get("/", response_class=HTMLResponse)
def index() -> str:
    """GET / — serve the main dashboard HTML page."""
    return (_WEB / "index.html").read_text()


@router.get("/analyst", response_class=HTMLResponse)
def analyst_page() -> str:
    """GET /analyst — serve the analyst dashboard HTML page."""
    return (_WEB / "analyst.html").read_text()
