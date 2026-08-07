<!-- markdownlint-disable MD013 -->
## 0.0.0 (unreleased)

- Remove dead `LangfuseClient.fetch_trace_detail` method and its unit test; the method had no production callers and was a thin delegation wrapper over `AsyncLangfuseReadClient.fetch_trace_detail`.
- Removed orphaned `LangfuseClient.fetch_trace_detail` method (no production consumer since the `CostService.trace_detail` removal).
- Bump `uv` from 0.11.21 to 0.12.1 in `Dockerfile` and `Dockerfile.dev`
- Remove remaining vestigial analyst references from AGENT.md, docker-compose.yml, docs/.docagent-memory.md, and .secrets.baseline.
- Remove stale "analyst proposals" reference from docker-compose.yml volume comment
- Added HTTP-level TestClient coverage for the ``/api/components`` route and extracted ``_fetch_or_error`` helper to deduplicate error-handling blocks in ``reconcile_project``.
- Add `make test-langfuse` target to run all Langfuse-related tests in a
  single pytest invocation, reducing tool-call overhead for CI-fix agents.
- Fix high-severity JS dependency advisories by bumping overrides to fixed versions (brace-expansion 5.0.9, minimatch 10.2.6, postcss 8.5.25) so `npm audit --audit-level=high` passes deterministically without a runtime patching step.
- Remove remaining vestigial analyst references from CONTRIBUTING.md, ARCHITECTURE.md, deploy/README.md, CodeQL config, and docker-compose files. robotsix-llmio is now a regular base dependency.
- Document 404 `PROJECT_NOT_FOUND` error contract in `_CHAT_SKILL` (served at `GET /chat-skill`) for unmatched `?project=<scope>` values.
- Unknown `?project=<slug>` query parameters now return **404** with `{"error":{"code":"PROJECT_NOT_FOUND",...}}` instead of silently returning 200 with empty data. This covers all project-scoped endpoints (`/api/summary`, `/api/by-agent`, `/api/by-model`, `/api/backend-trend`, `/api/trend`, `/api/highlights`, `/api/reconcile`). The previously dead `ProjectNotFoundError` exception is now raised from `CostService._projects()`.
- Dashboard: the session highlight is labelled "most expensive **session**", not "most expensive ticket". A ticket is mill's unit of work; the underlying field has always been Langfuse's generic `sessionId`, which is a chat conversation for the chat agent and an ingest batch for cognee. Now that discovery is generic, a mill-specific label mislabels every other component's data. The `aggregate_by_session` docstring says the same thing so the next reader doesn't reintroduce it.
- Sync reference docs, ARCHITECTURE.md, and README after analyst removal and registry-driven config: removed stale ProjectConfig/AnalystConfig/analyst content from configuration.md, cli.md, index.md, and api.md; added registry settings (registry_base_url, registry_api_key, registry_poll_interval_seconds); updated ARCHITECTURE.md layout, data-flow, invariants, and loop table for cache.py/metrics.py/registry.py and per-window caches; added GET /metrics to README API table.
- Removed vestigial LLM cost-analyst references from README.md, ARCHITECTURE.md, shared.js (ANALYST_ API constants), index.html (nav link), dashboard.css (comment), and pyproject.toml (mypy override for test_analyst). Updated test comment references and reconcile.py install hint.
- Remove orphaned CostService methods (`candidate_traces`, `trace_detail`, `top_ticket`, `top_stage`) and `ProjectConfigError` exception — all had zero callers after the LLM cost-analyst subsystem removal. Drop hardcoded `projects` field from `GET /health`.
- Dockerfile: remove `--extra analyst` from `uv export` invocations — the `analyst` extra was removed when `robotsix-llmio` became a regular dependency.
- Address review feedback on the registry-based project discovery PR:
  - Clarified that the `except A, B:` exception clauses in `registry.py` and
    `_utils.py` are intentional PEP 758 syntax (Python 3.14 target) that catch
    both exception types, with inline clarifying comments.
  - Removed the unused `cfg` dependency from the `chat_skill` route handler.
- Rewrite `RegistryClient` to match the 7af1 central-deploy schema: `GET /fleet/langfuse`
  with `X-API-Key` auth, parsing `langfuse_host` + `projects[]` (`alias`, `public_key`,
  `secret_key`).  Drop stale analyst endpoints from the `_CHAT_SKILL` docstring.
