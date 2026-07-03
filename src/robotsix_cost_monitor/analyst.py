"""Cost-analyst: a deterministic digest + a robotsix-llmio analysis pass.

The digest (stage table + specimens) is always available and needs no LLM. When
``settings.analyst`` is configured with an OpenRouter key, :func:`run_analyst`
runs a **level-3** orchestrator over the digest, with a **level-2** sub-agent
it can call to drill into the most expensive traces, and stores
cost-reduction proposals under ``.data/analyst/proposals.json`` (surfaced in the
dashboard).
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import structlog
from pydantic import BaseModel

from .config import AnalystConfig, Config, data_dir
from .reconcile import _safe_load_json
from .service import CostService

logger = structlog.get_logger(__name__)

#: Cap a single trace's serialized detail handed to the trace agent.
_TRACE_CHAR_CAP = 24_000

#: Shared cost-model caveat appended to every analysis prompt.
_COST_MODEL_NOTE = (
    "IMPORTANT cost-model context: the Claude SDK backend (Claude / Opus models) "
    "runs on a FIXED monthly SUBSCRIPTION — its traced cost is an ESTIMATE, not "
    "marginal spend, and is paid regardless of volume. So: (1) do NOT recommend "
    "switching Claude-SDK work to a pay-per-token model (e.g. DeepSeek via "
    "OpenRouter) merely to 'reduce cost' — that can ADD real marginal cost while "
    "the subscription is already paid; (2) for Claude-SDK the only lever is "
    "keeping usage within the subscription's limits — cut genuinely wasteful or "
    "excess calls, don't model-switch; (3) real marginal savings come from the "
    "pay-per-token OpenRouter backends — trim prompts/context, right-size among "
    "OpenRouter tiers, and avoid redundant calls/retries. Weight your proposals "
    "accordingly and say which backend (subscription vs pay-per-token) each targets."
)

_ORCHESTRATOR_SYSTEM = (
    "You are a cost-reduction analyst for an LLM agent fleet. You are given a "
    "deterministic cost digest (per-stage spend + specimens) and `trace_findings` "
    "— per-trace cost analyses of the most expensive recent traces (each has "
    "trace_id, project, cost, and a finding). Synthesise across them to identify "
    "the highest-leverage waste (model-tier over-provisioning, prompt/token "
    "bloat, redundant tool calls, retry/cycle waste). Return ONLY high-confidence, "
    "concrete cost reductions as proposals. Each proposal is a candidate board "
    "ticket, so make it actionable: a clear `title`, and a `rationale` with the "
    "evidence (which stage/trace, the cost) AND a concrete fix. A downstream "
    "board manager turns these into tickets (deduping + refining), so DON'T "
    "pre-merge distinct issues — list each separately; just omit anything trivial "
    "or low-confidence.\n\n"
    + _COST_MODEL_NOTE
    + "\n\n"
    + 'Return ONLY a JSON object (no prose, no code fences): {"summary": "...", '
    '"proposals": [{"title": "...", "rationale": "...", "estimated_saving": '
    '"..."}]}.'
)

_TRACE_SYSTEM = (
    "You are a trace-level cost analyst. You are given one LLM agent trace with "
    "its observations. Identify concretely where cost/tokens are wasted "
    "(oversized prompts, an over-provisioned model tier for the work, repeated or "
    "redundant tool calls, retry/error loops) and quantify it where you can. Be "
    "specific and terse; this feeds a higher-level analyst. " + _COST_MODEL_NOTE
)

#: Cap the serialized payload for the ticket/stage analyses (history is large).
_TARGET_CHAR_CAP = 48_000

_PROPOSAL_JSON = (
    'Return ONLY a JSON object (no prose, no code fences): {"summary": "...", '
    '"proposals": [{"title": "...", "rationale": "...", "estimated_saving": '
    '"..."}]}. Each proposal is a candidate board ticket: clear title + a '
    "rationale with evidence and a concrete fix; list distinct issues separately; "
    "omit anything trivial."
)

_TICKET_SYSTEM = (
    "You are a cost analyst examining the single most EXPENSIVE BOARD TICKET over "
    "its whole lifecycle. You are given the ticket's total cost, its cost broken "
    "down by stage (cost_by_stage — each stage/agent's spend on THIS ticket), its "
    "traces, and the ticket's board history (state transitions, re-refinements, "
    "retries, comments) + description. Diagnose WHY this ticket was so expensive "
    "across its lifecycle — process-level waste: repeated re-refinement, "
    "implement/audit retry loops, bouncing between states, oversized context "
    "carried across stages, redundant rework — not just per-trace token bloat. "
    "Then propose concrete, high-confidence ways to cut the cost of tickets like "
    "this. " + _COST_MODEL_NOTE + " " + _PROPOSAL_JSON
)

_STAGE_SYSTEM = (
    "You are a cost analyst examining the single most EXPENSIVE STAGE (agent) "
    "across the whole fleet. You are given the stage name, its total cost and "
    "share of traced spend, and a sample of its priciest traces (with details). "
    "Diagnose WHY this stage dominates spend and how to reduce it GLOBALLY "
    "(model-tier right-sizing, prompt/context trimming, caching, fewer/cheaper "
    "tool calls, avoiding retries) — changes that apply to every run of the "
    "stage, not a one-off. " + _COST_MODEL_NOTE + " " + _PROPOSAL_JSON
)


class Proposal(BaseModel):
    """A single high-confidence cost-reduction proposal."""

    title: str
    rationale: str
    estimated_saving: str = ""


class Analysis(BaseModel):
    """Structured output of the orchestrator agent — proposals only.

    Ticket creation is delegated to the board manager, which turns the
    proposals into tickets (dedup + refinement); the analyst no longer decides
    on a single synthesised ticket.
    """

    summary: str = ""
    proposals: list[Proposal] = []


def _store_path() -> Path:
    d = data_dir() / "analyst"
    d.mkdir(parents=True, exist_ok=True)
    return d / "proposals.json"


async def build_digest(
    service: CostService, hours: int, config: Config
) -> dict[str, Any]:
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
    ][: config.settings.analyst.top_stages]
    return {
        "window_hours": hours,
        "total_cost": summary["total_cost"],
        "projects": summary["projects"],
        "stages": stages,
        "highlights": highlights,
    }


def load_proposals() -> dict[str, Any]:
    return _safe_load_json(_store_path(), {"generated_at": None, "proposals": []})


def _run_agents(
    a: AnalystConfig,
    digest: dict[str, Any],
    candidates: list[dict[str, Any]],
    details: dict[str, dict[str, Any]],
) -> tuple[Analysis, list[dict[str, Any]]]:
    """Run the analyst: a level-2 trace pre-pass, then a level-3 orchestrator.

    robotsix-llmio's ``run_agent`` is blocking, so the caller runs this in a
    thread. Trace details are pre-fetched into *details*. The orchestrator has
    NO tools (so it can run on the Claude SDK without gaining host bash/file
    tools) — the per-trace findings are computed up front and handed to it.
    """
    # Lazy imports so the dashboard works without the optional `analyst` extra.
    from robotsix_llmio import get_provider_for_level
    from robotsix_llmio.core.run import run_agent

    _maybe_setup_tracing(a)

    # Level 2 (intermediate): parse each expensive trace into a terse finding,
    # up front (so the orchestrator needs no tools). Provider/model from llmio's
    # tier config (LEVEL2 → openrouter-deepseek/deepseek-v4-pro).
    trace_provider = get_provider_for_level(2, api_key=a.openrouter_key)
    findings: list[dict[str, Any]] = []
    for c in candidates:
        detail = details.get(c["trace_id"])
        if not detail:
            continue
        ht = trace_provider.build_agent(
            level=2,
            model=a.trace_model or None,
            system_prompt=_TRACE_SYSTEM,
            output_type=str,
            name="cost-analyst-trace",
        )
        payload = json.dumps(detail)[:_TRACE_CHAR_CAP]

        # Bind the loop vars via defaults (ruff B023) and annotate the return so
        # run_agent's generic resolves (a plain lambda can't be inferred here).
        def _run_trace(handle: Any = ht, p: str = payload) -> str:
            return str(handle.run_sync(p).output)

        finding = run_agent(
            ht,
            _run_trace,
            label="cost-analyst-trace",
            project=a.langfuse_project_id,
        )
        findings.append(
            {
                "trace_id": c["trace_id"],
                "project": c.get("project"),
                "name": c.get("name"),
                "cost": c.get("cost"),
                # Why the deterministic selector picked this trace.
                "rank": c.get("rank"),
                "pct_of_traced": c.get("pct_of_traced"),
                "selection_reason": c.get("selection_reason"),
                # The L2 agent's analysis of the waste inside the trace.
                "finding": finding,
            }
        )

    # Level 3 (high-level orchestration): synthesise the digest + trace findings.
    analysis = _opus_analysis(
        a,
        system_prompt=_ORCHESTRATOR_SYSTEM,
        payload=json.dumps({"digest": digest, "trace_findings": findings}),
        name="cost-analyst",
    )
    return analysis, findings


def _maybe_setup_tracing(a: AnalystConfig) -> None:
    """Wire the analyst's own Langfuse tracing (best-effort, idempotent)."""
    if a.langfuse_public_key and a.langfuse_secret_key:
        with contextlib.suppress(Exception):
            from robotsix_llmio.core.tracing import setup_langfuse_tracing

            setup_langfuse_tracing(
                public_key=a.langfuse_public_key,
                secret_key=a.langfuse_secret_key,
                base_url=a.langfuse_base_url,
                project_id=a.langfuse_project_id,
                service_name="robotsix-cost-analyst",
            )


