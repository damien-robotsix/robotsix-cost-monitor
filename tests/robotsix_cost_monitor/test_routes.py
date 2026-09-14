"""Unit tests for route helpers, dependency providers, and route-handler edge
cases from ``src/robotsix_cost_monitor/routes.py``.

These tests avoid importing ``create_app`` (which transitively requires the
optional ``robotsix-llmio`` package). Instead, they build a minimal FastAPI
app directly, mount the router from ``routes``, and wire the shared exception
handlers from ``robotsix_http.fastapi`` (plus the ``CostMonitorError`` adapter)
exactly as ``create_app`` does.
"""

from __future__ import annotations

import sys
from typing import cast
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from fastapi import FastAPI, Request, Response
from fastapi.testclient import TestClient
from robotsix_http.fastapi import (
    DomainError,
    create_health_router,
    domain_error_handler,
    register_exception_handlers,
)

from robotsix_cost_monitor.exceptions import CostMonitorError

# ---------------------------------------------------------------------------
# Mock the optional ``robotsix-llmio`` package before importing
# ``robotsix_cost_monitor.routes`` (which transitively imports
# ``robotsix_cost_monitor.reconcile`` → ``robotsix_llmio.openrouter``).
# This keeps the test suite runnable when ``robotsix-llmio`` is not installed.
#
# Save and restore the original sys.modules entries so that other test
# modules that need the real robotsix_llmio are
# not broken by this mock leaking across the whole session.
# ---------------------------------------------------------------------------
_orig_llmio = sys.modules.get("robotsix_llmio")
_orig_llmio_openrouter = sys.modules.get("robotsix_llmio.openrouter")
_orig_llmio_core = sys.modules.get("robotsix_llmio.core")
_orig_llmio_core_langfuse = sys.modules.get("robotsix_llmio.core.langfuse_async_client")

_llmio = MagicMock()
_llmio_openrouter = MagicMock()
_llmio_openrouter.OpenRouterKeyCostSource = MagicMock()
_llmio_core = MagicMock()
_llmio_core_langfuse = MagicMock()
_llmio_core_langfuse.AsyncLangfuseReadClient = MagicMock
sys.modules["robotsix_llmio"] = _llmio
sys.modules["robotsix_llmio.openrouter"] = _llmio_openrouter
sys.modules["robotsix_llmio.core"] = _llmio_core
sys.modules["robotsix_llmio.core.langfuse_async_client"] = _llmio_core_langfuse

from robotsix_cost_monitor.config import Config  # noqa: E402
from robotsix_cost_monitor.routes import (  # noqa: E402
    MAX_WINDOW_HOURS,
    _window,
    get_config,
    get_service,
    router,
)
from tests.robotsix_cost_monitor.helpers import _config, _proj  # noqa: E402

# Restore the original sys.modules entries so the mock does not leak.
if _orig_llmio is not None:
    sys.modules["robotsix_llmio"] = _orig_llmio
else:
    sys.modules.pop("robotsix_llmio", None)
if _orig_llmio_openrouter is not None:
    sys.modules["robotsix_llmio.openrouter"] = _orig_llmio_openrouter
else:
    sys.modules.pop("robotsix_llmio.openrouter", None)
if _orig_llmio_core is not None:
    sys.modules["robotsix_llmio.core"] = _orig_llmio_core
else:
    sys.modules.pop("robotsix_llmio.core", None)
if _orig_llmio_core_langfuse is not None:
    sys.modules["robotsix_llmio.core.langfuse_async_client"] = _orig_llmio_core_langfuse
else:
    sys.modules.pop("robotsix_llmio.core.langfuse_async_client", None)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_request(app: FastAPI) -> Request:
    """Build a bare Request whose ``app`` is the given FastAPI instance."""
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": [],
        "app": app,
    }
    return Request(scope)