- Adopt `@robotsix/ui` shared styling base for the dashboard UI.  The
  cost-monitor pages now load the compiled `dist/style.css` (dark theme,
  hue-tinted to match the existing navy palette via `--rsu-dark-hue: 226`
  and `--rsu-dark-saturation: 41%`).  Duplicated base styles (box-sizing
  reset, body typography) are removed from the local `dashboard.css`; only
  cost-monitor-specific component classes remain.
- Extract `TTLCache` into its own module (`src/robotsix_cost_monitor/cache.py`) — the generic stale-while-revalidate cache is now independently importable and testable.
- **Removed** the hardcoded per-project Langfuse credential list from config.  Cost-monitor now discovers projects at runtime from the central-deploy registry (`registry_base_url` + `registry_api_key` settings), so newly-deployed Langfuse-enabled components appear automatically without touching cost-monitor config.
- **Removed** the LLM cost-analyst subsystem entirely — analyst endpoints (`/api/analyst/*`), background analyst scheduler, LLM agent code, chat-skill analyst section, and the `[analyst]` extra dependency.
- **Added** `RegistryClient` in `clients/registry.py` for querying the central-deploy component registry.
- **Changed** `CostService` to accept a `RegistryClient` and populate its project map dynamically via `refresh_projects()`.
- **Changed** config model: `ProjectConfig` and `AnalystConfig` classes removed; `Settings` gains `registry_base_url`, `registry_api_key`, and `registry_poll_interval_seconds`.
- Dashboard cache now covers both window and backend dimensions: all five data kinds (traces, models, backend costs, agent usage, trace counts) are fetched as a unit and cached together, so switching the backend filter never triggers a fresh Langfuse round-trip.  Startup cache warming now pre-fetches all dashboard window presets (1 h, 6 h, 1 d, 1 w) instead of only the default window.
- Added `GET /chat-skill` endpoint returning a Markdown skill document
  describing the HTTP API surface for the robotsix-chat agent (base URL,
  all read endpoints with query parameters, authentication requirements,
  and a safety section marking mutating endpoints as confirmation-gated).
- Document `docs/modules.yaml` file-registration requirement in AGENT.md Testing conventions, so agents register every new source or test file under an appropriate module.
- **Dashboard caching with stale-while-revalidate:** the ``CostService``
  now serves cached cost aggregates immediately while refreshing from
  Langfuse in the background when data is stale.  A periodic cache-warming
  loop (``dashboard_refresh_interval_seconds``, default 120s) keeps
  dashboard aggregates precomputed so the frontend never blocks on a live
  API fetch.  The ``/api/summary`` response includes ``last_updated`` for
  data-freshness visibility, and ``POST /api/refresh`` provides on-demand
  cache invalidation.
- Add `low_balance_threshold_usd` config field (default $5.00) — when the
  OpenRouter account remaining balance drops below this threshold during
  reconciliation, a warning is logged and surfaced in the dashboard via a
  "low bal" pill and the reconcile warning banner.
- Add `exclude-newer = "3 days"` to `[tool.uv]` for supply-chain hardening (cooldown window for newly-published packages).
- Split `tests/robotsix_cost_monitor/test_service.py` (1387 lines) into 7 per-section modules
  (`test_service_edge_cases.py`, `test_service_single_project.py`, `test_service_cache.py`,
  `test_service_cross_project.py`, `test_service_exception_isolation.py`, `test_service_by_agent.py`,
  `test_service_by_agent_segmented.py`) and moved `_svc` / `_model_row` helpers into `helpers.py`.
- Highlights ("most expensive trace" / "most expensive ticket") now respect the
  backend selector. The `/api/highlights` endpoint accepts a `backend` query
  parameter (defaults to `all`), and the dashboard passes the currently selected
  backend so the highlight values stay consistent with the other filtered panels.
