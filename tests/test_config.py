"""Unit tests for config.py I/O helpers and AnalystConfig model."""

from __future__ import annotations

from pathlib import Path

import pytest

from robotsix_cost_monitor.config import (
    AnalystConfig,
    _config_path,
    data_dir,
)

# -- _config_path -------------------------------------------------------


def test_config_path_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COST_MONITOR_CONFIG", "/custom/config.yaml")
    assert _config_path() == Path("/custom/config.yaml")


def test_config_path_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("COST_MONITOR_CONFIG", raising=False)
    result = _config_path()
    assert result.name == "projects.yaml"
    assert result.parent.name == "config"


# -- data_dir -----------------------------------------------------------


def test_data_dir_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COST_MONITOR_DATA", "/custom/data")
    assert data_dir() == Path("/custom/data")


def test_data_dir_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("COST_MONITOR_DATA", raising=False)
    result = data_dir()
    assert result.name == ".data"


# -- AnalystConfig ------------------------------------------------------


def test_analyst_defaults_disabled() -> None:
    cfg = AnalystConfig()
    assert cfg.enabled is False
    assert cfg.can_file_tickets is False


def test_analyst_enabled_with_openrouter_key() -> None:
    cfg = AnalystConfig(openrouter_key="sk-abc123")
    assert cfg.enabled is True
    assert cfg.can_file_tickets is False  # no broker configured


def test_analyst_can_file_tickets_with_full_broker() -> None:
    cfg = AnalystConfig(
        openrouter_key="sk-abc123",
        broker_host="broker.example.com",
        broker_token="tok-xyz",
    )
    assert cfg.enabled is True
    assert cfg.can_file_tickets is True


def test_analyst_cannot_file_tickets_without_token() -> None:
    cfg = AnalystConfig(
        openrouter_key="sk-abc123",
        broker_host="broker.example.com",
        # broker_token missing
    )
    assert cfg.enabled is True
    assert cfg.can_file_tickets is False


def test_analyst_cannot_file_tickets_without_host() -> None:
    cfg = AnalystConfig(
        openrouter_key="sk-abc123",
        broker_token="tok-xyz",
        # broker_host missing
    )
    assert cfg.enabled is True
    assert cfg.can_file_tickets is False


def test_analyst_empty_strings_are_falsy() -> None:
    cfg = AnalystConfig(
        openrouter_key="",
        broker_host="",
        broker_token="",
    )
    assert cfg.enabled is False
    assert cfg.can_file_tickets is False


def test_analyst_field_defaults() -> None:
    cfg = AnalystConfig()
    assert cfg.window_hours == 24
    assert cfg.top_stages == 8
    assert cfg.max_trace_analyses == 12
    assert cfg.traces_per_agent == 1
    assert cfg.schedule_hours == 24.0
    assert cfg.broker_port == 443
    assert cfg.broker_scheme == "https"
    assert cfg.board_agent_id == "board-robotsix-mill"
    assert cfg.board_repo_id == "robotsix-cost-monitor"
    assert cfg.global_model is None
    assert cfg.trace_model is None
    assert cfg.broker_host is None
    assert cfg.broker_token is None
    assert cfg.openrouter_key is None
    assert cfg.langfuse_public_key is None
    assert cfg.langfuse_secret_key is None
    assert cfg.langfuse_base_url is None
    assert cfg.langfuse_project_id is None
