"""App + config tests using a zero-project config (no network)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from robotsix_cost_monitor.app import create_app
from robotsix_cost_monitor.config import Config, ProjectConfig, load_config


def _empty_app() -> TestClient:
    return TestClient(create_app(Config(projects=[])))


def test_health():
    r = _empty_app().get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_summary_empty_is_zero():
    r = _empty_app().get("/api/summary?hours=24")
    assert r.status_code == 200
    body = r.json()
    assert body["total_cost"] == 0.0
    assert body["projects"] == []
    assert body["window_hours"] == 24


def test_by_agent_and_trend_empty():
    c = _empty_app()
    assert c.get("/api/by-agent?hours=24").json() == []
    assert len(c.get("/api/trend?hours=24&buckets=12").json()) == 12


def test_by_model_empty():
    r = _empty_app().get("/api/by-model?hours=24")
    assert r.status_code == 200
    assert r.json() == []


def test_index_served():
    r = _empty_app().get("/")
    assert r.status_code == 200
    assert "cost monitor" in r.text


def test_reconcile_unconfigured_project():
    app = create_app(
        Config(
            projects=[
                ProjectConfig(
                    name="demo", public_key="pk", secret_key="sk", base_url="http://x"
                )
            ]
        )
    )
    r = TestClient(app).get("/api/reconcile?project=demo")
    assert r.status_code == 200
    assert r.json()[0]["configured"] is False


def test_project_slug():
    p = ProjectConfig(name="Robotsix Mill", public_key="pk", secret_key="sk")
    assert p.slug == "robotsix-mill"


def test_load_config_missing(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        load_config(tmp_path / "nope.yaml")


def test_load_config_roundtrip(tmp_path: Path):
    cfg = tmp_path / "projects.yaml"
    cfg.write_text(
        "projects:\n"
        "  - name: A\n    public_key: pk\n    secret_key: sk\n"
        "    base_url: http://lf\n"
        "settings:\n  default_window_hours: 48\n"
    )
    loaded = load_config(cfg)
    assert loaded.projects[0].name == "A"
    assert loaded.settings.default_window_hours == 48
    assert loaded.settings.analyst.enabled is False