async def _cost_monitor_error_handler(request: Request, exc: Exception) -> Response:
    """Mirror ``app._cost_monitor_error_handler``: map onto ``DomainError``."""
    err = cast(CostMonitorError, exc)
    return await domain_error_handler(
        request,
        DomainError(err.detail, code=err.error_code, status_code=err.status_code),
    )


def _client(
    cfg: Config | None = None,
    service: object | None = None,
    **test_client_kwargs: object,
) -> TestClient:
    """Build a TestClient against a minimal FastAPI app that mounts the
    production router, the shared health router, and the shared exception
    handlers.

    ``app.state.config`` and ``app.state.service`` are populated from the
    arguments so that ``Depends(get_config)`` / ``Depends(get_service)``
    resolve correctly.

    Extra keyword arguments are forwarded to ``TestClient`` (e.g.
    ``raise_server_exceptions=False`` for testing the 500 error path).
    """
    app = FastAPI()
    app.state.config = cfg or _config()
    app.state.service = service if service is not None else Mock()
    register_exception_handlers(app)
    app.add_exception_handler(CostMonitorError, _cost_monitor_error_handler)
    app.include_router(create_health_router())
    app.include_router(router)
    return TestClient(app, **test_client_kwargs)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Dependency providers
# ---------------------------------------------------------------------------


def test_get_config_returns_app_state_config() -> None:
    app = FastAPI()
    app.state.config = cfg = _config()
    req = _make_request(app)
    assert get_config(req) is cfg


def test_get_service_returns_app_state_service() -> None:
    app = FastAPI()
    app.state.service = svc = object()
    req = _make_request(app)
    assert get_service(req) is svc


# ---------------------------------------------------------------------------
# _window
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "hours,expected",
    [
        (24, 24),  # nonzero → supplied hours
        (0, 168),  # zero → config default
        (None, 168),  # None → config default
        (169, 168),  # above the ceiling → clamped
        (10**9, 168),  # absurd request → clamped, not honoured
    ],
    ids=[
        "nonzero",
        "zero_falls_back",
        "none_falls_back",
        "above_max_clamped",
        "absurd_clamped",
    ],
)
def test_window(hours: int | None, expected: int) -> None:
    cfg = _config(default_window_hours=168)
    assert _window(hours, cfg) == expected  # type: ignore[arg-type]


def test_window_clamps_oversized_config_default() -> None:
    """A misconfigured default is clamped too — the ceiling is not bypassable.

    Every extra hour is more traces fetched and cached, so the bound has to
    hold regardless of where the value came from.
    """
    cfg = _config(default_window_hours=10_000)
    assert _window(0, cfg) == MAX_WINDOW_HOURS


# ---------------------------------------------------------------------------
# Route handler edge cases via TestClient
# ---------------------------------------------------------------------------


@pytest.fixture
def client() -> TestClient:
    """A TestClient against an app with one demo project and a mock service."""
    demo = _proj("Demo")
    cfg = _config()
    svc = Mock()
    svc.last_updated = None
    svc.invalidate_all = Mock()
    svc._project_map = {demo.slug: demo}
    svc.projects = Mock(return_value=[demo])
    svc.components = Mock(return_value={demo.component_id or demo.slug: [demo]})
    # Default async methods return empty results so routes don't crash.
    svc.summary = AsyncMock(
        return_value={
            "window_hours": 168,
            "total_cost": 0.0,
            "projects": [],
        }
    )
    svc.by_agent = AsyncMock(return_value=[])
    svc.by_model = AsyncMock(return_value=[])
    svc.backend_trend = AsyncMock(return_value=[])
    svc.trend = AsyncMock(return_value=[])
    svc.highlights = AsyncMock(return_value={})
    return _client(cfg, svc)


