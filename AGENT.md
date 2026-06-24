# robotsix-cost-monitor — Agent Guide

## Testing conventions

- Tests live under `tests/` and run with `pytest`.
- **No network / no live LLM in tests.** The suite is fully offline:
  - `robotsix_llmio.core.AsyncLangfuseReadClient` is mocked via
    `unittest.mock.patch.object` on the composed `LangfuseClient._lf` instance
    (see `tests/clients/test_langfuse.py`).
  - The LLM analyst path is stubbed by monkeypatching the local `_run_agents`
    wrapper rather than `robotsix_llmio.core.run_agent` directly (see
    `tests/test_analyst.py`).
  - `tests/conftest.py` provides a `_mock_client()` factory that returns a
    `Mock` with `AsyncMock` fetch methods returning empty results — prefer this
    when adding new tests that need a LangfuseClient seam.
- Use `pytest-asyncio` for async tests. The `conftest.py` provides a
  session-scoped `event_loop` fixture for compatibility with `pytest-xdist`.

## Configuration invariants

### Environment variables

| Variable | Purpose | Default |
|---|---|---|
| `COST_MONITOR_CONFIG` | Path to the YAML project config (relative to repo root) | `config/projects.yaml` |
| `COST_MONITOR_DATA` | Writable runtime-state directory (reconciliation snapshots, analyst proposals) | `.data` |

Both are documented in `.env.example`. Never rename or remove these env vars
without updating every call-site (`_config_path()`, `data_dir()` in
`src/robotsix_cost_monitor/config.py`) and `.env.example`.

### YAML config shape

The real config lives at `config/projects.yaml` (gitignored). The committed
template is `config/projects.example.yaml`. Top-level keys:

- **`projects`** — list of Langfuse projects to monitor. Each entry: `name`,
  `public_key`, `secret_key`, `base_url`, optional `openrouter_key`.
- **`settings`** — global knobs: `default_window_hours`, `cache_ttl_seconds`,
  `reconcile_tolerance_usd`, `reconcile_schedule_hours`, plus an optional
  **`analyst`** block (LLM cost-analyst).

New fields added to the config MUST flow through the Pydantic models in
`src/robotsix_cost_monitor/config.py` and be reflected in the example file.

### Model hierarchy (`src/robotsix_cost_monitor/config.py`)

```
Config                       # top-level: projects + settings
├── projects: list[ProjectConfig]
│     name, public_key, secret_key, base_url, openrouter_key?
│     └── .slug  (derived URL-safe identifier)
└── settings: Settings
      default_window_hours, cache_ttl_seconds, reconcile_tolerance_usd,
      reconcile_schedule_hours
      └── analyst: AnalystConfig
            openrouter_key?, global_model?, trace_model?, window_hours,
            top_stages, traces_per_agent, max_trace_analyses, schedule_hours,
            broker_host?, broker_port, broker_scheme, broker_token?,
            board_manager_id, board_agent_id, board_repo_id,
            langfuse_* (own tracing project)
            ├── .enabled       (bool — openrouter_key is set)
            └── .can_file_tickets  (bool — broker configured)
```

All config loading goes through `load_config()` → `Config.model_validate()`.
Never bypass the Pydantic validation.

## Delegation points (do NOT re-implement)

### Logging

```python
from robotsix_llmio.logging import setup_logging
setup_logging(loggers=["robotsix_cost_monitor"], fmt="json")
```

Called once in `src/robotsix_cost_monitor/app.py`. Agents MUST NOT add a
second logging framework or replace this call.

### YAML loading

```python
from robotsix_yaml_config import read_yaml_file
raw = read_yaml_file(path)
```

Called in `config.py:load_config()`. Never add a second YAML parser.

### Langfuse

```python
from robotsix_llmio.core import AsyncLangfuseReadClient
client = AsyncLangfuseReadClient(public_key=..., secret_key=..., base_url=...)
```

Used by `src/robotsix_cost_monitor/clients/langfuse.py` (`LangfuseClient._lf`).
All Langfuse HTTP transport is delegated to this shared client. Never
instantiate a second Langfuse client or call the Langfuse REST API directly.

## OpenRouter client (`robotsix-llmio`)

`OpenRouterKeyCostSource` is a sync OpenRouter client imported from `robotsix_llmio.openrouter`
(part of the optional `[analyst]` extra). It wraps the per-key usage endpoint:

- `fetch_key_usage()` → `KeyUsage` — per-key cumulative usage (the reconciliation basis),
  returned as a `KeyUsage(usage, limit, label)` dataclass. Called via `asyncio.to_thread`
  to avoid blocking the event loop.
- Account credits are fetched separately via a direct `httpx` async call to
  `GET /api/v1/credits` (`_fetch_credits` helper), populating `result["balance"]`
  with `total_credits`, `total_usage`, and `remaining`.

The local `robotsix_cost_monitor.clients.openrouter.OpenRouterClient` has been deleted
in favour of this shared client. New OpenRouter endpoints or features should go into
`robotsix-llmio`.

## Data directory convention

Persistent runtime state lives under `.data/` (overridable via
`COST_MONITOR_DATA`). Two subsystems write here:

| Subsystem | Path | Content |
|---|---|---|
| Reconciliation | `.data/reconcile/<slug>.json` | Per-project cumulative-usage snapshots + `last.json` aggregate result |
| Analyst | `.data/analyst/proposals.json` | Stored cost-reduction proposals (surfaced in the dashboard) |

The `data_dir_audit` periodic workflow inspects this directory. Agents MUST
NOT repurpose `.data/` for unrelated state — use it only for reconciliation
snapshots and analyst output. Follow the fleet convention (shared with
`robotsix-chat`, `robotsix-auto-mail`).

## Reconciliation flow (`src/robotsix_cost_monitor/reconcile.py`)

Reconciliation snapshots OpenRouter **per-key cumulative usage** on each run,
diffs it against the prior snapshot to get the provider delta for the interval,
then compares that to the Langfuse traced cost (filtered to the `openrouter`
backend only) over the same interval.

### Snapshot file format (per project)

```json
{"cumulative": 12.5, "at": "2026-01-15T12:00:00+00:00"}
```

- `cumulative` — the OpenRouter key's cumulative usage (float USD)
- `at` — ISO-8601 datetime of the fetch

### Idempotency invariant

Reconciliation MUST be idempotent: running it twice back-to-back with no
intervening spend should produce `provider_delta_usd` ≈ 0 and
`within_tolerance: true`. The snapshot is saved **before** the comparison
so that a failed Langfuse query does not lose the OpenRouter reading.
