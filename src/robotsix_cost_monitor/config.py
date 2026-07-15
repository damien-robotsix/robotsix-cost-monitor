"""Configuration models + loader for robotsix-cost-monitor.

A single JSON file (``config/projects.json``) lists the Langfuse projects to
monitor plus optional global settings. Real keys live only in that file (it is
gitignored); ``config/projects.example.json`` is the committed template.
"""

from __future__ import annotations

import os
from pathlib import Path

from pydantic import BaseModel, Field
from robotsix_config import load_config as _load_config


class ProjectConfig(BaseModel):
    """One Langfuse project to monitor."""

    name: str
    public_key: str = Field(pattern=r"^pk-lf-")
    secret_key: str = Field(pattern=r"^sk-lf-")
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
    producing and storing cost-reduction proposals under ``.data/analyst/``.
    """

    # -- LLM (robotsix-llmio) --
    # Provider + model per level come from llmio's tier config (LEVEL2 →
    # openrouter-deepseek/deepseek-v4-pro for the trace agent; LEVEL3 →
    # claude-sdk/opus for the orchestrator). These optional overrides only pin a
    # specific MODEL for a level; blank → the llmio tier default.
    openrouter_key: str | None = None
    global_model: str | None = None  # L3 orchestrator model; blank → tier-3 default
    trace_model: str | None = None  # L2 trace model; blank → tier-2 default
    window_hours: int = 24
    top_stages: int = 8
    # Trace selection is PER AGENT (so cheaper agents aren't crowded out by the
    # priciest one): take the top `traces_per_agent` traces of each agent, then
    # cap the total at `max_trace_analyses`. Keep max_trace_analyses ≥ the number
    # of agents for full coverage.
    traces_per_agent: int = 1
    max_trace_analyses: int = 12  # overall cap on traces analyzed per run
    # >0 → run ALL analyses (fleet + most-costly ticket + most-costly stage) on
    # this cadence; default daily. 0 disables the scheduler (manual only).
    schedule_hours: float = 24.0

    # -- The analyst's own Langfuse project (so its L2/L3 runs are traced) --
    langfuse_public_key: str | None = None
    langfuse_secret_key: str | None = None
    langfuse_base_url: str | None = None
    langfuse_project_id: str | None = None

    @property
    def enabled(self) -> bool:
        """Whether the cost-analyst mode is enabled in the effective config."""
        return bool(self.openrouter_key)


class Settings(BaseModel):
    """Global dashboard settings."""

    default_window_hours: int = 168
    cache_ttl_seconds: int = 60
    reconcile_tolerance_usd: float = 1.0
    # Auto-run reconciliation every N hours (0 disables; default daily). The
    # stored result drives the dashboard warning banner.
    reconcile_schedule_hours: float = 24.0
    # Per-day subscription call cap for volume-vs-cap monitoring; 0 = disabled/unknown.
    subscription_call_cap: int = 0
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


def _config_path() -> Path:
    """Resolve the config path.

    Honors ``COST_MONITOR_CONFIG``; otherwise ``config/projects.json`` relative
    to the repo root (two parents up from this file's package).
    """
    env = os.environ.get("COST_MONITOR_CONFIG")
    if env:
        return Path(env)
    return Path(__file__).resolve().parents[2] / "config" / "projects.json"


def data_dir() -> Path:
    """Resolve the runtime-state directory for persistence.

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
            f"config not found at {p} — copy config/projects.example.json to "
            f"config/projects.json and fill in your Langfuse keys "
            f"(or set COST_MONITOR_CONFIG)."
        )
    return _load_config(Config, path=p)