def test_health_returns_ok(client: TestClient) -> None:
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_chat_skill_returns_200_with_markdown(client: TestClient) -> None:
    """GET /chat-skill returns a Markdown skill document."""
    r = client.get("/chat-skill")
    assert r.status_code == 200
    body = r.text
    # Must be a substantial Markdown document (not a trivial one-liner).
    assert len(body) > 300
    # Key sections from the skill doc.
    assert "# robotsix-cost-monitor — Chat Agent Skill" in body
    assert "## Base URL" in body
    assert "http://cost-monitor:8080" in body
    assert "## Authentication" in body
    assert "## Read endpoints" in body
    assert "## Safety" in body
    # All major read endpoints are documented.
    for ep in (
        "GET /api/summary",
        "GET /api/projects",
        "GET /api/by-agent",
        "GET /api/by-model",
        "GET /api/trend",
        "GET /api/backend-trend",
        "GET /api/highlights",
        "GET /api/reconcile",
        "GET /api/reconcile/last",
        "GET /health",
    ):
        assert ep in body, f"Missing endpoint: {ep}"
    # Mutating endpoints are listed in the Safety section.
    for ep in ("POST /api/refresh",):
        assert ep in body, f"Missing mutating endpoint: {ep}"
    # No credentials are embedded.
    assert "sk-lf-" not in body
    assert "pk-lf-" not in body
    assert "secret" not in body.lower()


def test_chat_skill_no_credentials_leaked(client: TestClient) -> None:
    """The chat-skill doc must not embed any config secrets."""
    r = client.get("/chat-skill")
    body = r.text
    # No Langfuse key patterns.
    assert "sk-lf-" not in body
    assert "pk-lf-" not in body
    # No OpenRouter key patterns.
    assert "sk-or-" not in body


def test_projects_returns_slug(client: TestClient) -> None:
    r = client.get("/api/projects")
    assert r.status_code == 200
    assert r.json() == {
        "items": [{"name": "Demo", "slug": "demo", "component": ""}],
        "total": 1,
        "offset": 0,
        "limit": 100,
        "has_more": False,
    }


def test_components_returns_list_of_dicts(client: TestClient) -> None:
    """GET /api/components — response shape matches dashboard.js contract."""
    r = client.get("/api/components")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == len(body["items"])
    assert body["offset"] == 0
    assert body["limit"] == 100
    items = body["items"]
    assert isinstance(items, list)
    assert len(items) >= 1
    for entry in items:
        assert isinstance(entry, dict)
        assert "component" in entry
        assert "projects" in entry
        assert isinstance(entry["projects"], list)
        for proj in entry["projects"]:
            assert isinstance(proj, dict)
            assert "name" in proj
            assert "slug" in proj
            assert "reconcilable" in proj
            assert isinstance(proj["reconcilable"], bool)


def test_summary_window_defaults_to_config_default(client: TestClient) -> None:
    """``hours`` query param defaults to 0, so _window falls back to
    settings.default_window_hours (168).
    """
    r = client.get("/api/summary?project=all")
    assert r.status_code == 200
    # The mock service returns whatever we stubbed, but the route's _window
    # logic runs before the service call — confirming it passed 168.
    svc = client.app.state.service  # type: ignore[attr-defined]
    svc.summary.assert_called_once_with("all", 168, "all")


def test_summary_passes_explicit_hours(client: TestClient) -> None:
    r = client.get("/api/summary?project=all&hours=48")
    assert r.status_code == 200
    svc = client.app.state.service  # type: ignore[attr-defined]
    svc.summary.assert_called_once_with("all", 48, "all")


def test_summary_passes_backend_filter(client: TestClient) -> None:
    r = client.get("/api/summary?project=all&hours=24&backend=openrouter")
    assert r.status_code == 200
    svc = client.app.state.service  # type: ignore[attr-defined]
    svc.summary.assert_called_once_with("all", 24, "openrouter")


def test_by_agent_default_backend(client: TestClient) -> None:
    r = client.get("/api/by-agent?hours=24")
    assert r.status_code == 200
    client.app.state.service.by_agent.assert_called_once_with("all", 24, "all")  # type: ignore[attr-defined]


