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
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from robotsix_http import ExternalHTTPError

from .aggregations import BackendKind
from .clients.mill import MillAPIError, MillClient
from .config import Config
from .exceptions import CostMonitorError
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


#: Hard ceiling on a requested window.  Every extra hour is more traces fetched
#: from Langfuse and held in the per-window cache, and ``hours`` is client
#: supplied — so it is clamped rather than trusted.  Matches the largest
#: dashboard preset (one week).
MAX_WINDOW_HOURS = 168


def _window(hours: int, config: Config) -> int:
    """Resolve the effective window: fall back to the default, clamp to the max."""
    return min(hours or config.settings.default_window_hours, MAX_WINDOW_HOURS)


def resolve_project(
    project: str = Query("all"), cfg: Config = Depends(get_config)
) -> str:
    """Validate and return the project slug query parameter."""
    return project


def resolve_hours(
    hours: int = Query(0, ge=0, le=MAX_WINDOW_HOURS), cfg: Config = Depends(get_config)
) -> int:
    """Return *hours* (clamped to :data:`MAX_WINDOW_HOURS`), or the config default."""
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
def health() -> dict[str, Any]:
    """GET /health — health check returning status."""
    return {"status": "ok"}


@router.get("/readyz")
def readyz() -> dict[str, Any]:
    """GET /readyz — readiness probe returning status."""
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Chat skill (robotsix-chat agent access point)
# ---------------------------------------------------------------------------

_CHAT_SKILL = """\
# robotsix-cost-monitor — Chat Agent Skill

## Base URL

```
http://cost-monitor:8080
```

## Authentication

HTTP Basic auth **may** be required (configured at deploy time — ask the
operator for credentials).  All endpoints return 401 when auth is enabled
and no valid credentials are supplied.  `/health` is always exempt.

## Read endpoints

All read endpoints accept an optional `?project=<scope>` query parameter
(default `all`) and an optional `?hours=<n>` window (default 168 h, capped
at 168).

`<scope>` resolves at either level:

- a **component id** (e.g. `chat`) — every Langfuse project that component
  owns, aggregated;
- a **project slug** (e.g. `robotsix-chat-cognee`) — that one LLM function.

A component owns one project per LLM function, so `chat` covers both
`robotsix-chat` and `robotsix-chat-cognee`.  Components and their projects
are discovered from the central-deploy registry — anything with a Langfuse
config is monitored automatically, so do not assume a fixed list; call
`GET /api/components` to see what exists right now.

An unmatched `<scope>` (stale or mistyped slug) returns `404` with error
code `PROJECT_NOT_FOUND` — distinct from a valid-but-empty project and from
`?project=all` which always returns `200`.

### Cost summaries

| Endpoint | Description |
|---|---|
| `GET /api/summary` | Cost summary by project & component. Optional `?backend=`. |
| `GET /api/components` | Discovered components and the projects each owns. |
| `GET /api/projects` | All discovered projects (name + slug + owning component). |

### Per-agent / per-model breakdowns

| Endpoint | Description |
|---|---|
| `GET /api/by-agent` | Cost breakdown by agent name. Optional `?backend=`. |
| `GET /api/by-model` | Cost breakdown by model. |

### Trends

| Endpoint | Description |
|---|---|
| `GET /api/trend` | Cost trend series bucketed by time. Optional `?buckets=`. |
| `GET /api/backend-trend` | Cost trend per backend. Optional `?backend=`. |

### Highlights & reconciliation

| Endpoint | Description |
|---|---|
| `GET /api/highlights` | Most expensive trace and session. Optional `?backend=`. |
| `GET /api/reconcile` | Reconcile OpenRouter usage against Langfuse traced costs. |
| `GET /api/reconcile/last` | Most recent reconciliation result. |

### Health

| Endpoint | Description |
|---|---|
| `GET /health` | Health check (status + project names). Always unauthenticated. |
| `GET /readyz` | Readiness probe (dependency checks). Always unauthenticated. |

## Safety

**Mutating endpoints** — these change server state (invalidate caches).
The chat agent MUST ask for explicit operator confirmation before
calling any of them:

| Endpoint | What it does |
|---|---|
| `POST /api/refresh` | Invalidate all caches; next request fetches fresh data. |

All read endpoints (`GET`) are safe and require no confirmation.
"""


@router.get("/chat-skill", response_class=PlainTextResponse)
def chat_skill() -> str:
    """GET /chat-skill — robotsix-chat agent skill document (Markdown)."""
    return _CHAT_SKILL


@router.get("/api/projects")
async def projects(
    service: CostService = Depends(get_service),
) -> list[dict[str, str]]:
    """GET /api/projects — list all discovered projects with name and slug."""
    return [
        {"name": p.name, "slug": p.slug, "component": p.component_id}
        for p in service.projects()
    ]


