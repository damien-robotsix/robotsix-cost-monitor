"""Component-aware project resolution.

A component owns one Langfuse project per LLM function, so a selector has to
resolve at two levels — component and project — without any per-component code.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

from robotsix_cost_monitor.clients.models import RegistryProject
from robotsix_cost_monitor.service import CostService
from tests.robotsix_cost_monitor.helpers import _proj, _svc


def _multi() -> CostService:
    """Service with one two-project component and one single-project component."""
    return _svc(
        _proj("robotsix-chat", component="chat"),
        _proj("robotsix-chat-cognee", component="chat"),
        _proj("robotsix-mill", component="mill"),
    )


class TestComponentGrouping:
    def test_components_groups_projects_by_owner(self) -> None:
        svc = _multi()
        groups = {k: [p.slug for p in v] for k, v in svc.components().items()}
        assert groups == {
            "chat": ["robotsix-chat", "robotsix-chat-cognee"],
            "mill": ["robotsix-mill"],
        }

    def test_project_without_component_groups_under_its_own_slug(self) -> None:
        """An unknown owner must not collapse projects into one bucket."""
        svc = _svc(_proj("orphan-a", component=""), _proj("orphan-b", component=""))
        groups = {k: [p.slug for p in v] for k, v in svc.components().items()}
        assert groups == {"orphan-a": ["orphan-a"], "orphan-b": ["orphan-b"]}


class TestSelectorResolution:
    def test_component_id_selects_all_its_projects(self) -> None:
        svc = _multi()
        assert [p.slug for p in svc._projects("chat")] == [
            "robotsix-chat",
            "robotsix-chat-cognee",
        ]

    def test_project_slug_selects_just_that_project(self) -> None:
        svc = _multi()
        assert [p.slug for p in svc._projects("robotsix-chat")] == ["robotsix-chat"]

    def test_all_selects_everything(self) -> None:
        svc = _multi()
        assert len(svc._projects("all")) == 3
        assert len(svc._projects(None)) == 3

    def test_unknown_selector_selects_nothing(self) -> None:
        assert _multi()._projects("ghost") == []

    def test_project_slug_wins_over_component_id_on_collision(self) -> None:
        """A project is the more specific thing, so it takes precedence.

        Guards the single-project component case, where a component and its
        only project commonly share a name.
        """
        svc = _svc(
            _proj("mill", component="mill"),
            _proj("other", component="mill"),
        )
        assert [p.slug for p in svc._projects("mill")] == ["mill"]


class TestSummaryRollup:
    async def test_summary_rolls_projects_up_by_component(self) -> None:
        svc = _multi()
        for slug, cost in (
            ("robotsix-chat", 10.0),
            ("robotsix-chat-cognee", 2.0),
            ("robotsix-mill", 5.0),
        ):
            client = svc._clients[slug]
            object.__setattr__(
                client,
                "fetch_model_usage_window",
                AsyncMock(return_value=[{"model": "m", "cost": cost}]),
            )
            object.__setattr__(
                client, "fetch_trace_count_window", AsyncMock(return_value=1)
            )

        result = await svc.summary("all", 24)
        assert result["total_cost"] == 17.0
        comps = {c["component"]: c for c in result["components"]}
        assert comps["chat"]["cost"] == 12.0
        assert comps["chat"]["trace_count"] == 2
        assert [p["slug"] for p in comps["chat"]["projects"]] == [
            "robotsix-chat",
            "robotsix-chat-cognee",
        ]
        assert comps["mill"]["cost"] == 5.0
        # Ordered by spend so the dashboard leads with the expensive component.
        assert [c["component"] for c in result["components"]] == ["chat", "mill"]


class TestRegistryProjectDefaults:
    def test_component_id_defaults_to_empty(self) -> None:
        """Older registry payloads without component_id must still validate."""
        p = RegistryProject(
            name="x", slug="x", langfuse_public_key="pk", langfuse_secret_key="sk"
        )
        assert p.component_id == ""
        assert p.openrouter_key is None
