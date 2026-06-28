## 0.0.0 (unreleased)

- **Added developer-convenience Makefile targets (`lint`, `typecheck`, `format`, `serve`, `docs`, `clean`).**
  The `Makefile` now provides canonical entry points for common development
  workflows: pre-commit linting (`make lint`), mypy type-checking
  (`make typecheck`), ruff formatting (`make format`), dev server
  (`make serve`), docs preview (`make docs`), and cache cleanup
  (`make clean`). CI is unaffected — these are purely developer-local aliases.

- **Added typed Pydantic v2 response models for Langfuse API shapes.**
  New `src/robotsix_cost_monitor/clients/models.py` with `LangfuseMetricsRow`
  and `LangfuseTrace` `BaseModel` classes. `LangfuseClient` now parses API
  responses through `model_validate()` at the boundary instead of passing
  raw `dict[str, Any]`. `aggregations.py` trace functions accept
  `LangfuseTrace` instead of `dict[str, Any]`. `service.py` uses attribute
  access on traces throughout. All affected tests updated.

- **Replaced vendored `_LangfuseRESTClient` with `AsyncLangfuseReadClient` from robotsix-llmio.**
  `robotsix-llmio` is now a hard (non-optional) core dependency. The vendored
  ~70-line `_LangfuseRESTClient` class in `clients/langfuse.py` has been deleted;
  `LangfuseClient` now composes `AsyncLangfuseReadClient` directly.

- **Added `.nvmrc` and `.node-version` to pin Node.js to version 20.**
  These files ensure `nvm`, `fnm`, `nodenv`, and similar tools automatically
  select the same Node version used in CI (`js-tests` job),
  eliminating local-vs-CI reproducibility gaps.

- **Fixed `_parse_analysis` docstring: s/level-2/agent/.**  The docstring
  incorrectly claimed the function parsed output from a level-2 agent, but it
  is called exclusively from `_opus_analysis`, which uses a level-3 orchestrator.

- **Consolidated `_load_json` in `analyst.py` with `_safe_load_json` from `reconcile.py`.**
  Deleted the local `_load_json` helper and replaced its two call sites
  (`load_proposals`, `load_targeted_analysis`) with the generic `_safe_load_json`,
  removing a duplicate JSON-loading pattern.

- **Added `robotsix_cost_monitor.aggregations` and `robotsix_cost_monitor.clients` to API reference.** The `docs/api.md` mkdocstrings listing now includes both modules so their docstrings appear in generated documentation.

- **Extracted shared `_build_analysis_response` factory in `analyst.py`.**  The
  duplicate `out` dict literal (6 fields) in `run_analyst` and
  `_run_opus_analysis_and_file` is replaced by a single helper function,
  eliminating the clone pair and keeping the response shape consistent.
- **Extracted shared `_safe_load_json` helper in `reconcile.py`.**
  Replaced two duplicate JSON-loading patterns (`_load_snapshot` and
  `load_last_reconcile`) with a single `_safe_load_json(path, default)`
  generic function.

- **Removed legacy nested-dict reply branch from `managerReply()` in analyst.js.**
  The `typeof rr.reply === 'object'` branch (handling `rr.reply.reply`) was dead
  code — no production backend path produces a nested-dict reply.  The string
  branch and error branch handle all current production cases.

- **Swapped incorrect `global_model` / `trace_model` comments in example config.**
  The inline YAML comments on `global_model` and `trace_model` were reversed
  relative to what the fields actually control.  `global_model` is the level-3
  orchestrator model; `trace_model` is the level-2 trace model.  The comments in
  `config/projects.example.yaml` now match the authoritative docstrings in
  `src/robotsix_cost_monitor/config.py`.

- **Fixed strict TypeScript type errors in static JS files.**  Added null checks,
  catch-block type assertions, and element-type casts to `shared.js`,
  `analyst.js`, and `dashboard.js` so that `tsc --noEmit` with `strict: true`
  passes cleanly.

- **Made `robotsix-llmio` import in `reconcile.py` lazy with graceful fallback.**
  The `OpenRouterKeyCostSource` import is now inside `reconcile_project()` and
  wrapped in `try/except ImportError`, so the dashboard and CLI remain usable
  when the optional `analyst` extra is not installed.

- **Added `.npmrc` with `save-exact`, `min-release-age`, and `engine-strict`.** Pinned
  all npm devDependencies (`@biomejs/biome`, `jsdom`, `vitest`) to exact versions in
  `package.json`, removing `^` ranges to ensure deterministic installs. The `.npmrc`
  also blocks packages younger than 7 days and enforces Node.js engine requirements.

- **Registered seven flat Python test files in `docs/modules.yaml`.**
  `tests/test_aggregations.py`, `tests/test_analyst.py`, `tests/test_app.py`,
  `tests/test_cli.py`, `tests/test_config.py`, `tests/test_reconcile.py`, and
  `tests/test_service.py` now have corresponding `tests.*` module entries.

