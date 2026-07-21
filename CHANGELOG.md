## 0.0.0 (unreleased)

- Add `engines` field to `package.json` (`"node": ">=22"`) so that `.npmrc`'s `engine-strict=true` actually enforces the Node.js version requirement.
- Replace hand-rolled RetryClient with robotsix-http
- Add `npm audit --audit-level=high` to the `js-tests` CI job, right after `npm audit signatures`, to catch high/critical CVEs in npm dependencies.
- Add `--ignore-scripts` to global `npm install` of `@anthropic-ai/claude-code` in `Dockerfile.dev` for defense-in-depth parity with the production Dockerfile.
- Pin TypeScript to exact version `5.9.3` in `package.json` (replacing caret range `^5.7`)
- Add Vitest coverage configuration (`@vitest/coverage-v8`) with 75% thresholds for JS tests, matching Python-side coverage parity
- Add `--ignore-scripts` to the global `npm install` of `@anthropic-ai/claude-code` in the Dockerfile runtime stage, extending defense-in-depth against malicious lifecycle scripts to the container build.
- Add `BackendKind = Literal["openrouter", "claude-sdk"]` type alias in
  `aggregations.py` and annotate `backend_for_model()` and `backend_trend()`
  with it for static-checking safety.
- Handle Langfuse fetch failures in `reconcile_project()` gracefully: network errors, bad JSON, and unexpected exceptions are now caught and reported as an error dict instead of crashing the reconcile.
- Add dedicated test file ``tests/robotsix_cost_monitor/test__utils.py`` for ``_utils.py``, with analyst call-site coverage (``load_proposals`` / ``load_targeted_analysis``)
- Adopt the canonical structlog-to-stdlib bridge: ``ProcessorFormatter``
  with ``foreign_pre_chain`` unifies structlog, Uvicorn, and third-party
  logs into a single JSON/console format. A new ``add_correlation_id``
  processor injects ``request_id`` from ``asgi-correlation-id`` into every
  log event. Added ``LOG_LEVEL`` env var (default ``INFO``) and passed
  ``log_config=None`` to ``uvicorn.run`` so the bridge isn't overridden.
- Add `ignore-scripts=true` to `.npmrc` to disable lifecycle scripts during `npm install`/`npm ci` as defense-in-depth against install-time supply-chain attacks.
- Add `biome` (JS/TS lint) pre-commit hook via `npx @biomejs/biome check` matching CI paths.
- Add `workflow_dispatch` trigger to the Release Please workflow
  (`.github/workflows/release-please.yml`), enabling manual release creation
  from the GitHub Actions UI in addition to the existing push-to-main trigger.
- Centralize analyst analysis kind strings (`"ticket"`, `"stage"`, `"fleet"`) as a `Literal` type alias `AnalystKind` in `analyst.py`, replacing bare `str` annotations in route handlers and analysis functions.
- Reorganize `tests/helpers.py` → `tests/robotsix_cost_monitor/helpers.py` to align with per-module test layout convention. Update import paths in 5 test files and add `tests/__init__.py` for package resolution.
- Add `codespell` and `markdownlint-cli2` pre-commit hooks plus config files (`.markdownlint.jsonc`, `.codespell-ignore`).
- Update `ARCHITECTURE.md` directory listing: `app.py` description no longer claims route handlers (extracted to `routes.py`), and add a `routes.py` entry.
- Delete `config/projects.example.yaml` — superseded by `config/projects.example.json`.
- Enable Biome CSS linting and formatting for `dashboard.css` by adding `*.css` to `files.include` in `biome.json`
- Update `vulture_whitelist.py`: replace stale `analyst_ticket_run` and `analyst_stage_run` entries with `analyst_run_targeted` and `analyst_targeted`, matching the current route handler names.
- Add mypy type checking for the test suite (`uv run mypy src/ tests/`) in CI and Makefile. Add a per-module override to relax `disallow_untyped_defs` for test modules and remove now-unnecessary `# type: ignore[no-untyped-def]` comments from `test_langfuse.py`.
- Migrate config loading from `robotsix-yaml-config` to the fleet-standard
  `robotsix-config` library. The config file format changes from YAML
  (`config/projects.yaml`) to JSON (`config/projects.json`), with the example
  template at `config/projects.example.json`.  
  The `load_config()` helper now delegates to `robotsix_config.load_config()`
  for validation. Remove the `robotsix-yaml-config` dependency.
