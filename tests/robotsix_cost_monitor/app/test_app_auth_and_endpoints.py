"""App auth, probes, security headers, API endpoints and config loading tests."""

# mypy: disable-error-code="arg-type"

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr

from robotsix_cost_monitor.config import Config, Settings, load_config


def _auth_app(make_client: Callable[..., TestClient]) -> TestClient:
    from robotsix_cost_monitor.config import AuthConfig, Settings

    cfg = Config(
        settings=Settings(
            auth=AuthConfig(
                username="admin",
                password=SecretStr("s3cret"),  # pragma: allowlist secret
            )
        ),
    )
    return make_client(config=cfg)


def test_auth_required_returns_401_without_credentials(
    make_client: Callable[..., TestClient],
) -> None:
    r = _auth_app(make_client).get("/")
    assert r.status_code == 401
    assert r.headers.get("www-authenticate", "").lower().startswith("basic")


def test_auth_rejects_wrong_credentials(
    make_client: Callable[..., TestClient],
) -> None:
    r = _auth_app(make_client).get("/", auth=("admin", "wrong"))
    assert r.status_code == 401


def test_auth_accepts_correct_credentials(
    make_client: Callable[..., TestClient],
) -> None:
    r = _auth_app(make_client).get("/", auth=("admin", "s3cret"))
    assert r.status_code == 200


def test_auth_health_is_exempt(make_client: Callable[..., TestClient]) -> None:
    # The container healthcheck hits /health without credentials.
    r = _auth_app(make_client).get("/health")
    assert r.status_code == 200


def _probe_app(
    make_client: Callable[..., TestClient],
    app_factory: Callable[..., FastAPI],
    tmp_path: Path,
    *,
    with_project: bool,
) -> TestClient:
    """Auth-enabled app with data_dir under *tmp_path* (lifespan not run)."""
    from robotsix_cost_monitor.config import AuthConfig

    cfg = Config(
        settings=Settings(
            data_dir=tmp_path,
            auth=AuthConfig(
                username="admin",
                password=SecretStr("s3cret"),  # pragma: allowlist secret
            ),
        ),
    )
    app = app_factory(config=cfg)
    if with_project:
        app.state.service._project_map = {"p": Mock()}
    return make_client(app=app)


def test_auth_readyz_exempt_and_ready(
    make_client: Callable[..., TestClient],
    app_factory: Callable[..., FastAPI],
    tmp_path: Path,
) -> None:
    # Orchestrator/gateway probes hit /readyz without credentials.
    r = _probe_app(make_client, app_factory, tmp_path, with_project=True).get("/readyz")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_auth_liveness_is_exempt(
    make_client: Callable[..., TestClient],
    app_factory: Callable[..., FastAPI],
    tmp_path: Path,
) -> None:
    r = _probe_app(make_client, app_factory, tmp_path, with_project=False).get(
        "/health/live"
    )
    assert r.status_code == 200


def test_readyz_503_when_no_projects(
    make_client: Callable[..., TestClient],
    app_factory: Callable[..., FastAPI],
    tmp_path: Path,
) -> None:
    r = _probe_app(make_client, app_factory, tmp_path, with_project=False).get(
        "/readyz"
    )
    assert r.status_code == 503
    body = r.json()
    assert body["status"] == "unready"
    assert any(f.startswith("projects:") for f in body["failures"])


def test_readyz_503_when_data_dir_unwritable(
    make_client: Callable[..., TestClient],
    app_factory: Callable[..., FastAPI],
    tmp_path: Path,
) -> None:
    client = _probe_app(make_client, app_factory, tmp_path, with_project=True)
    with patch("robotsix_cost_monitor.app.os.access", return_value=False):
        r = client.get("/readyz")
    assert r.status_code == 503
    failures = r.json()["failures"]
    assert failures == ["data_dir: reconcile data directory is not writable"]
    assert str(tmp_path) not in r.text


def test_no_hand_rolled_readyz_in_routes() -> None:
    from robotsix_cost_monitor.routes import router

    assert "/readyz" not in {getattr(r, "path", None) for r in router.routes}


def test_auth_disabled_when_unconfigured(client: TestClient) -> None:
    # No username/password -> dashboard is open (loopback/dev).
    r = client.get("/")
    assert r.status_code == 200


def test_health(client: TestClient) -> None:
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_security_headers_on_html_page(client: TestClient) -> None:
    """The index HTML page includes security response headers."""
    r = client.get("/")
    assert r.status_code == 200
    assert r.headers["x-content-type-options"] == "nosniff"
    assert "content-security-policy" in r.headers


def test_security_headers_on_json_api(client: TestClient) -> None:
    """JSON API responses also include security response headers."""
    r = client.get("/health")
    assert r.status_code == 200
    assert r.headers["x-content-type-options"] == "nosniff"
    assert "content-security-policy" in r.headers


def test_security_headers_follow_balanced_preset(client: TestClient) -> None:
    """Headers come from the BALANCED preset plus Cache-Control: no-store."""
    r = client.get("/api/summary?hours=24")
    assert r.status_code == 200
    assert r.headers["cross-origin-opener-policy"] == "same-origin"
    assert r.headers["cross-origin-resource-policy"] == "same-origin"
    assert r.headers["strict-transport-security"] == (
        "max-age=31536000; includeSubDomains"
    )
    assert r.headers["x-frame-options"] == "SAMEORIGIN"
    assert "no-store" in r.headers["cache-control"]
    csp = r.headers["content-security-policy"]
    assert "script-src 'self' 'unsafe-inline'" in csp
    assert "object-src 'none'" in csp