- **Registered `tests/clients/test_langfuse.py` in module manifest.** Added
  `tests.clients.test_langfuse` entry to `docs/modules.yaml`.
- **Added `traces_per_agent` to example config.** The
  `config/projects.example.yaml` now includes `traces_per_agent: 1` under
  `settings.analyst:`, matching the Pydantic default of 1 trace per agent.
  The existing regression test now also asserts this field.
- **Added `reconcile_schedule_hours` to example config.** The
  `config/projects.example.yaml` now includes `reconcile_schedule_hours: 24.0`
  under `settings:`, matching the Pydantic default. A regression test ensures the
  example value stays in sync with the code default.

- **Added JS linting, formatting, and type-checking with Biome.**  Configured
  `@biomejs/biome` as a dev dependency with `biome.json` covering the static JS
  sources and Vitest test files.  Added `lint`, `format`, and `lint:ci` npm
  scripts and a `npm run lint:ci` step to the `js-tests` CI job.  Also added
  JSDoc type annotations (including `@typedef` type definitions) to every
  exported function in `shared.js`, `analyst.js`, and `dashboard.js`.

- **Made `robotsix_llmio` import lazy in `reconcile.py`.**  The
  `OpenRouterKeyCostSource` import now lives inside `reconcile_project` instead of
  at module top-level, so the app, CLI, and routes modules are importable without
  the optional `analyst` extra installed.

- **Added Makefile with `test` target to ensure dependencies are installed before running pytest.**
  `make test` runs `uv sync --locked --all-extras` followed by `uv run pytest`,
  preventing `ModuleNotFoundError` for `structlog` and other declared dependencies.

- **Registered JS test files in module taxonomy.** Added `tests.web.analyst`,
  `tests.web.dashboard`, and `tests.web.shared` entries to `docs/modules.yaml`
  for the Vitest test files under `tests/web/`.

- **Registered `tests/conftest.py` and `tests/helpers.py` in `docs/modules.yaml`.**
  Added `tests.conftest` and `tests.helpers` module entries for shared test
  infrastructure (fixtures, factories, data builders).

- **Integrated `googleapis/release-please-action` for automated version management.**
  Added `release-please-config.json` and `.github/workflows/release-please.yml` to
  auto-create Release PRs that bump the version in `pyproject.toml` and
  `src/robotsix_cost_monitor/__init__.py`, update `CHANGELOG.md` from conventional
  commits, and generate `v*` tags on merge.  Added a `conventional-pre-commit`
  hook to `.pre-commit-config.yaml` and documented the commit-message convention
  in `CONTRIBUTING.md`.

- **Replaced hand-rolled brokered request pattern with `BrokeredRequester`.**
  The `_brokered_agent()` factory and manual `agent.send_request()` +
  `reply.body` extraction in `_file_proposals()` and `_fetch_ticket_context()`
  are replaced by `BrokeredRequester` from `robotsix_agent_comm.sdk.brokered_request`,
  which encapsulates transport-pair creation, request, reply unwrapping, and
  teardown in one `request()` call.  Pinned `robotsix-agent-comm` to a newer
  commit that includes this class.

- **Added docstrings to all 20 FastAPI route handlers.**  Each handler in
  `src/robotsix_cost_monitor/routes.py` now carries a one-line docstring
  describing its purpose and URL, improving mkdocstrings output and IDE hover
  help.

- **Consolidated analyst web modules in `docs/modules.yaml`.**
  Merged `robotsix_cost_monitor.web.analyst` and `robotsix_cost_monitor.web.static.analyst`
  into `robotsix_cost_monitor.analyst`, matching the `robotsix_cost_monitor.app` pattern
  where one module owns both Python source and frontend web assets.

- **Fixed `dict_tracebacks`/`ConsoleRenderer` incompatibility in structlog config.**
  `_configure_logging()` now uses `format_exc_info` (string output) when the
  format is `console` and `dict_tracebacks` (structured output) only when the
  format is `json`.  This prevents a `TypeError` inside `ConsoleRenderer` when
  `logger.exception()` is called with an active exception.  Also moved the
  `_configure_logging()` call from module level into `create_app()` to avoid
  global side-effects on import.

- **Restored OpenRouter account-level credit balance in reconciliation.**
  `reconcile.py` now uses the sync `OpenRouterKeyCostSource` from `robotsix-llmio`
  (called via `asyncio.to_thread`) and fetches the per-account credit balance via
  a direct `httpx` call to `GET /api/v1/credits`, populating `result["balance"]` so the
  dashboard's per-project balance badge (`r.balance.remaining`) renders correctly.
  A credits-fetch failure is silently suppressed and does not fail reconciliation.

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