def test_by_model_defaults(client: TestClient) -> None:
    r = client.get("/api/by-model?hours=24")
    assert r.status_code == 200
    client.app.state.service.by_model.assert_called_once_with("all", 24)  # type: ignore[attr-defined]


def test_by_agent_pagination_envelope(client: TestClient) -> None:
    """/api/by-agent applies offset/limit and reports total/has_more."""
    rows = [{"name": f"agent-{i}", "cost": float(i)} for i in range(5)]
    client.app.state.service.by_agent = AsyncMock(return_value=rows)  # type: ignore[attr-defined]
    r = client.get("/api/by-agent?hours=24&offset=1&limit=2")
    assert r.status_code == 200
    body = r.json()
    assert body["items"] == rows[1:3]
    assert body["total"] == 5
    assert body["offset"] == 1
    assert body["limit"] == 2
    assert body["has_more"] is True


def test_by_agent_pagination_last_page_has_no_more(client: TestClient) -> None:
    """When the window reaches the end of the set, has_more is False."""
    rows = [{"name": f"agent-{i}", "cost": float(i)} for i in range(3)]
    client.app.state.service.by_agent = AsyncMock(return_value=rows)  # type: ignore[attr-defined]
    r = client.get("/api/by-agent?hours=24&offset=2&limit=10")
    assert r.status_code == 200
    body = r.json()
    assert body["items"] == rows[2:]
    assert body["total"] == 3
    assert body["has_more"] is False


def test_pagination_params_are_validated(client: TestClient) -> None:
    """Out-of-range offset/limit are rejected with 422."""
    assert client.get("/api/by-agent?offset=-1").status_code == 422
    assert client.get("/api/by-agent?limit=0").status_code == 422
    assert client.get("/api/by-agent?limit=1001").status_code == 422


def test_backend_trend_defaults(client: TestClient) -> None:
    r = client.get("/api/backend-trend?hours=24&backend=openrouter")
    assert r.status_code == 200
    client.app.state.service.backend_trend.assert_called_once_with(  # type: ignore[attr-defined]
        "all", 24, "openrouter"
    )


def test_trend_defaults(client: TestClient) -> None:
    r = client.get("/api/trend?hours=24")
    assert r.status_code == 200
    client.app.state.service.trend.assert_called_once_with("all", 24, 48)  # type: ignore[attr-defined]


def test_highlights_defaults(client: TestClient) -> None:
    r = client.get("/api/highlights?hours=24")
    assert r.status_code == 200
    client.app.state.service.highlights.assert_called_once_with("all", 24, "all")  # type: ignore[attr-defined]


def test_highlights_with_backend(client: TestClient) -> None:
    r = client.get("/api/highlights?hours=24&backend=openrouter")
    assert r.status_code == 200
    client.app.state.service.highlights.assert_called_once_with("all", 24, "openrouter")  # type: ignore[attr-defined]


def test_summary_body_includes_effective_hours(client: TestClient) -> None:
    """The summary body echoes the resolved window as ``effective_hours``."""
    r = client.get("/api/summary?project=all&hours=24")
    assert r.status_code == 200
    assert r.json()["effective_hours"] == 24


def test_summary_effective_hours_defaults_to_config(client: TestClient) -> None:
    """Omitting ``hours`` resolves to the config default in ``effective_hours``."""
    r = client.get("/api/summary?project=all")
    assert r.status_code == 200
    assert r.json()["effective_hours"] == 168


def test_highlights_body_includes_effective_hours(client: TestClient) -> None:
    r = client.get("/api/highlights?hours=48")
    assert r.status_code == 200
    assert r.json()["effective_hours"] == 48


@pytest.mark.parametrize(
    "path",
    [
        "/api/summary?hours=24",
        "/api/by-agent?hours=24",
        "/api/by-model?hours=24",
        "/api/backend-trend?hours=24",
        "/api/trend?hours=24",
        "/api/highlights?hours=24",
    ],
)
def test_windowed_endpoints_advertise_effective_hours_header(
    client: TestClient, path: str
) -> None:
    """Every windowed endpoint (list- or dict-shaped) sets X-Effective-Hours."""
    r = client.get(path)
    assert r.status_code == 200
    assert r.headers["X-Effective-Hours"] == "24"


