"""Configuration models + loader for robotsix-cost-monitor.

A single JSON file (``config/config.json``) lists the Langfuse projects to
monitor plus optional global settings. Real keys live only in that file (it is
gitignored); ``config/config.example.json`` is the committed template.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, SecretStr, field_validator
from robotsix_config import load_config as _load_config


class ProjectConfig(BaseModel):
    """One Langfuse project to monitor."""

    name: str
    public_key: SecretStr
    secret_key: SecretStr
    base_url: str = Field(
        default="https://cloud.langfuse.com", json_schema_extra={"advanced": True}
    )
    # Optional OpenRouter API/management key for reconciliation of this project.
    openrouter_key: SecretStr | None = None

    @field_validator("public_key", mode="before")
    @classmethod
    def _validate_public_key(cls, v: object) -> object:
        if isinstance(v, str) and not v.startswith("pk-lf-"):
            raise ValueError("must start with 'pk-lf-'")
        return v

    @field_validator("secret_key", mode="before")
    @classmethod
    def _validate_secret_key(cls, v: object) -> object:
        if isinstance(v, str) and not v.startswith("sk-lf-"):
            raise ValueError("must start with 'sk-lf-'")
        return v

    @field_validator("openrouter_key", mode="before")
    @classmethod
    def _coerce_empty_openrouter_key(cls, v: object) -> object:
        return None if v == "" else v

    @property
    def slug(self) -> str:
        """URL-safe identifier derived from the display name."""
        return self.name.strip().lower().replace(" ", "-").replace("/", "-")


class AnalystConfig(BaseModel):
    """LLM cost-analyst settings (optional — disabled without an OpenRouter key).

    The analyst runs a level-2 (llmio tier-2) agent over the deterministic cost
    digest, with a level-3 sub-agent that drills into the most expensive traces,
    producing and storing cost-reduction proposals under ``.data/analyst/``.
    """

    # -- LLM (robotsix-llmio) --
    # Provider + model per level come from llmio's tier config (LEVEL2 →
    # openrouter-deepseek/deepseek-v4-pro for the trace agent; LEVEL3 →
    # claude-sdk/opus for the orchestrator). These optional overrides only pin a
    # specific MODEL for a level; blank → the llmio tier default.
    openrouter_key: SecretStr | None = None
    global_model: str | None = Field(
        default=None, json_schema_extra={"advanced": True}
    )  # L3 orchestrator model; blank → tier-3 default
    trace_model: str | None = Field(
        default=None, json_schema_extra={"advanced": True}
    )  # L2 trace model; blank → tier-2 default
    window_hours: int = Field(default=24, json_schema_extra={"advanced": True})
    top_stages: int = Field(default=8, json_schema_extra={"advanced": True})
    # Trace selection is PER AGENT (so cheaper agents aren't crowded out by the
    # priciest one): take the top `traces_per_agent` traces of each agent, then
    # cap the total at `max_trace_analyses`. Keep max_trace_analyses ≥ the number
    # of agents for full coverage.
    traces_per_agent: int = Field(default=1, json_schema_extra={"advanced": True})
    max_trace_analyses: int = Field(
        default=12, json_schema_extra={"advanced": True}
    )  # overall cap on traces analyzed per run
    # >0 → run ALL analyses (fleet + most-costly ticket + most-costly stage) on
    # this cadence; default daily. 0 disables the scheduler (manual only).
    schedule_hours: float = Field(default=24.0, json_schema_extra={"advanced": True})

    # -- The analyst's own Langfuse project (so its L2/L3 runs are traced) --
    langfuse_public_key: SecretStr | None = None
    langfuse_secret_key: SecretStr | None = None
    langfuse_base_url: str | None = Field(
        default=None, json_schema_extra={"advanced": True}
    )
    langfuse_project_id: str | None = Field(
        default=None, json_schema_extra={"advanced": True}
    )

    @field_validator("openrouter_key", "langfuse_public_key", "langfuse_secret_key", mode="before")
    @classmethod
    def _coerce_empty_to_none(cls, v: object) -> object:
        return None if v == "" else v

    @property
    def enabled(self) -> bool:
        """Whether the cost-analyst mode is enabled in the effective config."""
        return bool(self.openrouter_key)


class Settings(BaseModel):
    """Global dashboard settings."""

    default_window_hours: int = Field(default=168, json_schema_extra={"advanced": True})
    cache_ttl_seconds: int = Field(default=60, json_schema_extra={"advanced": True})
    reconcile_tolerance_usd: float = Field(
        default=1.0, json_schema_extra={"advanced": True}
    )
    # Auto-run reconciliation every N hours (0 disables; default daily). The
    # stored result drives the dashboard warning banner.
    reconcile_schedule_hours: float = Field(
        default=24.0, json_schema_extra={"advanced": True}
    )
    # Per-day subscription call cap for volume-vs-cap monitoring; 0 = disabled/unknown.
    subscription_call_cap: int = Field(default=0, json_schema_extra={"advanced": True})
    # Runtime data directory for persistence (.data by default; /data in containers).
    data_dir: Path = Field(default=Path(".data"), json_schema_extra={"advanced": True})
    # Structured log output format: "console" or "json".
    log_format: str = Field(default="console", json_schema_extra={"advanced": True})
    # Minimum log level for all loggers.
    log_level: str = Field(default="INFO", json_schema_extra={"advanced": True})
    analyst: AnalystConfig = Field(default_factory=AnalystConfig)


class Config(BaseModel):
    """Top-level config: the projects to monitor + global settings."""

    projects: list[ProjectConfig] = Field(default_factory=list)
    settings: Settings = Field(default_factory=Settings)

    def project(self, slug: str) -> ProjectConfig | None:
        """Return the project config matching the given slug."""
        for p in self.projects:
            if p.slug == slug:
                return p
        return None


def load_config() -> Config:
    """Load and validate the configuration.

    Reads the path from ``ROBOTSIX_CONFIG_FILE`` (default ``config/config.json``).
    Raises ``FileNotFoundError`` with a helpful message when the config is missing.
    """
    from robotsix_config.config import resolve_config_path

    resolved = resolve_config_path()
    if not resolved.exists():
        raise FileNotFoundError(
            "config not found — copy config/config.example.json to "
            "config/config.json and fill in your keys "
            "(or set ROBOTSIX_CONFIG_FILE)."
        )
    return _load_config(Config)
