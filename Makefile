.PHONY: test install install-test install-lint lint typecheck format serve docs clean schema verify-schema security

install:
	UV_MALWARE_CHECK=1 uv sync --locked --all-extras --all-groups

install-test:
	UV_MALWARE_CHECK=1 uv sync --locked --group dev

install-lint:
	UV_MALWARE_CHECK=1 uv sync --locked --group lint

# `make test` installs dev deps (requires network) then runs pytest.
# For offline/CI use, the mill runs its own `test_command` from
# .robotsix-mill/config.yaml, which uses `--no-sync` against a
# pre-built venv (see Dockerfile.dev).
test: install-test
	uv run --no-sync pytest --cov=robotsix_cost_monitor --cov-report=term-missing

lint: install-lint
	uv run pre-commit run --all-files

typecheck: install-lint
	uv run mypy src/ tests/

format:
	uv run ruff format src/

serve:
	uv run robotsix-cost-monitor serve --host 127.0.0.1 --port 8099

docs:
	uv run mkdocs serve

schema:
	uv run python scripts/generate_config_schema.py

verify-schema: schema
	@if ! git diff --exit-code config/config.schema.json; then \
		echo "ERROR: config/config.schema.json is stale — run 'make schema' and commit the result."; \
		exit 1; \
	fi

security:
	uv audit --frozen
	uvx zizmor --min-severity medium .github/workflows/

clean:
	rm -rf .coverage .mypy_cache .ruff_cache .pytest_cache htmlcov/
