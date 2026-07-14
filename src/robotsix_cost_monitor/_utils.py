"""Shared internal utilities — keep lean; prefer not to grow this module."""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast


def safe_load_json[T](path: Path, default: T) -> T:
    """Load and parse ``path`` as JSON, returning *default* on any error.

    Catches ``FileNotFoundError`` (via ``.exists()`` returning ``False``),
    ``json.JSONDecodeError``, and most ``OSError`` subclasses during the
    read.  ``PermissionError`` raised by ``.exists()`` itself is NOT caught
    — it propagates to the caller.
    """
    if not path.exists():
        return default
    try:
        return cast(T, json.loads(path.read_text()))
    except (json.JSONDecodeError, OSError):
        return default
