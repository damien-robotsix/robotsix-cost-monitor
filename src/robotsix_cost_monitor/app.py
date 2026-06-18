"""FastAPI app: cost dashboard + reconciliation endpoints, server-rendered UI."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from .analyst import build_digest, load_proposals, run_analyst
from .config import Config, load_config
from .reconcile import reconcile_project
from .service import CostService

_WEB = Path(__file__).resolve().parent / "web"


def create_app(config: Config | None = None) -> FastAPI:
    cfg = config or load_config()
    service = CostService(cfg)
    app = FastAPI(title="robotsix-cost-monitor", version="0.1.0")
    app.state.config = cfg
    app.state.service = service

    @app.get("/health")
    def health() -> dict[str, Any]:
        return {"status": "ok", "projects": [p.name for p in cfg.projects]}

    @app.get("/api/projects")
    def projects() -> list[dict[str, str]]:
        return [{"name": p.name, "slug": p.slug} for p in cfg.projects]

    @app.get("/api/summary")
    async def summary(
        project: str = Query("all"),
        hours: int = Query(0, ge=0),
    ) -> dict[str, Any]:
        h = hours or cfg.settings.default_window_hours
        return await service.summary(project, h)

    @app.get("/api/by-agent")
    async def by_agent(
        project: str = Query("all"),
        hours: int = Query(0, ge=0),
    ) -> list[dict[str, Any]]:
        h = hours or cfg.settings.default_window_hours
        return await service.by_agent(project, h)

    @app.get("/api/by-model")
    async def by_model(
        project: str = Query("all"),
        hours: int = Query(0, ge=0),
    ) -> list[dict[str, Any]]:
        h = hours or cfg.settings.default_window_hours
        return await service.by_model(project, h)

    @app.get("/api/backend-trend")
    async def backend_trend(
        project: str = Query("all"),
        hours: int = Query(0, ge=0),
        backend: str = Query("all"),
    ) -> list[dict[str, Any]]:
        h = hours or cfg.settings.default_window_hours
        return await service.backend_trend(project, h, backend)

    @app.get("/api/trend")
    async def trend(
        project: str = Query("all"),
        hours: int = Query(0, ge=0),
        buckets: int = Query(48, ge=1, le=200),
    ) -> list[dict[str, Any]]:
        h = hours or cfg.settings.default_window_hours
        return await service.trend(project, h, buckets)

    @app.get("/api/highlights")
    async def highlights(
        project: str = Query("all"),
        hours: int = Query(0, ge=0),
    ) -> dict[str, Any]:
        h = hours or cfg.settings.default_window_hours
        return await service.highlights(project, h)

    @app.get("/api/reconcile")
    async def reconcile(project: str = Query("all")) -> list[dict[str, Any]]:
        targets = (
            cfg.projects
            if project == "all"
            else [p for p in cfg.projects if p.slug == project]
        )
        return [await reconcile_project(p, cfg.settings) for p in targets]

    @app.get("/api/analyst/digest")
    async def analyst_digest(hours: int = Query(0, ge=0)) -> dict[str, Any]:
        h = hours or cfg.settings.analyst.window_hours
        return await build_digest(service, h)

    @app.get("/api/analyst/proposals")
    def analyst_proposals() -> dict[str, Any]:
        return load_proposals()

    @app.post("/api/analyst/run")
    async def analyst_run() -> dict[str, Any]:
        return await run_analyst(cfg, service)

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        return (_WEB / "index.html").read_text()

    if (_WEB / "static").is_dir():
        app.mount("/static", StaticFiles(directory=_WEB / "static"), name="static")

    return app