- Fix: Replace YAML `...` placeholder with actual `step-security/harden-runner` step in the `module-validation` job of `.github/workflows/ci.yml`. The harden-runner step now appears as the first step (same pinned SHA `9af89fc71515a100421586dfdb3dc9c984fbf411 # v2.19.4`) with `egress-policy: audit`, matching every other job in the workflow file.
- Bump `[tool.ruff] target-version` to `"py314"` and `[tool.mypy] python_version` to `"3.14"` to match `requires-python = ">=3.14"`.
- Promoted `_safe_load_json` to `safe_load_json` in a new `_utils.py` shared module; updated all imports in `reconcile.py`, `analyst.py`, and `test_reconcile.py`.
- Refactor `RetryClient.get()` to reduce nesting: extract `_attempt_get` and `_raise_on_exhaustion` helpers, and reuse `_get_retry_delay` in the network-error path instead of an inline jitter formula.
- Collapse duplicated `analyst_ticket_run` and `analyst_stage_run` POST handlers into a single `/api/analyst/run/{kind}` route with a 404 guard for unknown kinds.
# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Add `scripts/generate_config_schema.py` to auto-regenerate `config/projects.schema.json` from the Pydantic config models, plus `make schema` / `make verify-schema` targets, a CI freshness gate (`config-schema` job), and a pre-commit hook to prevent silent schema drift.
- Document `LOG_FORMAT` env var in both `docs/reference/configuration.md` and `docs/reference/cli.md` env-var tables.
- Updated `docs/index.md` with links to the Configuration Reference and CLI Reference pages.
- Activate `[tool.coverage]` configuration: add `pytest-cov` dev dependency and pass `--cov=robotsix_cost_monitor --cov-report=term-missing` in both `make test` and CI.
- Document all 20 API endpoints in the README, up from 8 previously undocumented routes.
- Add `module-validation` CI job that validates `docs/modules.yaml` against the canonical robotsix-modules JSON Schema. The job uses `robotsix-modules-validate` when the dev dependency is available, falling back to a vendored `scripts/validate_modules.py` (uses only `pyyaml` + `jsonschema`) when offline.
- Adopt `robotsix-modules` as a dev dependency (Git source) and add a vendored inline validator (`scripts/validate_modules.py` + `scripts/modules.schema.yaml`) for offline resilience.
- Add typed exception hierarchy (`CostMonitorError`, `ExternalServiceError`, `ExternalAuthError`, etc.) to distinguish retriable transient errors from terminal configuration errors.
- Add `RetryClient` (jittered exponential-backoff httpx wrapper) for Langfuse and OpenRouter HTTP calls.
- Add `cost_monitor_error_handler` to return consistent JSON error envelopes for cost-monitor errors.
- Add `Dockerfile.dev` that pre-installs the `dev`, `lint`, and `docs` dependency groups at image-build time so the test sandbox can run `make test` / `uv run pytest` without a PyPI round-trip (the sandbox has no outbound internet).
- Added `COST_MONITOR_CONFIG` and `COST_MONITOR_DATA` entries to `deploy/.env.example`, matching the mandatory env vars documented in AGENT.md.
- Added Configuration Reference and CLI Reference pages to the MkDocs documentation site.
- Enable `triage_boilerplate` periodic workflow (`.robotsix-mill/periodic/triage_boilerplate.yaml`).
- Add Dependabot auto-merge caller workflow to auto-merge Dependabot PRs once required checks pass.
- Enable `changelog_autofill` periodic workflow to auto-insert changelog entries for PRs failing the `changelog` check.
- Add link to robotsix-standards repo in README.md and AGENT.md.
- Generate CycloneDX SBOM at build time (`uv export --format cyclonedx1.5`): new `sbom` job in `ci.yml`, Docker image includes SBOM at `/home/appuser/sbom.cyclonedx.json`, release workflow generates and attests (SLSA provenance) the SBOM.
- Add periodic `security_posture` workflow.
- Added `[tool.bandit]` config to `pyproject.toml` — excludes test directories and venv/node_modules from bandit scans, resolving a misleading `-c pyproject.toml` reference in pre-commit.
- Dashboard: segmented by-agent panel with subscription-vs-marginal split — `renderByAgentSegmented` now renders two distinct columns (OpenRouter marginal and subscription estimate) with per-stage call counts, badges subscription-only stages, and shows volume-vs-cap warning.
- Added `marginal_reducible` flag to `aggregate_by_name_split` — each stage row now carries a boolean indicating whether the stage has any OpenRouter (pay-per-token) cost.
- Enriched `by_agent_segmented` service result — returns a dict with `window_hours`, `rows`, `openrouter_marginal_total`, `subscription_estimate_total`, `subscription_count_total`, `subscription_cap`, and `subscription_cap_pct`.
- Added `subscription_call_cap` setting — configurable int (default 0) in `Settings` for volume-vs-cap monitoring of subscription-backed stages.
- Added vulture whitelist entries for `clients/models.py` — suppressed false-positives for Pydantic `model_config` and field declarations.
- Added `jsconfig.json` and `npm run typecheck` to CI. The new `jsconfig.json` enables `tsc --noEmit` type-checking (`strict`, `allowJs`, `checkJs`, `target: ES2022`) across the JS frontend. Added `typescript` as a devDependency.
- Added typed Pydantic v2 response models for Langfuse API shapes (`LangfuseMetricsRow`, `LangfuseTrace`). `LangfuseClient` now parses API responses through `model_validate()` at the boundary.
- Added `.nvmrc` and `.node-version` to pin Node.js to version 20.
- Added `robotsix_cost_monitor.aggregations` and `robotsix_cost_monitor.clients` to API reference. The `docs/api.md` mkdocstrings listing now includes both modules.
- Added JS linting, formatting, and type-checking with Biome. Configured `@biomejs/biome` as a dev dependency with `biome.json` covering static JS sources and Vitest test files.
- Added Makefile with `test` target to ensure dependencies are installed before running pytest.
- Registered JS test files in module taxonomy. Added `tests.web.analyst`, `tests.web.dashboard`, and `tests.web.shared` entries to `docs/modules.yaml`.
- Registered `tests/conftest.py` and `tests/helpers.py` in `docs/modules.yaml`.
- Integrated `googleapis/release-please-action` for automated version management. Added `release-please-config.json` and `.github/workflows/release-please.yml`, `conventional-pre-commit` hook, and documented commit-message convention in `CONTRIBUTING.md`.
- Added docstrings to all 20 FastAPI route handlers.
- Added `zizmor` GitHub Actions security audit to CI (new `workflow-audit` job).
- Added `reconcile_schedule_hours` to example config. The `config/projects.example.yaml` now includes `reconcile_schedule_hours: 24.0` under `settings:`.
- Added `traces_per_agent` to example config. The `config/projects.example.yaml` now includes `traces_per_agent: 1` under `settings.analyst:`.
- Registered seven flat Python test files in `docs/modules.yaml`.
- Registered `tests/clients/test_langfuse.py` in module manifest.
- Added segmented per-stage cost aggregation by backend. New `GET /api/by-agent-segmented` endpoint splits each stage's cost into OpenRouter marginal and Claude-SDK subscription-estimated pools.
- Adopted `structlog` as the first-party structured logging layer, replacing the optional `robotsix_llmio.logging.setup_logging` fallback. Added `asgi-correlation-id` middleware for `X-Request-ID` propagation.
- Added `dependency-hygiene` job to CI running `deptry .` against the full dependency tree.
- Added `ARCHITECTURE.md` and `CONTRIBUTING.md`. Both linked from `README.md`.
- Added developer-convenience Makefile targets (`lint`, `typecheck`, `format`, `serve`, `docs`, `clean`).
- Added `.npmrc` with `save-exact`, `min-release-age`, and `engine-strict`. Pinned all npm devDependencies to exact versions in `package.json`.

