"""Tests for shared internal utilities — ``_utils.py``."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from robotsix_cost_monitor import analyst as analyst_mod
from robotsix_cost_monitor._utils import safe_load_json

# ---------------------------------------------------------------------------
# safe_load_json — core function
# ---------------------------------------------------------------------------


def test_safe_load_json_valid(tmp_path: Path) -> None:
    """safe_load_json returns parsed JSON for a valid file."""
    path = tmp_path / "data.json"
    path.write_text('{"key": [1, 2, 3]}')
    result: dict[str, Any] = safe_load_json(path, default={})
    assert result == {"key": [1, 2, 3]}


def test_safe_load_json_missing(tmp_path: Path) -> None:
    """safe_load_json returns the default when the file is absent."""
    path = tmp_path / "not_there.json"
    result = safe_load_json(path, default={"fallback": True})
    assert result == {"fallback": True}


def test_safe_load_json_corrupt(tmp_path: Path) -> None:
    """safe_load_json returns the default on corrupt JSON."""
    path = tmp_path / "bad.json"
    path.write_text("not json {{{")
    result = safe_load_json(path, default=42)
    assert result == 42


def test_safe_load_json_permission_error_propagates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """OSError raised by Path.exists() propagates (not caught by the except)."""
    path = tmp_path / "unreachable.json"
    # Simulate a permission error during existence check.
    monkeypatch.setattr(
        Path, "exists", lambda self: (_ for _ in ()).throw(PermissionError)
    )
    with pytest.raises(PermissionError):
        safe_load_json(path, default=None)


# ---------------------------------------------------------------------------
# analyst call-sites — load_proposals / load_targeted_analysis
# ---------------------------------------------------------------------------


def test_load_proposals_corrupt(
    tmp_path: Path,
) -> None:
    """load_proposals returns default when proposals.json is corrupt."""
    d = tmp_path / "analyst"
    d.mkdir()
    (d / "proposals.json").write_text("not json {{{")
    result = analyst_mod.load_proposals(tmp_path)
    assert result == {"generated_at": None, "proposals": []}


def test_load_proposals_permission_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """load_proposals lets PermissionError propagate (not caught)."""
    d = tmp_path / "analyst"
    d.mkdir()
    (d / "proposals.json").write_text("{}")
    monkeypatch.setattr(
        Path, "exists", lambda self: (_ for _ in ()).throw(PermissionError)
    )
    with pytest.raises(PermissionError):
        analyst_mod.load_proposals(tmp_path)


def test_load_targeted_analysis_permission_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """load_targeted_analysis lets PermissionError propagate (not caught)."""
    d = tmp_path / "analyst"
    d.mkdir()
    (d / "ticket.json").write_text("{}")
    monkeypatch.setattr(
        Path, "exists", lambda self: (_ for _ in ()).throw(PermissionError)
    )
    with pytest.raises(PermissionError):
        analyst_mod.load_targeted_analysis("ticket", tmp_path)