def test_html_page_not_cacheable(client: TestClient) -> None:
    """The authenticated dashboard HTML carries Cache-Control: no-store."""
    r = client.get("/")
    assert r.status_code == 200
    assert "no-store" in r.headers["cache-control"]


def test_summary_empty_is_zero(client: TestClient) -> None:
    r = client.get("/api/summary?hours=24")
    assert r.status_code == 200
    body = r.json()
    assert body["total_cost"] == 0.0
    assert body["projects"] == []
    assert body["window_hours"] == 24


def test_summary_unknown_project_returns_404(client: TestClient) -> None:
    """An unknown project slug returns 404 with PROJECT_NOT_FOUND."""
    r = client.get("/api/summary?project=nonexistent")
    assert r.status_code == 404
    body = r.json()
    assert body["error"]["code"] == "PROJECT_NOT_FOUND"


def test_summary_project_all_returns_200_when_no_projects(
    client: TestClient,
) -> None:
    """?project=all is always valid — returns 200 even with zero projects."""
    r = client.get("/api/summary?project=all")
    assert r.status_code == 200


def test_unknown_project_across_endpoints(client: TestClient) -> None:
    """Every project-scoped endpoint returns 404 with PROJECT_NOT_FOUND for an unknown slug."""
    c = client
    endpoints = [
        "/api/summary?project=nope",
        "/api/by-agent?project=nope",
        "/api/by-model?project=nope",
        "/api/backend-trend?project=nope&backend=openrouter",
        "/api/trend?project=nope",
        "/api/highlights?project=nope",
        "/api/reconcile?project=nope",
    ]
    for ep in endpoints:
        r = c.get(ep)
        assert r.status_code == 404, f"{ep} returned {r.status_code}"
        body = r.json()
        assert body["error"]["code"] == "PROJECT_NOT_FOUND", f"{ep} code mismatch"


def test_by_agent_and_trend_empty(client: TestClient) -> None:
    c = client
    assert c.get("/api/by-agent?hours=24").json()["items"] == []
    assert len(c.get("/api/trend?hours=24&buckets=12").json()) == 12


def test_by_agent_accepts_backend_param(client: TestClient) -> None:
    """The /api/by-agent route accepts ?backend=... and returns empty for no projects."""
    c = client
    r = c.get("/api/by-agent?hours=24&backend=openrouter")
    assert r.status_code == 200
    assert r.json()["items"] == []


def test_by_agent_backend_all_is_default(client: TestClient) -> None:
    """Omitting ?backend=... is equivalent to ?backend=all."""
    c = client
    assert (
        c.get("/api/by-agent?hours=24").json()
        == c.get("/api/by-agent?hours=24&backend=all").json()
    )


def test_by_model_empty(client: TestClient) -> None:
    r = client.get("/api/by-model?hours=24")
    assert r.status_code == 200
    assert r.json()["items"] == []


def test_backend_trend_empty(client: TestClient) -> None:
    r = client.get("/api/backend-trend?hours=24&backend=openrouter")
    assert r.status_code == 200
    assert r.json() == []


def test_index_served(client: TestClient) -> None:
    r = client.get("/")
    assert r.status_code == 200
    assert "cost monitor" in r.text
    # The AppShell is mounted into this container element.
    assert 'id="appshell-root"' in r.text
    # The dashboard renders the last reconcile into this element on load.
    assert 'id="recon-when"' in r.text


def test_settings_served(client: TestClient) -> None:
    r = client.get("/settings")
    assert r.status_code == 200
    assert "settings" in r.text.lower()
    # The AppShell and ConfigPanel are mounted on the settings page.
    assert 'id="appshell-root"' in r.text
    assert 'id="settings-root"' in r.text
    assert "mountAppShell" in r.text
    assert "mountConfigPanel" in r.text


def test_reconcile_last_served_from_disk(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    make_client: Callable[..., TestClient],
) -> None:
    """The persisted last reconcile is served by ``/api/reconcile/last`` — this is
    what lets the dashboard show the last run after a page reload or container
    restart (the file is on the persisted data volume).
    """
    monkeypatch.setattr(
        "robotsix_cost_monitor.reconcile.data_dir", lambda settings=None: tmp_path
    )
    recon = tmp_path / "reconcile"
    recon.mkdir()
    (recon / "last.json").write_text(
        json.dumps(
            {
                "generated_at": "2026-06-19T15:37:25+00:00",
                "status": "ok",
                "results": [
                    {
                        "project": "demo",
                        "configured": True,
                        "within_tolerance": True,
                        "provider_delta_usd": 1.0,
                        "langfuse_cost_usd": 1.0,
                        "drift_usd": 0.0,
                    }
                ],
            }
        )
    )

    app = make_client(config=Config(settings=Settings(data_dir=tmp_path)))

    r = app.get("/api/reconcile/last")

    assert r.status_code == 200
    body = r.json()
    assert body["generated_at"] == "2026-06-19T15:37:25+00:00"
    assert body["status"] == "ok"
    assert body["results"][0]["project"] == "demo"


def test_load_config_missing(tmp_path: Path) -> None:
    """Loading a nonexistent file returns defaults (robotsix_config behavior)."""
    config = load_config(tmp_path / "nope.json")
    assert isinstance(config, Config)


def test_load_config_roundtrip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cfg_file = tmp_path / "config.json"
    cfg_file.write_text(
        json.dumps(
            {
                "projects": [
                    {
                        "name": "A",
                        "public_key": "pk-lf-a",
                        "secret_key": "sk-lf-a",
                        "base_url": "http://lf",
                    }
                ],
                "settings": {"default_window_hours": 48},
            }
        )
    )
    monkeypatch.setenv("ROBOTSIX_CONFIG_FILE", str(cfg_file))
    loaded = load_config()
    assert loaded.settings.default_window_hours == 48
