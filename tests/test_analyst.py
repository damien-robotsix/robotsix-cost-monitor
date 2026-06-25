"""Offline tests for the cost-analyst orchestration (no LLM / network).

The level-2/level-3 llmio agents and the agent-comm client are stubbed; these
tests exercise the wiring around them: the disabled path, the stored output
shape, and the proposal-filing branch (the board manager owns ticket creation).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock

import pytest
from conftest import _config

from robotsix_cost_monitor import analyst as analyst_mod
from robotsix_cost_monitor.analyst import (
    Analysis,
    Proposal,
    _parse_analysis,
    run_analyst,
)


def test_parse_analysis_plain_json() -> None:
    a = _parse_analysis(
        '{"summary": "s", "proposals": [{"title": "t", "rationale": "r"}]}'
    )
    assert a.summary == "s"
    assert a.proposals[0].title == "t"


def test_parse_analysis_code_fenced() -> None:
    a = _parse_analysis('```json\n{"summary": "z", "proposals": []}\n```')
    assert a.summary == "z"
    assert a.proposals == []


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
        self, slug: str, hours: int, limit: int, *, per_agent: int = 1
    ) -> list[dict[str, Any]]:
        return [{"trace_id": "t1", "project": "p", "name": "explore", "cost": 9.0}]

    async def trace_detail(self, project: str, trace_id: str) -> dict[str, Any]:
        return {"id": trace_id, "observations": []}

    async def top_ticket(self, slug: str | None, hours: int) -> dict[str, Any] | None:
        return {
            "session_id": "demo · 20250101T000000Z-test-1a2b",
            "cost": 45.0,
            "count": 7,
            "by_stage": [{"name": "implement", "cost": 30.0, "count": 3}],
            "traces": [
                {"trace_id": "t2", "name": "implement", "cost": 15.0},
                {"trace_id": "t3", "name": "review", "cost": 12.0},
            ],
        }

    async def top_stage(
        self, slug: str | None, hours: int, sample: int = 8
    ) -> dict[str, Any] | None:
        return {
            "stage": "implement",
            "cost": 120.0,
            "count": 15,
            "pct_of_traced": 28.5,
            "traces": [
                {"trace_id": "t4", "project": "p", "cost": 25.0},
                {"trace_id": "t5", "project": "p", "cost": 18.0},
            ],
        }


class TestSplitSession:
    def test_board_and_ticket(self) -> None:
        board, tid = analyst_mod._split_session("demo · 20250101T000000Z-test-1a2b")
        assert board == "demo"
        assert tid == "20250101T000000Z-test-1a2b"

    def test_no_separator(self) -> None:
        board, tid = analyst_mod._split_session("just_a_session_id")
        assert board == ""
        assert tid == "just_a_session_id"

    def test_multiple_separators_splits_first_only(self) -> None:
        board, tid = analyst_mod._split_session("a · b · c")
        assert board == "a"
        assert tid == "b · c"

    def test_leading_trailing_whitespace(self) -> None:
        board, tid = analyst_mod._split_session("  foo   ·   bar  ")
        assert board == "foo"
        assert tid == "bar"


class TestLoadTargetedAnalysis:
    def test_no_file_returns_default(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("COST_MONITOR_DATA", str(tmp_path))
        result = analyst_mod.load_targeted_analysis("ticket")
        assert result == {"generated_at": None}

    def test_valid_json(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("COST_MONITOR_DATA", str(tmp_path))
        d = tmp_path / "analyst"
        d.mkdir()
        (d / "ticket.json").write_text(
            '{"generated_at": "2025-01-01T00:00:00Z", "summary": "ok"}'
        )
        result = analyst_mod.load_targeted_analysis("ticket")
        assert result["generated_at"] == "2025-01-01T00:00:00Z"
        assert result["summary"] == "ok"

    def test_invalid_json_returns_default(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("COST_MONITOR_DATA", str(tmp_path))
        d = tmp_path / "analyst"
        d.mkdir()
        (d / "ticket.json").write_text("not json")
        result = analyst_mod.load_targeted_analysis("ticket")
        assert result == {"generated_at": None}


async def test_disabled_without_key() -> None:
    out = await run_analyst(_config(), _FakeService())  # type: ignore[arg-type]
    assert out == {
        "enabled": False,
        "detail": "analyst.openrouter_key not configured",
    }


async def test_run_stores_proposals_and_files(
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
    )
    monkeypatch.setattr(analyst_mod, "_run_agents", lambda *a, **k: (analysis, []))
    filed: dict[str, Any] = {}

    def _fake_file(a: Any, analysis: Analysis) -> dict[str, Any]:
        filed["analysis"] = analysis
        return {"filed": True, "reply": {"reply": "created T-9 from proposal 1"}}

    monkeypatch.setattr(analyst_mod, "_file_proposals", _fake_file)

    cfg = _config(
        openrouter_key="sk-x",
        broker_host="ai-broker.example",
        broker_token="tok",
    )
    out = await run_analyst(cfg, _FakeService())  # type: ignore[arg-type]

    assert out["enabled"] is True
    assert out["proposals"][0]["title"] == "Drop explore to L2"
    assert out["filing_result"] == {
        "filed": True,
        "reply": {"reply": "created T-9 from proposal 1"},
    }
    # The whole analysis (all proposals) is handed to the board manager.
    assert filed["analysis"].proposals[0].title == "Drop explore to L2"
    # Persisted for the dashboard / analyst page.
    stored = json.loads((tmp_path / "analyst" / "proposals.json").read_text())
    assert stored["proposals"][0]["title"] == "Drop explore to L2"


async def test_no_filing_when_broker_unconfigured(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("COST_MONITOR_DATA", str(tmp_path))
    analysis = Analysis(proposals=[Proposal(title="x", rationale="y")])
    monkeypatch.setattr(analyst_mod, "_run_agents", lambda *a, **k: (analysis, []))
    called = {"n": 0}
    monkeypatch.setattr(
        analyst_mod, "_file_proposals", lambda *a, **k: called.__setitem__("n", 1)
    )

    # openrouter_key set (enabled) but no broker → proposals are not filed.
    out = await run_analyst(_config(openrouter_key="sk-x"), _FakeService())  # type: ignore[arg-type]
    assert called["n"] == 0
    assert out["filing_result"] is None


async def test_build_digest_shape() -> None:
    svc = _FakeService()
    cfg = _config()
    digest = await analyst_mod.build_digest(svc, 24, cfg)  # type: ignore[arg-type]
    assert digest["window_hours"] == 24
    assert digest["total_cost"] == 12.0
    assert isinstance(digest["stages"], list)
    assert digest["stages"][0]["name"] == "explore"
    assert "pct" in digest["stages"][0]
    assert "avg_per_trace" in digest["stages"][0]


# -- targeted (ticket / stage) analyst tests --------------------------------


async def test_run_ticket_analyst_disabled() -> None:
    out = await analyst_mod.run_ticket_analyst(_config(), _FakeService())  # type: ignore[arg-type]
    assert out == {
        "enabled": False,
        "detail": "analyst.openrouter_key not configured",
    }


async def test_run_ticket_analyst_no_top_ticket(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("COST_MONITOR_DATA", str(tmp_path))

    svc = _FakeService()
    object.__setattr__(svc, "top_ticket", AsyncMock(return_value=None))

    out = await analyst_mod.run_ticket_analyst(
        _config(openrouter_key="sk-x"),
        svc,  # type: ignore[arg-type]
    )
    assert out["enabled"] is True
    assert out["detail"] == "no ticket sessions in the window"


async def test_run_ticket_analyst_normal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("COST_MONITOR_DATA", str(tmp_path))

    async def _fake_opus_and_file(
        a: Any,
        system_prompt: str,
        name: str,
        payload: str,
        out_prefix: str,
        extra_out: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return {
            "enabled": True,
            "generated_at": "2025-01-01T00:00:00Z",
            "summary": "test summary",
            "proposals": [
                {"title": "Reduce tier", "rationale": "...", "estimated_saving": "$10"}
            ],
            "filing_result": None,
            **(extra_out or {}),
        }

    monkeypatch.setattr(analyst_mod, "_run_opus_analysis_and_file", _fake_opus_and_file)

    out = await analyst_mod.run_ticket_analyst(
        _config(openrouter_key="sk-x"),
        _FakeService(),  # type: ignore[arg-type]
    )
    assert out["enabled"] is True
    assert out["summary"] == "test summary"
    assert out["proposals"][0]["title"] == "Reduce tier"
    assert out["ticket_id"] == "20250101T000000Z-test-1a2b"


async def test_run_ticket_analyst_no_board_context_when_no_broker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("COST_MONITOR_DATA", str(tmp_path))

    async def _fake_opus_and_file(
        a: Any,
        **kw: Any,
    ) -> dict[str, Any]:
        return {
            "enabled": True,
            "generated_at": "2025-01-01T00:00:00Z",
            "summary": "ok",
            "proposals": [],
            "filing_result": None,
            "history_available": kw.get("extra_out", {}).get("history_available", None),
        }

    monkeypatch.setattr(analyst_mod, "_run_opus_analysis_and_file", _fake_opus_and_file)

    # openrouter_key set but no broker → context fetch skipped, history_available=False
    out = await analyst_mod.run_ticket_analyst(
        _config(openrouter_key="sk-x"),
        _FakeService(),  # type: ignore[arg-type]
    )
    assert out["history_available"] is False


async def test_run_stage_analyst_disabled() -> None:
    out = await analyst_mod.run_stage_analyst(_config(), _FakeService())  # type: ignore[arg-type]
    assert out == {
        "enabled": False,
        "detail": "analyst.openrouter_key not configured",
    }


async def test_run_stage_analyst_no_top_stage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("COST_MONITOR_DATA", str(tmp_path))

    svc = _FakeService()
    object.__setattr__(svc, "top_stage", AsyncMock(return_value=None))

    out = await analyst_mod.run_stage_analyst(
        _config(openrouter_key="sk-x"),
        svc,  # type: ignore[arg-type]
    )
    assert out["enabled"] is True
    assert out["detail"] == "no traces in the window"


async def test_run_stage_analyst_normal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("COST_MONITOR_DATA", str(tmp_path))

    async def _fake_opus_and_file(
        a: Any,
        system_prompt: str,
        name: str,
        payload: str,
        out_prefix: str,
        extra_out: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return {
            "enabled": True,
            "generated_at": "2025-01-01T00:00:00Z",
            "summary": "stage summary",
            "proposals": [
                {"title": "Cache prompts", "rationale": "...", "estimated_saving": "$5"}
            ],
            "filing_result": None,
            **(extra_out or {}),
        }

    monkeypatch.setattr(analyst_mod, "_run_opus_analysis_and_file", _fake_opus_and_file)

    out = await analyst_mod.run_stage_analyst(
        _config(openrouter_key="sk-x"),
        _FakeService(),  # type: ignore[arg-type]
    )
    assert out["enabled"] is True
    assert out["summary"] == "stage summary"
    assert out["stage"] == "implement"
    assert out["sample_size"] == 2


def test_load_proposals_no_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("COST_MONITOR_DATA", str(tmp_path))
    result = analyst_mod.load_proposals()
    assert result == {"generated_at": None, "proposals": []}


def test_load_proposals_valid(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COST_MONITOR_DATA", str(tmp_path))
    d = tmp_path / "analyst"
    d.mkdir()
    (d / "proposals.json").write_text(
        '{"generated_at": "2025-01-01T00:00:00Z", "proposals": [{"title": "T"}]}'
    )
    result = analyst_mod.load_proposals()
    assert result["generated_at"] == "2025-01-01T00:00:00Z"
    assert result["proposals"][0]["title"] == "T"


async def test_run_opus_analysis_and_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("COST_MONITOR_DATA", str(tmp_path))

    analysis = Analysis(
        summary="test",
        proposals=[Proposal(title="P1", rationale="r")],
    )
    monkeypatch.setattr(
        analyst_mod,
        "_opus_analysis",
        lambda *a, **kw: analysis,
    )
    monkeypatch.setattr(
        analyst_mod,
        "_file_proposals",
        lambda a, analysis: {"filed": True, "reply": {"ok": True}},
    )

    a = _config(
        openrouter_key="sk-x",
        broker_host="ai-broker.example",
        broker_token="tok",
    ).settings.analyst

    out = await analyst_mod._run_opus_analysis_and_file(
        a,
        system_prompt="test prompt",
        name="test",
        payload="{}",
        out_prefix="test_kind",
        extra_out={"extra": "data"},
    )
    assert out["enabled"] is True
    assert out["summary"] == "test"
    assert out["proposals"][0]["title"] == "P1"
    assert out["filing_result"] == {"filed": True, "reply": {"ok": True}}
    assert out["extra"] == "data"


async def test_run_opus_analysis_and_file_no_broker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("COST_MONITOR_DATA", str(tmp_path))

    analysis = Analysis(
        summary="test",
        proposals=[Proposal(title="P1", rationale="r")],
    )
    monkeypatch.setattr(
        analyst_mod,
        "_opus_analysis",
        lambda *a, **kw: analysis,
    )

    a = _config(openrouter_key="sk-x").settings.analyst  # no broker config

    out = await analyst_mod._run_opus_analysis_and_file(
        a,
        system_prompt="test prompt",
        name="test",
        payload="{}",
        out_prefix="test_kind",
    )
    assert out["enabled"] is True
    assert out["proposals"][0]["title"] == "P1"
    assert out["filing_result"] is None


class TestMaybeSetupTracing:
    def test_noop_when_no_keys(self) -> None:
        a = _config().settings.analyst
        # Should not raise; no langfuse keys → noop
        analyst_mod._maybe_setup_tracing(a)

    def test_calls_setup_when_keys_present(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        a = _config(
            openrouter_key="sk-x",
            langfuse_public_key="pk-test",
            langfuse_secret_key="sk-test",
            langfuse_base_url="http://localhost",
            langfuse_project_id="test-proj",
        ).settings.analyst
        called: dict[str, Any] = {}

        def fake_setup(**kw: Any) -> None:
            called.update(kw)

        monkeypatch.setattr(
            analyst_mod,
            "setup_langfuse_tracing",
            fake_setup,
            raising=False,
        )
        # Also need to mock the import inside _maybe_setup_tracing
        import sys
        import types

        fake_tracing = types.ModuleType("robotsix_llmio.core.tracing")
        fake_tracing.setup_langfuse_tracing = fake_setup
        fake_core = types.ModuleType("robotsix_llmio.core")
        fake_core.tracing = fake_tracing
        fake_llmio = types.ModuleType("robotsix_llmio")
        fake_llmio.core = fake_core
        monkeypatch.setitem(sys.modules, "robotsix_llmio", fake_llmio)
        monkeypatch.setitem(sys.modules, "robotsix_llmio.core", fake_core)
        monkeypatch.setitem(sys.modules, "robotsix_llmio.core.tracing", fake_tracing)
        analyst_mod._maybe_setup_tracing(a)
        assert called.get("public_key") == "pk-test"
        assert called.get("secret_key") == "sk-test"
