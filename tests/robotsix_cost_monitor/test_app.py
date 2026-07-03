"""App + config tests using a zero-project config (no network)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from robotsix_cost_monitor.app import create_app
from robotsix_cost_monitor.config import Config, ProjectConfig, load_config


def _empty_app() -> TestClient:
    return TestClient(create_app(Config(projects=[])))


def test_health() -> None:
    r = _empty_app().get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_summary_empty_is_zero() -> None:
    r = _empty_app().get("/api/summary?hours=24")
    assert r.status_code == 200
    body = r.json()
    assert body["total_cost"] == 0.0
    assert body["projects"] == []
    assert body["window_hours"] == 24


def test_summary_unknown_project_returns_404() -> None:
    """An unknown project slug returns 404 with a structured error envelope."""
    r = _empty_app().get("/api/summary?project=nonexistent")
    assert r.status_code == 404
    body = r.json()
    assert body["error"]["code"] == "HTTP_ERROR"
    assert "nonexistent" in body["error"]["detail"]


def test_summary_project_all_returns_200_when_no_projects() -> None:
    """?project=all is always valid — returns 200 even with zero projects."""
    r = _empty_app().get("/api/summary?project=all")
    assert r.status_code == 200


def test_unknown_project_across_endpoints() -> None:
    """Every project-scoped endpoint returns 404 for an unknown slug."""
    c = _empty_app()
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
        assert body["error"]["code"] == "HTTP_ERROR"
        assert "nope" in body["error"]["detail"]


def test_by_agent_and_trend_empty() -> None:
    c = _empty_app()
    assert c.get("/api/by-agent?hours=24").json() == []
    assert len(c.get("/api/trend?hours=24&buckets=12").json()) == 12


def test_by_agent_accepts_backend_param() -> None:
    """The /api/by-agent route accepts ?backend=... and returns empty for no projects."""
    c = _empty_app()
    r = c.get("/api/by-agent?hours=24&backend=openrouter")
    assert r.status_code == 200
    assert r.json() == []


def test_by_agent_backend_all_is_default() -> None:
    """Omitting ?backend=... is equivalent to ?backend=all."""
    c = _empty_app()
    assert (
        c.get("/api/by-agent?hours=24").json()
        == c.get("/api/by-agent?hours=24&backend=all").json()
    )


def test_by_model_empty() -> None:
    r = _empty_app().get("/api/by-model?hours=24")
    assert r.status_code == 200
    assert r.json() == []


def test_backend_trend_empty() -> None:
    r = _empty_app().get("/api/backend-trend?hours=24&backend=openrouter")
    assert r.status_code == 200
    assert r.json() == []


def test_index_served() -> None:
    r = _empty_app().get("/")
    assert r.status_code == 200
    assert "cost monitor" in r.text
    # The dashboard renders the last reconcile into this element on load.
    assert 'id="recon-when"' in r.text


def test_reconcile_last_served_from_disk(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The persisted last reconcile is served by ``/api/reconcile/last`` — this is
    what lets the dashboard show the last run after a page reload or container
    restart (the file is on the persisted data volume).
    """
    monkeypatch.setenv("COST_MONITOR_DATA", str(tmp_path))
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

    r = _empty_app().get("/api/reconcile/last")

    assert r.status_code == 200
    body = r.json()
    assert body["generated_at"] == "2026-06-19T15:37:25+00:00"
    assert body["status"] == "ok"
    assert body["results"][0]["project"] == "demo"


def test_reconcile_unconfigured_project() -> None:
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


def test_project_slug() -> None:
    p = ProjectConfig(name="Robotsix Mill", public_key="pk", secret_key="sk")
    assert p.slug == "robotsix-mill"


def test_load_config_missing(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_config(tmp_path / "nope.yaml")


def test_load_config_roundtrip(tmp_path: Path) -> None:
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


# ---------------------------------------------------------------------------
# Analyst scheduler — restart-resilient cadence
# ---------------------------------------------------------------------------


def test_initial_analyst_delay_never_ran_runs_now() -> None:
    """With no prior run, the first analysis fires immediately."""
    from robotsix_cost_monitor.app import _initial_analyst_delay

    now = datetime(2026, 6, 21, 12, 0, tzinfo=UTC)
    assert _initial_analyst_delay(24 * 3600, None, now) == 0.0


def test_initial_analyst_delay_overdue_runs_now() -> None:
    """When more than one interval has elapsed since the last run, run now."""
    from robotsix_cost_monitor.app import _initial_analyst_delay

    now = datetime(2026, 6, 21, 12, 0, tzinfo=UTC)
    last = datetime(2026, 6, 19, 12, 0, tzinfo=UTC)  # 48h ago
    assert _initial_analyst_delay(24 * 3600, last, now) == 0.0


def test_initial_analyst_delay_waits_only_the_remainder() -> None:
    """A restart mid-interval waits only the remaining time, not a fresh 24h."""
    from robotsix_cost_monitor.app import _initial_analyst_delay

    now = datetime(2026, 6, 21, 12, 0, tzinfo=UTC)
    last = datetime(2026, 6, 21, 6, 0, tzinfo=UTC)  # 6h ago, interval 24h
    assert _initial_analyst_delay(24 * 3600, last, now) == 18 * 3600


def test_initial_analyst_delay_future_last_run_falls_back_to_interval() -> None:
    """A last-run timestamp in the future (clock skew) waits a full interval
    rather than firing immediately.
    """
    from robotsix_cost_monitor.app import _initial_analyst_delay

    now = datetime(2026, 6, 21, 12, 0, tzinfo=UTC)
    future = datetime(2026, 6, 21, 18, 0, tzinfo=UTC)
    assert _initial_analyst_delay(24 * 3600, future, now) == 24 * 3600


def test_last_analyst_run_picks_most_recent(monkeypatch: pytest.MonkeyPatch) -> None:
    """``_last_analyst_run`` returns the newest generated_at across the three
    persisted analyses (and handles naive timestamps as UTC).
    """
    from robotsix_cost_monitor import app

    monkeypatch.setattr(
        app, "load_proposals", lambda: {"generated_at": "2026-06-19T15:37:25+00:00"}
    )
    monkeypatch.setattr(
        app,
        "load_targeted_analysis",
        lambda kind: {
            "ticket": {"generated_at": "2026-06-20T09:00:00"},  # naive → UTC
            "stage": {"generated_at": None},
        }[kind],
    )

    assert app._last_analyst_run() == datetime(2026, 6, 20, 9, 0, tzinfo=UTC)


def test_last_analyst_run_none_when_unrun(monkeypatch: pytest.MonkeyPatch) -> None:
    """No persisted timestamps → ``None`` (so the first run fires immediately)."""
    from robotsix_cost_monitor import app

    monkeypatch.setattr(app, "load_proposals", lambda: {"generated_at": None})
    monkeypatch.setattr(
        app, "load_targeted_analysis", lambda kind: {"generated_at": None}
    )

    assert app._last_analyst_run() is None
