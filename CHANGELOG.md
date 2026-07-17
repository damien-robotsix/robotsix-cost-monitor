## 0.0.0 (unreleased)

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

## [0.2.0](https://github.com/damien-robotsix/robotsix-cost-monitor/compare/v0.1.0...v0.2.0) (2026-07-17)


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