def _opus_analysis(
    a: AnalystConfig, *, system_prompt: str, payload: str, name: str
) -> Analysis:
    """Run the level-3 (tier-3 → Claude Opus) orchestrator on *payload*, no tools.

    Shared by the fleet / ticket / stage analyses. output_type=str (avoids
    structured-output parsing edge-cases with reasoning models), parsed by
    :func:`_parse_analysis`.
    """
    from robotsix_llmio import build_agent_for_level
    from robotsix_llmio.core.run import run_agent

    _maybe_setup_tracing(a)
    h = build_agent_for_level(
        3,
        model=a.global_model or None,
        system_prompt=system_prompt,
        output_type=str,
        name=name,
    )
    raw = str(
        run_agent(
            h,
            lambda: h.run_sync(payload).output,
            label=name,
            project=a.langfuse_project_id,
        )
    )
    return _parse_analysis(raw)


def _parse_analysis(raw: str) -> Analysis:
    """Parse an agent's JSON reply into an :class:`Analysis`.

    Tolerant of code fences / surrounding prose; on any failure the raw text is
    kept as the summary so a run is never lost.
    """
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("```", 2)[1] if text.count("```") >= 2 else text
        text = text.removeprefix("json").strip("`").strip()
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end != -1 and end > start:
        with contextlib.suppress(Exception):
            return Analysis.model_validate(json.loads(text[start : end + 1]))
    return Analysis(summary=raw[:1000])


