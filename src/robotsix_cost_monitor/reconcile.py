"""OpenRouter ↔ Langfuse cost reconciliation via cumulative-usage snapshots.

OpenRouter exposes only cumulative key usage, so we snapshot it (under
``.data/reconcile/<slug>.json``) and diff successive readings to get the spend
in the interval, then compare that to the Langfuse traced cost over the same
interval. Drift above the tolerance is flagged.
"""

from __future__ import annotations

import contextlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .config import ProjectConfig, Settings, data_dir
from .langfuse import LangfuseClient
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
    # Per-KEY cumulative usage is the reconciliation basis (isolates this
    # consumer even when several keys share one OpenRouter account).
    try:
        cumulative = await orc.fetch_key_usage()
    except Exception as exc:  # noqa: BLE001 — surface as status, not a crash
        result["error"] = f"OpenRouter fetch failed: {exc}"
        return result

    # Account-level remaining balance — informational only (shared balance pool).
    # Optional: a balance fetch failure must not fail the reconcile.
    with contextlib.suppress(Exception):
        result["balance"] = await orc.fetch_credits()

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
    # Traced cost over the SAME interval as the provider delta (both since the
    # prior snapshot), so the two sides are comparable. Using a rounded ≥1h
    # window here made short intervals nonsensical (provider over minutes vs
    # traced over an hour).
    #
    # Compare like-for-like: OpenRouter's per-key spend only reconciles against
    # the *openrouter*-backend traced cost. Claude-SDK (level-3) traffic is
    # traced in Langfuse but billed by Anthropic, not OpenRouter — including it
    # made "traced" exceed "provider" by the Claude portion.
    by_backend = await lf.fetch_cost_by_backend(interval_h)
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