- Convert `AnalystKind` from a `Literal` type alias to a `StrEnum` with members `TICKET`, `STAGE`, `FLEET`. All dispatch sites updated to enum comparisons — adding a fourth kind now only requires an enum member and the type checker flags every incomplete dispatch.
- Fix `GET /api/analyst/fleet` always returning `{"generated_at": None}` by reading from `proposals.json` (where `run_analyst()` writes) instead of the never-written `fleet.json`.
- Update `README.md`: correct stale "no robotsix-llmio dependency" claim, add missing `GET /api/analyst/fleet` and `POST /api/analyst/run/fleet` API rows, document `analyst` CLI subcommand.
- Added `"fleet"` handling to the `POST /api/analyst/run/{kind}` route so the API matches the CLI behavior of running the full fleet analyst.  Changed the fallback status code from 404 to 422 for unknown analyst kinds.
- Document the `auth` settings field and its `AuthConfig` sub-fields in the configuration reference (`docs/reference/configuration.md`).
- Added `robotsix_cost_monitor.exceptions` module to API docs (`docs/api.md`).
- Bump `@anthropic-ai/claude-code` in both Dockerfiles from 2.1.199/2.1.158 to 2.1.220 to match `package.json`. Added `ARG CLAUDE_CODE_VERSION` in each Dockerfile so future bumps only need to update the ARG default.
- Remove `--ignore-scripts` from claude-code npm install in `Dockerfile.dev`, matching the production Dockerfile. The `@anthropic-ai/claude-code` 2.x package fetches a native binary during its postinstall script; skipping it breaks `claude --version`.
- Add `@anthropic-ai/claude-code` to `package.json` devDependencies so
  Dependabot's npm ecosystem tracks version bumps for the globally-installed
  CLI in the Dockerfiles.
- Move dashboard bind address from Compose `command:` override into config: added `server_host`/`server_port` settings (defaults `0.0.0.0`/`8080`). The CLI `serve` subcommand reads these from config, with `--host`/`--port` flags retained for overrides. Replaced `${MONITOR_PORT}` env-var port mapping with a fixed `8099:8080` in `docker-compose.yml`.
- Remove stale `::: robotsix_cost_monitor.clients._http` directive from `docs/api.md`; the module was migrated to the shared `robotsix-http` library.
- Fix `log_format` default column in configuration docs: remove non-existent CI-based `"console"` fallback; the code unconditionally defaults to `"json"`.
- Remove unused `logger` variable and `structlog` import from `analyst.py` — the module had no logging calls, so the variable was dead code.
- Add `analyst` CLI subcommand (`robotsix-cost-monitor analyst`) with
  `--kind` option (fleet/ticket/stage/all), mirroring the existing
  reconcile subcommand pattern.
- Fix Docker build failure in the runtime stage: remove `--ignore-scripts` from the `npm install -g` command for `@anthropic-ai/claude-code` so the postinstall script can download the platform-native binary.
- Restore `--ignore-scripts` flag on `npm install -g @anthropic-ai/claude-code` in Dockerfile (lost during version bump).
- Remove dead `security_posture` periodic workflow file (was silently rejected by the loader, not in the workflow catalog).
- Fix high-severity npm audit vulnerability (GHSA-mh99-v99m-4gvg) in brace-expansion transitive dependency by adding an override to pin brace-expansion to >=5.0.8.
- Pass `cfg.settings` to `load_last_reconcile`, `load_proposals`, and `load_targeted_analysis` in the dashboard API routes so they respect a custom `data_dir` setting instead of always reading from `.data/`.
- Thread `settings` through `_last_analyst_run()` so the analyst scheduler's restart-resilience check sees data written to a custom `data_dir`, preventing redundant analysis runs after container restarts.
- `Settings.data_dir` now actually controls the runtime-state directory (was previously declared on the model but ignored — `data_dir()` hardcoded `.data`). The `data_dir()` function accepts an optional `Settings` argument; callers in the analyst and reconciler pipelines now pass `config.settings` so custom `data_dir` paths work end-to-end.
- Enable pytest strictness settings: `--strict-markers`, `--strict-config`, `xfail_strict`, and `filterwarnings = ["error"]` to catch deprecation warnings and marker configuration issues early in CI.
- Fix stale `config/projects.schema.json` references in `.pre-commit-config.yaml` and `Makefile` — both now use the correct `config/config.schema.json` path.
- Add security response headers middleware (`secure`) with a permissive CSP (inline scripts/styles) and standard headers (`X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, HSTS, `Permissions-Policy`).
- **Breaking:** Cut over to `robotsix-standards` config standard — rename config
  file to `config/config.json`, resolve via `ROBOTSIX_CONFIG_FILE` (drop
  `COST_MONITOR_CONFIG`), retype all six secret fields as `pydantic.SecretStr`,
  move `LOG_LEVEL`/`LOG_FORMAT` into the config model, and drop `.env.example`.
  Commit `config/config.schema.json` with CI drift check.
- Merge `config-files` module into `config` module in `docs/modules.yaml` (documentation-only consolidation — no files moved).
- Add `make security` target running `uv audit --frozen` and `zizmor` on GitHub Actions workflows.
- Mark expert-only and rarely-changed config settings as `"advanced": true` in the Pydantic models and regenerated JSON schema, so the central-deploy Configure UI hides them behind its "Show advanced settings" toggle by default.
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
- Update `vulture_whitelist
