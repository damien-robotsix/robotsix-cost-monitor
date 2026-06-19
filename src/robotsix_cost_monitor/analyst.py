"""Cost-analyst: a deterministic digest + a robotsix-llmio analysis pass.

The digest (stage table + specimens) is always available and needs no LLM. When
``settings.analyst`` is configured with an OpenRouter key, :func:`run_analyst`
runs a **level-2** (llmio tier-2) agent over the digest, with a **level-3**
sub-agent it can call to drill into the most expensive traces, and stores
cost-reduction proposals under ``.data/analyst/proposals.json`` (surfaced in the
dashboard). When a broker is configured and the analysis warrants it, the
analyst also files a board ticket via agent-comm (pull/mailbox → the central
broker → the board agent).
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from pydantic import BaseModel

from .config import AnalystConfig, Config, data_dir
from .service import CostService

logger = logging.getLogger(__name__)

#: Cap a single trace's serialized detail handed to the level-3 agent.
_TRACE_CHAR_CAP = 24_000

#: llmio provider for the analyst's agents. ``openrouter`` isn't a registered
#: provider name; ``openrouter-deepseek`` is the OpenRouter-backed one.
_PROVIDER = "openrouter-deepseek"

#: Default level-3 model. tier-3 defaults to the Claude SDK (``opus``), which the
#: OpenRouter provider can't serve, so the trace agent uses the strongest
#: llmio-known OpenRouter model (override via analyst.trace_model).
_DEFAULT_TRACE_MODEL = "deepseek/deepseek-v4-pro"

_L2_SYSTEM = (
    "You are a cost-reduction analyst for an LLM agent fleet. You are given a "
    "deterministic cost digest (per-stage spend + specimens) and a list of the "
    "most expensive recent traces (candidate_traces: each has trace_id, project, "
    "name, cost). Use the analyze_trace(trace_id) tool to drill into the traces "
    "that look most wasteful (model-tier over-provisioning, prompt/token bloat, "
    "redundant tool calls, retry/cycle waste) — call it only for genuinely "
    "suspicious traces, not all of them. Then return ONLY high-confidence, "
    "concrete cost reductions. Set `ticket` ONLY when a problem is significant "
    "and actionable enough to warrant a tracked board ticket (clear title + a "
    "description with evidence and a concrete fix); otherwise leave it null.\n\n"
    'Return ONLY a JSON object (no prose, no code fences): {"summary": "...", '
    '"proposals": [{"title": "...", "rationale": "...", "estimated_saving": '
    '"..."}], "ticket": {"title": "...", "description": "..."} or null}.'
)

_L3_SYSTEM = (
    "You are a trace-level cost analyst. You are given one LLM agent trace with "
    "its observations. Identify concretely where cost/tokens are wasted "
    "(oversized prompts, an over-provisioned model tier for the work, repeated or "
    "redundant tool calls, retry/error loops) and quantify it where you can. Be "
    "specific and terse; this feeds a higher-level analyst."
)


class Proposal(BaseModel):
    """A single high-confidence cost-reduction proposal."""

    title: str
    rationale: str
    estimated_saving: str = ""


class TicketRequest(BaseModel):
    """A board ticket the analyst wants filed for a significant cost issue."""

    title: str
    description: str


class Analysis(BaseModel):
    """Structured output of the level-2 analyst agent."""

    summary: str = ""
    proposals: list[Proposal] = []
    ticket: TicketRequest | None = None


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
    p = _store_path()
    if not p.exists():
        return {"generated_at": None, "proposals": []}
    try:
        data: dict[str, Any] = json.loads(p.read_text())
        return data
    except (json.JSONDecodeError, OSError):
        return {"generated_at": None, "proposals": []}


def _run_agents(
    a: AnalystConfig,
    digest: dict[str, Any],
    candidates: list[dict[str, Any]],
    details: dict[str, dict[str, Any]],
) -> Analysis:
    """Run the level-2 agent (with its level-3 sub-agent tool) synchronously.

    robotsix-llmio's ``run_agent`` is blocking, so the caller runs this in a
    thread. All network I/O the agents need (trace details) is pre-fetched into
    *details*, keyed by trace_id, so the level-3 tool stays in-memory.
    """
    # Lazy imports so the dashboard works without the optional `analyst` extra.
    from robotsix_llmio.core.factory import get_provider
    from robotsix_llmio.core.run import run_agent

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

    provider = get_provider(provider=_PROVIDER, api_key=a.openrouter_key)

    def analyze_trace(trace_id: str) -> str:
        """Run the level-3 sub-agent on one expensive trace's full detail.

        Pass a trace_id taken from candidate_traces; returns a terse,
        trace-specific cost analysis.
        """
        detail = details.get(trace_id)
        if not detail:
            return f"No detail available for trace {trace_id!r}."
        h3 = provider.build_agent(
            level=3,
            model=a.trace_model or _DEFAULT_TRACE_MODEL,
            system_prompt=_L3_SYSTEM,
            output_type=str,
            name="cost-analyst-trace",
        )
        payload = json.dumps(detail)[:_TRACE_CHAR_CAP]
        return cast(
            "str",
            run_agent(
                h3,
                lambda: h3.run_sync(payload).output,
                label="cost-analyst-trace",
                project=a.langfuse_project_id,
            ),
        )

    # output_type=str (not Analysis): DeepSeek reasoning ("thinking") models
    # reject the forced tool_choice pydantic-ai uses for structured output, so
    # the L2 agent returns JSON text we parse. The analyze_trace tool (optional
    # tool_choice) is unaffected.
    h2 = provider.build_agent(
        level=2,
        model=a.global_model or None,
        system_prompt=_L2_SYSTEM,
        tools=[analyze_trace],
        output_type=str,
        name="cost-analyst",
    )
    user = json.dumps({"digest": digest, "candidate_traces": candidates})
    raw = str(
        run_agent(
            h2,
            lambda: h2.run_sync(user).output,
            label="cost-analyst",
            project=a.langfuse_project_id,
        )
    )
    return _parse_analysis(raw)


def _parse_analysis(raw: str) -> Analysis:
    """Parse the level-2 agent's JSON reply into an :class:`Analysis`.

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


