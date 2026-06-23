## 0.0.0 (unreleased)

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
