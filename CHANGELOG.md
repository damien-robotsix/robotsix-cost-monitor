# Changelog

## [0.2.0](https://github.com/damien-robotsix/robotsix-cost-monitor/compare/v0.1.0...v0.2.0) (2026-06-28)


### Features

* **analyst:** file tickets via the board manager (dedup + source), not the responder ([#46](https://github.com/damien-robotsix/robotsix-cost-monitor/issues/46)) ([2e495a6](https://github.com/damien-robotsix/robotsix-cost-monitor/commit/2e495a66dc2dc2c7bc8e31dcd05e8378157b3ec4))
* **analyst:** hand all proposals to the board manager for ticket creation ([#59](https://github.com/damien-robotsix/robotsix-cost-monitor/issues/59)) ([e7e0424](https://github.com/damien-robotsix/robotsix-cost-monitor/commit/e7e0424ded342e2585f08f9f07e88f7b0c3aa26d))
* **analyst:** llmio L2 + L3 trace sub-agent + broker ticket filing ([#18](https://github.com/damien-robotsix/robotsix-cost-monitor/issues/18)) ([f77a0a9](https://github.com/damien-robotsix/robotsix-cost-monitor/commit/f77a0a94408b569c5ee59e9547ba8e71b51512b0))
* **analyst:** most-costly-ticket and most-costly-stage analyses ([#62](https://github.com/damien-robotsix/robotsix-cost-monitor/issues/62)) ([19f0108](https://github.com/damien-robotsix/robotsix-cost-monitor/commit/19f01082857a0eeef925e48b088ba5c968f8804e))
* **analyst:** run the L3 orchestrator on Claude Opus (Claude SDK) ([#51](https://github.com/damien-robotsix/robotsix-cost-monitor/issues/51)) ([6bcc09a](https://github.com/damien-robotsix/robotsix-cost-monitor/commit/6bcc09a45dcd258590a8872d6fda4f2dde7086d3))
* **analyst:** select candidate traces per agent, not globally ([#61](https://github.com/damien-robotsix/robotsix-cost-monitor/issues/61)) ([6e82162](https://github.com/damien-robotsix/robotsix-cost-monitor/commit/6e8216212231915411ce3e1e8af26cad5ac17506))
* **analyst:** surface why each trace was selected for analysis ([#60](https://github.com/damien-robotsix/robotsix-cost-monitor/issues/60)) ([54c512e](https://github.com/damien-robotsix/robotsix-cost-monitor/commit/54c512e0d85b44345cd9ebd6d4e2479ecc6d85b5))
* **analyst:** teach prompts the Claude-SDK subscription cost model ([#64](https://github.com/damien-robotsix/robotsix-cost-monitor/issues/64)) ([466d454](https://github.com/damien-robotsix/robotsix-cost-monitor/commit/466d4543b8f2b7c3f492bca061f53141084de947))
* attribute unnamed traces to their session in by-agent view ([#5](https://github.com/damien-robotsix/robotsix-cost-monitor/issues/5)) ([b95f29e](https://github.com/damien-robotsix/robotsix-cost-monitor/commit/b95f29e1022a4e0a0850fe2fffc78a2845854bf3))
* daily auto-reconciliation + dashboard warning banner ([#58](https://github.com/damien-robotsix/robotsix-cost-monitor/issues/58)) ([af36a83](https://github.com/damien-robotsix/robotsix-cost-monitor/commit/af36a839d520cb783cc6875dfb58de3db2d2ca53))
* Dockerize + continuous-deploy stack ([#1](https://github.com/damien-robotsix/robotsix-cost-monitor/issues/1)) ([e8be9d2](https://github.com/damien-robotsix/robotsix-cost-monitor/commit/e8be9d255db99db046fbd3785559c3b1586f7e17))
* filter by backend (OpenRouter vs ClaudeSDK) ([#4](https://github.com/damien-robotsix/robotsix-cost-monitor/issues/4)) ([4ad3be7](https://github.com/damien-robotsix/robotsix-cost-monitor/commit/4ad3be7b9792637e0ebfd2dee77d8850ea236735))
* per-model cost breakdown on the dashboard ([#3](https://github.com/damien-robotsix/robotsix-cost-monitor/issues/3)) ([98130a2](https://github.com/damien-robotsix/robotsix-cost-monitor/commit/98130a2c55cb3a93ac3b21b31a8e68adaa29058e))
* reconcile on per-key OpenRouter usage, not account credits ([#7](https://github.com/damien-robotsix/robotsix-cost-monitor/issues/7)) ([a655387](https://github.com/damien-robotsix/robotsix-cost-monitor/commit/a6553876da18abfb7df2abce554a955261a840cb))
* robotsix-cost-monitor — multi-Langfuse cost dashboard + reconciliation + cost-analyst ([5033d33](https://github.com/damien-robotsix/robotsix-cost-monitor/commit/5033d33fe05d4aa67537158dd37edfdfd68838e1))
* **web:** cost-analyst page — trigger + last-run traces/proposals/ticket ([#57](https://github.com/damien-robotsix/robotsix-cost-monitor/issues/57)) ([f89fb09](https://github.com/damien-robotsix/robotsix-cost-monitor/commit/f89fb097015f1fe4a5ef2876d05468bbf7987ef0))


### Bug Fixes

* **analyst:** migrate to llmio's get_provider_for_identifier API ([#95](https://github.com/damien-robotsix/robotsix-cost-monitor/issues/95)) ([5a06f96](https://github.com/damien-robotsix/robotsix-cost-monitor/commit/5a06f96f3b1ecf67feaf85a0409e593208333031))
* **analyst:** resume the daily cadence across restarts instead of resetting it ([#97](https://github.com/damien-robotsix/robotsix-cost-monitor/issues/97)) ([5ab62cc](https://github.com/damien-robotsix/robotsix-cost-monitor/commit/5ab62cc8df8fcff0590f72b7ef7465e25bf548b8))
* **analyst:** return text JSON from L2 (DeepSeek thinking rejects tool_choice) ([#44](https://github.com/damien-robotsix/robotsix-cost-monitor/issues/44)) ([3d1fe1f](https://github.com/damien-robotsix/robotsix-cost-monitor/commit/3d1fe1ff24cdcfe75827416d3a75ee59994982dd))
* **analyst:** use the openrouter-deepseek provider with a valid L3 model ([#43](https://github.com/damien-robotsix/robotsix-cost-monitor/issues/43)) ([b8175fa](https://github.com/damien-robotsix/robotsix-cost-monitor/commit/b8175fa627c5d467786f59cc98bad31e2e5bbb75))
* **deps:** bump robotsix-llmio to main (restores AsyncLangfuseReadClient) ([#94](https://github.com/damien-robotsix/robotsix-cost-monitor/issues/94)) ([f53b9b4](https://github.com/damien-robotsix/robotsix-cost-monitor/commit/f53b9b478cf57599f8b61e622e5f655315027bf0))
* **docker:** install git in the builder for the analyst extra's git deps ([#19](https://github.com/damien-robotsix/robotsix-cost-monitor/issues/19)) ([9f94ce1](https://github.com/damien-robotsix/robotsix-cost-monitor/commit/9f94ce1d3ca1573a13287b571a9da9f528d2504e))
* **reconcile:** compare OpenRouter spend against openrouter-backend traced cost ([#27](https://github.com/damien-robotsix/robotsix-cost-monitor/issues/27)) ([01bd9e8](https://github.com/damien-robotsix/robotsix-cost-monitor/commit/01bd9e8d13f2798f7fdaa9066e4a362ba8d1b712))
* **reconcile:** show the last reconcile on page load, not just drift warnings ([#98](https://github.com/damien-robotsix/robotsix-cost-monitor/issues/98)) ([1512090](https://github.com/damien-robotsix/robotsix-cost-monitor/commit/151209091adf787f121047d904e71610f01b076c))
* **reconcile:** trace cost over the exact snapshot interval ([#9](https://github.com/damien-robotsix/robotsix-cost-monitor/issues/9)) ([8fa77db](https://github.com/damien-robotsix/robotsix-cost-monitor/commit/8fa77dbd3036daf57090675d8c5b616b3ca8713c))
* **web:** consistent per-analysis 'analyze' buttons on /analyst ([#63](https://github.com/damien-robotsix/robotsix-cost-monitor/issues/63)) ([824c6fe](https://github.com/damien-robotsix/robotsix-cost-monitor/commit/824c6fefe2c78dca57655569b862ea09364a6f4d))
* window-accurate per-model/backend cost (was day-granular & over-counting) ([#6](https://github.com/damien-robotsix/robotsix-cost-monitor/issues/6)) ([266cf12](https://github.com/damien-robotsix/robotsix-cost-monitor/commit/266cf12f8faf56cdde49d20feaaa53fdfc88a0f7))


### Performance Improvements

* **summary:** count traces via metrics, not by paging them all ([#96](https://github.com/damien-robotsix/robotsix-cost-monitor/issues/96)) ([e5e1f7f](https://github.com/damien-robotsix/robotsix-cost-monitor/commit/e5e1f7f314ea63adab569d335dd34dd3c55f9cf5))

## 0.0.0 (unreleased)

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
