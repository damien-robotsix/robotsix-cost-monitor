## 0.0.0 (unreleased)

- Added Configuration Reference and CLI Reference pages to the MkDocs documentation site.
- Remove orphaned `[tool.bandit]` section from `pyproject.toml` — bandit was never installed or invoked; security scanning is already covered by Ruff S rules, trufflehog, detect-secrets, and CodeQL in CI.
- Change `[tool.ruff] target-version` from `py312` to `py314` to match `requires-python = ">=3.14"`.
- Refactor `_ORCHESTRATOR_SYSTEM` to reference shared `_PROPOSAL_JSON` constant instead of duplicating the JSON-output instruction inline.
- Enable ruff pydocstyle (D) rules — all public API items now require docstrings; tests are excluded.
- Enable `triage_boilerplate` periodic workflow (`.robotsix-mill/periodic/triage_boilerplate.yaml`).
- Sync ``_TICKET_SYSTEM`` prompt with actual payload: remove promise of board
  history and ticket description (both still ``None``), and note their
  unavailability so the LLM does not speculate about missing data.
- Removed the broker filing panel from the analyst dashboard (`filingHTML`, `managerReply`, and `FilingResult` typedef in `analyst.js`).
- Align Docker image to round-4 fleet standard: runtime user `app` with home `/home/app`, persistent data at `/data` (from `/home/appuser/.data`), updated compose bind-mounts accordingly.
- **Remove `robotsix-agent-comm` broker dependency and analyst ticket-filing.**  
  The LLM cost-analyst no longer files board tickets through the central broker.
  Removed the `robotsix-agent-comm` optional dependency, all broker fields from
  `AnalystConfig` (`broker_host`, `broker_port`, `broker_scheme`, `broker_token`,
  `board_manager_id`, `board_agent_id`, `board_repo_id`), the `can_file_tickets`
  property, `_file_proposals`, `_fetch_ticket_context`, and all filing code paths.
  The analyst still produces cost-reduction proposals and persists them to
  `.data/analyst/` as before.
- Align `.pre-commit-config.yaml` to 2026-07 standards: remove `bandit` (CI-only), add `check-json`, `check-merge-conflict`, `check-added-large-files`, `detect-private-key`, `actionlint`, and `hadolint` hooks
- Update all `robotsix-github-workflows` reusable workflow SHA pins to current HEAD (`77e10e28…`) and add `baseline-check` caller to CI pipeline
- **Onboard to central-deploy; retire Watchtower continuous-deploy stack.**  
  - Rewrite `deploy/docker-compose.yml` for central-deploy compatibility: add `x-central-deploy` extension with `contract-version: "1.0"` as the first non-blank line, replace bind-mount volumes with named volumes (`cost_monitor_config`, `cost_monitor_data`), remove Watchtower service and labels, add `robotsix.deploy.stateful` labels to named volumes, and add `robotsix.deploy.config-target: cost_monitor_config` label to the cost-monitor service.  
  - Fix `.github/dependabot.yml`: add `docker` package-ecosystem as a properly separated list entry (was previously inserted as a sibling key under `uv`, breaking the YAML structure).  
  - Generate `config/projects.schema.json` from the Pydantic `Config` model for IDE validation of `config/projects.yaml`; add `format: uri` to `base_url`, `pattern: "^pk-lf-"`/`"^sk-lf-"` to `public_key`/`secret_key`, `minItems: 1` to `projects`, and add `base_url`/`projects` to their respective `required` arrays.  
  - Update `deploy/README.md` to reflect central-deploy button-triggered updates (replacing Watchtower polling), named-volume provisioning steps, and add a "Migrating from bind-mounts to named volumes" section with `docker volume create` + `docker run --rm alpine cp` commands for both config and data.
