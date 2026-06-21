"""FastAPI app: cost dashboard + reconciliation endpoints, server-rendered UI."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from .analyst import (
    build_digest,
    load_proposals,
    load_targeted_analysis,
    run_analyst,
    run_stage_analyst,
    run_ticket_analyst,
)
from .config import Config, load_config
from .reconcile import load_last_reconcile, reconcile_all, reconcile_project
from .service import CostService

_WEB = Path(__file__).resolve().parent / "web"
logger = logging.getLogger(__name__)

# Lazy import so the dashboard works without the optional `analyst` extra.
try:
    from robotsix_llmio.logging import setup_logging

    setup_logging(loggers=["robotsix_cost_monitor"], fmt="json")
except ImportError:
    pass


def _window(hours: int, config: Config) -> int:
    return hours or config.settings.default_window_hours


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
    """The most recent ``generated_at`` across the persisted fleet/ticket/stage
    analyses, or ``None`` when none has run yet.

    Used to resume the analyst cadence across process restarts: the dashboard's
    scheduler lives in-process and is redeployed often (Watchtower), so a timer
    that simply sleeps a full interval on every start would keep resetting and
    the daily analysis would rarely fire."""
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
    """Seconds to wait before the first scheduled analysis.

    ``0`` when a full *interval* has already elapsed since *last_run* (or nothing
    has ever run), else only the remaining time — so the ~daily cadence is stable
    regardless of how often the container restarts. A *last_run* in the future
    (clock skew) falls back to a full interval rather than running immediately."""
    if last_run is None:
        return 0.0
    elapsed = (now - last_run).total_seconds()
    if elapsed < 0:
        return interval
    return max(0.0, interval - elapsed)


async def _analyst_loop(cfg: Config, service: CostService, hours: float) -> None:
    """Run all analyses (fleet + most-costly ticket + most-costly stage) every
    *hours* hours until cancelled.

    The first delay is derived from the last persisted run (not a fresh full
    sleep) so frequent redeploys don't starve the schedule: if a full interval
    has already elapsed it runs at once, otherwise it waits only the remainder."""
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
            except Exception:  # noqa: BLE001 — a failed run must not kill the loop
                logger.exception("scheduled %s analysis failed", label)
        delay = interval


async def _reconcile_loop(cfg: Config, hours: float) -> None:
    """Reconcile all projects every *hours* hours (with an initial run so the
    banner has data immediately) until cancelled."""
    interval = max(1.0, hours) * 3600
    while True:
        try:
            await reconcile_all(cfg)
        except Exception:  # noqa: BLE001 — a failed run must not kill the loop
            logger.exception("scheduled reconcile failed")
        await asyncio.sleep(interval)


def create_app(config: Config | None = None) -> FastAPI:
    cfg = config or load_config()
    service = CostService(cfg)

    @contextlib.asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
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

    app = FastAPI(title="robotsix-cost-monitor", version="0.1.0", lifespan=lifespan)
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
        h = _window(hours, cfg)
        return await service.summary(project, h)

    @app.get("/api/by-agent")
    async def by_agent(
        project: str = Query("all"),
        hours: int = Query(0, ge=0),
        backend: str = Query("all"),
    ) -> list[dict[str, Any]]:
        h = _window(hours, cfg)
        return await service.by_agent(project, h, backend)

    @app.get("/api/by-model")
    async def by_model(
        project: str = Query("all"),
        hours: int = Query(0, ge=0),
    ) -> list[dict[str, Any]]:
        h = _window(hours, cfg)
        return await service.by_model(project, h)

    @app.get("/api/backend-trend")
    async def backend_trend(
        project: str = Query("all"),
        hours: int = Query(0, ge=0),
        backend: str = Query("all"),
    ) -> list[dict[str, Any]]:
        h = _window(hours, cfg)
        return await service.backend_trend(project, h, backend)

    @app.get("/api/trend")
    async def trend(
        project: str = Query("all"),
        hours: int = Query(0, ge=0),
        buckets: int = Query(48, ge=1, le=200),
    ) -> list[dict[str, Any]]:
        h = _window(hours, cfg)
        return await service.trend(project, h, buckets)

    @app.get("/api/highlights")
    async def highlights(
        project: str = Query("all"),
        hours: int = Query(0, ge=0),
    ) -> dict[str, Any]:
        h = _window(hours, cfg)
        return await service.highlights(project, h)

    @app.get("/api/reconcile")
    async def reconcile(project: str = Query("all")) -> list[dict[str, Any]]:
        # Running all projects persists last.json (banner + scheduler share it);
        # a single-project run is a transient check that doesn't overwrite it.
        if project == "all":
            out = await reconcile_all(cfg)
            return cast("list[dict[str, Any]]", out["results"])
        targets = [p for p in cfg.projects if p.slug == project]
        return [await reconcile_project(p, cfg.settings) for p in targets]

    @app.get("/api/reconcile/last")
    def reconcile_last() -> dict[str, Any]:
        return load_last_reconcile()

    @app.get("/api/analyst/digest")
    async def analyst_digest(hours: int = Query(0, ge=0)) -> dict[str, Any]:
        h = hours or cfg.settings.analyst.window_hours
        return await build_digest(service, h, cfg)

    @app.get("/api/analyst/proposals")
    def analyst_proposals() -> dict[str, Any]:
        return load_proposals()

    @app.post("/api/analyst/run")
    async def analyst_run() -> dict[str, Any]:
        return await run_analyst(cfg, service)

    @app.get("/api/analyst/ticket")
    def analyst_ticket() -> dict[str, Any]:
        return load_targeted_analysis("ticket")

    @app.post("/api/analyst/ticket-run")
    async def analyst_ticket_run() -> dict[str, Any]:
        return await run_ticket_analyst(cfg, service)

    @app.get("/api/analyst/stage")
    def analyst_stage() -> dict[str, Any]:
        return load_targeted_analysis("stage")

    @app.post("/api/analyst/stage-run")
    async def analyst_stage_run() -> dict[str, Any]:
        return await run_stage_analyst(cfg, service)

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        return (_WEB / "index.html").read_text()

    @app.get("/analyst", response_class=HTMLResponse)
    def analyst_page() -> str:
        return (_WEB / "analyst.html").read_text()

    if (_WEB / "static").is_dir():
        app.mount("/static", StaticFiles(directory=_WEB / "static"), name="static")

    return app
