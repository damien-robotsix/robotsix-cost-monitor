"""Contract test: AnalystKind enum members cross-tier consistency.

Ensures that AnalystKind members are consistently referenced across:
- routes.py (POST handler branches)
- analyst.js (frontend JavaScript strings and makeTargeted calls)
- analyst.html (HTML element IDs)
- test_routes.py (test URL literals)

A rename of an enum member that misses any of these locations is caught at
``pytest`` time rather than at runtime.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

# ---------------------------------------------------------------------------
# Mock ``structlog`` before importing ``robotsix_cost_monitor.analyst``
# (which transitively imports ``.service`` → ``structlog``).
# ---------------------------------------------------------------------------
_orig_structlog = sys.modules.get("structlog")
sys.modules["structlog"] = MagicMock()

from robotsix_cost_monitor.analyst import AnalystKind  # noqa: E402

# Restore the original sys.modules entry so the mock does not leak.
if _orig_structlog is not None:
    sys.modules["structlog"] = _orig_structlog
else:
    sys.modules.pop("structlog", None)

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC = REPO_ROOT / "src" / "robotsix_cost_monitor"
TESTS = REPO_ROOT / "tests" / "robotsix_cost_monitor"


# ============================================================================
# 1. Source of truth
# ============================================================================


class TestAnalystKindSourceOfTruth:
    """The AnalystKind enum is the authoritative list of analysis scopes."""

    def test_has_three_members(self) -> None:
        values = {m.value for m in AnalystKind}
        assert values == {"ticket", "stage", "fleet"}, (
            f"Unexpected AnalystKind members: {values}"
        )


# ============================================================================
# 2. Route handlers (routes.py)
# ============================================================================


class TestAnalystKindInRoutes:
    """Every AnalystKind member must have an explicit branch in the POST handler."""

    def test_every_kind_branched_in_post_handler(self) -> None:
        routes_text = (SRC / "routes.py").read_text()
        for member in AnalystKind:
            assert f"AnalystKind.{member.name}" in routes_text, (
                f"Missing AnalysKind.{member.name} branch in routes.py "
                f"POST /api/analyst/run/{{kind}} handler"
            )

    def test_post_route_path_uses_kind_parameter(self) -> None:
        routes_text = (SRC / "routes.py").read_text()
        assert '"/api/analyst/run/{kind}"' in routes_text, (
            "Missing POST /api/analyst/run/{kind} route decorator"
        )

    def test_get_route_path_uses_kind_parameter(self) -> None:
        routes_text = (SRC / "routes.py").read_text()
        assert '"/api/analyst/{kind}"' in routes_text, (
            "Missing GET /api/analyst/{kind} route decorator"
        )


# ============================================================================
# 3. Frontend JavaScript (analyst.js)
# ============================================================================


class TestAnalystKindInJavaScript:
    """Every AnalystKind string value must appear in analyst.js."""

    def test_every_kind_value_in_js(self) -> None:
        js_text = (SRC / "web" / "static" / "analyst.js").read_text()
        for member in AnalystKind:
            assert member.value in js_text, (
                f"Missing '{member.value}' string in analyst.js"
            )

    def test_make_targeted_calls_use_ticket_and_stage(self) -> None:
        """makeTargeted must be called for ticket and stage (frontend-wired kinds)."""
        js_text = (SRC / "web" / "static" / "analyst.js").read_text()
        assert (
            "makeTargeted('ticket'" in js_text or 'makeTargeted("ticket"' in js_text
        ), "Missing makeTargeted('ticket', …) call in analyst.js"
        assert "makeTargeted('stage'" in js_text or 'makeTargeted("stage"' in js_text, (
            "Missing makeTargeted('stage', …) call in analyst.js"
        )


# ============================================================================
# 4. Frontend HTML (analyst.html)
# ============================================================================


class TestAnalystKindInHTML:
    """ticket and stage have dedicated frontend panels; fleet does not."""

    def test_ticket_stage_element_ids_present(self) -> None:
        html_text = (SRC / "web" / "analyst.html").read_text()
        for kind in ("ticket", "stage"):
            assert f'id="{kind}-btn"' in html_text, (
                f"Missing id='{kind}-btn' in analyst.html"
            )
            assert f'id="{kind}-analysis"' in html_text, (
                f"Missing id='{kind}-analysis' in analyst.html"
            )

    def test_fleet_has_no_panel_ids(self) -> None:
        """Fleet uses run-btn / run-meta; it must not have dedicated panel IDs."""
        html_text = (SRC / "web" / "analyst.html").read_text()
        assert 'id="fleet-btn"' not in html_text, (
            "Unexpected id='fleet-btn' in analyst.html — fleet uses run-btn"
        )
        assert 'id="fleet-analysis"' not in html_text, (
            "Unexpected id='fleet-analysis' in analyst.html — fleet uses run-meta"
        )


# ============================================================================
# 5. Test URL literals (test_routes.py)
# ============================================================================


class TestAnalystKindInTestRoutes:
    """Every kind must have GET and POST test URLs in test_routes.py."""

    def test_every_kind_has_get_test_url(self) -> None:
        test_text = (TESTS / "test_routes.py").read_text()
        for member in AnalystKind:
            assert f"/api/analyst/{member.value}" in test_text, (
                f"Missing GET /api/analyst/{member.value} URL in test_routes.py"
            )

    def test_every_kind_has_post_test_url(self) -> None:
        test_text = (TESTS / "test_routes.py").read_text()
        for member in AnalystKind:
            assert f"/api/analyst/run/{member.value}" in test_text, (
                f"Missing POST /api/analyst/run/{member.value} URL in test_routes.py"
            )
