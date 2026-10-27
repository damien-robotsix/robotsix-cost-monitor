"""Tests for the standard config HTTP surface.

`config-ownership.md` requires every deployable component to expose
`GET /config`, `PUT /config`, `GET /config/versions` and
`POST /config/rollback`. Because the deploy plane keeps no copy of these
values, this surface is the only way config is inspected or changed at
runtime — so the tests below care most about the two ways it can lose data:
returning a secret it should have masked, and overwriting a stored secret
with the mask a client echoed back.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from robotsix_cost_monitor.app import create_app
from robotsix_cost_monitor.config import Config

AUTH = ("ops", "s3cret")


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    cfg_file = tmp_path / "config.json"
    cfg_file.write_text(
        json.dumps(
            {
                "settings": {
                    "auth": {"username": "ops", "password": "s3cret"},
                    "log_level": "INFO",
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("ROBOTSIX_CONFIG_FILE", str(cfg_file))
    client = TestClient(
        create_app(Config.model_validate(json.loads(cfg_file.read_text())))
    )
    # The dashboard is behind HTTP Basic auth whenever it is exposed, so
    # exercise the surface the way it is actually reached.
    client.auth = AUTH
    return client


class TestGetConfig:
    def test_returns_config_schema_and_version(self, client: TestClient) -> None:
        body = client.get("/config").json()
        assert set(body) >= {"config", "schema", "version"}
        assert body["schema"]["title"] == "Config"

    def test_secrets_are_masked(self, client: TestClient) -> None:
        """The password is a SecretStr; it must never leave the process."""
        body = client.get("/config").json()
        assert body["config"]["settings"]["auth"]["password"] == "**********"

    def test_non_secrets_are_returned_intact(self, client: TestClient) -> None:
        body = client.get("/config").json()
        assert body["config"]["settings"]["auth"]["username"] == "ops"


class TestPutConfig:
    def test_partial_update_keeps_other_keys(self, client: TestClient) -> None:
        r = client.put("/config", json={"settings": {"log_level": "DEBUG"}})
        assert r.status_code == 200
        cfg = r.json()["config"]
        assert cfg["settings"]["log_level"] == "DEBUG"
        assert cfg["settings"]["auth"]["username"] == "ops"

    def test_echoed_mask_keeps_the_secret(self, client: TestClient) -> None:
        """The regression this surface exists to avoid: a client GETs the
        config, edits one field, and PUTs everything back — including the
        mask it was shown."""
        current = client.get("/config").json()["config"]
        current["settings"]["log_level"] = "WARNING"
        client.put("/config", json=current)
        after = client.get("/config").json()["config"]
        assert after["settings"]["log_level"] == "WARNING"
        assert after["settings"]["auth"]["password"] == "**********"
        # and the real value survived, not the literal mask
        assert client.get("/config").status_code == 200

    def test_version_increments(self, client: TestClient) -> None:
        before = client.get("/config").json()["version"]
        after = client.put("/config", json={"settings": {"log_level": "DEBUG"}}).json()
        assert after["version"] > before

    def test_invalid_update_returns_422(self, client: TestClient) -> None:
        r = client.put("/config", json={"settings": {"log_level": {"bad": "type"}}})
        assert r.status_code == 422

    def test_update_takes_effect_without_a_restart(self, client: TestClient) -> None:
        """A write that lands on disk but not on app.state reads as a
        successful save that silently did nothing."""
        client.put("/config", json={"settings": {"log_level": "DEBUG"}})
        app = cast("FastAPI", client.app)
        assert app.state.config.settings.log_level == "DEBUG"


class TestVersionsAndRollback:
    def test_versions_are_newest_first(self, client: TestClient) -> None:
        client.put("/config", json={"settings": {"log_level": "DEBUG"}})
        versions = client.get("/config/versions").json()["versions"]
        assert versions
        assert versions[0]["version"] > versions[-1]["version"]
        assert "changed_keys" in versions[0]

    def test_versions_omits_the_snapshots(self, client: TestClient) -> None:
        client.put("/config", json={"settings": {"log_level": "DEBUG"}})
        versions = client.get("/config/versions").json()["versions"]
        assert all("data" not in v for v in versions)

    def test_rollback_restores_an_earlier_value(self, client: TestClient) -> None:
        client.put("/config", json={"settings": {"log_level": "DEBUG"}})
        first = client.get("/config/versions").json()["versions"][-1]["version"]
        r = client.post("/config/rollback", json={"version": first})
        assert r.status_code == 200
        assert r.json()["config"]["settings"]["log_level"] == "INFO"

    def test_rollback_keeps_live_secret(self, client: TestClient) -> None:
        """The history stores no secrets, so a rollback must carry the current
        one forward rather than blanking it."""
        client.put("/config", json={"settings": {"log_level": "DEBUG"}})
        first = client.get("/config/versions").json()["versions"][-1]["version"]
        client.post("/config/rollback", json={"version": first})
        assert (
            client.get("/config").json()["config"]["settings"]["auth"]["password"]
            == "**********"
        )

    def test_unknown_version_is_rejected(self, client: TestClient) -> None:
        assert client.post("/config/rollback", json={"version": 999}).status_code == 422

    def test_non_integer_version_is_rejected(self, client: TestClient) -> None:
        assert client.post("/config/rollback", json={"version": "x"}).status_code == 422


class TestConfigSurfaceRequiresAuth:
    """The config surface reads and writes credentials, so it must never be
    reachable unauthenticated when auth is configured."""

    def test_all_routes_401_when_anon(self, client: TestClient) -> None:
        anon = TestClient(cast("FastAPI", client.app))
        assert anon.get("/config").status_code == 401
        assert anon.put("/config", json={}).status_code == 401
        assert anon.get("/config/versions").status_code == 401
        assert anon.post("/config/rollback", json={"version": 1}).status_code == 401
