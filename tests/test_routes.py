"""Unit tests for route helpers, dependency providers, exception handlers,
and route-handler edge cases from ``src/robotsix_cost_monitor/routes.py``.

These tests avoid importing ``create_app`` (which transitively requires the
optional ``robotsix-llmio`` package). Instead, they build a minimal FastAPI
app directly, mount the router from ``routes``, and wire the exception handlers.
"""

from __future__ import annotations

import json
import sys
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# Mock the optional ``robotsix-llmio`` package before importing
# ``robotsix_cost_monitor.routes`` (which transitively imports
# ``robotsix_cost_monitor.reconcile`` → ``robotsix_llmio.openrouter``).
# This keeps the test suite runnable without the ``analyst`` extra.
#
# Save and restore the original sys.modules entries so that other test
# modules (e.g. test_analyst.py) that need the real robotsix_llmio are
# not broken by this mock leaking across the whole session.
# ---------------------------------------------------------------------------
_orig_llmio = sys.modules.get("robotsix_llmio")
_orig_llmio_openrouter = sys.modules.get("robotsix_llmio.openrouter")

_llmio = MagicMock()
_llmio_openrouter = MagicMock()
_llmio_openrouter.OpenRouterKeyCostSource = MagicMock()
sys.modules["robotsix_llmio"] = _llmio
sys.modules["robotsix_llmio.openrouter"] = _llmio_openrouter

from robotsix_cost_monitor.config import Config  # noqa: E402
from robotsix_cost_monitor.routes import (  # noqa: E402
    _require_project,
    _window,
    get_config,
    get_service,
    http_exception_handler,
    register_exception_handlers,
    router,
    unhandled_handler,
    validation_handler,
)
from conftest import _config, _proj  # noqa: E402

# Restore the original sys.modules entries so the mock does not leak.
if _orig_llmio is not None:
    sys.modules["robotsix_llmio"] = _orig_llmio
else:
    sys.modules.pop("robotsix_llmio", None)
if _orig_llmio_openrouter is not None:
    sys.modules["robotsix_llmio.openrouter"] = _orig_llmio_openrouter
else:
    sys.modules.pop("robotsix_llmio.openrouter", None)


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
# _require_project
# ---------------------------------------------------------------------------


def test_require_project_all_always_passes() -> None:
    """``project="all"`` never raises — even with zero projects."""
    _require_project("all", _config())  # no exception


def test_require_project_valid_slug_passes() -> None:
    cfg = _config(_proj("Demo Project"))
    _require_project("demo-project", cfg)  # no exception


def test_require_project_unknown_slug_raises_404() -> None:
    cfg = _config(_proj("Demo"))
    with pytest.raises(HTTPException) as exc:
        _require_project("nope", cfg)
    assert exc.value.status_code == 404
    assert "nope" in exc.value.detail


def test_require_project_case_sensitive_slug() -> None:
    """The slug derived from the name is lowercase; an uppercase variant must
    fail because Config.project does an exact slug match."""
    cfg = _config(_proj("Demo"))
    with pytest.raises(HTTPException) as exc:
        _require_project("Demo", cfg)
    assert exc.value.status_code == 404


# ---------------------------------------------------------------------------
# _window
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "hours,expected",
    [
        (24, 24),      # nonzero → supplied hours
        (0, 168),      # zero → config default
        (None, 168),   # None → config default
    ],
    ids=["nonzero", "zero_falls_back", "none_falls_back"],
)
def test_window(hours: int | None, expected: int) -> None:
    cfg = _config(default_window_hours=168)
    assert _window(hours, cfg) == expected  # type: ignore[arg-type]


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
    body = json.loads(resp.body)
    assert body["error"]["code"] == "VALIDATION_ERROR"


async def test_validation_handler_includes_field_details() -> None:
    req = _make_request(FastAPI())
    exc = _validation_error()
    resp = await validation_handler(req, exc)
    body = json.loads(resp.body)
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
    body = json.loads(resp.body)
    assert body["error"]["details"][0]["field"] == "project → slug"


