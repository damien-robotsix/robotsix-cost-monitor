# robotsix-cost-monitor

A standalone cost-monitoring service for LLM agent fleets. Connects to **several
Langfuse projects** and shows their costs in one convenient dashboard, plus
**OpenRouter ↔ Langfuse reconciliation**.

Extracted from `robotsix-mill` so cost tracking lives in one place and can watch
multiple projects at once.

## Features

- **Multi-project dashboard** — per-project and aggregated cost over a window;
  cost-over-time trend; cost by agent/stage; most-expensive trace & session.
- **Reconciliation** — diffs each project's OpenRouter cumulative spend
  (snapshot-based) against Langfuse traced cost; flags drift beyond a tolerance;
  shows the remaining OpenRouter balance.
Built on `robotsix-llmio` for Langfuse (`AsyncLangfuseReadClient`) and OpenRouter
(`OpenRouterKeyCostSource`) — no second client instantiation or direct REST API calls.

## Setup

```bash
uv sync --locked
cp config/config.example.json config/config.json   # then fill in real keys
uv run robotsix-cost-monitor serve --host 127.0.0.1 --port 8099
# open http://127.0.0.1:8099
```

When deployed by robotsix-central-deploy, the deploy API key used to reach the
registry is injected automatically as `DEPLOY_API_KEY` (the deploy manifest
declares the `agent` deploy-access setting) — no manual `registry_api_key`
provisioning is needed. Set `registry_base_url` in the config to the
central-deploy registry URL; leave `registry_api_key` empty.

Each project needs a Langfuse `public_key` / `secret_key` / `base_url`. Add an
`openrouter_key` per project to enable reconciliation. The real config file
(`config/config.json`) is gitignored; `config/config.example.json` is the
committed template. Override the path with `ROBOTSIX_CONFIG_FILE`.

## CLI

```bash
uv run robotsix-cost-monitor serve [--host H --port P]     # run the dashboard
uv run robotsix-cost-monitor summary [--project SLUG --hours N]
uv run robotsix-cost-monitor reconcile [--project SLUG]
```

## API

| Method | Path | Query Parameters | Response |
| -------- | ------ | ------------------ | ---------- |
| GET | `/health` | — | `{"status":"ok","projects":["…"]}` |
| GET | `/metrics` | — | Prometheus scrape endpoint (counters/gauges for reconcile runs, cache warm-ups, etc.) |
| GET | `/chat-skill` | — | Markdown skill document for the robotsix-chat agent (base URL, read endpoints, auth, safety) |
| GET | `/` | — | Dashboard HTML page |
| GET | `/api/projects` | — | List of configured projects (`name`, `slug`) |
| GET | `/api/summary` | `?project=<slug\|all>&hours=<N>&backend=<all\|backend>` | Total cost, per-project totals, and per-component rollup (includes ISO-8601 `last_updated` when cached data is available). Optional `backend` filter (e.g. `openrouter`) restricts costs to that backend. |
| POST | `/api/refresh` | — | Invalidate all caches and force a fresh Langfuse fetch on the next dashboard request |
| GET | `/api/by-agent` | `?project=<slug\|all>&hours=<N>&backend=<all\|backend>` | Cost breakdown by agent name |
| GET | `/api/by-agent-segmented` | `?project=<slug\|all>&hours=<N>` | Agent costs segmented by model and backend |
| GET | `/api/by-model` | `?project=<slug\|all>&hours=<N>` | Cost breakdown by model |
| GET | `/api/backend-trend` | `?project=<slug\|all>&hours=<N>&backend=<all\|backend>` | Cost trend per backend |
| GET | `/api/trend` | `?project=<slug\|all>&hours=<N>&buckets=<1-200>` | Bucketed cost-over-time trend series |
| GET | `/api/highlights` | `?project=<slug\|all>&hours=<N>&backend=<all\|backend>` | Most expensive trace and session for the window |
| GET | `/api/reconcile` | `?project=<slug\|all>` | OpenRouter↔Langfuse reconciliation result |
| GET | `/api/reconcile/last` | — | Most recent reconciliation result (powers the dashboard warning banner) |
| POST | `/api/reconcile/run` | `?project=<slug>` | Run reconciliation for a specific project (returns JSON result) |
| GET | `/api/stuck-tickets` | — | Tickets stuck in non-terminal states longer than the configured threshold (503 when mill API unreachable) |

## Architecture

See [ARCHITECTURE.md](ARCHITECTURE.md) for the directory layout, data flow,
background loop lifecycle, and key invariants.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for dev setup, running tests/lint,
PR workflow, and the git-dependency upgrade process.

## Standards

This repo follows the [robotsix stack standards](https://github.com/damien-robotsix/robotsix-standards).

## Development

```bash
uv run ruff check . && uv run ruff format --check .
uv run mypy src/
uv run pytest
```
