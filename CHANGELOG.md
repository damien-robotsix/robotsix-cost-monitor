## 0.0.0 (unreleased)

- **Added `zizmor` GitHub Actions security audit to CI.** A new
  `workflow-audit` job in `.github/workflows/ci.yml` runs `uvx zizmor
  --min-severity medium .github/workflows/` on every PR to detect
  unpinned action refs, template injection, excessive permissions, and
  other GitHub Actions security issues.

- **Extracted shared cache-access helper in `CostService`.** Five private
  methods (`_traces`, `_trace_count`, `_model_usage`, `_backend_cost`,
  `_agent_usage`) now delegate to a single `_cached_fetch` helper that
  encapsulates the key-lookup, monotonic-deadline check, TTL-based caching
  pattern. This removes ~22 lines of duplicate boilerplate and makes future
  cache-behaviour changes (e.g. stale-while-revalidate) local to one method.
- **Fixed example config `max_trace_analyses` drift.** The committed
  `config/projects.example.yaml` now sets `max_trace_analyses: 12`, matching the
  Pydantic default in `AnalystConfig`. A regression test loads the example YAML
  and asserts the value equals the code default to prevent future drift.

- **Dashboard renders segmented per-stage cost by backend.** The
  "cost by agent / stage" panel now fetches `/api/by-agent-segmented` and
  shows each stage's OpenRouter marginal cost as the primary figure with a
  separate, visually de-emphasized column for the subscription-estimated
  (Claude-SDK fixed) cost. A legend in the panel header explains the two
  pools to prevent conflation of fixed-subscription estimates with marginal
  cash. Added `renderByAgentSegmented` export with vitest/jsdom test coverage.

- **Added segmented per-stage cost aggregation by backend.** The new
  `GET /api/by-agent-segmented` endpoint splits each stage's cost into
  OpenRouter marginal (pay-per-token) and Claude-SDK subscription-estimated
  (fixed) pools, ranked by marginal cash. This prevents the `refine` stage's
  heavy subscription usage (~$51) from dominating the cost rankings and
  inviting a mis-optimization. The existing `/api/by-agent` endpoint is
  unchanged.

- **Adopted `structlog` as the first-party structured logging layer**, replacing
  the optional `robotsix_llmio.logging.setup_logging` fallback. All loggers now
  use `structlog.get_logger(__name__)` with `stdlib.LoggerFactory` bridging so
  stdlib handlers (OTel/Sentry) continue to work. Added `asgi-correlation-id`
  middleware (`CorrelationIdMiddleware`) for `X-Request-ID` propagation across
  every log entry. The `LOG_FORMAT` environment variable controls output format
  (`json` for production, `console` for dev).

- **Extracted route and exception handlers into `routes.py`.** All HTTP route
  handlers and exception handlers previously inline in `create_app()` now live in
  `src/robotsix_cost_monitor/routes.py` behind a module-level `router = APIRouter()`.
  Route handlers use FastAPI dependency injection (`Depends(get_config)`,
  `Depends(get_service)`) instead of closures over `create_app` locals. The
  `create_app` factory is reduced to ~70 lines and assembles the app via
  `register_exception_handlers(app)` + `app.include_router(router)`.

- **Added `dependency-hygiene` job to CI.** A new `dependency-hygiene` CI job
  runs `deptry .` against the full dependency tree (`--all-extras`), failing on
  unused, missing, or misclassified dependencies.

- **Extracted `_require_project` helper in `app.py`.** Seven route handlers
  that validated a project slug against the config now delegate to a shared
  `_require_project(project, cfg)` function, eliminating ~21 lines of
  duplicated control-flow logic.
- **Added `ARCHITECTURE.md` and `CONTRIBUTING.md`.** The architecture doc
  covers directory layout, data flow, background loop lifecycle, the optional
  `analyst` extra, and key invariants. The contributing doc covers dev setup,
  test/lint/type-check commands, PR workflow, and the git-dependency upgrade
  process. Both are linked from `README.md`.

- **Vendored `LangfuseClient` REST helper.** The `LangfuseClient` now uses a
  small, self-contained `_LangfuseRESTClient` instead of importing from the
  optional `robotsix-llmio` package. This means `robotsix-cost-monitor serve`
  and `summary` work without installing the `analyst` extra, restoring the
  README promise that the Langfuse and OpenRouter clients are self-contained
  (`httpx`-only).
