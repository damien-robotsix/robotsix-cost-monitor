# Architecture

## Directory layout

```text
.
├── config/                     # Operational JSON config (gitignored, template committed)
│   └── config.example.json     #   Template listing Langfuse projects + OpenRouter keys
├── deploy/                     # Production deployment stack (docker-compose + env)
├── docs/                       # MkDocs documentation source
├── src/robotsix_cost_monitor/  # Python package (the application)
│   ├── app.py                  #   FastAPI app factory + lifespan (background loops)
│   ├── routes.py               #   Route handlers, exception handlers, dependency providers
│   ├── cli.py                  #   CLI entrypoint (serve / summary / reconcile)
│   ├── config.py               #   Pydantic settings models + JSON config loader (robotsix-config)
│   ├── service.py              #   Cross-project cost aggregation layer + SWR TTL cache
│   ├── reconcile.py            #   OpenRouter ↔ Langfuse reconciliation engine
│   ├── analyst.py              #   Optional LLM cost-analyst (robotsix-llmio)
│   ├── aggregations.py         #   Pure cost-aggregation functions (no I/O)
│   ├── clients/
│   │   └── langfuse.py         #   Self-contained async Langfuse REST client (httpx)
│   └── web/                    #   Server-rendered dashboard UI
│       ├── index.html          #     Main dashboard page
│       ├── analyst.html        #     Analyst results page
│       └── static/             #     JS + CSS assets
├── tests/                      # Test suite (pytest + vitest for JS)
├── Dockerfile                  # Multi-stage container build
├── docker-compose.yml          # Local dev Compose (builds + runs the service)
├── pyproject.toml              # Python project metadata, deps, tool config
└── uv.lock                     # Reproducible dependency lockfile
```

## Data flow

```text
┌──────────────┐   REST (httpx)    ┌──────────────┐
│  Langfuse     │ ◄─────────────── │  Langfuse     │
│  (per project)│                  │  Client       │
└──────────────┘                  └──────┬────────┘
                                         │ trace dicts
                                  ┌──────▼────────┐
┌──────────────┐   REST (httpx)   │  CostService   │──► TTL cache (in-memory)
│  OpenRouter   │ ◄────────────── │                │──► aggregations.py
│  (per key)    │                 └──────┬────────┘    (pure functions)
└──────────────┘                        │
       ▲                         ┌──────▼────────┐
       │  snapshot diff          │  FastAPI app   │──► /api/* JSON endpoints
       │                         │  (app.py)      │──► HTML dashboard
       └─────────────────────────┤                │
           reconcile.py          └──────┬────────┘
                                        │
          ┌─────────────────────────────▼──────────────────┐
          │  Background loops (FastAPI lifespan)            │
          │  • reconcile_loop: snapshots OpenRouter per-key │
          │    cumulative usage on a configurable interval  │
          │  • analyst_loop: runs all 3 analyses (fleet /   │
          │    ticket / stage) on a configurable interval   │
          │  • cache_refresh_loop: keeps dashboard cost     │
          │    aggregates precomputed; a one-shot warm-up   │
          │    runs at startup                              │
          └────────────────────────────────────────────────┘
```

### How a request flows

1. **Ingress** — The browser (or a CLI `summary`/`reconcile` invocation) hits
   the FastAPI app.
2. **Cache check** — `CostService` looks up the in-memory TTL cache keyed by
   `(project_slug, window_hours)`. A fresh entry returns immediately; a stale
   entry is still served while a **background refresh** is triggered
   (stale-while-revalidate); a cold miss fetches fresh data from Langfuse.
   Each cache entry stores all five data kinds (traces, model usage, backend
   costs, agent usage, trace counts) as a single `WindowData` snapshot, so any
   (window, backend) combination is served without an extra Langfuse fetch.
3. **Langfuse fetch** — `LangfuseClient` calls the Langfuse public REST API
   (`/api/public/traces`, `/api/public/metrics/*`) via `httpx`. Each project
   gets its own client (keyed by `public_key`/`secret_key`/`base_url`).
4. **Aggregation** — Pure functions in `aggregations.py` transform the raw
   trace dicts into the shapes the dashboard needs (by-agent, by-model,
   trend, highlights).
5. **Response** — JSON for API endpoints; server-rendered HTML for the
   dashboard pages (`web/index.html`, `web/analyst.html`).

### Reconciliation data flow

Reconciliation works by **snapshotting** OpenRouter's cumulative per-key
usage (OpenRouter has no per-window cost endpoint):