### Changed
- Remove stale `tests/web/` references from `package.json` Biome scripts and `biome.json` include array (directory was emptied in a prior ticket).
- Remove stale `analyst_stage` and `analyst_ticket` entries from `vulture_whitelist.py` (these route handlers were collapsed into `analyst_targeted(kind)`).
- Consolidated `clients-http` module into `clients` in `docs/modules.yaml` taxonomy; `_http.py` is an internal detail of the clients sub-package.
- Consolidated `tests-conftest` module into `tests-helpers`: moved the `event_loop` fixture from `tests/conftest.py` into `tests/helpers.py`, updated three test files to import from `helpers` instead of `conftest`, and deleted `tests/conftest.py`.
- Extract repeated exception-handling boilerplate in `CostService` into a private `_safe_project_fetch` helper, eliminating ~23 lines of duplication.
- Move `tests/web/dashboard.test.js` to `tests/robotsix_cost_monitor/web/static/dashboard.test.js` and update its import path to match sibling JS tests.
- Collapse duplicated `analyst_stage()` and `analyst_ticket()` GET handlers into a single `@router.get("/api/analyst/{kind}")` parameterized route in `routes.py`.
- Extract hardcoded API endpoint paths and query-parameter names from `dashboard.js` and `analyst.js` into shared `API` and `QS` constants in `shared.js`.
- Collapse redundant `except CostMonitorError` / `except Exception` pairs in `_analyst_loop` and `_reconcile_loop` into single `except Exception` blocks.
- Register `.robotsix-mill/periodic/repo_description_sync.yaml` in module taxonomy and remove stale entries for deleted periodic configs.
- Upgrade `actions/upload-artifact` from v4 (Node.js 20, EOL) to v7.0.1 in CI and release workflows.
- `_require_project` in routes now raises `ProjectNotFoundError` (instead of bare `HTTPException`) so API consumers receive the typed `error_code: "PROJECT_NOT_FOUND"` in the JSON error envelope.
- Moved `analyst.test.js` from `tests/web/` to `tests/robotsix_cost_monitor/web/static/` (per-module layout).
- Move `mypy` and `vulture` from the `dev` dependency group to a new `typing` group so that `uv sync` does not require downloading `pathspec` (a mypy dependency) when only running tests.
- Move `tests/web/shared.test.js` to `tests/robotsix_cost_monitor/web/static/shared.test.js` and update vitest config include pattern to align with per-module test layout convention.
- Migrate all `except Exception` catch-sites in `service.py`, `app.py`, and `reconcile.py` to catch typed exceptions with a catch-all fallback.
- Simplify `test_command` in `.robotsix-mill/config.yaml`: always sync dev deps before running pytest.
- Split `[dependency-groups] dev` into `dev` (test-only: pytest*, respx) and `lint` (ruff, mypy, vulture) so that `make test` no longer requires downloading lint tools.
- Trace-level analyst prompt now instructs the agent to identify the current repo from `session.id` metadata before attempting to access paths.
- Moved `vulture` from the `dev` dependency group to a new `lint` group so that `uv sync --group dev` does not require network-only packages.
- Pin `mypy<2` in dev dependencies to avoid the `ast-serialize` transitive dependency introduced in mypy 2.1.0.
- Moved `respx` from hard dev dependency to optional `http-mock` group; `test_langfuse.py` now uses `pytest.importorskip("respx")` so the test suite runs without it.
- Move analyst JS test to per-module layout (`tests/robotsix_cost_monitor/web/static/analyst.test.js`) and update vitest config accordingly.
- Add `UV_OFFLINE: "1"` to the `ci` job's `env` block in `.github/workflows/ci.yml` to prevent cold-cache DNS failures in air-gapped CI.
- Bump Node.js from 20 (EOL) to 22 LTS across `.nvmrc`, `.node-version`, and CI workflow.
- Consolidated 5 duplicate TTL cache dicts into a reusable `TTLCache[K, V]` class with an `async get_or_fetch(key, fetch_fn)` method.
- Refactor `_ORCHESTRATOR_SYSTEM` to reference shared `_PROPOSAL_JSON` constant instead of duplicating the JSON-output instruction inline.
- Enable ruff pydocstyle (D) rules — all public API items now require docstrings; tests are excluded.
- Sync `_TICKET_SYSTEM` prompt with actual payload: remove promise of board history and ticket description (both still `None`), and note their unavailability so the LLM does not speculate about missing data.
- Align Docker image to round-4 fleet standard: runtime user `app` with home `/home/app`, persistent data at `/data` (from `/home/appuser/.data`), updated compose bind-mounts accordingly.
- Align `.pre-commit-config.yaml` to 2026-07 standards: remove `bandit` (CI-only), add `check-json`, `check-merge-conflict`, `check-added-large-files`, `detect-private-key`, `actionlint`, and `hadolint` hooks.
- Update all `robotsix-github-workflows` reusable workflow SHA pins to current HEAD (`77e10e28…`) and add `baseline-check` caller to CI pipeline.
- Onboard to central-deploy; retire Watchtower continuous-deploy stack. Rewrite `deploy/docker-compose.yml` for central-deploy compatibility, replace bind-mount volumes with named volumes, remove Watchtower service and labels, fix `.github/dependabot.yml`, generate `config/projects.schema.json`, update `deploy/README.md`.
- Extract `_gather_list_results` helper in `CostService` to eliminate duplicated project-gather-with-error-isolation pattern.
- Extract repeated `_window`/`_require_project` boilerplate from seven route handlers into a composable `ProjectWindow` FastAPI dependency (`resolve_project`, `resolve_hours`, `project_window`).
- Adopt `respx` for HTTP mocking in Langfuse client tests, replacing hand-rolled `_async_client_mock()` / `_response()` helpers.
- Deduplicated `setStatus` into `shared.js`, removing local copies from `dashboard.js` and `analyst.js`.
- Rename `data_dir_audit` periodic workflow to `data_dir_gc` for `.data/` directory cleanup.
- Consolidated JS web test module entries (`tests.web.analyst`, `tests.web.dashboard`, `tests.web.shared`) into their source modules in `docs/modules.yaml`.
- build(deps): Update uvicorn[standard] requirement from >=0.34 to >=0.49.0.
- Update Bandit pre-commit hook from 1.8.3 to 1.9.4 for latest security checks and Python 3.14+ compatibility.
- Consolidated `docs/modules.yaml` module entries — merged `robotsix_cost_monitor.langfuse` and `tests.clients.test_langfuse` into `robotsix_cost_monitor.clients`.
- Eliminated duplicated proposals HTML template in `analyst.js` — the inline `.map(...).join('')` block in `render()` now delegates to the existing `proposalsHTML(props)` function.
- Extracted `_sorted_cost_rows` helper in `aggregations.py` — deduplicates sort+format boilerplate in `aggregate_by_name`, `aggregate_by_session`, and `aggregate_by_name_backend`.
- Moved `tests/test_aggregations.py` to per-module layout — relocated to `tests/robotsix_cost_monitor/test_aggregations.py`; merged test entry into the source module's paths in `docs/modules.yaml`.
- Extracted duplicated early-return block in `analyst.py` — `run_ticket_analyst` and `run_stage_analyst` now share a `_no_top_early_return(kind, detail)` helper.
- Moved `tests/test_service.py` to `tests/robotsix_cost_monitor/test_service.py` to align with the per-module test layout convention.
- Moved `tests/test_routes.py` to `tests/robotsix_cost_monitor/test_routes.py` to align with the per-module test layout convention.
- Moved `tests/test_app.py` to `tests/robotsix_cost_monitor/test_app.py` to align with the per-module test layout convention.
- Moved `tests/test_analyst.py` to `tests/robotsix_cost_monitor/test_analyst.py` to align with the per-module test layout convention.
- Replaced vendored `_LangfuseRESTClient` with `AsyncLangfuseReadClient` from robotsix-llmio. `robotsix-llmio` is now a hard (non-optional) core dependency.
- Consolidated `_load_json` in `analyst.py` with `_safe_load_json` from `reconcile.py`. Deleted the local `_load_json` helper and replaced its two call sites.
- Extracted shared `_build_analysis_response` factory in `analyst.py`. The duplicate `out` dict literal (6 fields) in `run_analyst` and `_run_opus_analysis_and_file` is replaced by a single helper.
- Extracted shared `_safe_load_json` helper in `reconcile.py`. Replaced two duplicate JSON-loading patterns with a single `_safe_load_json(path, default)` generic function.
- Made `robotsix-llmio` import in `reconcile.py` lazy with graceful fallback. The `OpenRouterKeyCostSource` import is now inside `reconcile_project()` and wrapped in `try/except ImportError`.
- Consolidated analyst web modules in `docs/modules.yaml`. Merged `robotsix_cost_monitor.web.analyst` and `robotsix_cost_monitor.web.static.analyst` into `robotsix_cost_monitor.analyst`.
- Extracted shared cache-access helper in `CostService`. Five private methods now delegate to a single `_cached_fetch` helper that encapsulates the key-lookup, monotonic-deadline check, TTL-based caching pattern.
- Dashboard renders segmented per-stage cost by backend. The "cost by agent / stage" panel now fetches `/api/by-agent-segmented` and shows OpenRouter marginal cost as primary figure with a de-emphasized subscription-estimated column.
- Extracted route and exception handlers into `routes.py`. All HTTP route handlers and exception handlers previously inline in `create_app()` now live in `routes.py` behind a module-level `router = APIRouter()`.
- Extracted `_require_project` helper in `app.py`. Seven route handlers that validated a project slug against the config now delegate to a shared helper.
- Vendored `LangfuseClient` REST helper. The `LangfuseClient` now uses a small, self-contained `_LangfuseRESTClient` instead of importing from the optional `robotsix-llmio` package.
- Replaced hand-rolled brokered request pattern with `BrokeredRequester` from `robotsix_agent_comm.sdk.brokered_request`.