def test_effective_hours_header_reports_default(client: TestClient) -> None:
    """When ``hours`` is omitted the header reports the resolved config default."""
    r = client.get("/api/by-agent")
    assert r.status_code == 200
    assert r.headers["X-Effective-Hours"] == "168"


@pytest.mark.parametrize(
    "path",
    [
        "/api/summary?hours=169",
        "/api/by-agent?hours=169",
        "/api/trend?hours=200000",
    ],
)
def test_hours_above_ceiling_is_rejected_not_clamped(
    client: TestClient, path: str
) -> None:
    """A window above the 168 h ceiling is rejected with a clear 422 error."""
    r = client.get(path)
    assert r.status_code == 422
    body = r.json()
    assert body["error"]["code"] == "validation_error"
    detail = body["error"]["detail"]
    assert detail[0]["loc"][-1] == "hours"
    # The message names the ceiling so the caller knows the limit.
    assert "168" in detail[0]["msg"]
    # The service is never called for a rejected request.
    client.app.state.service.summary.assert_not_called()  # type: ignore[attr-defined]


def test_negative_hours_is_rejected(client: TestClient) -> None:
    r = client.get("/api/summary?hours=-1")
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "validation_error"


def test_chat_skill_documents_time_window(client: TestClient) -> None:
    """The chat-skill doc explains default, ceiling, clamping and feedback."""
    body = client.get("/chat-skill").text
    assert "## Time window" in body
    # Default window is stated explicitly.
    assert "168" in body
    # Rejection (not silent clamping) of over-ceiling requests is documented.
    assert "validation_error" in body
    # The feedback mechanisms are documented.
    assert "X-Effective-Hours" in body
    assert "effective_hours" in body


def test_reconcile_unknown_project_returns_404() -> None:
    """Unknown project slug returns 404 with PROJECT_NOT_FOUND."""
    from robotsix_cost_monitor.exceptions import ProjectNotFoundError

    svc = Mock()
    svc._projects = Mock(
        side_effect=ProjectNotFoundError("Project 'nonexistent' not found")
    )
    r = _client(service=svc).get("/api/reconcile?project=nonexistent")
    assert r.status_code == 404
    body = r.json()
    assert body["error"]["code"] == "PROJECT_NOT_FOUND"


def test_index_returns_html() -> None:
    r = _client().get("/")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/html")


# ---------------------------------------------------------------------------
# Custom error envelopes — exercising the full app error path
# ---------------------------------------------------------------------------


def test_invalid_query_param_type_validation_envelope() -> None:
    """Pass a string where an integer is expected → 422 with validation_error."""
    r = _client().get("/api/summary?hours=abc")
    assert r.status_code == 422
    body = r.json()
    assert body["error"]["code"] == "validation_error"
    detail = body["error"]["detail"]
    assert len(detail) >= 1
    locs = [d.get("loc", []) for d in detail]
    assert any("hours" in loc for loc in locs)


def test_unknown_project_returns_404() -> None:
    """Unknown project slug returns 404 with PROJECT_NOT_FOUND."""
    from robotsix_cost_monitor.exceptions import ProjectNotFoundError

    svc = Mock()
    svc.summary = AsyncMock(
        side_effect=ProjectNotFoundError("Project 'nonexistent' not found")
    )
    r = _client(service=svc).get("/api/summary?project=nonexistent")
    assert r.status_code == 404
    body = r.json()
    assert body["error"]["code"] == "PROJECT_NOT_FOUND"


