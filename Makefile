.PHONY: test install

install:
	uv sync --locked --all-extras

test: install
	uv run pytest