@router.get("/api/components")
async def components(
    service: CostService = Depends(get_service),
) -> list[dict[str, Any]]:
    """GET /api/components — discovered components and the projects they own.

    Drives the dashboard's selector.  Everything here comes from registry
    discovery, so a newly onboarded component with a Langfuse config appears
    without any change to this service.
    """
    return [
        {
            "component": component_id,
            "projects": [
                {
                    "name": p.name,
                    "slug": p.slug,
                    "reconcilable": bool(p.openrouter_key),
                }
                for p in projects_
            ],
        }
        for component_id, projects_ in service.components().items()
    ]


@router.get("/api/summary")
async def summary(
    backend: str = Query("all"),
    pw: ProjectWindow = Depends(project_window),
    service: CostService = Depends(get_service),
) -> dict[str, Any]:
    """GET /api/summary — total cost and per-project totals for the window."""
    result = await service.summary(pw.project, pw.hours, backend)
    lu = service.last_updated
    if lu is not None:
        result["last_updated"] = lu.isoformat()
    return result


@router.post("/api/refresh")
async def refresh_cache(
    service: CostService = Depends(get_service),
) -> dict[str, Any]:
    """POST /api/refresh — invalidate all caches and force a fresh fetch.

    The next dashboard request will block on a fresh Langfuse fetch (cold
    start), then subsequent requests within the TTL will be served from
    cache with stale-while-revalidate background refresh.
    """
    service.invalidate_all()
    return {
        "status": "ok",
        "message": "Cache invalidated — next request will fetch fresh data.",
    }


@router.get("/api/by-agent")
async def by_agent(
    backend: str = Query("all"),
    pw: ProjectWindow = Depends(project_window),
    service: CostService = Depends(get_service),
) -> list[dict[str, Any]]:
    """GET /api/by-agent — cost breakdown by agent name for a project and window."""
    return await service.by_agent(pw.project, pw.hours, backend)


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
    backend: str = Query("all"),
    pw: ProjectWindow = Depends(project_window),
    service: CostService = Depends(get_service),
) -> dict[str, Any]:
    """GET /api/highlights — most expensive trace and session for the window.

    Accepts an optional ``backend`` query parameter to filter results to
    a specific backend (e.g. ``openrouter``).  Defaults to ``all``.
    """
    return await service.highlights(pw.project, pw.hours, backend)


@router.get("/api/reconcile")
async def reconcile(
    project: str = Query("all"),
    cfg: Config = Depends(get_config),
    service: CostService = Depends(get_service),
) -> list[dict[str, Any]]:
    """GET /api/reconcile — reconcile OpenRouter usage against Langfuse traced costs."""
    if project == "all":
        out = await reconcile_all(cfg, service)
        return cast("list[dict[str, Any]]", out["results"])
    targets = service._projects(project)
    return [await reconcile_project(p, cfg.settings) for p in targets]


@router.get("/api/reconcile/last")
def reconcile_last(cfg: Config = Depends(get_config)) -> dict[str, Any]:
    """GET /api/reconcile/last — return the most recent reconciliation result."""
    return load_last_reconcile(cfg.settings)


@router.get("/api/stuck-tickets")
async def stuck_tickets(request: Request) -> list[dict[str, Any]]:
    """GET /api/stuck-tickets — return tickets stuck in non-terminal states.

    Fetches fresh results from the mill board on every call.  Returns an
    empty list when stuck-ticket detection is disabled (no mill_base_url
    or stuck_ticket_threshold_hours = 0).  Returns 503 when the mill
    board API is unreachable — the caller must not treat that as "no
    stuck tickets".
    """
    mill: MillClient = request.app.state.mill
    try:
        stuck = await mill.fetch_stuck_tickets()
    except MillAPIError:
        raise HTTPException(
            status_code=503,
            detail="mill board API unavailable; stuck-ticket state unknown",
        ) from None
    return [
        {
            "ticket_id": t.ticket_id,
            "title": t.title,
            "state": t.state,
            "kind": t.kind,
            "source": t.source,
            "created_at": t.created_at,
            "updated_at": t.updated_at,
            "stuck_for_hours": t.stuck_for_hours,
        }
        for t in stuck
    ]


@router.get("/", response_class=HTMLResponse)
def index() -> str:
    """GET / — serve the main dashboard HTML page."""
    return (_WEB / "index.html").read_text()


@router.get("/settings", response_class=HTMLResponse)
def settings_page() -> str:
    """GET /settings — serve the settings page (shared config panel)."""
    return (_WEB / "settings.html").read_text()
