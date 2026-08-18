# Configuration Reference

The project is configured through a single JSON file (default: `config/config.json`,
overridable via `ROBOTSIX_CONFIG_FILE`). The schema is defined by two Pydantic models
in `robotsix_cost_monitor.config`: `Config` (top-level container) and `Settings`
(global dashboard and automation settings).

A complete example is available at [`config/config.example.json`](https://github.com/damien-robotsix/robotsix-cost-monitor/blob/main/config/config.example.json).

Project credentials (Langfuse keys, OpenRouter keys) are **discovered at runtime**
from the central-deploy registry (see `clients/registry.py`) — there is no hardcoded
project list in the config file.

---

## Top-level (`Config`)

| Key | Type | Default | Description |
| --- | --- | --- | --- |
| `settings` | `Settings` | `{}` | Global dashboard and automation settings. |

---

## `settings` — Global settings (`Settings`)

| Key | Type | Default | Description |
| --- | --- | --- | --- |
| `server_host` | `str` | `"0.0.0.0"` | Host address the dashboard web server binds to. Overridable via `serve --host`. |
| `server_port` | `int` | `8080` | TCP port the dashboard web server listens on. Overridable via `serve --port`. |
| `registry_base_url` | `str` | `""` | Base URL of the central-deploy registry API. Required for project discovery. |
| `registry_api_key` | `SecretStr` | `""` | API key for authenticating to the central-deploy registry. When deployed by robotsix-central-deploy with the `robotsix.deploy.access: "agent"` label, leave empty — the `DEPLOY_API_KEY` environment variable is injected automatically at deploy time. For local development, set a real key in the config file. |
| `registry_poll_interval_seconds` | `int` | `300` | Seconds between registry re-polls for project discovery. Set to `0` to only fetch at startup and on manual refresh. |
| `default_window_hours` | `int` | `168` | Default time window (in hours) for dashboard cost aggregations (7 days). |
| `cache_ttl_seconds` | `int` | `60` | How long per-trace cost results are cached before re-fetching from Langfuse. |
| `dashboard_refresh_interval_seconds` | `int` | `120` | Interval (seconds) between background dashboard cache-refresh runs that keep cost aggregates precomputed so the frontend never blocks on a live Langfuse fetch. Set to `0` to disable the periodic refresh loop. |
| `reconcile_tolerance_usd` | `float` | `1.0` | Maximum allowed drift (USD) between OpenRouter and Langfuse costs before reconciliation is flagged. |
| `reconcile_schedule_hours` | `float` | `24.0` | Interval in hours between automatic reconciliation runs. Set to `0` to disable scheduled reconciliation. |
| `subscription_call_cap` | `int` | `0` | Per-day cap on subscription-triggered calls. Set to `0` to disable the cap. |
| `low_balance_threshold_usd` | `float` | `5.0` | OpenRouter account remaining-balance threshold in USD. When the remaining balance drops below this value during reconciliation, a warning is logged and a "low bal" pill is shown in the dashboard. Set to `0` to disable the low-balance check. |
| `log_format` | `str` | `"json"` | Structured log output format. `"json"` for production ingestion; `"console"` for coloured human-readable output. |
| `log_level` | `str` | `"INFO"` | Minimum log level for all loggers. Set to `"DEBUG"` for verbose diagnostics. |
| `data_dir` | `str` | `".data"` | Directory for persistent runtime state (reconciliation snapshots). |
| `auth` | `AuthConfig` | `{}` (empty = disabled) | HTTP Basic authentication credentials for the dashboard. When `username` and `password` are set, all endpoints except `/health` require HTTP Basic auth. When either is empty, the dashboard is served with no access control. |

---

## `settings.auth` — Dashboard authentication (`AuthConfig`)

| Key | Type | Default | Description |
| --- | --- | --- | --- |
| `username` | `str` | `""` | HTTP Basic auth username. When empty, auth is disabled. |
| `password` | `SecretStr` | `""` | HTTP Basic auth password. Stored as a Pydantic `SecretStr`. |

---

## Environment variables

| Variable | Default | Description |
| --- | --- | --- |
| `ROBOTSIX_CONFIG_FILE` | `config/config.json` | Path to the JSON configuration file (relative to repository root). |
| `DEPLOY_API_KEY` | *(unset)* | Deploy API key auto-injected by robotsix-central-deploy when the component declares the `agent` deploy-access setting. Used as the registry API key when `settings.registry_api_key` is empty. |

Log format, log level, and data directory are now configured via `settings.log_format`,
`settings.log_level`, and `settings.data_dir` in the config file rather than environment
variables.
