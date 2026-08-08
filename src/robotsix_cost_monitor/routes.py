"""HTTP route handlers (APIRouter) and exception handlers.

All route handlers that were previously inline inside ``create_app`` now live
here, using FastAPI dependency injection to obtain ``Config`` and ``CostService``
from ``app.state``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, NamedTuple, cast

import structlog
from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from robotsix_config import (
    InvalidConfigError,
    apply_update,
    current_version,
    mask_secrets,
    read_versions,
    resolve_config_path,
    rollback,
)
from robotsix_http import ExternalHTTPError

from .aggregations import BackendKind
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
| `GET /api/summary` | Total cost, per-project totals, and a per-component rollup. |
| `GET /api/components` | Discovered components and the projects each owns. |
| `GET /api/projects` | All discovered projects (name + slug + owning component). |

### Per-agent / per-model breakdowns

| Endpoint | Description |
|---|---|
| `GET /api/by-agent` | Cost breakdown by agent name. Optional `?backend=`. |
| `GET /api/by-agent-segmented` | Agent costs segmented by model and backend. |
| `GET /api/by-model` | Cost breakdown by model. |

### Trends

| Endpoint | Description |
|---|---|
| `GET /api/trend` | Cost trend series bucketed by time. Optional `?buckets=`. |
| `GET /api/backend-trend` | Cost trend per backend. Optional `?backend=`. |

### Highlights & reconciliation

| Endpoint | Description |
|---|---|
| `GET /api/highlights` | Most expensive trace and session for the window. |
| `GET /api/reconcile` | Reconcile OpenRouter usage against Langfuse traced costs. |
| `GET /api/reconcile/last` | Most recent reconciliation result. |

### Health

| Endpoint | Description |
|---|---|
| `GET /health` | Health check (status + project names). Always unauthenticated. |

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
    pw: ProjectWindow = Depends(project_window),
    service: CostService = Depends(get_service),
) -> dict[str, Any]:
    """GET /api/summary — total cost and per-project totals for the window."""
    result = await service.summary(pw.project, pw.hours)
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


@router.get("/", response_class=HTMLResponse)
def index() -> str:
    """GET / — serve the main dashboard HTML page."""
    return (_WEB / "index.html").read_text()


def _read_config_file() -> dict[str, Any]:
    """Return the raw contents of the component's config file.

    Read from disk rather than dumping ``app.state.config`` so that
    ``GET /config`` reflects what is actually persisted — including any key
    the model would drop — and so it agrees with what ``PUT /config`` merges
    into.
    """
    path = resolve_config_path()
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    return cast("dict[str, Any]", loaded) if isinstance(loaded, dict) else {}


# ---------------------------------------------------------------------------
# Standard config HTTP surface
# ---------------------------------------------------------------------------
# Required of every deployable component by robotsix-standards
# `config-ownership.md`. The deploy plane keeps no copy of these values — it
# reads them from the component — so this surface is how config is inspected
# and changed at runtime, and the `<config>.versions` sidecar beside the
# config file is where its history lives.
#
# All four handlers delegate to `robotsix_config.history`. That is deliberate:
# `PUT /config` has to deep-merge, restore secrets the caller did not really
# resubmit, validate, write, and record — in that order — and reimplementing
# that sequence per component is how a form save ends up erasing a live
# credential.


def _masked(raw: dict[str, Any]) -> dict[str, Any]:
    """Return *raw* with secret values replaced by the mask sentinel."""
    return mask_secrets(raw, Config)


def _reload_app_config(request: Request, raw: dict[str, Any]) -> Config:
    """Re-validate *raw* and publish it on ``app.state`` for later requests.

    Without this the write lands on disk but every handler keeps serving the
    `Config` captured at startup, so a successful save looks like a no-op
    until the container restarts.
    """
    cfg = Config.model_validate(raw)
    request.app.state.config = cfg
    return cfg


@router.get("/config")
def read_config(request: Request) -> dict[str, Any]:
    """GET /config — effective config with secrets masked, plus schema and version."""
    raw = _read_config_file()
    return {
        "config": _masked(raw),
        "schema": Config.model_json_schema(),
        "version": current_version(),
    }


@router.put("/config")
def write_config(update: dict[str, Any], request: Request) -> dict[str, Any]:
    """PUT /config — apply a partial update and record a new version.

    Keys omitted from *update* keep their current values. A secret submitted
    as the mask sentinel or as an empty string counts as unchanged.
    """
    try:
        merged, _changed, version = apply_update(Config, update)
    except InvalidConfigError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    _reload_app_config(request, merged)
    return {"config": _masked(merged), "version": version}


@router.get("/config/versions")
def config_versions() -> dict[str, Any]:
    """GET /config/versions — the version history, without the snapshots."""
    return {"versions": list(reversed(read_versions(include_data=False)))}


@router.post("/config/rollback")
def config_rollback(body: dict[str, Any], request: Request) -> dict[str, Any]:
    """POST /config/rollback — restore an earlier version as a new version.

    Secrets are not rolled back: the history never stores them, so they are
    carried forward at their current values rather than being blanked.
    """
    target = body.get("version")
    if not isinstance(target, int):
        raise HTTPException(status_code=422, detail="'version' must be an integer")
    try:
        restored, _changed, version = rollback(Config, target)
    except InvalidConfigError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    _reload_app_config(request, restored)
    return {"config": _masked(restored), "version": version}