def _build_analysis_response(
    a: AnalystConfig,
    analysis: Analysis,
    *,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the standard analysis response dict.

    Shared between ``run_analyst`` and ``_run_opus_analysis_and_file`` to keep
    the response shape consistent.
    """
    out: dict[str, Any] = {
        "enabled": True,
        "generated_at": datetime.now(UTC).isoformat(),
        "window_hours": a.window_hours,
        "summary": analysis.summary,
        "proposals": [p.model_dump() for p in analysis.proposals],
    }
    if extra:
        out.update(extra)
    return out


async def run_analyst(config: Config, service: CostService) -> dict[str, Any]:
    """Run the analyst (digest → L2 agent + L3 sub-agent → optional ticket).

    Returns ``{"enabled": False}`` when no OpenRouter key is configured.
    """
    a = config.settings.analyst
    if not a.enabled:
        return {"enabled": False, "detail": "analyst.openrouter_key not configured"}

    digest = await build_digest(service, a.window_hours, config)

    # Pre-fetch the top-cost traces' details (async) so the L3 tool is in-memory.
    candidates = await service.candidate_traces(
        "all", a.window_hours, a.max_trace_analyses, per_agent=a.traces_per_agent
    )
    details: dict[str, dict[str, Any]] = {}
    for c in candidates:
        with contextlib.suppress(Exception):
            details[c["trace_id"]] = await service.trace_detail(
                c["project"], c["trace_id"]
            )

    analysis, findings = await asyncio.to_thread(
        _run_agents, a, digest, candidates, details
    )

    out = _build_analysis_response(a, analysis)
    out["analyzed_traces"] = findings
    _store_path().write_text(json.dumps(out, indent=2))
    return out


# --- targeted (ticket / stage) analyses -----------------------------------


def _targeted_store_path(kind: str) -> Path:
    d = data_dir() / "analyst"
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{kind}.json"


def _no_top_early_return(kind: str, detail: str) -> dict[str, Any]:
    out: dict[str, Any] = {
        "enabled": True,
        "generated_at": datetime.now(UTC).isoformat(),
        "detail": detail,
    }
    _targeted_store_path(kind).write_text(json.dumps(out, indent=2))
    return out


def load_targeted_analysis(kind: str) -> dict[str, Any]:
    """Last stored ticket/stage analysis (for the page); empty when none yet."""
    return _safe_load_json(_targeted_store_path(kind), {"generated_at": None})


def _split_session(session_id: str) -> tuple[str, str]:
    """Parse a Langfuse session id ``"<board> · <ticket_id>"`` → (board, id)."""
    parts = session_id.split(" · ", 1)
    if len(parts) == 2:
        return parts[0].strip(), parts[1].strip()
    return "", session_id.strip()


async def _run_opus_analysis_and_file(
    a: AnalystConfig,
    system_prompt: str,
    name: str,
    payload: str,
    out_prefix: str,
    extra_out: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run Opus analysis and store the result."""
    analysis = await asyncio.to_thread(
        _opus_analysis, a, system_prompt=system_prompt, payload=payload, name=name
    )
    out = _build_analysis_response(a, analysis, extra=extra_out)
    _targeted_store_path(out_prefix).write_text(json.dumps(out, indent=2))
    return out


async def run_ticket_analyst(config: Config, service: CostService) -> dict[str, Any]:
    """Analyse the single most expensive ticket over its whole lifecycle.

    Aggregates the ticket's per-stage trace cost + its board history, runs the
    level-3 (Opus) global analysis, and files the proposals via the manager.
    """
    a = config.settings.analyst
    if not a.enabled:
        return {"enabled": False, "detail": "analyst.openrouter_key not configured"}

    top = await service.top_ticket("all", a.window_hours)
    if not top:
        return _no_top_early_return("ticket", "no ticket sessions in the window")

    board_id, ticket_id = _split_session(top["session_id"])

    payload = json.dumps(
        {
            "ticket_id": ticket_id,
            "board": board_id,
            "total_cost_usd": top["cost"],
            "trace_count": top["count"],
            "cost_by_stage": top["by_stage"],
            "traces": top["traces"],
            "ticket": None,
            "history": None,
            "description": None,
        }
    )[:_TARGET_CHAR_CAP]
    return await _run_opus_analysis_and_file(
        a,
        system_prompt=_TICKET_SYSTEM,
        name="cost-analyst-ticket",
        payload=payload,
        out_prefix="ticket",
        extra_out={
            "session_id": top["session_id"],
            "board_id": board_id,
            "ticket_id": ticket_id,
            "total_cost": top["cost"],
            "trace_count": top["count"],
            "by_stage": top["by_stage"],
            "traces": top["traces"],
            "history_available": False,
        },
    )


async def run_stage_analyst(config: Config, service: CostService) -> dict[str, Any]:
    """Analyse the single most expensive stage (agent) across the fleet.

    Samples the stage's priciest traces (with detail), runs the level-3 (Opus)
    global analysis, and files the proposals via the manager.
    """
    a = config.settings.analyst
    if not a.enabled:
        return {"enabled": False, "detail": "analyst.openrouter_key not configured"}

    top = await service.top_stage("all", a.window_hours, sample=a.max_trace_analyses)
    if not top:
        return _no_top_early_return("stage", "no traces in the window")

    sampled: list[dict[str, Any]] = []
    for t in top["traces"]:
        detail: dict[str, Any] | None = None
        with contextlib.suppress(Exception):
            detail = await service.trace_detail(t["project"], t["trace_id"])
        sampled.append({"trace_id": t["trace_id"], "cost": t["cost"], "detail": detail})

    payload = json.dumps(
        {
            "stage": top["stage"],
            "total_cost_usd": top["cost"],
            "pct_of_traced": top["pct_of_traced"],
            "trace_count": top["count"],
            "sample_traces": sampled,
        }
    )[:_TARGET_CHAR_CAP]
    return await _run_opus_analysis_and_file(
        a,
        system_prompt=_STAGE_SYSTEM,
        name="cost-analyst-stage",
        payload=payload,
        out_prefix="stage",
        extra_out={
            "stage": top["stage"],
            "total_cost": top["cost"],
            "pct_of_traced": top["pct_of_traced"],
            "trace_count": top["count"],
            "sample_size": len(sampled),
        },
    )
