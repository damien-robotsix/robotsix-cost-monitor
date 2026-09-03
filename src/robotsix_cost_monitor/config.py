"""Configuration models + loader for robotsix-cost-monitor.

Cost-monitor discovers projects at runtime from the central-deploy registry
instead of carrying hardcoded Langfuse credentials. The config file only holds
generic settings: the registry URL + API key, polling/window defaults, and
auth/reconcile knobs.

The config is located via the ``ROBOTSIX_CONFIG_FILE`` environment variable
(default ``config/config.json``). ``config/config.example.json`` is the
committed template (gitignored real keys).
"""

from __future__ import annotations

import os
from pathlib import Path

from pydantic import BaseModel, Field, SecretStr
from robotsix_config import load_config as _load_config


class AuthConfig(BaseModel):
    """HTTP Basic auth for the dashboard.

    The dashboard has no other access control, so when it is exposed through
    the central-deploy gateway (an unauthenticated reverse proxy) this MUST
    be set — otherwise the cost data is public. When either field is empty
    the dashboard is served open (local dev / SSH-tunnel only). ``/health``
    is always exempt so the container healthcheck works.
    """

    username: str = Field(
        default="",
        description=(
            "Dashboard HTTP Basic auth username. Empty means the dashboard is "
            "served open."
        ),
    )
    password: SecretStr = Field(
        default=SecretStr(""),
        description=(
            "Dashboard HTTP Basic auth password. Empty means the dashboard is "
            "served open."
        ),
    )


class Settings(BaseModel):
    """Global dashboard settings — no per-project config (registry-driven)."""

    auth: AuthConfig = Field(
        default_factory=AuthConfig,
        description=(
            "HTTP Basic auth — REQUIRED when exposed via the gateway (see AuthConfig)."
        ),
    )
    # Binding every interface is deliberate: the dashboard serves from inside a
    # container behind the central-deploy gateway, and a service that binds
    # 127.0.0.1 there is unreachable through it — the container's own
    # healthcheck still passes, so it fails as a 502 rather than a crash.
    server_host: str = Field(
        default="0.0.0.0",  # noqa: S104  # nosec B104 - see above
        description="Bind address for the dashboard web server.",
    )
    server_port: int = Field(
        default=8080,
        description="Port for the dashboard web server.",
    )
    registry_base_url: str = Field(
        default="",
        description=(
            "Central-deploy registry base URL — projects are discovered at runtime."
        ),
    )
    registry_api_key: SecretStr = Field(
        default=SecretStr(""),
        description=(
            "API key for authenticating to the central-deploy registry. When "
            "deployed by robotsix-central-deploy with the robotsix.deploy.access: "
            '"agent" label, leave empty — the DEPLOY_API_KEY environment variable '
            "is injected automatically at deploy time."
        ),
    )
    registry_poll_interval_seconds: int = Field(
        default=300,
        description=(
            "Seconds between registry re-polls (0 = only at startup + manual refresh)."
        ),
    )
    default_window_hours: int = Field(
        default=168,
        description="Default cost-aggregation window in hours (e.g. 168 = 7 days).",
    )
    cache_ttl_seconds: int = Field(
        default=60,
        description=(
            "Seconds before cached Langfuse data is considered stale and re-fetched."
        ),
    )
    dashboard_refresh_interval_seconds: int = Field(
        default=120,
        description=(
            "Background cache-refresh interval — keeps dashboard aggregates "
            "precomputed so the frontend never blocks on a live Langfuse "
            "fetch. 0 disables."
        ),
    )
    reconcile_tolerance_usd: float = Field(
        default=1.0,
        description=(
            "Maximum allowed difference in USD between provider cost and traced "
            "cost before reconciliation is flagged as out of tolerance."
        ),
    )
    reconcile_schedule_hours: float = Field(
        default=24.0,
        description=(
            "Auto-run reconciliation every N hours (0 disables; default daily). "
            "The stored result drives the dashboard warning banner."
        ),
    )
    subscription_call_cap: int = Field(
        default=0,
        description=(
            "Per-day subscription call cap for volume-vs-cap monitoring; "
            "0 = disabled/unknown."
        ),
    )
    low_balance_threshold_usd: float = Field(
        default=5.0,
        description=(
            "OpenRouter account remaining-balance threshold in USD. When the "
            "remaining balance drops below this value a warning is logged and "
            "surfaced in the dashboard. Set to 0 to disable the low-balance "
            "check."
        ),
    )
    data_dir: Path = Field(
        default=Path(".data"),
        description=(
            "Runtime data directory for persistence (.data by default; /data in "
            "containers)."
        ),
    )
    log_format: str = Field(
        default="json",
        description='Structured log output format: "console" or "json".',
    )
    log_level: str = Field(
        default="INFO",
        description="Minimum log level for all loggers.",
    )
    mill_base_url: str = Field(
        default="",
        description=(
            'Base URL of the robotsix-mill board API (e.g. "http://mill:8080"). '
            "When empty, stuck-ticket detection is disabled."
        ),
    )
    mill_api_key: SecretStr = Field(
        default=SecretStr(""),
        json_schema_extra={"writeOnly": True},
        description=(
            "API key for authenticating to the mill board API. When deployed by "
            'robotsix-central-deploy with the robotsix.deploy.access: "agent" '
            "label, leave empty — the DEPLOY_API_KEY env var is used as a "
            "fallback."
        ),
    )
    stuck_ticket_threshold_hours: int = Field(
        default=48,
        description=(
            "Hours a ticket may remain in a non-terminal state before it is "
            "flagged as stuck. 0 disables stuck-ticket detection."
        ),
    )
    stuck_ticket_check_interval_seconds: int = Field(
        default=600,
        description=("Seconds between stuck-ticket checks (default 600 = 10 minutes)."),
    )