### Fixed
- Fix incorrect username in deploy README: `appuser` → `app` to match the Dockerfile.
- Fix: remove `base_url` from the JSON Schema `required` list for `ProjectConfig`, matching the Pydantic model default (`https://cloud.langfuse.com`).
- Fix deploy `docker-compose.yml` volume mount paths to match the Dockerfile: config volume now mounts to `/home/app/config` and data volume to `/data`.
- Fix `_TRACE_SYSTEM` prompt referencing non-existent `session.id` JSON key — changed to `sessionId` to match the aliased field in the trace payload.
- Fix `Dockerfile.dev` to pass `--active` to `uv sync` so dev/lint/docs groups are installed into `/opt/venv` rather than a separate `.venv` in the build directory.
- `LangfuseTrace` model now preserves extra fields (like `observations`) from the Langfuse API via `extra="allow"` in its `model_config`.
- Fix CI workflow YAML syntax error: remove `timeout-minutes` from reusable-workflow-call jobs (`ci`, `security`, `docs`, `publish`) where it is not a valid property.
- Fixed docstring drift in `_opus_analysis` — replaced "DeepSeek thinking rejects forced tool_choice" with correct rationale ("avoids structured-output parsing edge-cases with reasoning models").
- Fixed `_parse_analysis` docstring: s/level-2/agent/. The docstring incorrectly claimed the function parsed output from a level-2 agent, but it is called exclusively from `_opus_analysis`.
- Swapped incorrect `global_model` / `trace_model` comments in example config. The inline YAML comments were reversed relative to what the fields actually control.
- Fixed strict TypeScript type errors in static JS files. Added null checks, catch-block type assertions, and element-type casts to `shared.js`, `analyst.js`, and `dashboard.js`.
- Fixed `dict_tracebacks`/`ConsoleRenderer` incompatibility in structlog config. `_configure_logging()` now uses `format_exc_info` (string output) when format is `console` and `dict_tracebacks` only when format is `json`.
- Restored OpenRouter account-level credit balance in reconciliation. `reconcile.py` now fetches per-account credit balance via direct `httpx` call to `GET /api/v1/credits`.
- Fixed example config `max_trace_analyses` drift. The committed `config/projects.example.yaml` now sets `max_trace_analyses: 12`, matching the Pydantic default.

