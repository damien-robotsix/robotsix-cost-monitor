"""OpenRouter ↔ Langfuse cost reconciliation via cumulative-usage snapshots.

OpenRouter exposes only cumulative key usage, so we snapshot it (under
``.data/reconcile/<slug>.json``) and diff successive readings to get the spend
in the interval, then compare that to the Langfuse traced cost over the same
interval. Drift above the tolerance is flagged.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import structlog

from ._utils import safe_load_json
from .clients.langfuse import LangfuseClient
from .config import Config, ProjectConfig, Settings
from .exceptions import ExternalServiceError

logger = structlog.get_logger(__name__)


def _state_dir(data_dir: Path) -> Path:
    d = data_dir / "reconcile"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _snapshot_path(slug: str, data_dir: Path) -> Path:
    return _state_dir(data_dir) / f"{slug}.json"


def _load_snapshot(slug: str, data_dir: Path) -> dict[str, Any] | None:
    return safe_load_json(_snapshot_path(slug, data_dir), None)


def _save_snapshot(slug: str, cumulative: float, at: datetime, data_dir: Path) -> None:
    _snapshot_path(slug, data_dir).write_text(
        json.dumps({"cumulative": cumulative, "at": at.isoformat()})
    )


def _hours_between(a: datetime, b: datetime) -> float:
    return max(0.0, (b - a).total_seconds() / 3600.0)


async def _fetch_credits(api_key: str) -> dict[str, float]:
    """Fetch account-level credit balance from OpenRouter (informational)."""
    from robotsix_http import RetryClient

    url = "https://openrouter.ai/api/v1/credits"
    headers = {"Authorization": f"Bearer {api_key}"}
    async with httpx.AsyncClient(timeout=20.0) as http_client:
        client = RetryClient(http_client)
        resp = await client.get(url, headers=headers)
    data = resp.json().get("data") or {}
    return {
        "total_credits": float(data.get("total_credits", 0) or 0),
        "total_usage": float(data.get("total_usage", 0) or 0),
        "remaining": float(data.get("remaining", 0) or 0),
    }


async def reconcile_project(
    project: ProjectConfig, settings: Settings
) -> dict[str, Any]:
    """Reconcile one project's OpenRouter spend vs Langfuse traced cost.

    Snapshots the key's cumulative usage and diffs against the previous
    snapshot; compares the provider delta to the Langfuse traced cost over the
    same interval. Returns a status dict (also includes the remaining
    balance). The snapshot is updated on every call.
    """
    now = datetime.now(UTC)
    result: dict[str, Any] = {
        "project": project.name,
        "slug": project.slug,
        "configured": bool(project.openrouter_key),
        "at": now.isoformat(),
    }
    if not project.openrouter_key:
        result["detail"] = "no openrouter_key configured for this project"
        return result

    try:
        from robotsix_llmio.openrouter import OpenRouterKeyCostSource
    except ImportError:
        result["error"] = (
            "robotsix-llmio is not installed. Install it with: uv sync --extra analyst"
        )
        return result

    orc = OpenRouterKeyCostSource(api_key=project.openrouter_key.get_secret_value())
    # Per-KEY cumulative usage is the reconciliation basis (isolates this
    # consumer even when several keys share one OpenRouter account).
    try:
        cumulative = (await asyncio.to_thread(orc.fetch_key_usage)).usage
    except ExternalServiceError as exc:
        logger.warning("OpenRouter fetch transient failure: %s", exc)
        result["error"] = f"OpenRouter fetch failed: {exc}"
        return result
    except Exception as exc:
        logger.exception("OpenRouter fetch unexpected failure: %s", exc)
        result["error"] = f"OpenRouter fetch failed: {exc}"
        return result

    # Account-level remaining balance — informational only (shared balance pool).
    # Optional: a balance fetch failure must not fail the reconcile.
    with contextlib.suppress(Exception):
        result["balance"] = await _fetch_credits(project.openrouter_key.get_secret_value())

    prior = _load_snapshot(project.slug, settings.data_dir)
    _save_snapshot(project.slug, cumulative, now, settings.data_dir)

    if prior is None:
        result["detail"] = "first snapshot recorded — reconciliation on next run"
        return result

    prior_at = datetime.fromisoformat(prior["at"])
    interval_h = _hours_between(prior_at, now)
    provider_delta = round(cumulative - float(prior["cumulative"]), 6)

    lf = LangfuseClient(
        public_key=project.public_key.get_secret_value(),
        secret_key=project.secret_key.get_secret_value(),
        base_url=project.base_url,
    )
    # Traced cost over the SAME interval as the provider delta (both since the
    # prior snapshot), so the two sides are comparable. Using a rounded ≥1h
    # window here made short intervals nonsensical (provider over minutes vs
    # traced over an hour).
    #
    # Compare like-for-like: OpenRouter's per-key spend only reconciles against
    # the *openrouter*-backend traced cost. Claude-SDK (level-3) traffic is
    # traced in Langfuse but billed by Anthropic, not OpenRouter — including it
    # made "traced" exceed "provider" by the Claude portion.
    try:
        by_backend = await lf.fetch_cost_by_backend(interval_h)
    except (ExternalServiceError, httpx.HTTPError, json.JSONDecodeError) as exc:
        logger.warning("Langfuse fetch failed during reconcile: %s", exc)
        result["error"] = f"Langfuse fetch failed: {exc}"
        return result
    except Exception as exc:
        logger.exception("Langfuse fetch unexpected failure: %s", exc)
        result["error"] = f"Langfuse fetch failed: {exc}"
        return result

    logged = round(by_backend.get("openrouter", 0.0), 6)
    total_traced = round(sum(by_backend.values()), 6)

    drift = round(provider_delta - logged, 6)
    result.update(
        {
            "interval_hours": round(interval_h, 2),
            "provider_delta_usd": provider_delta,
            # OpenRouter-backend only — the value comparable to the provider side.
            "langfuse_cost_usd": logged,
            # All backends (incl. claude-sdk), for transparency.
            "langfuse_total_cost_usd": total_traced,
            "langfuse_cost_by_backend": {k: round(v, 6) for k, v in by_backend.items()},
            "drift_usd": drift,
            "within_tolerance": abs(drift) <= settings.reconcile_tolerance_usd,
            "tolerance_usd": settings.reconcile_tolerance_usd,
        }
    )
    return result


def _last_path(data_dir: Path) -> Path:
    return _state_dir(data_dir) / "last.json"


def reconcile_status(results: list[dict[str, Any]]) -> str:
    """Overall status across per-project reconcile results.

    ``warning`` if any configured project errored or drifted beyond tolerance;
    ``pending`` while every configured project is still on its first snapshot;
    ``ok`` otherwise. Unconfigured projects are ignored.
    """
    comparable = [r for r in results if r.get("configured", True)]
    if any(r.get("error") or r.get("within_tolerance") is False for r in comparable):
        return "warning"
    if comparable and all("within_tolerance" not in r for r in comparable):
        return "pending"
    return "ok"


async def reconcile_all(config: Config) -> dict[str, Any]:
    """Reconcile every project, persist the result, and return it.

    The stored ``last.json`` powers the dashboard's warning banner and the
    ``/api/reconcile/last`` endpoint.
    """
    results = [await reconcile_project(p, config.settings) for p in config.projects]
    out: dict[str, Any] = {
        "generated_at": datetime.now(UTC).isoformat(),
        "status": reconcile_status(results),
        "tolerance_usd": config.settings.reconcile_tolerance_usd,
        "results": results,
    }
    _last_path(config.settings.data_dir).write_text(json.dumps(out, indent=2))
    return out


def load_last_reconcile(data_dir: Path) -> dict[str, Any]:
    """Return the last stored reconcile result (for the banner); empty when none yet."""
    return safe_load_json(
        _last_path(data_dir),
        {"generated_at": None, "status": "unknown", "results": []},
    )
