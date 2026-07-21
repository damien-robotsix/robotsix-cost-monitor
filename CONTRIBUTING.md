# Contributing

## Dev setup

```bash
# Clone and install
git clone <repo-url>
cd robotsix-cost-monitor
uv sync --locked

# Create a local config (gitignored — never commit real keys)
cp config/projects.example.json config/projects.json
# Edit config/projects.json and fill in your Langfuse keys
```

The project targets **Python ≥ 3.14**. Dependency management uses
[uv](https://docs.astral.sh/uv/); the lockfile (`uv.lock`) is committed.

### Optional: analyst extra

The LLM cost-analyst requires additional packages:

```bash
uv sync --locked --extra analyst
```

Without this extra, the dashboard, reconciliation, and CLI commands still
work — only the `/api/analyst/*` endpoints are unavailable.

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
2. Make your changes. Add or update tests to cover new behaviour.
3. Run the full check suite locally:
   ```bash
   uv run ruff check . && uv run ruff format --check .
   uv run mypy src/
   uv run pytest
   ```
4. Push and open a PR. CI will run the full matrix.
5. If you touched files outside `tests/`, `.github/`, or `CHANGELOG.md`,
   add a changelog entry under `## [Unreleased]` with the appropriate category header (`### Added`, `### Changed`, `### Fixed`, etc.) in `CHANGELOG.md`. Release-please will later categorize and move entries into versioned sections.

## Git-dependency upgrade process

The `analyst` extra pins a private git dependency with exact commit
SHAs:

- `robotsix-llmio` (LLM agent framework)

To upgrade it to a newer revision:
1. Update the commit SHA in the `[project.optional-dependencies]` table of
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
