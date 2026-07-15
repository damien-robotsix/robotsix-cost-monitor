# Configuration Reference

The project is configured through a single JSON file (default: `config/projects.json`,
overridable via `COST_MONITOR_CONFIG`). The schema is defined by four Pydantic models
in `robotsix_cost_monitor.config`: `Config`, `ProjectConfig`, `Settings`, and
`AnalystConfig`.

A complete example is available at [`config/projects.example.json`](https://github.com/damien-robotsix/robotsix-cost-monitor/blob/main/config/projects.example.json).

---

## Top-level (`Config`)

| Key | Type | Default | Description |
|---|---|---|---|
| `projects` | `list[ProjectConfig]` | `[]` | Langfuse projects to monitor. |
| `settings` | `Settings` | `{}` | Global dashboard and automation settings. |

---

## `projects[]` — Project entries (`ProjectConfig`)

Each entry in the `projects` list connects to one Langfuse project.

| Key | Type | Required | Default | Description |
|---|---|---|---|---|
| `name` | `str` | yes | — | Display label shown in the dashboard UI. |
| `public_key` | `str` | yes | — | Langfuse public API key. |
| `secret_key` | `str` | yes | — | Langfuse secret API key. |
| `base_url` | `str` | no | `https://cloud.langfuse.com` | Base URL of the Langfuse instance (self-hosted or Cloud). |
| `openrouter_key` | `str` or `null` | no | `null` | OpenRouter API key for this project's cost reconciliation. When `null`, reconciliation is skipped for this project. |

---

## `settings` — Global settings (`Settings`)

| Key | Type | Default | Description |
|---|---|---|---|
| `default_window_hours` | `int` | `168` | Default time window (in hours) for dashboard cost aggregations (7 days). |
| `cache_ttl_seconds` | `int` | `60` | How long per-trace cost results are cached before re-fetching from Langfuse. |
| `reconcile_tolerance_usd` | `float` | `1.0` | Maximum allowed drift (USD) between OpenRouter and Langfuse costs before reconciliation is flagged. |
| `reconcile_schedule_hours` | `float` | `24.0` | Interval in hours between automatic reconciliation runs. Set to `0` to disable scheduled reconciliation. |
| `subscription_call_cap` | `int` | `0` | Per-day cap on subscription-triggered calls. Set to `0` to disable the cap. |
| `analyst` | `AnalystConfig` | `{}` | Nested configuration for the optional LLM cost-analyst (see below). |

---

## `settings.analyst` — LLM cost-analyst (`AnalystConfig`)

The analyst is an optional feature that uses an LLM to review high-cost traces and
suggest optimisations. It is **enabled** when `settings.analyst.openrouter_key` is set
to a non-null value.

| Key | Type | Default | Description |
|---|---|---|---|
| `openrouter_key` | `str` or `null` | `null` | OpenRouter API key for the analyst's own LLM calls. `null` disables the analyst entirely. |
| `global_model` | `str` or `null` | `null` | L3 orchestrator model. Blank or `null` uses the tier-3 default. |
| `trace_model` | `str` or `null` | `null` | L2 per-trace analysis model. Blank or `null` uses the tier-2 default. |
| `window_hours` | `int` | `24` | Look-back window (hours) for selecting traces to analyse. |
| `top_stages` | `int` | `8` | Number of top-cost stages to surface per agent. |
| `traces_per_agent` | `int` | `1` | Top-N traces per unique agent before the overall cap is applied. |
| `max_trace_analyses` | `int` | `12` | Hard cap on the number of traces the analyst examines in a single run. |
| `schedule_hours` | `float` | `24.0` | Interval between automatic analyst runs. `0` means manual-only. |
| `langfuse_public_key` | `str` or `null` | `null` | Public key for the analyst's own Langfuse tracing project. |
| `langfuse_secret_key` | `str` or `null` | `null` | Secret key for the analyst's own Langfuse tracing project. |
| `langfuse_base_url` | `str` or `null` | `null` | Base URL for the analyst's Langfuse instance. |
| `langfuse_project_id` | `str` or `null` | `null` | Project ID for the analyst's Langfuse tracing. |

---

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `COST_MONITOR_CONFIG` | `config/projects.json` | Path to the JSON configuration file (relative to repository root). |
| `COST_MONITOR_DATA` | `.data/` | Directory for persistent runtime state (reconciliation snapshots, analyst proposals). |
| `LOG_FORMAT` | `json` (when `CI` is set) else `console` | Structured log output format. `json` for production ingestion; `console` for coloured human-readable output during local development. |