1. `reconcile_project()` fetches the key's current cumulative usage via
   `OpenRouterKeyCostSource.fetch_key_usage()` (called via `asyncio.to_thread`)
   and the account-level credit balance via a direct `httpx` call to
   `GET /api/v1/credits` (`_fetch_credits` helper).
2. It diffs against the **prior snapshot** (stored under
   `<data_dir>/reconcile/<slug>.json`) to get `provider_delta_usd` — the
   OpenRouter spend in the interval.
3. It queries Langfuse for the **openrouter-backend** traced cost over the
   **same interval** (since the prior snapshot).
4. If the drift exceeds `reconcile_tolerance_usd`, the dashboard banner
   warns.

Snapshots are saved **before** the comparison, so a failed Langfuse query
does not lose the OpenRouter reading (idempotency invariant).

## Background loop lifecycle

Both background loops are started in the FastAPI **lifespan** (async context
manager in `create_app()`) and cancelled on shutdown:

| Loop | Config key | Default | What it does |
| --- | --- | --- | --- |
| `_reconcile_loop` | `settings.reconcile_schedule_hours` | 24 h | Runs `reconcile_all()` for every project; stores result in `.data/reconcile/last.json` (powers the warning banner) |
| `_analyst_loop` | `settings.analyst.schedule_hours` | 24 h | Runs all three analyses (fleet, most-costly ticket, most-costly stage); persists results under `.data/analyst/` |
| `_cache_refresh_loop` | `settings.dashboard_refresh_interval_seconds` | 120 s | Periodically re-fetches dashboard aggregates so the cache stays warm; a one-shot `_warm_cache` also runs at startup, pre-fetching all dashboard window presets (1 h, 6 h, 1 d, 1 w) so window switches are cache hits from the first page load |

- The analyst loop computes its **first delay** from the last persisted run
  timestamp (`_last_analyst_run()`), so frequent redeploys (Watchtower) don't
  starve the schedule — if a full interval has elapsed it runs immediately.
- The cache-warm loop (**best-effort**) logs and discards failures — a cold
  cache is a performance problem, not a correctness one; the stale-while-
  revalidate SWR path still keeps the dashboard responsive.
- A failed run logs the exception and **does not kill the loop**.
- All loops are **asyncio tasks**; the app's lifespan cancels them on
  shutdown.

## Optional `analyst` extra

The LLM cost-analyst is optional — the dashboard, reconciliation, and all
CLI commands work without it. It requires two packages installed via the
`[analyst]` extra:

| Package | Role |
| --- | --- |
| `robotsix-llmio` | Level-2 (DeepSeek via OpenRouter) and Level-3 (Claude Opus) LLM agents that analyse cost patterns |

- All imports of these packages are **lazy** (inside function bodies in
  `analyst.py`), guarded by `analyst.enabled` checks in `app.py`.
- The analyst runs **three analyses** per cycle: a **fleet-wide** analysis,
  a **most-costly ticket** analysis, and a **most-costly stage** analysis.
- Each analysis produces proposals which are stored under `.data/analyst/` for
  surfacing in the dashboard.

## Key invariants

- **No `robotsix-llmio` dependency in the base install.** The Langfuse client is
  self-contained (`httpx` only). The OpenRouter client is imported from `robotsix-llmio`
  (analyst extra). The analyst extra is installed separately.
- **Reconciliation is idempotent.** Running it twice back-to-back with no
  intervening spend must produce `provider_delta_usd ≈ 0` and
  `within_tolerance: true`.
- **Snapshots are saved before comparison.** A failed Langfuse query cannot
  lose an OpenRouter reading.
- **The TTL cache is process-local.** Restarting the app clears it. The
  cache keys on `(project_slug, window_hours)` with a configurable TTL
  (`cache_ttl_seconds`, default 60 s) and **stale-while-revalidate**
  semantics: stale values are served immediately while a background refresh
  fetches new data. Each entry is a unified `WindowData` snapshot holding all
  five data kinds, and every dashboard window preset (1 h, 6 h, 1 d, 1 w) is
  pre-warmed at startup and on the refresh cadence. `POST /api/refresh`
  invalidates all caches on demand.
- **Configuration flows through Pydantic.** `Config` →
  `Config.model_validate()` is the only path. Never bypass the models.
- **Runtime state lives under the configured data directory**
  (`settings.data_dir`, default `.data`). Two subsystems write here:
  reconciliation (`<data_dir>/reconcile/`) and analyst (`<data_dir>/analyst/`).
- **The dashboard has no built-in auth.** In production, a host nginx
  terminates TLS + basic auth and proxies to `127.0.0.1:8080` inside the
  container.
