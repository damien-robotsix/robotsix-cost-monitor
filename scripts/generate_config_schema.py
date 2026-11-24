#!/usr/bin/env python3
"""Regenerate config/config.schema.json from Pydantic models.

Usage:
    python scripts/generate_config_schema.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Add src/ to the path so the models are importable
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from robotsix_cost_monitor.config import Config

ROOT = Path(__file__).resolve().parents[1]


def check_config_parity() -> None:
    """Fail if the tracked and example configs expose different settings keys.

    Pydantic defaults silently mask config-surface drift at runtime (a missing
    key loads fine), so this enforces the AGENT.md invariant that every config
    field flows through to the tracked template. Both CI (config-schema job)
    and the pre-commit config-schema hook run this script, so both catch drift.
    """
    tracked = json.loads((ROOT / "config" / "config.json").read_text())["settings"]
    example = json.loads((ROOT / "config" / "config.example.json").read_text())[
        "settings"
    ]
    tracked_keys, example_keys = set(tracked), set(example)
    if tracked_keys != example_keys:
        raise SystemExit(
            "config/config.json settings keys differ from config/config.example.json\n"
            f"  only in example: {sorted(example_keys - tracked_keys)}\n"
            f"  only in config.json: {sorted(tracked_keys - example_keys)}"
        )


check_config_parity()

schema = Config.model_json_schema()
schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"

out = ROOT / "config" / "config.schema.json"
out.write_text(json.dumps(schema, indent=2) + "\n")
print(f"Schema written to {out}")
