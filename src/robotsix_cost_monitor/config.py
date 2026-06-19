"""Configuration models + loader for robotsix-cost-monitor.

A single YAML file (``config/projects.yaml``) lists the Langfuse projects to
monitor plus optional global settings. Real keys live only in that file (it is
gitignored); ``config/projects.example.yaml`` is the committed template.
"""

from __future__ import annotations

import os
from pathlib import Path

import yaml
from pydantic import BaseModel, Field


class ProjectConfig(BaseModel):
    """One Langfuse project to monitor."""

    name: str
    public_key: str
    secret_key: str
    base_url: str = "https://cloud.langfuse.com"
    # Optional OpenRouter API/management key for reconciliation of this project.
    openrouter_key: str | None = None

    @property
    def slug(self) -> str:
        """URL-safe identifier derived from the display name."""
        return self.name.strip().lower().replace(" ", "-").replace("/", "-")


class AnalystConfig(BaseModel):
    """LLM cost-analyst settings (optional — disabled without an OpenRouter key).

    The analyst runs a level-2 (llmio tier-2) agent over the deterministic cost
    digest, with a level-3 sub-agent that drills into the most expensive traces,
    and — when configured with a broker — files a board ticket via agent-comm
    when a cost problem warrants it.
    """

    # -- LLM (robotsix-llmio) --
    openrouter_key: str | None = None
    # Level-3 orchestrator provider: "claude-sdk" → Claude Opus (needs the
    # mounted ~/.claude + the claude CLI in the image; falls back to OpenRouter
    # if unavailable). "openrouter-deepseek" → deepseek-v4-pro.
    orchestrator_provider: str = "claude-sdk"
    global_model: str | None = None  # L3 orchestrator model; blank → provider default
    trace_model: str | None = None  # level-2 trace agent; blank → llmio tier-2 default
    window_hours: int = 24
    top_stages: int = 8
    max_trace_analyses: int = 5  # how many top-cost traces the L3 agent may open
    schedule_hours: float = 0.0  # >0 → run automatically on this cadence

    # -- Ticket filing via the agent-comm broker (optional) --
    broker_host: str | None = None
    broker_port: int = 443
    broker_scheme: str = "https"
    broker_token: str | None = None
    # The analyst files tickets by *messaging the board manager* (which dedups +
    # acts), never the dumb responder — so there's no filing path that bypasses
    # the manager. board_agent_id is kept for optional read queries.
    board_manager_id: str = "board-manager-robotsix-mill"
    board_agent_id: str = "board-robotsix-mill"
    board_repo_id: str = "robotsix-cost-monitor"

    # -- The analyst's own Langfuse project (so its L2/L3 runs are traced) --
    langfuse_public_key: str | None = None
    langfuse_secret_key: str | None = None
    langfuse_base_url: str | None = None
    langfuse_project_id: str | None = None

    @property
    def enabled(self) -> bool:
        return bool(self.openrouter_key)

    @property
    def can_file_tickets(self) -> bool:
        return bool(self.broker_host and self.broker_token)


class Settings(BaseModel):
    """Global dashboard settings."""

    default_window_hours: int = 168
    cache_ttl_seconds: int = 60
    reconcile_tolerance_usd: float = 1.0
    analyst: AnalystConfig = Field(default_factory=AnalystConfig)


class Config(BaseModel):
    """Top-level config: the projects to monitor + global settings."""

    projects: list[ProjectConfig] = Field(default_factory=list)
    settings: Settings = Field(default_factory=Settings)

    def project(self, slug: str) -> ProjectConfig | None:
        for p in self.projects:
            if p.slug == slug:
                return p
        return None


def _config_path() -> Path:
    """Resolve the config path.

    Honors ``COST_MONITOR_CONFIG``; otherwise ``config/projects.yaml`` relative
    to the repo root (two parents up from this file's package).
    """
    env = os.environ.get("COST_MONITOR_CONFIG")
    if env:
        return Path(env)
    return Path(__file__).resolve().parents[2] / "config" / "projects.yaml"


def data_dir() -> Path:
    """Resolve the runtime-state directory (reconciliation snapshots, analyst
    proposals).

    Honors ``COST_MONITOR_DATA``; otherwise ``.data`` relative to the repo root
    (two parents up from this file's package). In a container the package lives
    in site-packages, so the env var must point at a writable/persisted path.
    """
    env = os.environ.get("COST_MONITOR_DATA")
    if env:
        return Path(env)
    return Path(__file__).resolve().parents[2] / ".data"


def load_config(path: Path | None = None) -> Config:
    """Load and validate the configuration.

    Raises ``FileNotFoundError`` with a helpful message when the config is
    missing (the example template is committed; the real file is not).
    """
    p = path or _config_path()
    if not p.exists():
        raise FileNotFoundError(
            f"config not found at {p} — copy config/projects.example.yaml to "
            f"config/projects.yaml and fill in your Langfuse keys "
            f"(or set COST_MONITOR_CONFIG)."
        )
    raw = yaml.safe_load(p.read_text()) or {}
    return Config.model_validate(raw)
