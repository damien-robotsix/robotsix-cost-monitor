# robotsix-cost-monitor — Agent Guide

This repo follows the [robotsix stack standards](https://github.com/damien-robotsix/robotsix-standards).

## Testing conventions

- Tests live under `tests/` and run with `pytest`.
- **Rule:** Every new source or test file MUST be registered under an
  appropriate module in `docs/modules.yaml` (CI's module-taxonomy
  validation runs `uv run robotsix-modules-validate docs/modules.yaml`
  in the `ci` workflow and fails otherwise). Add any new test to the
  module owning its path, e.g. a new test under `tests/` typically
  belongs to `project-root` unless a more specific source module
  covers it.
- **No network / no live LLM in tests.** The suite is fully offline:
  - `robotsix_llmio.core.AsyncLangfuseReadClient` is mocked via
    `unittest.mock.patch.object` on the composed `LangfuseClient._lf` instance
    (see `tests/robotsix_cost_monitor/clients/test_langfuse.py`).
  - `tests/robotsix_cost_monitor/helpers.py` provides a `_mock_client()` factory that returns a
    `Mock` with `AsyncMock` fetch methods returning empty results — prefer this
    when adding new tests that need a LangfuseClient seam.
- Use `pytest-asyncio` for async tests.

## Configuration invariants

### Environment variables

| Variable | Purpose | Default |
| --- | --- | --- |
| `ROBOTSIX_CONFIG_FILE` | Path to the JSON config file (relative to repo root) | `config/config.json` |

Data directory is configured via `settings.data_dir` in the config file
(default `.data`). Log format and level are also config fields
(`settings.log_format`, `settings.log_level`).

### JSON config shape

The real config lives at `config/config.json` (gitignored). The committed
template is `config/config.example.json`. Top-level keys:

- **`projects`** — list of Langfuse projects to monitor. Each entry: `name`,
  `public_key`, `secret_key`, `base_url`, optional `openrouter_key`.
- **`settings`** — global knobs: `default_window_hours`, `cache_ttl_seconds`,
  `reconcile_tolerance_usd`, `reconcile_schedule_hours`.

New fields added to the config MUST flow through the Pydantic models in
`src/robotsix_cost_monitor/config.py` and be reflected in the example file.

### Model hierarchy (`src/robotsix_cost_monitor/config.py`)

```text
Config                       # top-level: settings
└── settings: Settings
      auth (AuthConfig), server_host, server_port, registry_base_url,
      registry_api_key, registry_poll_interval_seconds,
      default_window_hours, cache_ttl_seconds,
      dashboard_refresh_interval_seconds, reconcile_tolerance_usd,
      reconcile_schedule_hours,
      low_balance_threshold_usd, data_dir, log_format, log_level
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

### Config loading

```python
from robotsix_config import load_config

config = load_config(Config, path=path)
```

Called in `config.py:load_config()`. Never add a second config loader.

### Langfuse

```python
from robotsix_llmio.core import AsyncLangfuseReadClient

client = AsyncLangfuseReadClient(public_key=..., secret_key=..., base_url=...)
```

Used by `src/robotsix_cost_monitor/clients/langfuse.py` (`LangfuseClient._lf`).
All Langfuse HTTP transport is delegated to this shared client. Never
instantiate a second Langfuse client or call the Langfuse REST API directly.

## OpenRouter client (`robotsix-llmio`)

`OpenRouterKeyCostSource` is a sync OpenRouter client imported from `robotsix_llmio.openrouter`.
It wraps the per-key usage endpoint:

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

Persistent runtime state lives under the directory set by `settings.data_dir`
in the config file (default `.data`). One subsystem writes here:

| Subsystem | Path | Content |
| --- | --- | --- |
| Reconciliation | `.data/reconcile/<slug>.json` | Per-project cumulative-usage snapshots + `last.json` aggregate result |

The `data_dir_audit` periodic workflow inspects this directory. Agents MUST
NOT repurpose `.data/` for unrelated state — use it only for reconciliation
snapshots. Follow the fleet convention (shared with
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