def test_internal_error_returns_sanitized_envelope() -> None:
    """Force a 500 via a mock service that raises an unhandled exception."""
    svc = Mock()
    svc.summary = AsyncMock(side_effect=RuntimeError("crash"))
    r = _client(_config(), svc, raise_server_exceptions=False).get(
        "/api/summary?hours=24"
    )
    assert r.status_code == 500
    body = r.json()
    assert body["error"]["code"] == "internal_error"
    assert body["error"]["detail"] == "Internal Server Error"


# ---------------------------------------------------------------------------
# Response-shape contract tests — verify every API endpoint returns data
# matching the TypeScript typedefs in ``dashboard.js``.
# ---------------------------------------------------------------------------


def test_summary_response_shape(client: TestClient) -> None:
    """GET /api/summary — response matches ``Summary`` typedef."""
    svc = client.app.state.service  # type: ignore[attr-defined]
    svc.summary = AsyncMock(
        return_value={
            "window_hours": 168,
            "total_cost": 12.5,
            "projects": [
                {
                    "name": "Demo",
                    "slug": "demo",
                    "component": "",
                    "cost": 4.5,
                    "trace_count": 10,
                },
                {
                    "name": "Chat",
                    "slug": "chat",
                    "component": "chat",
                    "cost": 8.0,
                    "trace_count": 42,
                },
            ],
            "components": [
                {
                    "component": "chat",
                    "cost": 8.0,
                    "trace_count": 42,
                    "projects": [
                        {
                            "name": "Chat",
                            "slug": "chat",
                            "component": "chat",
                            "cost": 8.0,
                            "trace_count": 42,
                        },
                    ],
                },
            ],
        }
    )
    svc.last_updated = None

    r = client.get("/api/summary?hours=24")
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body, dict)
    assert isinstance(body["total_cost"], (int, float))
    assert isinstance(body["window_hours"], int)
    assert isinstance(body["projects"], list)
    for p in body["projects"]:
        assert isinstance(p["name"], str)
        assert isinstance(p["cost"], (int, float))
        assert isinstance(p["trace_count"], int)
    assert isinstance(body["components"], list)
    for c in body["components"]:
        assert isinstance(c["component"], str)
        assert isinstance(c["cost"], (int, float))
        assert isinstance(c["trace_count"], int)
        assert isinstance(c["projects"], list)


def test_summary_includes_last_updated_when_set(client: TestClient) -> None:
    """When ``service.last_updated`` is set, the response includes the key."""
    svc = client.app.state.service  # type: ignore[attr-defined]
    svc.summary = AsyncMock(
        return_value={
            "window_hours": 1,
            "total_cost": 0.0,
            "projects": [],
            "components": [],
        }
    )
    from datetime import UTC, datetime

    svc.last_updated = datetime(2025, 1, 15, 12, 0, 0, tzinfo=UTC)

    r = client.get("/api/summary?hours=1")
    assert r.status_code == 200
    body = r.json()
    assert "last_updated" in body
    assert isinstance(body["last_updated"], str)


def test_by_agent_response_shape(client: TestClient) -> None:
    """GET /api/by-agent — response items have name/cost/count keys."""
    svc = client.app.state.service  # type: ignore[attr-defined]
    svc.by_agent = AsyncMock(
        return_value=[
            {"name": "implement", "cost": 5.0, "count": 10},
            {"name": "review", "cost": 3.0, "count": 5},
        ]
    )

    r = client.get("/api/by-agent?hours=24")
    assert r.status_code == 200
    body = r.json()["items"]
    assert isinstance(body, list)
    for row in body:
        assert isinstance(row, dict)
        assert isinstance(row["name"], str)
        assert isinstance(row["cost"], (int, float))
        assert isinstance(row["count"], int)


