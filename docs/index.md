# robotsix-cost-monitor

A standalone cost-monitoring service for LLM agent fleets. It connects to several
Langfuse projects and shows their costs in one convenient dashboard, plus
OpenRouter ↔ Langfuse reconciliation and an optional LLM cost-analyst.

Extracted from `robotsix-mill` so cost tracking lives in one place and can watch
multiple projects at once.

## Quick start

```bash
uv sync
cp config/projects.example.yaml config/projects.yaml   # fill in real keys
uv run robotsix-cost-monitor serve --host 127.0.0.1 --port 8099
# open http://127.0.0.1:8099
```

Each project needs a Langfuse `public_key` / `secret_key` / `base_url`. Add an
`openrouter_key` per project to enable reconciliation. The real config file
(`config/projects.yaml`) is gitignored; `config/projects.example.yaml` is the
committed template. Override the path with `COST_MONITOR_CONFIG`.

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

## CLI

```bash
uv run robotsix-cost-monitor serve [--host H --port P]   # run the dashboard
uv run robotsix-cost-monitor summary [--project SLUG --hours N]
uv run robotsix-cost-monitor reconcile [--project SLUG]
```

## API

`GET /api/summary`, `/api/by-agent`, `/api/trend`, `/api/highlights`,
`/api/reconcile`, `/api/analyst/digest`, `/api/analyst/proposals`,
`POST /api/analyst/run` — all accept `?project=<slug>|all&hours=<N>`.

## Development

```bash
uv run ruff check . && uv run ruff format --check .
uv run mypy src/
uv run pytest
```