async def test_validation_handler_missing_type_defaults_to_validation_error() -> None:
    """When ``type`` is absent from the error dict, code defaults to
    ``"validation_error"``."""
    req = _make_request(FastAPI())
    exc = RequestValidationError(errors=[{"loc": ("body",), "msg": "bad"}])
    resp = await validation_handler(req, exc)
    body = json.loads(resp.body)
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
    body = json.loads(resp.body)
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
    body = json.loads(resp.body)
    assert body["error"]["code"] == "INTERNAL_ERROR"
    assert body["error"]["detail"] == "Internal Server Error"


async def test_unhandled_handler_logs_exception() -> None:
    """The handler must log the full exception (without leaking details to the
    HTTP response)."""
    req = _make_request(FastAPI())
    exc = RuntimeError("test bug")

    with patch("robotsix_cost_monitor.routes.logger") as mock_logger:
        await unhandled_handler(req, exc)

    mock_logger.exception.assert_called_once()
    args = mock_logger.exception.call_args[0]
    assert "Unhandled exception" in args[0]
    assert args[1] == "GET"
    assert args[2] == "/"


# ---------------------------------------------------------------------------
# register_exception_handlers
# ---------------------------------------------------------------------------


def test_register_exception_handlers_wires_all_three() -> None:
    app = MagicMock(spec=FastAPI)
    register_exception_handlers(app)
    assert app.add_exception_handler.call_count == 3
    calls = [(c[0][0], c[0][1]) for c in app.add_exception_handler.call_args_list]
    # exception class → handler function
    from fastapi.exceptions import RequestValidationError as RVE

    assert calls == [
        (RVE, validation_handler),
        (HTTPException, http_exception_handler),
        (Exception, unhandled_handler),
    ]


# ---------------------------------------------------------------------------
# Route handler edge cases via TestClient
# ---------------------------------------------------------------------------


@pytest.fixture
def client() -> TestClient:
    """A TestClient against an app with one demo project and a mock service."""
    cfg = _config(_proj("Demo"))
    svc = Mock()
    # Default async methods return empty results so routes don't crash.
    svc.summary = AsyncMock(
        return_value={
            "window_hours": 168,
            "total_cost": 0.0,
            "projects": [],
        }
    )
    svc.by_agent = AsyncMock(return_value=[])
    svc.by_agent_segmented = AsyncMock(return_value=[])
    svc.by_model = AsyncMock(return_value=[])
    svc.backend_trend = AsyncMock(return_value=[])
    svc.trend = AsyncMock(return_value=[])
    svc.highlights = AsyncMock(return_value={})
    return _client(cfg, svc)


def test_health_includes_project_names(client: TestClient) -> None:
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["projects"] == ["Demo"]


def test_projects_returns_slug(client: TestClient) -> None:
    r = client.get("/api/projects")
    assert r.status_code == 200
    assert r.json() == [{"name": "Demo", "slug": "demo"}]


def test_summary_window_defaults_to_config_default(client: TestClient) -> None:
    """``hours`` query param defaults to 0, so _window falls back to
    settings.default_window_hours (168)."""
    r = client.get("/api/summary?project=all")
    assert r.status_code == 200
    # The mock service returns whatever we stubbed, but the route's _window
    # logic runs before the service call — confirming it passed 168.
    svc = client.app.state.service
    svc.summary.assert_called_once_with("all", 168)


def test_summary_passes_explicit_hours(client: TestClient) -> None:
    r = client.get("/api/summary?project=all&hours=48")
    assert r.status_code == 200
    svc = client.app.state.service
    svc.summary.assert_called_once_with("all", 48)


def test_by_agent_default_backend(client: TestClient) -> None:
    r = client.get("/api/by-agent?hours=24")
    assert r.status_code == 200
    client.app.state.service.by_agent.assert_called_once_with("all", 24, "all")