def _file_ticket(a: AnalystConfig, ticket: TicketRequest) -> dict[str, Any]:
    """File *ticket* on the board via the agent-comm broker (pull/mailbox).

    Synchronous (the agent-comm pull client is sync); the caller runs it in a
    thread. Returns the board agent's reply body, or an ``error`` entry.
    """
    from robotsix_agent_comm.sdk.agent import Agent
    from robotsix_agent_comm.transport.brokered import create_transport_pair

    # Only reached when can_file_tickets is True (host + token are set); the
    # ``or ""`` just narrows str | None → str for the type checker.
    registry, transport = create_transport_pair(
        "brokered",
        broker_host=a.broker_host or "",
        broker_port=a.broker_port,
        broker_scheme=a.broker_scheme,
        broker_token=a.broker_token or "",
    )
    # Ask the board MANAGER (not the dumb responder) in natural language, so it
    # deduplicates and records the source. The manager is an LLM agent, so allow
    # a generous timeout. (It can ask back / we could continue the exchange —
    # the broker + the manager's memory support multi-turn — but one self-
    # completing request is enough here.)
    agent = Agent(
        "cost-analyst", registry, transport=transport, pull=True, timeout=180.0
    )
    message = (
        f"Please file a board ticket on the {a.board_repo_id} board.\n"
        f"Title: {ticket.title}\n\nDescription:\n{ticket.description}\n\n"
        "First check the existing open tickets — if one already covers this "
        "issue, comment on / update that one instead of creating a duplicate. "
        "Reply with the ticket id (created or existing) and what you did."
    )
    try:
        with agent:
            reply = agent.send_request(
                a.board_manager_id, {"message": message}, timeout=180.0
            )
    except Exception as exc:  # noqa: BLE001 — surface as status, not a crash
        logger.warning("ticket filing failed: %s", exc)
        return {"filed": False, "error": str(exc)}
    body = getattr(reply, "body", None)
    return {"filed": True, "reply": body}


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
        "all", a.window_hours, a.max_trace_analyses
    )
    details: dict[str, dict[str, Any]] = {}
    for c in candidates:
        with contextlib.suppress(Exception):
            details[c["trace_id"]] = await service.trace_detail(
                c["project"], c["trace_id"]
            )

    analysis = await asyncio.to_thread(_run_agents, a, digest, candidates, details)

    ticket_result: dict[str, Any] | None = None
    if analysis.ticket is not None and a.can_file_tickets:
        ticket_result = await asyncio.to_thread(_file_ticket, a, analysis.ticket)

    out: dict[str, Any] = {
        "enabled": True,
        "generated_at": datetime.now(UTC).isoformat(),
        "window_hours": a.window_hours,
        "summary": analysis.summary,
        "proposals": [p.model_dump() for p in analysis.proposals],
        "analyzed_traces": candidates,
        "ticket": analysis.ticket.model_dump() if analysis.ticket else None,
        "ticket_result": ticket_result,
    }
    _store_path().write_text(json.dumps(out, indent=2))
    return out