def test_by_model_response_shape(client: TestClient) -> None:
    """GET /api/by-model — response matches ``ModelRow`` typedef."""
    svc = client.app.state.service  # type: ignore[attr-defined]
    svc.by_model = AsyncMock(
        return_value=[
            {
                "model": "claude-sonnet-4-20250514",
                "backend": "claude-sdk",
                "cost": 8.0,
                "input_tokens": 1000,
                "output_tokens": 500,
                "total_tokens": 1500,
                "observations": 15,
            },
        ]
    )

    r = client.get("/api/by-model?hours=24")
    assert r.status_code == 200
    body = r.json()["items"]
    assert isinstance(body, list)
    for row in body:
        assert isinstance(row, dict)
        assert isinstance(row["model"], str)
        assert "backend" in row
        assert isinstance(row["cost"], (int, float))
        assert isinstance(row["total_tokens"], int)
        assert isinstance(row["observations"], int)


def test_trend_response_shape(client: TestClient) -> None:
    """GET /api/trend — response matches ``TrendPoint`` typedef."""
    svc = client.app.state.service  # type: ignore[attr-defined]
    svc.trend = AsyncMock(
        return_value=[
            {"bucket_start": "2025-01-15T00:00:00Z", "cost": 1.5},
            {"bucket_start": "2025-01-15T01:00:00Z", "cost": 2.0},
        ]
    )

    r = client.get("/api/trend?hours=24")
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body, list)
    for point in body:
        assert isinstance(point, dict)
        assert isinstance(point["bucket_start"], str)
        assert isinstance(point["cost"], (int, float))


def test_backend_trend_response_shape(client: TestClient) -> None:
    """GET /api/backend-trend — response matches ``TrendPoint`` typedef."""
    svc = client.app.state.service  # type: ignore[attr-defined]
    svc.backend_trend = AsyncMock(
        return_value=[
            {"bucket_start": "2025-01-15T00:00:00Z", "cost": 1.5},
            {"bucket_start": "2025-01-15T01:00:00Z", "cost": 2.0},
        ]
    )

    r = client.get("/api/backend-trend?hours=24&backend=openrouter")
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body, list)
    for point in body:
        assert isinstance(point, dict)
        assert isinstance(point["bucket_start"], str)
        assert isinstance(point["cost"], (int, float))


def test_highlights_response_shape(client: TestClient) -> None:
    """GET /api/highlights — response matches ``Highlights`` typedef."""
    svc = client.app.state.service  # type: ignore[attr-defined]
    svc.highlights = AsyncMock(
        return_value={
            "most_expensive_trace": {"name": "big-job", "cost": 10.0, "id": "tr-123"},
            "most_expensive_session": {
                "session_id": "sess-1",
                "cost": 15.0,
                "count": 3,
            },
            "session_cost_scope": "all",
        }
    )

    r = client.get("/api/highlights?hours=24")
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body, dict)
    # most_expensive_trace
    if body.get("most_expensive_trace") is not None:
        mt = body["most_expensive_trace"]
        assert isinstance(mt, dict)
        assert "cost" in mt
        assert isinstance(mt["cost"], (int, float))
    # most_expensive_session
    if body.get("most_expensive_session") is not None:
        ms = body["most_expensive_session"]
        assert isinstance(ms, dict)
        assert isinstance(ms["session_id"], str)
        assert isinstance(ms["cost"], (int, float))
        assert isinstance(ms["count"], int)
    # session_cost_scope
    assert isinstance(body["session_cost_scope"], str)


def test_reconcile_all_response_shape() -> None:
    """GET /api/reconcile?project=all — response matches ``ReconcileRow`` typedef."""
    svc = Mock()
    svc._project_map = {}
    svc.projects = Mock(return_value=[])

    with patch(
        "robotsix_cost_monitor.routes.reconcile_all",
        new_callable=AsyncMock,
    ) as mock_reconcile_all:
        mock_reconcile_all.return_value = {
            "generated_at": "2025-01-15T12:00:00Z",
            "status": "ok",
            "tolerance_usd": 1.0,
            "results": [
                {
                    "project": "Demo",
                    "configured": True,
                    "provider_delta_usd": 12.0,
                    "langfuse_cost_usd": 11.5,
                    "langfuse_total_cost_usd": 12.0,
                    "drift_usd": 0.5,
                    "within_tolerance": True,
                }
            ],
        }

        r = _client(service=svc).get("/api/reconcile?project=all")
        assert r.status_code == 200
        body = r.json()
        assert isinstance(body, list)
        for row in body:
            assert isinstance(row, dict)
            assert isinstance(row["project"], str)
            assert isinstance(row["configured"], bool)
            if row["configured"] and "error" not in row:
                assert isinstance(row["provider_delta_usd"], (int, float))
                assert isinstance(row["within_tolerance"], bool)


