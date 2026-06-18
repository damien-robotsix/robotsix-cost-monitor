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
    "description with evidence and a concrete fix); otherwise leave it null."
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

    provider = get_provider(provider="openrouter", api_key=a.openrouter_key)

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
            model=a.trace_model,
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

    h2 = provider.build_agent(
        level=2,
        model=a.global_model,
        system_prompt=_L2_SYSTEM,
        tools=[analyze_trace],
        output_type=Analysis,
        name="cost-analyst",
    )
    user = json.dumps({"digest": digest, "candidate_traces": candidates})
    return cast(
        "Analysis",
        run_agent(
            h2,
            lambda: h2.run_sync(user).output,
            label="cost-analyst",
            project=a.langfuse_project_id,
        ),
    )


def _file_ticket(a: AnalystConfig, ticket: TicketRequest) -> dict[str, Any]:
    """File *ticket* on the board via the agent-comm broker (pull/mailbox).

    Synchronous (the agent-comm pull client is sync); the caller runs it in a
    thread. Returns the board agent's reply body, or an ``error`` entry.
    """
    from robotsix_agent_comm.sdk.agent import Agent
    from robotsix_agent_comm.transport.brokered import create_transport_pair

    registry, transport = create_transport_pair(
        "brokered",
        broker_host=a.broker_host,
        broker_port=a.broker_port,
        broker_scheme=a.broker_scheme,
        broker_token=a.broker_token,
    )
    agent = Agent(
        "cost-analyst", registry, transport=transport, pull=True, timeout=30.0
    )
    try:
        with agent:
            reply = agent.send_request(
                a.board_agent_id,
                {
                    "op": "create_ticket",
                    "args": {
                        "title": ticket.title,
                        "description": ticket.description,
                        "repo_id": a.board_repo_id,
                    },
                },
                timeout=30.0,
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

    digest = await build_digest(service, a.window_hours)

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
