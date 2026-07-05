.PHONY: test install install-test install-lint lint typecheck format serve docs clean

install:
	uv sync --locked --all-extras --all-groups

install-test:
	uv sync --locked --group dev

install-lint:
	uv sync --locked --group lint

# `make test` installs dev deps (requires network) then runs pytest.
# For offline/CI use, the mill runs its own `test_command` from
# .robotsix-mill/config.yaml, which uses `--no-sync` against a
# pre-built venv (see Dockerfile.dev).
test: install-test
	uv run --no-sync pytest

lint: install-lint
	uv run pre-commit run --all-files

typecheck: install-lint
	uv run mypy src/

format:
	uv run ruff format src/

serve:
	uv run robotsix-cost-monitor serve --host 127.0.0.1 --port 8099

docs:
	uv run mkdocs serve

clean:
	rm -rf .coverage .mypy_cache .ruff_cache .pytest_cache htmlcov/