- Extract `_gather_list_results` helper in `CostService` to eliminate duplicated project-gather-with-error-isolation pattern across `by_agent`, `by_agent_segmented`, and `by_model`.
- Extract repeated `_window`/`_require_project` boilerplate from seven route handlers into a composable `ProjectWindow` FastAPI dependency (``resolve_project``, ``resolve_hours``, ``project_window``)
- Add Dependabot auto-merge caller workflow to auto-merge Dependabot PRs once required checks pass.
- Adopt `respx` for HTTP mocking in Langfuse client tests, replacing hand-rolled `_async_client_mock()` / `_response()` helpers and `unittest.mock.patch` blocks with `respx_mock` fixtures for higher-fidelity httpx transport interception.
- Enable `changelog_autofill` periodic workflow to auto-insert changelog entries for PRs failing the `changelog` check.
- Add link to robotsix-standards repo in README.md and AGENT.md.
- Deduplicated `setStatus` into `shared.js`, removing local copies from `dashboard.js` and `analyst.js`
- Rename `data_dir_audit` periodic workflow to `data_dir_gc` for `.data/` directory cleanup
- Consolidated JS web test module entries (`tests.web.analyst`, `tests.web.dashboard`, `tests.web.shared`) into their source modules in `docs/modules.yaml`, matching the Pattern A convention used for Python test modules.
- Fix CI workflow YAML syntax error: remove `timeout-minutes` from reusable-workflow-call jobs (`ci`, `security`, `docs`, `publish`) where it is not a valid property (#220 regression)
- build(deps): Update uvicorn[standard] requirement from >=0.34 to >=0.49.0 (PR #42)
- Update Bandit pre-commit hook from 1.8.3 to 1.9.4 for latest security checks and Python 3.14+ compatibility.
- Generate CycloneDX SBOM at build time (`uv export --format cyclonedx1.5`):
  - New `sbom` job in `ci.yml` uploads the SBOM as a build artifact on every push/PR.
  - Docker image now includes the SBOM at `/home/appuser/sbom.cyclonedx.json`.
  - Release workflow generates, attests (SLSA provenance), and archives the SBOM.
- Add periodic `security_posture` workflow
- **Consolidated `docs/modules.yaml` module entries** — merged
  `robotsix_cost_monitor.langfuse` and `tests.clients.test_langfuse` into
  `robotsix_cost_monitor.clients`, so the entire `clients/` sub-package
  (init, models, langfuse, and its tests) lives under one cohesive entry.

- **Added `[tool.bandit]` config to `pyproject.toml`** — excludes test
  directories and venv/node_modules from bandit scans, resolving a misleading
  `-c pyproject.toml` reference in pre-commit that previously pointed at a
  non-existent section. Also added `additional_dependencies: ["bandit[toml]"]`
  to the bandit pre-commit hook so the TOML config is parsed.

- **Eliminated duplicated proposals HTML template in `analyst.js`** — the
  inline `.map(...).join('')` block in `render()` now delegates to the
  existing `proposalsHTML(props)` function, removing ~12 lines of duplicated
  template logic and keeping both rendering paths in sync.
- **Extracted `_sorted_cost_rows` helper in `aggregations.py`** — deduplicates
  sort+format boilerplate in `aggregate_by_name`, `aggregate_by_session`, and
  `aggregate_by_name_backend`, ensuring consistent rounding precision.

- **Dashboard: segmented by-agent panel with subscription-vs-marginal split** —
  `renderByAgentSegmented` now renders two distinct columns (OpenRouter
  marginal and subscription estimate) with per-stage call counts, badges
  subscription-only stages with "subscription — no model-switch", and shows a
  volume-vs-cap warning when subscription calls approach the configured cap.

- **Added `marginal_reducible` flag to `aggregate_by_name_split`** — each stage
  row now carries a boolean indicating whether the stage has any OpenRouter
  (pay-per-token) cost, distinguishing subscription-backed stages from those
  with marginal spend.

- **Enriched `by_agent_segmented` service result** — returns a dict with
  `window_hours`, `rows`, `openrouter_marginal_total`,
  `subscription_estimate_total`, `subscription_count_total`,
  `subscription_cap`, and `subscription_cap_pct` (was a plain list).

- **Added `subscription_call_cap` setting** — configurable int (default 0)
  in `Settings` for volume-vs-cap monitoring of subscription-backed stages.

- **Moved `tests/test_aggregations.py` to per-module layout** — relocated to
  `tests/robotsix_cost_monitor/test_aggregations.py`; merged test entry into
  the source module's paths in `docs/modules.yaml`.

- **Fixed docstring drift in `_opus_analysis`** — replaced "DeepSeek thinking
  rejects forced tool_choice" with correct rationale ("avoids structured-output
  parsing edge-cases with reasoning models"); `_opus_analysis` runs Claude Opus,
  not DeepSeek.

- **Added vulture whitelist entries for `clients/models.py`** — suppressed
  false-positives for Pydantic `model_config` and field declarations
  (`total_cost`, `calculated_total_cost`) consumed via metaclass machinery.

- **Added `jsconfig.json` and `npm run typecheck` to CI.** The new `jsconfig.json`
  enables `tsc --noEmit` type-checking (`strict`, `allowJs`, `checkJs`,
  `target: ES2022`) across the JS frontend sources under
  `src/robotsix_cost_monitor/web/static/`. Added `typescript` as a devDependency
  and a `typecheck` npm script, and inserted a `npm run typecheck` step in the
  `js-tests` CI job after lint and before tests.
- **Extracted duplicated early-return block in `analyst.py`** — `run_ticket_analyst`
  and `run_stage_analyst` now share a `_no_top_early_return(kind, detail)` helper
  that constructs the "no top-{kind} data" response, writes it to the targeted
  store, and returns it. Eliminates the 6-line clone pair between the two functions.

- **Moved `tests/test_service.py` to `tests/robotsix_cost_monitor/test_service.py`**
  to align with the per-module test layout convention. Import paths updated
  to use relative imports (`..conftest`, `..helpers`). Added empty
  `tests/robotsix_cost_monitor/__init__.py` to enable relative imports.
  `docs/modules.yaml` updated accordingly.
- **Moved `tests/test_routes.py` to `tests/robotsix_cost_monitor/test_routes.py`**
  to align with the per-module test layout convention. Added
  `tests/robotsix_cost_monitor/__init__.py` and fixed conftest import to use
  a relative `..conftest` path. `docs/modules.yaml` updated accordingly.

- **Moved `tests/test_app.py` to `tests/robotsix_cost_monitor/test_app.py`**
  to align with the per-module test layout convention.
  `docs/modules.yaml` updated accordingly.

- **Moved `tests/test_analyst.py` to `tests/robotsix_cost_monitor/test_analyst.py`**
  to align with the per-module test layout convention.
  Merged the `tests.test_analyst` module entry into `robotsix_cost_monitor.analyst`
  in `docs/modules.yaml`.

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
