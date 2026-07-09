#!/usr/bin/env python3
"""Standalone vendored validator for docs/modules.yaml.

Uses only pyyaml and jsonschema — no other dependencies.
Called as a fallback when robotsix-modules-validate is not available.

Usage:
  python scripts/validate_modules.py docs/modules.yaml
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator


def _load_yaml(path: Path) -> dict:
    """Load a YAML file as a dict.

    Raises FileNotFoundError or yaml.YAMLError on failure.
    """
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _validate(taxonomy: dict, schema: dict) -> list[str]:
    """Validate *taxonomy* against *schema* and return error messages."""
    validator = Draft202012Validator(schema)
    errors = sorted(
        validator.iter_errors(taxonomy), key=lambda e: list(e.absolute_path)
    )
    messages: list[str] = []
    for error in errors:
        parts: list[str] = []
        for token in error.absolute_path:
            if isinstance(token, int):
                parts.append(f"[{token}]")
            elif parts:
                parts.append(f".{token}")
            else:
                parts.append(str(token))
        pointer = "".join(parts) or "<root>"
        messages.append(f"{pointer}: {error.message}")
    return messages


def main() -> None:
    """Validate a modules.yaml file against the vendored JSON Schema."""
    if len(sys.argv) < 2:
        print("Usage: validate_modules.py <path/to/modules.yaml>", file=sys.stderr)
        sys.exit(2)

    taxonomy_path = Path(sys.argv[1])
    schema_path = Path(__file__).resolve().parent / "modules.schema.yaml"

    if not schema_path.exists():
        print(f"Schema file not found: {schema_path}", file=sys.stderr)
        sys.exit(2)

    try:
        taxonomy = _load_yaml(taxonomy_path)
    except FileNotFoundError:
        print(f"File not found: {taxonomy_path}", file=sys.stderr)
        sys.exit(2)
    except yaml.YAMLError as exc:
        print(f"Invalid YAML in {taxonomy_path}: {exc}", file=sys.stderr)
        sys.exit(2)

    try:
        schema = _load_yaml(schema_path)
    except yaml.YAMLError as exc:
        print(f"Invalid YAML in schema {schema_path}: {exc}", file=sys.stderr)
        sys.exit(2)

    errors = _validate(taxonomy, schema)
    if errors:
        for msg in errors:
            print(msg, file=sys.stderr)
        sys.exit(1)

    sys.exit(0)


if __name__ == "__main__":
    main()
