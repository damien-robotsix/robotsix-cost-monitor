"""Standard config HTTP surface (APIRouter).

Required of every deployable component by robotsix-standards
`config-ownership.md`. The deploy plane keeps no copy of these values — it
reads them from the component — so this surface is how config is inspected
and changed at runtime, and the `<config>.versions` sidecar beside the
config file is where its history lives.

All handlers delegate to `robotsix_config.history`. That is deliberate:
`PUT /config` has to deep-merge, restore secrets the caller did not really
resubmit, validate, write, and record — in that order — and reimplementing
that sequence per component is how a form save ends up erasing a live
credential.
"""

from __future__ import annotations

import json
from typing import Any, cast

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from robotsix_config import (
    InvalidConfigError,
    apply_update,
    current_version,
    mask_secrets,
    read_versions,
    resolve_config_path,
    rollback,
)

from .config import Config

router = APIRouter()


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


def _config_validation_error(detail: str) -> JSONResponse:
    """Return the RFC 7807 problem response shared by every 422 config path."""
    return JSONResponse(
        status_code=422,
        media_type="application/problem+json",
        content={
            "type": "urn:robotsix:error:config-validation",
            "title": "Config Validation Error",
            "detail": detail,
            "status": 422,
        },
    )


@router.get("/config")
def read_config(request: Request) -> dict[str, Any]:
    """GET /config — effective config with secrets masked, plus schema and version."""
    raw = _read_config_file()
    return {
        "config": _masked(raw),
        "schema": Config.model_json_schema(),
        "version": current_version(),
    }


@router.put("/config", response_model=None)
def write_config(
    update: dict[str, Any],
    request: Request,
) -> dict[str, Any] | JSONResponse:
    """PUT /config — apply a partial update and record a new version.

    Keys omitted from *update* keep their current values. A secret submitted
    as the mask sentinel or as an empty string counts as unchanged.
    """
    try:
        merged, _changed, version = apply_update(Config, update)
    except InvalidConfigError as exc:
        return _config_validation_error(str(exc))
    _reload_app_config(request, merged)
    return {"config": _masked(merged), "version": version}


@router.get("/config/versions")
def config_versions() -> dict[str, Any]:
    """GET /config/versions — the version history, without the snapshots."""
    return {"versions": list(reversed(read_versions(include_data=False)))}


@router.post("/config/rollback", response_model=None)
def config_rollback(
    body: dict[str, Any],
    request: Request,
) -> dict[str, Any] | JSONResponse:
    """POST /config/rollback — restore an earlier version as a new version.

    Secrets are not rolled back: the history never stores them, so they are
    carried forward at their current values rather than being blanked.
    """
    target = body.get("version")
    if not isinstance(target, int):
        return _config_validation_error("'version' must be an integer")
    try:
        restored, _changed, version = rollback(Config, target)
    except InvalidConfigError as exc:
        return _config_validation_error(str(exc))
    _reload_app_config(request, restored)
    return {"config": _masked(restored), "version": version}
