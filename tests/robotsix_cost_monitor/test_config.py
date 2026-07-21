"""Unit tests for config.py I/O helpers and AnalystConfig model."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest
from pydantic import ValidationError

from robotsix_cost_monitor.config import (
    AnalystConfig,
    Config,
    ProjectConfig,
    Settings,
    data_dir,
    load_config,
)

# -- data_dir -----------------------------------------------------------


def test_data_dir_default(monkeypatch: pytest.MonkeyPatch) -> None:
    result = data_dir()
    assert result.name == ".data"


# -- AnalystConfig ------------------------------------------------------


def test_analyst_defaults_disabled() -> None:
    cfg = AnalystConfig()
    assert cfg.enabled is False


def test_analyst_enabled_with_openrouter_key() -> None:
    cfg = AnalystConfig(openrouter_key="sk-abc123")
    assert cfg.enabled is True


def test_analyst_empty_strings_are_falsy() -> None:
    cfg = AnalystConfig(
        openrouter_key="",
    )
    assert cfg.enabled is False


def test_example_config_max_trace_analyses_matches_code_default() -> None:
    """The example config must ship with the same max_trace_analyses as the
    Pydantic default, so users who copy it verbatim get the intended cap.
    """
    from pathlib import Path

    from robotsix_config import load_config

    from robotsix_cost_monitor.config import Config

    config = load_config(Config, path=Path("config/config.example.json"))
    assert config.settings.analyst is not None
    assert config.settings.analyst.max_trace_analyses == 12
    assert config.settings.analyst.traces_per_agent == 1
    assert config.settings.reconcile_schedule_hours == 24.0


def test_analyst_field_defaults() -> None:
    cfg = AnalystConfig()
    assert cfg.window_hours == 24
    assert cfg.top_stages == 8
    assert cfg.max_trace_analyses == 12
    assert cfg.traces_per_agent == 1
    assert cfg.schedule_hours == 24.0
    assert cfg.global_model is None
    assert cfg.trace_model is None
    assert cfg.openrouter_key is None
    assert cfg.langfuse_public_key is None
    assert cfg.langfuse_secret_key is None
    assert cfg.langfuse_base_url is None
    assert cfg.langfuse_project_id is None


# -- ProjectConfig ------------------------------------------------------


def test_project_config_slug() -> None:
    cfg = ProjectConfig(
        name="  My Awesome Project  ",
        public_key="pk-lf-abc",
        secret_key="sk-lf-xyz",
    )
    assert cfg.slug == "my-awesome-project"


def test_project_config_slug_special_chars() -> None:
    cfg = ProjectConfig(
        name="Project/A/B",
        public_key="pk-lf-abc",
        secret_key="sk-lf-xyz",
    )
    assert cfg.slug == "project-a-b"


def test_project_config_field_regex_patterns() -> None:
    # Valid public_key and secret_key pass.
    cfg = ProjectConfig(
        name="test",
        public_key="pk-lf-abc123",
        secret_key="sk-lf-xyz789",
    )
    assert cfg.public_key.get_secret_value() == "pk-lf-abc123"
    assert cfg.secret_key.get_secret_value() == "sk-lf-xyz789"

    # Invalid public_key (missing pk-lf- prefix) raises.
    with pytest.raises(ValidationError):
        ProjectConfig(
            name="test",
            public_key="pk-xyz-abc",
            secret_key="sk-lf-xyz",
        )

    # Invalid secret_key (missing sk-lf- prefix) raises.
    with pytest.raises(ValidationError):
        ProjectConfig(
            name="test",
            public_key="pk-lf-abc",
            secret_key="sk-xyz-abc",
        )


# -- Config.project -----------------------------------------------------


def test_config_project_lookup() -> None:
    config = Config(
        projects=[
            ProjectConfig(
                name="Alpha Project",
                public_key="pk-lf-aaa",
                secret_key="sk-lf-aaa",
            ),
            ProjectConfig(
                name="Beta Project",
                public_key="pk-lf-bbb",
                secret_key="sk-lf-bbb",
            ),
        ]
    )
    found = config.project("alpha-project")
    assert found is not None
    assert found.name == "Alpha Project"

    not_found = config.project("gamma-project")
    assert not_found is None


def test_config_project_empty() -> None:
    config = Config(projects=[])
    assert config.project("anything") is None


# -- Settings -----------------------------------------------------------


def test_settings_defaults() -> None:
    s = Settings()
    assert s.default_window_hours == 168
    assert s.cache_ttl_seconds == 60
    assert s.reconcile_tolerance_usd == 1.0
    assert s.reconcile_schedule_hours == 24.0
    assert s.subscription_call_cap == 0
    assert s.log_format == "json"
    assert s.log_level == "INFO"
    assert s.data_dir == ".data"
    assert isinstance(s.analyst, AnalystConfig)


def test_settings_subscription_call_cap() -> None:
    s = Settings(subscription_call_cap=5000)
    assert s.subscription_call_cap == 5000


# -- load_config --------------------------------------------------------


def test_load_config_found() -> None:
    """Write a minimal valid config to a temp file and load it."""
    data = {
        "projects": [
            {
                "name": "Temp Project",
                "public_key": "pk-lf-temp",
                "secret_key": "sk-lf-temp",
            }
        ],
        "settings": {},
    }
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(data, f)
        tmp_path = Path(f.name)

    try:
        config = load_config(tmp_path)
        assert isinstance(config, Config)
        assert len(config.projects) == 1
        assert config.projects[0].name == "Temp Project"
    finally:
        tmp_path.unlink()


def test_load_config_not_found() -> None:
    """When path is given to a nonexistent file, robotsix_config returns defaults."""
    nonexistent = Path("/nonexistent/path/config.json")
    config = load_config(nonexistent)
    assert isinstance(config, Config)
    assert config.projects == []


# -- data_dir extra -----------------------------------------------------


def test_data_dir_default_is_dot_data(monkeypatch: pytest.MonkeyPatch) -> None:
    result = data_dir()
    assert result.name == ".data"
