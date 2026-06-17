"""Cost-analyst: a deterministic cost digest + an optional LLM proposal pass.

The digest (stage table + specimens) is always available and needs no LLM. When
``settings.analyst`` is configured with a model, :func:`run_analyst` sends the
digest to an OpenAI-compatible endpoint and stores high-confidence
cost-reduction proposals under ``.data/analyst/proposals.json`` — surfaced in
the dashboard rather than written to any external board.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .config import Config, data_dir
from .service import CostService

_SYSTEM = (
    "You are a cost-reduction analyst for an LLM agent fleet. Given a cost "
    "digest (per-stage spend and specimen traces), propose ONLY high-confidence, "
    "concrete cost reductions (model-tier over-provisioning, prompt/token bloat, "
    "redundant tool calls, retry/cycle waste). Return JSON: "
    '{"proposals": [{"title": "...", "rationale": "...", "estimated_saving": "..."}]}. '
    "If nothing is high-confidence, return an empty list."
)


def _store_path() -> Path:
    d = data_dir() / "analyst"
    d.mkdir(parents=True, exist_ok=True)
    return d / "proposals.json"


async def build_digest(service: CostService, hours: int) -> dict[str, Any]:
    """Deterministic cost digest across all projects for the window."""
    summary = await service.summary("all", hours)
    by_agent = await service.by_agent("all", hours)
    highlights = await service.highlights("all", hours)
    total = summary["total_cost"] or 1e-9
    stages = [
        {
            **row,
            "pct": round(100 * row["cost"] / total, 1),
            "avg_per_trace": round(row["cost"] / max(1, row["count"]), 6),
        }
        for row in by_agent
    ]
    return {
        "window_hours": hours,
        "total_cost": summary["total_cost"],
        "projects": summary["projects"],
        "stages": stages,
        "highlights": highlights,
    }


def load_proposals() -> dict[str, Any]:
    p = _store_path()
    if not p.exists():
        return {"generated_at": None, "proposals": []}
    try:
        data: dict[str, Any] = json.loads(p.read_text())
        return data
    except (json.JSONDecodeError, OSError):
        return {"generated_at": None, "proposals": []}


async def run_analyst(config: Config, service: CostService) -> dict[str, Any]:
    """Run the LLM proposal pass; store + return the proposals.

    Returns ``{"enabled": False}`` when no model is configured.
    """
    a = config.settings.analyst
    if not a.enabled:
        return {"enabled": False, "detail": "analyst.model not configured"}

    digest = await build_digest(service, a.window_hours)

    # Lazy import so the dashboard works without the optional `analyst` extra.
    from openai import AsyncOpenAI

    client = AsyncOpenAI(api_key=a.api_key or "", base_url=a.base_url)
    resp = await client.chat.completions.create(
        model=a.model or "",
        messages=[
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": json.dumps(digest)},
        ],
        response_format={"type": "json_object"},
    )
    content = resp.choices[0].message.content or "{}"
    try:
        parsed = json.loads(content)
        proposals = parsed.get("proposals", []) if isinstance(parsed, dict) else []
    except json.JSONDecodeError:
        proposals = []

    out = {
        "enabled": True,
        "generated_at": datetime.now(UTC).isoformat(),
        "window_hours": a.window_hours,
        "proposals": proposals,
    }
    _store_path().write_text(json.dumps(out, indent=2))
    return out