def test_reconcile_single_project_response_shape() -> None:
    """GET /api/reconcile?project=demo — response matches ``ReconcileRow`` typedef."""
    svc = Mock()
    demo = _proj("Demo")
    svc._projects = Mock(return_value=[demo])

    with patch(
        "robotsix_cost_monitor.routes.reconcile_project",
        new_callable=AsyncMock,
    ) as mock_reconcile_project:
        mock_reconcile_project.return_value = {
            "project": "Demo",
            "slug": "demo",
            "configured": True,
            "at": "2025-01-15T12:00:00Z",
            "balance": {"remaining": 50.0},
            "low_balance": False,
            "interval_hours": 168,
            "provider_delta_usd": 12.0,
            "langfuse_cost_usd": 11.5,
            "langfuse_total_cost_usd": 12.0,
            "langfuse_cost_by_backend": {"openrouter": 11.5},
            "drift_usd": 0.5,
            "within_tolerance": True,
            "tolerance_usd": 1.0,
        }

        r = _client(service=svc).get("/api/reconcile?project=demo")
        assert r.status_code == 200
        body = r.json()
        assert isinstance(body, list)
        assert len(body) == 1
        row = body[0]
        assert isinstance(row["project"], str)
        assert isinstance(row["configured"], bool)
        assert isinstance(row["provider_delta_usd"], (int, float))
        assert isinstance(row["within_tolerance"], bool)
        # balance sub-shape
        assert isinstance(row["balance"], dict)
        assert isinstance(row["balance"]["remaining"], (int, float))
        assert isinstance(row["low_balance"], bool)


def test_reconcile_last_response_shape() -> None:
    """GET /api/reconcile/last — response matches ``ReconLast`` typedef."""
    with patch(
        "robotsix_cost_monitor.routes.load_last_reconcile",
    ) as mock_load:
        mock_load.return_value = {
            "generated_at": "2025-01-15T12:00:00Z",
            "status": "ok",
            "results": [
                {
                    "project": "Demo",
                    "configured": True,
                    "provider_delta_usd": 12.0,
                    "langfuse_cost_usd": 11.5,
                    "drift_usd": 0.5,
                    "within_tolerance": True,
                }
            ],
        }

        r = _client().get("/api/reconcile/last")
        assert r.status_code == 200
        body = r.json()
        assert isinstance(body, dict)
        assert isinstance(body.get("status"), str)
        assert isinstance(body.get("results"), list)
        for row in body["results"]:
            assert isinstance(row, dict)
            assert isinstance(row["project"], str)


def test_reconcile_last_defaults_when_no_data() -> None:
    """GET /api/reconcile/last — returns defaults before any reconcile has run."""
    with patch(
        "robotsix_cost_monitor.routes.load_last_reconcile",
    ) as mock_load:
        mock_load.return_value = {
            "generated_at": None,
            "status": "unknown",
            "results": [],
        }

        r = _client().get("/api/reconcile/last")
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "unknown"
        assert body["generated_at"] is None
        assert body["results"] == []


def test_refresh_response_shape(client: TestClient) -> None:
    """POST /api/refresh — response has status/message keys and invalidates cache."""
    svc = client.app.state.service  # type: ignore[attr-defined]

    r = client.post("/api/refresh")
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body, dict)
    assert body["status"] == "ok"
    assert isinstance(body["message"], str)
    svc.invalidate_all.assert_called_once()