def resolve_registry_api_key(settings: Settings) -> str:
    """Return the effective registry API key.

    When deployed by robotsix-central-deploy with the ``robotsix.deploy.access:
    "agent"`` label, the deploy API key is auto-injected as the
    ``DEPLOY_API_KEY`` environment variable — no manual config needed.  Falls
    back to ``settings.registry_api_key`` for local development.
    """
    env_val = os.environ.get("DEPLOY_API_KEY", "")
    if env_val:
        return env_val
    return settings.registry_api_key.get_secret_value()


def resolve_mill_api_key(settings: Settings) -> str:
    """Return the effective mill API key.

    Follows the same convention as :func:`resolve_registry_api_key`: the
    ``DEPLOY_API_KEY`` environment variable is the default when deployed by
    robotsix-central-deploy.  Falls back to ``settings.mill_api_key`` for
    local development.
    """
    env_val = os.environ.get("DEPLOY_API_KEY", "")
    if env_val:
        return env_val
    return settings.mill_api_key.get_secret_value()


class Config(BaseModel):
    """Top-level config: registry-driven project discovery + global settings.

    Project credentials are discovered at runtime from the central-deploy
    registry — there is no hardcoded project list.
    """

    settings: Settings = Field(default_factory=Settings)


def data_dir(settings: Settings | None = None) -> Path:
    """Resolve the runtime-state directory for persistence.

    When *settings* is given, the ``settings.data_dir`` field is used (relative
    paths are resolved against the repo root).  Without *settings* the legacy
    default ``.data`` relative to the repo root is returned for backward
    compatibility.
    """
    if settings is not None:
        path = Path(settings.data_dir)
        if not path.is_absolute():
            path = Path(__file__).resolve().parents[2] / path
        return Path(os.path.abspath(path)).resolve()
    return Path(
        os.path.abspath(Path(__file__).resolve().parents[2] / ".data")
    ).resolve()


def load_config(path: Path | None = None) -> Config:
    """Load and validate the configuration via ``ROBOTSIX_CONFIG_FILE``.

    When *path* is given (tests), passes it through directly to
    :func:`robotsix_config.load_config`.
    """
    if path is not None:
        return _load_config(Config, path=path)
    return _load_config(Config)
