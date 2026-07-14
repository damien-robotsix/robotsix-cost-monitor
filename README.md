# robotsix-cost-monitor

A standalone cost-monitoring service for LLM agent fleets. Connects to **several
Langfuse projects** and shows their costs in one convenient dashboard, plus
**OpenRouter ↔ Langfuse reconciliation** and an optional **LLM cost-analyst**.

Extracted from `robotsix-mill` so cost tracking lives in one place and can watch
multiple projects at once.

## Features

- **Multi-project dashboard** — per-project and aggregated cost over a window;
  cost-over-time trend; cost by agent/stage; most-expensive trace & ticket.
- **Reconciliation** — diffs each project's OpenRouter cumulative spend
  (snapshot-based) against Langfuse traced cost; flags drift beyond a tolerance;
  shows the remaining OpenRouter balance.
- **Cost-analyst (optional)** — a deterministic cost digest, plus an
  OpenAI-compatible LLM pass that proposes high-confidence cost reductions
  (surfaced in the dashboard, not written to any external board).

No `robotsix-llmio` dependency — the Langfuse and OpenRouter clients are
self-contained (`httpx`).

## Setup

```bash
uv sync --locked
cp config/projects.example.json config/projects.json   # then fill in real keys
uv run robotsix-cost-monitor serve --host 127.0.0.1 --port 8099
# open http://127.0.0.1:8099
```

Each project needs a Langfuse `public_key` / `secret_key` / `base_url`. Add an
`openrouter_key` per project to enable reconciliation. The real config file
(`config/projects.json`) is gitignored; `config/projects.example.json` is the
committed template. Override the path with `COST_MONITOR_CONFIG`.

## CLI

```bash
uv run robotsix-cost-monitor serve [--host H --port P]   # run the dashboard
uv run robotsix-cost-monitor summary [--project SLUG --hours N]
uv run robotsix-cost-monitor reconcile [--project SLUG]
```

## API

| Method | Path | Query Parameters | Response |
|--------|------|------------------|----------|
| GET | `/health` | — | `{"status":"ok","projects":["…"]}` |
| GET | `/` | — | Dashboard HTML page |
| GET | `/analyst` | — | Analyst dashboard HTML page |
| GET | `/api/projects` | — | List of configured projects (`name`, `slug`) |
| GET | `/api/summary` | `?project=<slug\|all>&hours=<N>` | Total cost and per-project totals |
| GET | `/api/by-agent` | `?project=<slug\|all>&hours=<N>&backend=<all\|backend>` | Cost breakdown by agent name |
| GET | `/api/by-agent-segmented` | `?project=<slug\|all>&hours=<N>` | Agent costs segmented by model and backend |
| GET | `/api/by-model` | `?project=<slug\|all>&hours=<N>` | Cost breakdown by model |
| GET | `/api/backend-trend` | `?project=<slug\|all>&hours=<N>&backend=<all\|backend>` | Cost trend per backend |
| GET | `/api/trend` | `?project=<slug\|all>&hours=<N>&buckets=<1-200>` | Bucketed cost-over-time trend series |
| GET | `/api/highlights` | `?project=<slug\|all>&hours=<N>` | Cost summaries (total, change, top agents) |
| GET | `/api/reconcile` | `?project=<slug\|all>` | OpenRouter↔Langfuse reconciliation result |
| GET | `/api/reconcile/last` | — | Most recent full reconciliation snapshot |
| GET | `/api/analyst/digest` | `?hours=<N>` | Cost-analysis digest from recent trace data |
| GET | `/api/analyst/proposals` | — | Saved cost-reduction proposals |
| POST | `/api/analyst/run` | — | Trigger a full cost-analyst analysis run |
| GET | `/api/analyst/ticket` | — | Saved ticket-level targeted analysis |
| POST | `/api/analyst/run/ticket` | — | Trigger a ticket-level targeted analysis run |
| GET | `/api/analyst/stage` | — | Saved stage-level targeted analysis |
| POST | `/api/analyst/run/stage` | — | Trigger a stage-level targeted analysis run |
| POST | `/api/analyst/run/{kind}` | — | Run a targeted analyst analysis (ticket or stage) |

## Architecture

See [ARCHITECTURE.md](ARCHITECTURE.md) for the directory layout, data flow,
background loop lifecycle, optional `analyst` extra, and key invariants.

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
