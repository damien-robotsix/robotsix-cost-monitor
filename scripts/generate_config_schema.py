#!/usr/bin/env python3
"""Regenerate config/projects.schema.json from Pydantic models.

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

schema = Config.model_json_schema()
schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"

out = Path(__file__).resolve().parents[1] / "config" / "projects.schema.json"
out.write_text(json.dumps(schema, indent=2) + "\n")
print(f"Schema written to {out}")