def test_by_agent_segmented_empty(client: TestClient) -> None:
    r = client.get("/api/by-agent-segmented?hours=24")
    assert r.status_code == 200
    assert r.json() == []


def test_by_model_defaults(client: TestClient) -> None:
    r = client.get("/api/by-model?hours=24")
    assert r.status_code == 200
    client.app.state.service.by_model.assert_called_once_with("all", 24)


def test_backend_trend_defaults(client: TestClient) -> None:
    r = client.get("/api/backend-trend?hours=24&backend=openrouter")
    assert r.status_code == 200
    client.app.state.service.backend_trend.assert_called_once_with(
        "all", 24, "openrouter"
    )


def test_trend_defaults(client: TestClient) -> None:
    r = client.get("/api/trend?hours=24")
    assert r.status_code == 200
    client.app.state.service.trend.assert_called_once_with("all", 24, 48)


def test_highlights_defaults(client: TestClient) -> None:
    r = client.get("/api/highlights?hours=24")
    assert r.status_code == 200
    client.app.state.service.highlights.assert_called_once_with("all", 24)


def test_reconcile_project_not_found_404(client: TestClient) -> None:
    r = client.get("/api/reconcile?project=nonexistent")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "HTTP_ERROR"


def test_index_returns_html() -> None:
    r = _client().get("/")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/html")


def test_analyst_page_returns_html() -> None:
    r = _client().get("/analyst")
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


def test_not_found_uses_http_error_envelope(client: TestClient) -> None:
    r = client.get("/api/summary?project=nonexistent")
    assert r.status_code == 404
    body = r.json()
    assert body["error"]["code"] == "HTTP_ERROR"
    assert body["error"]["detail"] == "Unknown project slug: nonexistent"


def test_internal_error_returns_sanitized_envelope() -> None:
    """Force a 500 via a mock service that raises an unhandled exception."""
    svc = Mock()
    svc.summary = AsyncMock(side_effect=RuntimeError("crash"))
    r = _client(_config(_proj("Demo")), svc, raise_server_exceptions=False).get(
        "/api/summary?hours=24"
    )
    assert r.status_code == 500
    body = r.json()
    assert body["error"]["code"] == "INTERNAL_ERROR"
    assert body["error"]["detail"] == "Internal Server Error"


def test_analyst_digest_default_window() -> None:
    """When ``hours=0``, the digest route falls back to analyst.window_hours."""
    svc = Mock()
    svc.highlights = AsyncMock(return_value={})
    cfg = _config(_proj("Demo"))
    # The build_digest function is patched to avoid real analyst logic.
    with patch("robotsix_cost_monitor.routes.build_digest") as mock_digest:
        mock_digest.return_value = {"digest": "ok"}
        r = _client(cfg, svc).get("/api/analyst/digest?hours=0")
        assert r.status_code == 200
        # build_digest should receive the config's analyst.window_hours (24 by default)
        mock_digest.assert_called_once_with(svc, 24, cfg)


def test_analyst_proposals_loads() -> None:
    """The route returns whatever load_proposals produces."""
    with patch(
        "robotsix_cost_monitor.routes.load_proposals",
        return_value={"generated_at": None},
    ):
        r = _client().get("/api/analyst/proposals")
        assert r.status_code == 200


def test_analyst_ticket_loads() -> None:
    with patch(
        "robotsix_cost_monitor.routes.load_targeted_analysis",
        return_value={"generated_at": None},
    ):
        r = _client().get("/api/analyst/ticket")
        assert r.status_code == 200


def test_analyst_stage_loads() -> None:
    with patch(
        "robotsix_cost_monitor.routes.load_targeted_analysis",
        return_value={"generated_at": None},
    ):
        r = _client().get("/api/analyst/stage")
        assert r.status_code == 200
