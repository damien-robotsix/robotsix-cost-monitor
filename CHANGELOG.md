## [0.3.0](https://github.com/damien-robotsix/robotsix-cost-monitor/compare/v0.2.0...v0.3.0) (2026-08-09)


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
* **auth:** add config-driven HTTP Basic auth for gateway exposure ([#380](https://github.com/damien-robotsix/robotsix-cost-monitor/issues/380)) ([0b3565f](https://github.com/damien-robotsix/robotsix-cost-monitor/commit/0b3565f3955ef75d82f824f9b1913fb70041e596))
* **config:** expose the standard config HTTP surface ([#459](https://github.com/damien-robotsix/robotsix-cost-monitor/issues/459)) ([dc0f625](https://github.com/damien-robotsix/robotsix-cost-monitor/commit/dc0f625aeb3c03d6d678bd296238510605f4e9f2))
* daily auto-reconciliation + dashboard warning banner ([#58](https://github.com/damien-robotsix/robotsix-cost-monitor/issues/58)) ([af36a83](https://github.com/damien-robotsix/robotsix-cost-monitor/commit/af36a839d520cb783cc6875dfb58de3db2d2ca53))
* Dockerize + continuous-deploy stack ([#1](https://github.com/damien-robotsix/robotsix-cost-monitor/issues/1)) ([e8be9d2](https://github.com/damien-robotsix/robotsix-cost-monitor/commit/e8be9d255db99db046fbd3785559c3b1586f7e17))
* filter by backend (OpenRouter vs ClaudeSDK) ([#4](https://github.com/damien-robotsix/robotsix-cost-monitor/issues/4)) ([4ad3be7](https://github.com/damien-robotsix/robotsix-cost-monitor/commit/4ad3be7b9792637e0ebfd2dee77d8850ea236735))
* group discovered projects by owning component ([#431](https://github.com/damien-robotsix/robotsix-cost-monitor/issues/431)) ([93246c0](https://github.com/damien-robotsix/robotsix-cost-monitor/commit/93246c062474819fb5788d53184f5ed1ff926b39))
* **mill:** enable the credit_balance periodic pass ([#465](https://github.com/damien-robotsix/robotsix-cost-monitor/issues/465)) ([913cf34](https://github.com/damien-robotsix/robotsix-cost-monitor/commit/913cf34a6feb69789f22ce47fb7183aaf845786e))
* per-model cost breakdown on the dashboard ([#3](https://github.com/damien-robotsix/robotsix-cost-monitor/issues/3)) ([98130a2](https://github.com/damien-robotsix/robotsix-cost-monitor/commit/98130a2c55cb3a93ac3b21b31a8e68adaa29058e))
* reconcile on per-key OpenRouter usage, not account credits ([#7](https://github.com/damien-robotsix/robotsix-cost-monitor/issues/7)) ([a655387](https://github.com/damien-robotsix/robotsix-cost-monitor/commit/a6553876da18abfb7df2abce554a955261a840cb))
* robotsix-cost-monitor — multi-Langfuse cost dashboard + reconciliation + cost-analyst ([5033d33](https://github.com/damien-robotsix/robotsix-cost-monitor/commit/5033d33fe05d4aa67537158dd37edfdfd68838e1))
* **web:** cost-analyst page — trigger + last-run traces/proposals/ticket ([#57](https://github.com/damien-robotsix/robotsix-cost-monitor/issues/57)) ([f89fb09](https://github.com/damien-robotsix/robotsix-cost-monitor/commit/f89fb097015f1fe4a5ef2876d05468bbf7987ef0))


### Bug Fixes

* **analyst:** migrate to llmio's get_provider_for_identifier API ([#95](https://github.com/damien-robotsix/robotsix-cost-monitor/issues/95)) ([5a06f96](https://github.com/damien-robotsix/robotsix-cost-monitor/commit/5a06f96f3b1ecf67feaf85a0409e593208333031))
* **analyst:** resume the daily cadence across restarts instead of resetting it ([#97](https://github.com/damien-robotsix/robotsix-cost-monitor/issues/97)) ([5ab62cc](https://github.com/damien-robotsix/robotsix-cost-monitor/commit/5ab62cc8df8fcff0590f72b7ef7465e25bf548b8))
* **analyst:** return text JSON from L2 (DeepSeek thinking rejects tool_choice) ([#44](https://github.com/damien-robotsix/robotsix-cost-monitor/issues/44)) ([3d1fe1f](https://github.com/damien-robotsix/robotsix-cost-monitor/commit/3d1fe1ff24cdcfe75827416d3a75ee59994982dd))
* **analyst:** use the openrouter-deepseek provider with a valid L3 model ([#43](https://github.com/damien-robotsix/robotsix-cost-monitor/issues/43)) ([b8175fa](https://github.com/damien-robotsix/robotsix-cost-monitor/commit/b8175fa627c5d467786f59cc98bad31e2e5bbb75))
* **ci:** grant security-events:write so the Release workflow can start ([#383](https://github.com/damien-robotsix/robotsix-cost-monitor/issues/383)) ([1cd5f77](https://github.com/damien-robotsix/robotsix-cost-monitor/commit/1cd5f777f517f8d5fd4f6a7ced2c51731b8f4581))
* **ci:** grant the Docs caller the Pages-Actions permissions ([#458](https://github.com/damien-robotsix/robotsix-cost-monitor/issues/458)) ([614bb53](https://github.com/damien-robotsix/robotsix-cost-monitor/commit/614bb5327a2a239b7319437cfc9a48001196a095))
* **ci:** repair Release workflow start-up failure (reusable SBOM permissions) ([#381](https://github.com/damien-robotsix/robotsix-cost-monitor/issues/381)) ([c37ae0d](https://github.com/damien-robotsix/robotsix-cost-monitor/commit/c37ae0d48455280d25ebc26537bbdd64c63408d6))
* **dashboard:** label the session highlight "session", not "ticket" ([#434](https://github.com/damien-robotsix/robotsix-cost-monitor/issues/434)) ([ef37554](https://github.com/damien-robotsix/robotsix-cost-monitor/commit/ef375540a216ed6d74fa9366483b4e9b8dc4b1fb))
* **deploy:** conform deploy compose to the central-deploy gateway contract ([#385](https://github.com/damien-robotsix/robotsix-cost-monitor/issues/385)) ([e6316b0](https://github.com/damien-robotsix/robotsix-cost-monitor/commit/e6316b01448809b10a4cf47f1e70fd914d0dc20f))
* **deps:** bump nanoid to 3.3.17 for GHSA-2v37-7h3g-55p8 ([#460](https://github.com/damien-robotsix/robotsix-cost-monitor/issues/460)) ([a605aa4](https://github.com/damien-robotsix/robotsix-cost-monitor/commit/a605aa47b494cce985b973bfd4787695452e7a7c))
* **deps:** bump robotsix-llmio to main (restores AsyncLangfuseReadClient) ([#94](https://github.com/damien-robotsix/robotsix-cost-monitor/issues/94)) ([f53b9b4](https://github.com/damien-robotsix/robotsix-cost-monitor/commit/f53b9b478cf57599f8b61e622e5f655315027bf0))
* **docker:** install claude-code without --ignore-scripts (native binary) ([#384](https://github.com/damien-robotsix/robotsix-cost-monitor/issues/384)) ([98aaad6](https://github.com/damien-robotsix/robotsix-cost-monitor/commit/98aaad617ba401cc5891505148b37be454c6d198))
* **docker:** install git in the builder for the analyst extra's git deps ([#19](https://github.com/damien-robotsix/robotsix-cost-monitor/issues/19)) ([9f94ce1](https://github.com/damien-robotsix/robotsix-cost-monitor/commit/9f94ce1d3ca1573a13287b571a9da9f528d2504e))
* **memory:** stop caching full Langfuse trace payloads ([#430](https://github.com/damien-robotsix/robotsix-cost-monitor/issues/430)) ([c8c3386](https://github.com/damien-robotsix/robotsix-cost-monitor/commit/c8c3386408a2658e3139e8757ffa0be287744d89))
* **reconcile:** compare OpenRouter spend against openrouter-backend traced cost ([#27](https://github.com/damien-robotsix/robotsix-cost-monitor/issues/27)) ([01bd9e8](https://github.com/damien-robotsix/robotsix-cost-monitor/commit/01bd9e8d13f2798f7fdaa9066e4a362ba8d1b712))
* **reconcile:** derive remaining balance instead of reading a field that does not exist ([#433](https://github.com/damien-robotsix/robotsix-cost-monitor/issues/433)) ([08504f4](https://github.com/damien-robotsix/robotsix-cost-monitor/commit/08504f411c9ad882f9a956b0edfcdffdd2254aad))
* **reconcile:** show the last reconcile on page load, not just drift warnings ([#98](https://github.com/damien-robotsix/robotsix-cost-monitor/issues/98)) ([1512090](https://github.com/damien-robotsix/robotsix-cost-monitor/commit/151209091adf787f121047d904e71610f01b076c))
* **reconcile:** trace cost over the exact snapshot interval ([#9](https://github.com/damien-robotsix/robotsix-cost-monitor/issues/9)) ([8fa77db](https://github.com/damien-robotsix/robotsix-cost-monitor/commit/8fa77dbd3036daf57090675d8c5b616b3ca8713c))
* **release:** align release-please with the fleet ([#466](https://github.com/damien-robotsix/robotsix-cost-monitor/issues/466)) ([590b968](https://github.com/damien-robotsix/robotsix-cost-monitor/commit/590b968e4a3c73f570749d29c6d65ef6e19c040c))
* **web:** consistent per-analysis 'analyze' buttons on /analyst ([#63](https://github.com/damien-robotsix/robotsix-cost-monitor/issues/63)) ([824c6fe](https://github.com/damien-robotsix/robotsix-cost-monitor/commit/824c6fefe2c78dca57655569b862ea09364a6f4d))
* window-accurate per-model/backend cost (was day-granular & over-counting) ([#6](https://github.com/damien-robotsix/robotsix-cost-monitor/issues/6)) ([266cf12](https://github.com/damien-robotsix/robotsix-cost-monitor/commit/266cf12f8faf56cdde49d20feaaa53fdfc88a0f7))


### Performance Improvements

* **summary:** count traces via metrics, not by paging them all ([#96](https://github.com/damien-robotsix/robotsix-cost-monitor/issues/96)) ([e5e1f7f](https://github.com/damien-robotsix/robotsix-cost-monitor/commit/e5e1f7f314ea63adab569d335dd34dd3c55f9cf5))


### Documentation

* **chat-skill:** document component-level scoping ([#432](https://github.com/damien-robotsix/robotsix-cost-monitor/issues/432)) ([93a883b](https://github.com/damien-robotsix/robotsix-cost-monitor/commit/93a883be1b9213c5f5d2b7dfdadb07dca5803cb7))

## Pre-release-please history

Everything below predates the release-please migration and was
maintained by hand or by towncrier. It is kept verbatim; new entries
are added above by release-please.

## [0.6.1](https://github.com/damien-robotsix/robotsix-cost-monitor/compare/v0.6.0...v0.6.1) (2026-09-03)


### Documentation

* Document frontend CI requirements and troubleshooting for developers (20260831T132119Z-document-frontend-ci-requirements-and-tr-3c00) ([#526](https://github.com/damien-robotsix/robotsix-cost-monitor/issues/526)) ([437928a](https://github.com/damien-robotsix/robotsix-cost-monitor/commit/437928acae0031234e6f3800c94163caa23f3e67))

## [0.6.0](https://github.com/damien-robotsix/robotsix-cost-monitor/compare/v0.5.1...v0.6.0) (2026-08-23)


### Features

* Adopt the shared AppShell navigation and align @robotsix/ui to v0.1.40 (cost-monitor) (20260823T113727Z-adopt-the-shared-appshell-navigation-and-d106) ([#515](https://github.com/damien-robotsix/robotsix-cost-monitor/issues/515)) ([97790f3](https://github.com/damien-robotsix/robotsix-cost-monitor/commit/97790f3daa38f3eb9a604f42d300ad99182ddf86))
* Config field subscription_call_cap is declared but never consumed — remove or implement the volume-vs-cap monitoring logic (20260817T222631Z-config-field-subscription-call-cap-is-de-0d40) ([#506](https://github.com/damien-robotsix/robotsix-cost-monitor/issues/506)) ([84556d7](https://github.com/damien-robotsix/robotsix-cost-monitor/commit/84556d7dd7ee36fa6e1f49c3529b17f60e2eea8b))
* Cost-monitor should detect and report stalled pending tickets (20260816T203446Z-cost-monitor-should-detect-and-report-st-35e7) ([#508](https://github.com/damien-robotsix/robotsix-cost-monitor/issues/508)) ([492cc2b](https://github.com/damien-robotsix/robotsix-cost-monitor/commit/492cc2b36284a3b4f2a6f2a18bd2e03023e2d7fb))

## [0.5.1] (2026-08-16)

### Features

* **stuck-tickets:** add mill board client, background loop, Prometheus metrics, and `GET /api/stuck-tickets` endpoint to detect tickets stuck in non-terminal states ([#](https://github.com/damien-robotsix/robotsix-cost-monitor/issues/))

### Bug Fixes

* CI red on main: 'JavaScript tests' job fails at npm audit --audit-level=high (high-severity JS dependency vulnerability) (20260816T213004Z-ci-red-on-main-javascript-tests-job-fail-a5e7) ([#498](https://github.com/damien-robotsix/robotsix-cost-monitor/issues/498)) ([18804f5](https://github.com/damien-robotsix/robotsix-cost-monitor/commit/18804f5c260446ef57ab8248bfc6a2fe2aa4adf7))

## [0.5.0](https://github.com/damien-robotsix/robotsix-cost-monitor/compare/v0.4.0...v0.5.0) (2026-08-10)


### Features

* Clean up stale AgentRow JSDoc properties in dashboard.js (20260808T183618Z-clean-up-stale-agentrow-jsdoc-properties-6098) ([#482](https://github.com/damien-robotsix/robotsix-cost-monitor/issues/482)) ([04338c6](https://github.com/damien-robotsix/robotsix-cost-monitor/commit/04338c618f00b339232a196f0224267560d52fda))
* Consume session_cost_scope in dashboard.js renderHighlights() to label filtered session highlight (20260809T092510Z-consume-session-cost-scope-in-dashboard-af6d) ([#475](https://github.com/damien-robotsix/robotsix-cost-monitor/issues/475)) ([b5a9100](https://github.com/damien-robotsix/robotsix-cost-monitor/commit/b5a9100eac668a08721309b42f8af7b92c311c09))


### Bug Fixes

* Implement GET /readyz readiness probe route (20260810T043440Z-implement-get-readyz-readiness-probe-rou-14bf) ([#486](https://github.com/damien-robotsix/robotsix-cost-monitor/issues/486)) ([90db988](https://github.com/damien-robotsix/robotsix-cost-monitor/commit/90db988cf92d02234cea8dbf2f96f4dfebd353a5))


### Documentation

* Document ?backend= on GET /api/highlights in _CHAT_SKILL docstring (20260810T025923Z-document-backend-on-get-api-highlights-i-fafe) ([#485](https://github.com/damien-robotsix/robotsix-cost-monitor/issues/485)) ([6adbc39](https://github.com/damien-robotsix/robotsix-cost-monitor/commit/6adbc393c4f7699bec4dbe0a3a007c484705fcbf))
* Document ?backend= on GET /api/summary in _CHAT_SKILL docstring (20260809T093913Z-document-backend-on-get-api-summary-in-c-ac96) ([#483](https://github.com/damien-robotsix/robotsix-cost-monitor/issues/483)) ([876f225](https://github.com/damien-robotsix/robotsix-cost-monitor/commit/876f22574685ca437ca8edac7f0727960d6ebfe4))
* Document /readyz in _CHAT_SKILL health table (20260809T151733Z-document-readyz-in-chat-skill-health-tab-06be) ([#484](https://github.com/damien-robotsix/robotsix-cost-monitor/issues/484)) ([ade3a29](https://github.com/damien-robotsix/robotsix-cost-monitor/commit/ade3a292000690ded22cf284311e0389b099b430))
* Fix AGENT.md stale references to non-existent tests/conftest.py (20260807T092408Z-fix-agent-md-stale-references-to-non-exi-9a26) ([#480](https://github.com/damien-robotsix/robotsix-cost-monitor/issues/480)) ([40cbcd8](https://github.com/damien-robotsix/robotsix-cost-monitor/commit/40cbcd8ab5a6fadd580baa9e68a6816096e495c5))

## [0.4.0](https://github.com/damien-robotsix/robotsix-cost-monitor/compare/v0.3.1...v0.4.0) (2026-08-09)


### Features

* Dashboard: show per-component cost breakdown when a backend filter is active with scope=all (20260808T185717Z-dashboard-show-per-component-cost-breakd-9d3f) ([#474](https://github.com/damien-robotsix/robotsix-cost-monitor/issues/474)) ([f5dbb84](https://github.com/damien-robotsix/robotsix-cost-monitor/commit/f5dbb8427761d73cfc1a24f789455b5706636984))
* Highlights (most expensive trace/session) still ignore backend filter after 86e8 fix (20260808T185116Z-highlights-most-expensive-trace-session-8ce5) ([#470](https://github.com/damien-robotsix/robotsix-cost-monitor/issues/470)) ([4f1d677](https://github.com/damien-robotsix/robotsix-cost-monitor/commit/4f1d677ccc7ef2f5c96951c0d7d2a1e747d9af08))


### Bug Fixes

* **ci:** bump the CodeQL pin so the workflow can start ([#471](https://github.com/damien-robotsix/robotsix-cost-monitor/issues/471)) ([49c7edb](https://github.com/damien-robotsix/robotsix-cost-monitor/commit/49c7edb37f36321d56c29924052fecd30e3a3be4))
* **release:** don't fail lock-sync when the release branch is gone ([#473](https://github.com/damien-robotsix/robotsix-cost-monitor/issues/473)) ([e6a6b87](https://github.com/damien-robotsix/robotsix-cost-monitor/commit/e6a6b87f5a22aadbf03ef9393b3f3be877b2f30b))

## [0.3.1](https://github.com/damien-robotsix/robotsix-cost-monitor/compare/v0.3.0...v0.3.1) (2026-08-09)


### Documentation

* **changelog:** put the newest release at the top ([#468](https://github.com/damien-robotsix/robotsix-cost-monitor/issues/468)) ([02c0976](https://github.com/damien-robotsix/robotsix-cost-monitor/commit/02c0976a591c92a54dc084b5dd83df37dd1777ca))

### 0.0.0 (unreleased, pre-release-please)

- Remove dead `LangfuseClient.fetch_trace_detail` method and its unit test; the method had no production callers and was a thin delegation wrapper over `AsyncLangfuseReadClient.fetch_trace_detail`.
- Removed orphaned `LangfuseClient.fetch_trace_detail` method (no production consumer since the `CostService.trace_detail` removal).
- Convert `docs/api.md` from MyST `{eval-rst}` fences to mkdocstrings native `:::` directive syntax, fixing broken API reference page rendering.
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
## 0.2.0 (2026-08-09)

### Features

- Expose the standard config HTTP surface required by `config-ownership.md`: `GET /config` (effective config with secrets masked, plus schema and version), `PUT /config` (partial update, validated and recorded as a new version), `GET /config/versions`, and `POST /config/rollback`. All four delegate to `robotsix_config.history`, so the version history lives in a `config.json.versions` sidecar beside the config file and secret values are never written to it. (config-http-surface)
- Commit a safe-default `config/config.json` (secrets empty) to seed the deploy plane's first deploy, and add a `/settings` page that mounts the `@robotsix/ui` config panel for runtime config editing with typed inputs, secret masking, and version history. (20260802T192013Z-implement-the-standard-config-surface-an-861e)

### Bugfixes

- Fixed the Docs workflow, which had never run. The caller granted `contents:
  write` — the shape `mkdocs gh-deploy` needs — but the shared docs spine deploys
  through the Pages Actions and requires `contents: read` plus `pages: write` and
  `id-token: write`. All three were unmet, and an unmet request fails the run at
  startup with no logs and no checks. (docs-pages-permissions)
- Bump the transitive `nanoid` dev dependency to 3.3.17, clearing GHSA-2v37-7h3g-55p8 (custom generators can loop indefinitely when size is zero), which was failing `npm audit --audit-level=high` in CI. (nanoid-advisory)
- Fix release Docker build: update package-lock.json to pin @robotsix/ui to v0.1.6 so dist/vanilla.js is present after npm ci. (20260808T142418Z-ci-failure-release-on-main-077c)

### Deprecations and Removals

- Dashboard stage breakdown, highlights, and total card now all honor the shared backend filter. Removed the marginal/subscription two-column design from the stage table; it now uses a single cost column. `/api/by-agent-segmented` endpoint and related UI, service method, and aggregation function have been removed. (20260807T220028Z-dashboard-backend-filter-not-applied-to-86e8)

### Misc

- 20260807T021237Z-robotsix-cost-monitor-enable-credit-bala-218e


<!-- markdownlint-disable MD013 -->
