# Contributing

## Dev setup

```bash
# Clone and install
git clone <repo-url>
cd robotsix-cost-monitor
uv sync --locked

# Create a local config (gitignored — never commit real keys)
cp config/config.example.json config/config.json
# Edit config/config.json and fill in your Langfuse keys
```

The project targets **Python ≥ 3.14**. Dependency management uses
[uv](https://docs.astral.sh/uv/); the lockfile (`uv.lock`) is committed.



## Running tests

```bash
uv run pytest                              # Python tests
uv run vitest run                          # Frontend JS tests (Vitest)
```

Coverage is enforced at ≥ 80% branch coverage. Run with:

```bash
uv run pytest --cov=src --cov-report=term-missing
```

## Lint, format, type-check

```bash
uv run ruff check .                        # Lint
uv run ruff format --check .               # Format check
uv run mypy src/                           # Type-check
uv run vulture src/ vulture_whitelist.py   # Dead-code analysis
```

CI runs all of these on every PR. Fix issues before pushing.

## Frontend CI checks

The frontend code (`src/robotsix_cost_monitor/web/static/` and its tests
under `tests/robotsix_cost_monitor/web/static/`) is guarded by a dedicated
CI job, **JavaScript tests** (job id `js-tests` in
`.github/workflows/ci.yml`). This job is a **required status check**: it runs
on every PR and **blocks merge** if any of its three checks fail.

### What is checked

| Check | npm script | Tool | What it does |
| --- | --- | --- | --- |
| Unit tests | `npm run test` | [Vitest](https://vitest.dev/) | Runs the frontend unit test suite |
| Type-checking | `npm run typecheck` | [TypeScript (`tsc`)](https://www.typescriptlang.org/docs/) | `tsc --noEmit` against `jsconfig.json` — no runtime output, types only |
| Linting | `npm run lint` | [Biome](https://biomejs.dev/) | Lints and format-checks the frontend sources |

> In CI the job runs `npm run coverage` (Vitest with coverage) and
> `npm run lint:ci` (`biome ci`, the non-writing CI variant); locally the
> `test` and `lint` scripts above cover the same ground.

### Running the checks locally

Install the Node toolchain once (Node ≥ 22, as pinned by `.nvmrc`), then:

```bash
npm ci                 # install pinned dependencies (first time / after lockfile changes)

npm run test           # Vitest unit tests
npm run typecheck      # tsc --noEmit type-checking
npm run lint           # Biome lint + format check
```

Run all three before pushing to reproduce the CI job locally.

### Fixing common failures

- **Test failures (`npm run test`)** — Vitest prints the failing test name,
  the expected vs. received values, and a stack trace. Reproduce a single
  file with `npx vitest run <path>` (or drop `run` for watch mode). Fix the
  code or update the test expectation, then re-run. See the
  [Vitest docs](https://vitest.dev/guide/).

- **Type errors (`npm run typecheck`)** — `tsc` reports the file, line, and a
  `TS####` code (e.g. `TS2339: Property 'foo' does not exist on type 'Bar'`).
  Add or correct the type annotation, narrow the value, or fix the typo it
  points at. See the
  [TypeScript handbook](https://www.typescriptlang.org/docs/).

- **Lint violations (`npm run lint`)** — Biome reports the rule id and the
  offending span. Many issues (formatting, import order, simple lint fixes)
  are auto-fixable — run `npm run format` (`biome check --write`) to apply
  them, then re-run `npm run lint` to confirm. See the
  [Biome docs](https://biomejs.dev/guides/getting-started/).

## Commit messages

We follow [Conventional Commits](https://www.conventionalcommits.org/)
(`feat:`, `fix:`, `chore:`, `docs:`, `refactor:`, `test:`, `ci:`, etc.).
release-please parses these for automated changelog generation and semver
version bumps. Breaking changes should include a `BREAKING CHANGE:` footer
or append `!` to the type (e.g. `feat!: ...`).

A `commit-msg` hook is available via pre-commit to validate messages
locally. See `.pre-commit-config.yaml` for the `conventional-pre-commit`
hook.

## PR workflow

1. Create a feature branch off `main`.

> **Manual releases:** The Release Please workflow can also be triggered
> manually from the GitHub Actions UI (`Actions` → `Release Please` →
> `Run workflow`). This is useful for testing or forcing a release without
> pushing to `main`.

1. Make your changes. Add or update tests to cover new behaviour.
2. Run the full check suite locally:

   ```bash
   uv run ruff check . && uv run ruff format --check .
   uv run mypy src/
   uv run pytest
   ```

3. Push and open a PR. CI will run the full matrix.
4. Commit subjects and PR titles must be conventional (`feat:`/`fix:`/`chore:`/`docs:`/`refactor:`/`test:`/`ci:`); release-please generates `CHANGELOG.md` automatically. Do **not** manually edit `CHANGELOG.md` — it is managed entirely by release-please.

## Git-dependency upgrade process

`robotsix-llmio` (LLM agent framework) is a regular git dependency pinned
with exact commit SHAs in `pyproject.toml`.

To upgrade it to a newer revision:

1. Update the commit SHA in the `[project.dependencies]` table of
   `pyproject.toml`.
2. Remove the git dependency line **temporarily** from `pyproject.toml`
   and its `[tool.uv.sources]` block (if present), then run:

   ```bash
   uv lock
   ```

   (The sandbox has no GitHub credentials, so `uv lock` fails with a git
   credential error if the git dependency is present. The lockfile generated
   without it is fine for local dev.)
3. Restore the git dependency lines in `pyproject.toml`.
4. Commit the updated `pyproject.toml` and `uv.lock`.

A human with GitHub credentials must run `uv lock` with the git dependency
present and commit the final lockfile before the change lands on `main`.

## Code conventions

- **Logging** goes through `robotsix_llmio.logging.setup_logging` (called in
  `app.py`). Do not add a second logging framework.
- **Config loading** uses `robotsix_config.load_config(Config, path=...)` with
  Pydantic validation. Do not add a second config loader.
- **Langfuse transport** goes through `robotsix_cost_monitor.clients.langfuse.LangfuseClient`.
  Do not instantiate a second Langfuse client or call the REST API directly.
- **Public API symbols** (functions, classes, parameters) should not be
  renamed without updating all call-sites and the changelog.
- **Python syntax** targets 3.14+ — comma-separated exception types (tuple syntax)
  are the norm (`except ValueError, TypeError:`).
