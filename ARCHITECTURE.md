# Architecture

## Directory layout

```text
.
├── config/                     # Operational JSON config (gitignored, template committed)
│   └── config.example.json     #   Template with registry + global settings
├── deploy/                     # Production deployment stack (docker-compose + env)
├── docs/                       # MkDocs documentation source
├── src/robotsix_cost_monitor/  # Python package (the application)
│   ├── app.py                  #   FastAPI app factory + lifespan (background loops)
│   ├── routes.py               #   Route handlers, exception handlers, dependency providers
│   ├── cli.py                  #   CLI entrypoint (serve / summary / reconcile)
│   ├── config.py               #   Pydantic settings models + JSON config loader (robotsix-config)
│   ├── cache.py                #   Generic TTL cache with stale-while-revalidate (SWR) semantics
│   ├── metrics.py              #   Custom Prometheus counters/gauges for background loops
│   ├── service.py              #   Cross-project cost aggregation layer
│   ├── reconcile.py            #   OpenRouter ↔ Langfuse reconciliation engine
│   ├── aggregations.py         #   Pure cost-aggregation functions (no I/O)
│   ├── clients/
│   │   ├── langfuse.py         #   Self-contained async Langfuse REST client (httpx)
│   │   ├── registry.py         #   Central-deploy registry client for project discovery
│   │   └── models.py           #   Shared client models (RegistryProject, etc.)
│   └── web/                    #   Server-rendered dashboard UI
│       ├── index.html          #     Main dashboard page
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
┌──────────────────┐  REST (httpx)│  CostService   │──► 5 independent
│  Central-deploy   │◄─────────── │                │    per-window TTL
│  Registry         │             │                │    caches (traces,
│  (GET /fleet/     │             │                │    models, backends,
│   langfuse)       │             │                │    agent usage,
└──────────────────┘             └──────┬────────┘    trace counts)
                                        │
       ▲                         ┌──────▼────────┐
       │  snapshot diff          │  FastAPI app   │──► /api/* JSON endpoints
       │                         │  (app.py)      │──► HTML dashboard
       └─────────────────────────┤                │──► GET /metrics
           reconcile.py          └──────┬────────┘    (Prometheus)
                                        │
          ┌─────────────────────────────▼──────────────────┐
          │  Background loops (FastAPI lifespan)            │
          │  • reconcile_loop: snapshots OpenRouter per-key │
          │    cumulative usage on a configurable interval  │
          │  • cache_refresh_loop: keeps dashboard cost     │
          │    aggregates precomputed; a one-shot warm-up   │
          │    runs at startup                              │
          │  • registry_poll_loop: re-queries the central-  │
          │    deploy registry to discover new/removed       │
          │    projects at runtime                          │
          └────────────────────────────────────────────────┘
```

### How a request flows

1. **Ingress** — The browser (or a CLI `summary`/`reconcile` invocation) hits
   the FastAPI app.
2. **Cache check** — `CostService` looks up the in-memory TTL cache keyed by
   `(project_slug, window_hours)`. A fresh entry returns immediately; a stale
   entry is still served while a **background refresh** is triggered
   (stale-while-revalidate); a cold miss fetches fresh data from Langfuse.
   Five independent caches hold traces, model usage, backend costs, agent
   usage, and trace counts separately, so any (window, backend) combination
   is served without an extra Langfuse fetch.
3. **Langfuse fetch** — `LangfuseClient` calls the Langfuse public REST API
   (`/api/public/traces`, `/api/public/metrics/*`) via `httpx`. Each project
   gets its own client (keyed by `public_key`/`secret_key`/`base_url`).
4. **Aggregation** — Pure functions in `aggregations.py` transform the raw
   trace dicts into the shapes the dashboard needs (by-agent, by-model,
   trend, highlights).
5. **Response** — JSON for API endpoints; server-rendered HTML for the
   dashboard pages (`web/index.html`).

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
| `_cache_refresh_loop` | `settings.dashboard_refresh_interval_seconds` | 120 s | Periodically re-fetches dashboard aggregates so the cache stays warm; a one-shot `_warm_cache` also runs at startup, pre-fetching all dashboard window presets (1 h, 6 h, 1 d, 1 w) so window switches are cache hits from the first page load |
| `_registry_poll_loop` | `settings.registry_poll_interval_seconds` | 300 s | Re-queries the central-deploy registry (`GET /fleet/langfuse`) to discover new or removed Langfuse projects without restarting the service; started only when `registry_poll_interval_seconds > 0` |

- The cache-warm loop (**best-effort**) logs and discards failures — a cold
  cache is a performance problem, not a correctness one; the stale-while-
  revalidate SWR path still keeps the dashboard responsive.
- A failed run logs the exception and **does not kill the loop**.
- All loops are **asyncio tasks**; the app's lifespan cancels them on
  shutdown.

## Key invariants

- **`robotsix-llmio` is a regular base dependency.** The Langfuse client and
  OpenRouter client are both provided by `robotsix-llmio`.
- **Reconciliation is idempotent.** Running it twice back-to-back with no
  intervening spend must produce `provider_delta_usd ≈ 0` and
  `within_tolerance: true`.
- **Snapshots are saved before comparison.** A failed Langfuse query cannot
  lose an OpenRouter reading.
- **Five independent per-window caches.** `CostService` maintains separate
  TTL caches for traces, model usage, backend costs, agent usage, and trace
  counts — each keyed on `(project_slug, window_hours)` with a configurable TTL
  (`cache_ttl_seconds`, default 60 s) and **stale-while-revalidate**
  semantics: stale values are served immediately while a background refresh
  fetches new data. Every dashboard window preset (1 h, 6 h, 1 d, 1 w) is
  pre-warmed at startup and on the refresh cadence. `POST /api/refresh`
  invalidates all caches on demand.
- **Project discovery is registry-driven.** Project credentials are fetched at
  runtime from the central-deploy registry (`GET /fleet/langfuse`) rather than
  hardcoded in the config file. The `_registry_poll_loop` re-discovers projects
  periodically so the service can pick up new or removed Langfuse projects
  without a restart.
- **Configuration flows through Pydantic.** `Config` →
  `Config.model_validate()` is the only path. Never bypass the models.
- **Runtime state lives under the configured data directory**
  (`settings.data_dir`, default `.data`). One subsystem writes here:
  reconciliation (`<data_dir>/reconcile/`).
- **The dashboard has no built-in auth.** In production, a host nginx
  terminates TLS + basic auth and proxies to `127.0.0.1:8080` inside the
  container.
