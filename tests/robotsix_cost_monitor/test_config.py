"""Unit tests for config.py I/O helpers."""

# mypy: disable-error-code="arg-type"

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from robotsix_cost_monitor.config import (
    Config,
    Settings,
    data_dir,
    load_config,
    resolve_registry_api_key,
)

# -- data_dir -----------------------------------------------------------


def test_data_dir_default(monkeypatch: pytest.MonkeyPatch) -> None:
    result = data_dir()
    assert result.name == ".data"


def test_data_dir_respects_settings_data_dir() -> None:
    """data_dir(settings) uses the configured data_dir field."""
    # Relative path — resolved against repo root.
    result = data_dir(settings=Settings(data_dir="custom/path"))
    assert result.name == "path"
    assert result.parent.name == "custom"

    # Absolute path — used as-is.
    result = data_dir(settings=Settings(data_dir="/absolute/custom"))
    assert result == Path("/absolute/custom")


# -- Settings -----------------------------------------------------------


def test_settings_defaults() -> None:
    s = Settings()
    assert s.server_host == "0.0.0.0"
    assert s.server_port == 8080
    assert s.default_window_hours == 168
    assert s.cache_ttl_seconds == 60
    assert s.reconcile_tolerance_usd == 1.0
    assert s.reconcile_schedule_hours == 24.0
    assert s.subscription_call_cap == 0
    assert s.log_format == "json"
    assert s.log_level == "INFO"
    assert s.data_dir == Path(".data")


def test_settings_subscription_call_cap() -> None:
    s = Settings(subscription_call_cap=5000)
    assert s.subscription_call_cap == 5000


def test_settings_data_dir_default() -> None:
    assert Settings().data_dir == Path(".data")


# -- resolve_registry_api_key -------------------------------------------


def test_resolve_registry_api_key_prefers_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """DEPLOY_API_KEY takes precedence over the config-file value."""
    monkeypatch.setenv("DEPLOY_API_KEY", "injected-key")
    settings = Settings(registry_api_key="config-key")
    assert resolve_registry_api_key(settings) == "injected-key"


def test_resolve_registry_api_key_falls_back_to_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When DEPLOY_API_KEY is unset, the config-file key is used."""
    monkeypatch.delenv("DEPLOY_API_KEY", raising=False)
    settings = Settings(registry_api_key="config-key")
    assert resolve_registry_api_key(settings) == "config-key"


# -- load_config --------------------------------------------------------


def test_load_config_found(monkeypatch: pytest.MonkeyPatch) -> None:
    """Write a minimal valid config to a temp file and load it."""
    data: dict[str, object] = {
        "settings": {},
    }
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(data, f)
        tmp_path = Path(f.name)

    try:
        monkeypatch.setenv("ROBOTSIX_CONFIG_FILE", str(tmp_path))
        config = load_config()
        assert isinstance(config, Config)
    finally:
        tmp_path.unlink()


def test_load_config_not_found() -> None:
    """When path is given to a nonexistent file, robotsix_config returns defaults."""
    nonexistent = Path("/nonexistent/path/config.json")
    config = load_config(nonexistent)
    assert isinstance(config, Config)
