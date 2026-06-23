"""HTTP route handlers (APIRouter) and exception handlers.

All route handlers that were previously inline inside ``create_app`` now live
here, using FastAPI dependency injection to obtain ``Config`` and ``CostService``
from ``app.state``.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, cast

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse

from .analyst import (
    build_digest,
    load_proposals,
    load_targeted_analysis,
    run_analyst,
    run_stage_analyst,
    run_ticket_analyst,
)
from .config import Config
from .reconcile import load_last_reconcile, reconcile_all, reconcile_project
from .service import CostService

_WEB = Path(__file__).resolve().parent / "web"
logger = logging.getLogger(__name__)

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


def _require_project(project: str, cfg: Config) -> None:
    if project != "all" and not cfg.project(project):
        raise HTTPException(status_code=404, detail=f"Unknown project slug: {project}")


def _window(hours: int, config: Config) -> int:
    return hours or config.settings.default_window_hours


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
    """Wire the three exception handlers onto *app*."""
    app.add_exception_handler(RequestValidationError, validation_handler)  # type: ignore[arg-type]
    app.add_exception_handler(HTTPException, http_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, unhandled_handler)


# ---------------------------------------------------------------------------
# Route handlers (was inside create_app)
# ---------------------------------------------------------------------------


@router.get("/health")
def health(cfg: Config = Depends(get_config)) -> dict[str, Any]:
    return {"status": "ok", "projects": [p.name for p in cfg.projects]}


@router.get("/api/projects")
def projects(cfg: Config = Depends(get_config)) -> list[dict[str, str]]:
    return [{"name": p.name, "slug": p.slug} for p in cfg.projects]


@router.get("/api/summary")
async def summary(
    project: str = Query("all"),
    hours: int = Query(0, ge=0),
    cfg: Config = Depends(get_config),
    service: CostService = Depends(get_service),
) -> dict[str, Any]:
    h = _window(hours, cfg)
    _require_project(project, cfg)
    return await service.summary(project, h)


@router.get("/api/by-agent")
async def by_agent(
    project: str = Query("all"),
    hours: int = Query(0, ge=0),
    backend: str = Query("all"),
    cfg: Config = Depends(get_config),
    service: CostService = Depends(get_service),
) -> list[dict[str, Any]]:
    h = _window(hours, cfg)
    _require_project(project, cfg)
    return await service.by_agent(project, h, backend)


@router.get("/api/by-model")
async def by_model(
    project: str = Query("all"),
    hours: int = Query(0, ge=0),
    cfg: Config = Depends(get_config),
    service: CostService = Depends(get_service),
) -> list[dict[str, Any]]:
    h = _window(hours, cfg)
    _require_project(project, cfg)
    return await service.by_model(project, h)


@router.get("/api/backend-trend")
async def backend_trend(
    project: str = Query("all"),
    hours: int = Query(0, ge=0),
    backend: str = Query("all"),
    cfg: Config = Depends(get_config),
    service: CostService = Depends(get_service),
) -> list[dict[str, Any]]:
    h = _window(hours, cfg)
    _require_project(project, cfg)
    return await service.backend_trend(project, h, backend)


@router.get("/api/trend")
async def trend(
    project: str = Query("all"),
    hours: int = Query(0, ge=0),
    buckets: int = Query(48, ge=1, le=200),
    cfg: Config = Depends(get_config),
    service: CostService = Depends(get_service),
) -> list[dict[str, Any]]:
    h = _window(hours, cfg)
    _require_project(project, cfg)
    return await service.trend(project, h, buckets)


@router.get("/api/highlights")
async def highlights(
    project: str = Query("all"),
    hours: int = Query(0, ge=0),
    cfg: Config = Depends(get_config),
    service: CostService = Depends(get_service),
) -> dict[str, Any]:
    h = _window(hours, cfg)
    _require_project(project, cfg)
    return await service.highlights(project, h)


@router.get("/api/reconcile")
async def reconcile(
    project: str = Query("all"),
    cfg: Config = Depends(get_config),
) -> list[dict[str, Any]]:
    # Running all projects persists last.json (banner + scheduler share it);
    # a single-project run is a transient check that doesn't overwrite it.
    _require_project(project, cfg)
    if project == "all":
        out = await reconcile_all(cfg)
        return cast("list[dict[str, Any]]", out["results"])
    targets = [p for p in cfg.projects if p.slug == project]
    return [await reconcile_project(p, cfg.settings) for p in targets]


@router.get("/api/reconcile/last")
def reconcile_last() -> dict[str, Any]:
    return load_last_reconcile()


@router.get("/api/analyst/digest")
async def analyst_digest(
    hours: int = Query(0, ge=0),
    cfg: Config = Depends(get_config),
    service: CostService = Depends(get_service),
) -> dict[str, Any]:
    h = hours or cfg.settings.analyst.window_hours
    return await build_digest(service, h, cfg)


@router.get("/api/analyst/proposals")
def analyst_proposals() -> dict[str, Any]:
    return load_proposals()


@router.post("/api/analyst/run")
async def analyst_run(
    cfg: Config = Depends(get_config),
    service: CostService = Depends(get_service),
) -> dict[str, Any]:
    return await run_analyst(cfg, service)


@router.get("/api/analyst/ticket")
def analyst_ticket() -> dict[str, Any]:
    return load_targeted_analysis("ticket")


@router.post("/api/analyst/ticket-run")
async def analyst_ticket_run(
    cfg: Config = Depends(get_config),
    service: CostService = Depends(get_service),
) -> dict[str, Any]:
    return await run_ticket_analyst(cfg, service)


@router.get("/api/analyst/stage")
def analyst_stage() -> dict[str, Any]:
    return load_targeted_analysis("stage")


@router.post("/api/analyst/stage-run")
async def analyst_stage_run(
    cfg: Config = Depends(get_config),
    service: CostService = Depends(get_service),
) -> dict[str, Any]:
    return await run_stage_analyst(cfg, service)


@router.get("/", response_class=HTMLResponse)
def index() -> str:
    return (_WEB / "index.html").read_text()


@router.get("/analyst", response_class=HTMLResponse)
def analyst_page() -> str:
    return (_WEB / "analyst.html").read_text()
