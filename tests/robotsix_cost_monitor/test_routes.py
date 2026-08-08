"""Unit tests for route helpers, dependency providers, exception handlers,
and route-handler edge cases from ``src/robotsix_cost_monitor/routes.py``.

These tests avoid importing ``create_app`` (which transitively requires the
optional ``robotsix-llmio`` package). Instead, they build a minimal FastAPI
app directly, mount the router from ``routes``, and wire the exception handlers.
"""

from __future__ import annotations

import json
import sys
from unittest.mock import AsyncMock, MagicMock, Mock

import pytest
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.testclient import TestClient

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
    http_exception_handler,
    register_exception_handlers,
    router,
    unhandled_handler,
    validation_handler,
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


def _client(
    cfg: Config | None = None,
    service: object | None = None,
    **test_client_kwargs: object,
) -> TestClient:
    """Build a TestClient against a minimal FastAPI app that mounts the
    production router and exception handlers.

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
# validation_handler
# ---------------------------------------------------------------------------


def _validation_error() -> RequestValidationError:
    """Build a minimal RequestValidationError with one field error."""
    return RequestValidationError(
        errors=[
            {
                "loc": ("body", "hours"),
                "msg": "ensure this value is greater than or equal to 0",
                "type": "value_error.number.not_ge",
            }
        ]
    )


async def test_validation_handler_returns_422() -> None:
    req = _make_request(FastAPI())
    exc = _validation_error()
    resp = await validation_handler(req, exc)
    assert resp.status_code == 422
    body = json.loads(resp.body)  # type: ignore[arg-type]
    assert body["error"]["code"] == "VALIDATION_ERROR"


async def test_validation_handler_includes_field_details() -> None:
    req = _make_request(FastAPI())
    exc = _validation_error()
    resp = await validation_handler(req, exc)
    body = json.loads(resp.body)  # type: ignore[arg-type]
    details = body["error"]["details"]
    assert len(details) == 1
    assert details[0]["field"] == "hours"
    assert details[0]["message"] == "ensure this value is greater than or equal to 0"
    assert details[0]["code"] == "value_error.number.not_ge"


async def test_validation_handler_strips_body_from_field_path() -> None:
    """The ``body`` loc segment is stripped from the human-readable field name."""
    req = _make_request(FastAPI())
    exc = RequestValidationError(
        errors=[{"loc": ("body", "project", "slug"), "msg": "X", "type": "T"}]
    )
    resp = await validation_handler(req, exc)
    body = json.loads(resp.body)  # type: ignore[arg-type]
    assert body["error"]["details"][0]["field"] == "project → slug"


async def test_validation_handler_missing_type_defaults_to_validation_error() -> None:
    """When ``type`` is absent from the error dict, code defaults to
    ``"validation_error"``.
    """
    req = _make_request(FastAPI())
    exc = RequestValidationError(errors=[{"loc": ("body",), "msg": "bad"}])
    resp = await validation_handler(req, exc)
    body = json.loads(resp.body)  # type: ignore[arg-type]
    assert body["error"]["details"][0]["code"] == "validation_error"


# ---------------------------------------------------------------------------
# http_exception_handler
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "status_code,detail",
    [
        (404, "Unknown project slug: nope"),
        (500, "boom"),
    ],
    ids=["404", "500"],
)
async def test_http_exception_handler(status_code: int, detail: str) -> None:
    req = _make_request(FastAPI())
    exc = HTTPException(status_code=status_code, detail=detail)
    resp = await http_exception_handler(req, exc)
    assert resp.status_code == status_code
    body = json.loads(resp.body)  # type: ignore[arg-type]
    assert body["error"]["code"] == "HTTP_ERROR"
    assert body["error"]["detail"] == detail


# ---------------------------------------------------------------------------
# unhandled_handler
# ---------------------------------------------------------------------------


async def test_unhandled_handler_returns_500_sanitized() -> None:
    req = _make_request(FastAPI())
    exc = ValueError("secret key leaked")
    resp = await unhandled_handler(req, exc)
    assert resp.status_code == 500
    body = json.loads(resp.body)  # type: ignore[arg-type]
    assert body["error"]["code"] == "INTERNAL_ERROR"
    assert body["error"]["detail"] == "Internal Server Error"


async def test_unhandled_handler_logs_exception() -> None:
    """The handler must log the full exception (without leaking details to the
    HTTP response).  After the structlog→stdlib bridge, ``logger.exception()``
    propagates to stdlib — verify via a structlog capturing handler.

    The routes module uses ``structlog.get_logger(__name__)`` which is a lazy
    proxy — ``capture_logs`` reconfigures structlog temporarily and the proxy
    picks it up on the next call.
    """
    import structlog

    req = _make_request(FastAPI())
    exc = RuntimeError("test bug")

    with structlog.testing.capture_logs() as cap_logs:
        await unhandled_handler(req, exc)

    assert len(cap_logs) >= 1
    event = cap_logs[-1]
    assert "Unhandled exception" in event["event"]
    assert event.get("exc_info") is not None


# ---------------------------------------------------------------------------
# register_exception_handlers
# ---------------------------------------------------------------------------


def test_register_exception_handlers_wires_all_five() -> None:
    app = MagicMock(spec=FastAPI)
    register_exception_handlers(app)
    assert app.add_exception_handler.call_count == 5
    calls = [(c[0][0], c[0][1]) for c in app.add_exception_handler.call_args_list]
    # exception class → handler function
    from fastapi.exceptions import RequestValidationError as RVE
    from robotsix_http import ExternalHTTPError

    from robotsix_cost_monitor.exceptions import CostMonitorError
    from robotsix_cost_monitor.routes import (
        cost_monitor_error_handler,
        external_http_error_handler,
    )

    assert calls == [
        (RVE, validation_handler),
        (HTTPException, http_exception_handler),
        (CostMonitorError, cost_monitor_error_handler),
        (ExternalHTTPError, external_http_error_handler),
        (Exception, unhandled_handler),
    ]


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
    assert r.json() == [{"name": "Demo", "slug": "demo", "component": ""}]


def test_components_returns_list_of_dicts(client: TestClient) -> None:
    """GET /api/components — response shape matches dashboard.js contract."""
    r = client.get("/api/components")
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body, list)
    assert len(body) >= 1
    for entry in body:
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
    svc.summary.assert_called_once_with("all", 168)


def test_summary_passes_explicit_hours(client: TestClient) -> None:
    r = client.get("/api/summary?project=all&hours=48")
    assert r.status_code == 200
    svc = client.app.state.service  # type: ignore[attr-defined]
    svc.summary.assert_called_once_with("all", 48)


def test_by_agent_default_backend(client: TestClient) -> None:
    r = client.get("/api/by-agent?hours=24")
    assert r.status_code == 200
    client.app.state.service.by_agent.assert_called_once_with("all", 24, "all")  # type: ignore[attr-defined]


def test_by_model_defaults(client: TestClient) -> None:
    r = client.get("/api/by-model?hours=24")
    assert r.status_code == 200
    client.app.state.service.by_model.assert_called_once_with("all", 24)  # type: ignore[attr-defined]


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
    """Pass a string where an integer is expected → 422 with VALIDATION_ERROR."""
    r = _client().get("/api/summary?hours=abc")
    assert r.status_code == 422
    body = r.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert len(body["error"]["details"]) >= 1
    fields = [d["field"] for d in body["error"]["details"]]
    assert any("hours" in f for f in fields)


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
    assert body["error"]["code"] == "INTERNAL_ERROR"
    assert body["error"]["detail"] == "Internal Server Error"
