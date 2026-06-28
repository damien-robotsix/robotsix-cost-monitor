.PHONY: test install lint typecheck format serve docs clean

install:
	uv sync --locked --all-extras

test: install
	uv run pytest

lint:
	uv run pre-commit run --all-files

typecheck:
	uv run mypy src/

format:
	uv run ruff format src/

serve:
	uv run robotsix-cost-monitor serve --host 127.0.0.1 --port 8099

docs:
	uv run mkdocs serve

clean:
	rm -rf .coverage .mypy_cache .ruff_cache .pytest_cache htmlcov/