### Removed
- Remove `pytest-cov>=6.0` from dev dependencies in `pyproject.toml` and `uv.lock` — it is not pre-cached in the CI sandbox image.
- Remove orphaned `[tool.bandit]` section from `pyproject.toml` — bandit was never installed or invoked; security scanning is already covered by Ruff S rules, trufflehog, detect-secrets, and CodeQL in CI.
- Removed the broker filing panel from the analyst dashboard (`filingHTML`, `managerReply`, and `FilingResult` typedef in `analyst.js`).
- Remove `robotsix-agent-comm` broker dependency and analyst ticket-filing. Removed the `robotsix-agent-comm` optional dependency, all broker fields from `AnalystConfig`, the `can_file_tickets` property, `_file_proposals`, `_fetch_ticket_context`, and all filing code paths. The analyst still produces cost-reduction proposals and persists them to `.data/analyst/` as before.
- Removed legacy nested-dict reply branch from `managerReply()` in analyst.js. The `typeof rr.reply === 'object'` branch was dead code — no production backend path produces a nested-dict reply.

### Security
- Add `step-security/harden-runner@v2.19.4` as the first step in every directly-defined CI job for runtime network egress control and supply-chain attack detection. Starts with `egress-policy: audit` mode across ci.yml (8 jobs) and release.yml (1 job).
- Add `zizmor` GitHub Actions security audit to CI. A new `workflow-audit` job runs `uvx zizmor --min-severity medium .github/workflows/` on every PR to detect unpinned action refs, template injection, excessive permissions, and other GitHub Actions security issues.
