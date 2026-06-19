"""Offline tests for the cost-analyst orchestration (no LLM / network).

The level-2/level-3 llmio agents and the agent-comm ticket client are stubbed;
these tests exercise the wiring around them: the disabled path, the digest +
candidate gathering, the stored output shape, and the ticket-filing branch.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from conftest import _config

from robotsix_cost_monitor import analyst as analyst_mod
from robotsix_cost_monitor.analyst import (
    Analysis,
    Proposal,
    TicketRequest,
    _parse_analysis,
    run_analyst,
)


def test_parse_analysis_plain_json() -> None:
    a = _parse_analysis(
        '{"summary": "s", "proposals": [{"title": "t", "rationale": "r"}], '
        '"ticket": {"title": "x", "description": "y"}}'
    )
    assert a.summary == "s"
    assert a.proposals[0].title == "t"
    assert a.ticket is not None and a.ticket.title == "x"


def test_parse_analysis_code_fenced() -> None:
    a = _parse_analysis(
        '```json\n{"summary": "z", "proposals": [], "ticket": null}\n```'
    )
    assert a.summary == "z"
    assert a.proposals == []
    assert a.ticket is None


def test_parse_analysis_garbage_keeps_text() -> None:
    a = _parse_analysis("not json at all")
    assert a.summary == "not json at all"
    assert a.proposals == []


class _FakeService:
    """Minimal CostService stand-in for the analyst's calls."""

    async def summary(self, slug: str, hours: int) -> dict[str, Any]:
        return {"total_cost": 12.0, "projects": []}

    async def by_agent(self, slug: str, hours: int) -> list[dict[str, Any]]:
        return [{"name": "explore", "cost": 9.0, "count": 3}]

    async def highlights(self, slug: str, hours: int) -> dict[str, Any]:
        return {"most_expensive_trace": None, "most_expensive_session": None}

    async def candidate_traces(
        self, slug: str, hours: int, limit: int
    ) -> list[dict[str, Any]]:
        return [{"trace_id": "t1", "project": "p", "name": "explore", "cost": 9.0}]

    async def trace_detail(self, project: str, trace_id: str) -> dict[str, Any]:
        return {"id": trace_id, "observations": []}


async def test_disabled_without_key() -> None:
    out = await run_analyst(_config(), _FakeService())  # type: ignore[arg-type]
    assert out == {
        "enabled": False,
        "detail": "analyst.openrouter_key not configured",
    }


async def test_run_stores_proposals_and_files_ticket(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("COST_MONITOR_DATA", str(tmp_path))

    analysis = Analysis(
        summary="explore is over-provisioned",
        proposals=[
            Proposal(
                title="Drop explore to L2", rationale="...", estimated_saving="$5/day"
            )
        ],
        ticket=TicketRequest(title="Explore cost spike", description="evidence + fix"),
    )
    monkeypatch.setattr(analyst_mod, "_run_agents", lambda *a, **k: analysis)
    filed: dict[str, Any] = {}

    def _fake_file(a: Any, ticket: TicketRequest) -> dict[str, Any]:
        filed["ticket"] = ticket
        return {"filed": True, "reply": {"id": "T-9"}}

    monkeypatch.setattr(analyst_mod, "_file_ticket", _fake_file)

    cfg = _config(
        openrouter_key="sk-x",
        broker_host="ai-broker.example",
        broker_token="tok",
    )
    out = await run_analyst(cfg, _FakeService())  # type: ignore[arg-type]

    assert out["enabled"] is True
    assert out["proposals"][0]["title"] == "Drop explore to L2"
    assert out["ticket"]["title"] == "Explore cost spike"
    assert out["ticket_result"] == {"filed": True, "reply": {"id": "T-9"}}
    assert filed["ticket"].title == "Explore cost spike"
    # Persisted for the dashboard.
    stored = json.loads((tmp_path / "analyst" / "proposals.json").read_text())
    assert stored["proposals"][0]["title"] == "Drop explore to L2"


async def test_no_ticket_when_broker_unconfigured(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("COST_MONITOR_DATA", str(tmp_path))
    analysis = Analysis(
        proposals=[],
        ticket=TicketRequest(title="x", description="y"),
    )
    monkeypatch.setattr(analyst_mod, "_run_agents", lambda *a, **k: analysis)
    called = {"n": 0}
    monkeypatch.setattr(
        analyst_mod, "_file_ticket", lambda *a, **k: called.__setitem__("n", 1)
    )

    # openrouter_key set (enabled) but no broker → ticket is not filed.
    out = await run_analyst(_config(openrouter_key="sk-x"), _FakeService())  # type: ignore[arg-type]
    assert called["n"] == 0
    assert out["ticket_result"] is None
