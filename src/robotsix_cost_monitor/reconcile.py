"""OpenRouter ↔ Langfuse cost reconciliation via cumulative-usage snapshots.

OpenRouter exposes only cumulative key usage, so we snapshot it (under
``.data/reconcile/<slug>.json``) and diff successive readings to get the spend
in the interval, then compare that to the Langfuse traced cost over the same
interval. Drift above the tolerance is flagged.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .config import ProjectConfig, Settings, data_dir
from .langfuse import LangfuseClient, total_cost
from .openrouter import OpenRouterClient


def _state_dir() -> Path:
    d = data_dir() / "reconcile"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _snapshot_path(slug: str) -> Path:
    return _state_dir() / f"{slug}.json"


def _load_snapshot(slug: str) -> dict[str, Any] | None:
    p = _snapshot_path(slug)
    if not p.exists():
        return None
    try:
        data: dict[str, Any] = json.loads(p.read_text())
        return data
    except (json.JSONDecodeError, OSError):
        return None


def _save_snapshot(slug: str, cumulative: float, at: datetime) -> None:
    _snapshot_path(slug).write_text(
        json.dumps({"cumulative": cumulative, "at": at.isoformat()})
    )


def _hours_between(a: datetime, b: datetime) -> float:
    return max(0.0, (b - a).total_seconds() / 3600.0)


async def reconcile_project(
    project: ProjectConfig, settings: Settings
) -> dict[str, Any]:
    """Reconcile one project's OpenRouter spend vs Langfuse traced cost.

    Snapshots the key's cumulative usage and diffs against the previous
    snapshot; compares the provider delta to the Langfuse traced cost over the
    same interval. Returns a status dict (also includes the remaining balance).
    The snapshot is updated on every call.
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

    orc = OpenRouterClient(project.openrouter_key)
    try:
        credits = await orc.fetch_credits()
    except Exception as exc:  # noqa: BLE001 — surface as status, not a crash
        result["error"] = f"OpenRouter fetch failed: {exc}"
        return result

    result["balance"] = credits
    cumulative = credits["total_usage"]
    prior = _load_snapshot(project.slug)
    _save_snapshot(project.slug, cumulative, now)

    if prior is None:
        result["detail"] = "first snapshot recorded — reconciliation on next run"
        return result

    prior_at = datetime.fromisoformat(prior["at"])
    interval_h = _hours_between(prior_at, now)
    provider_delta = round(cumulative - float(prior["cumulative"]), 6)

    lf = LangfuseClient(
        public_key=project.public_key,
        secret_key=project.secret_key,
        base_url=project.base_url,
    )
    # Round the interval up to whole hours for the Langfuse window query.
    traces = await lf.fetch_traces_window(max(1, round(interval_h + 0.5)))
    logged = total_cost(traces)

    drift = round(provider_delta - logged, 6)
    result.update(
        {
            "interval_hours": round(interval_h, 2),
            "provider_delta_usd": provider_delta,
            "langfuse_cost_usd": logged,
            "drift_usd": drift,
            "within_tolerance": abs(drift) <= settings.reconcile_tolerance_usd,
            "tolerance_usd": settings.reconcile_tolerance_usd,
        }
    )
    return result
