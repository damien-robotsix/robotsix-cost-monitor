"""Unit tests for reconcile_project + snapshot load/save (no network).

The optional ``robotsix-llmio`` package is mocked via an autouse fixture
that injects stub modules into ``sys.modules`` for the duration of each
test, so ``patch("robotsix_llmio.openrouter.OpenRouterKeyCostSource")``
works even without the ``analyst`` extra.  The mock is torn down after each
test so it cannot leak into other test modules (e.g. ``test_analyst.py``).
"""

from __future__ import annotations

import json
import sys
from collections.abc import AsyncIterator, Generator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from robotsix_cost_monitor._utils import safe_load_json
from robotsix_cost_monitor.config import Settings
from robotsix_cost_monitor.reconcile import (
    _load_snapshot,
    _save_snapshot,
    reconcile_project,
    reconcile_status,
)
from tests.robotsix_cost_monitor.helpers import _proj


@dataclass
class KeyUsage:
    """Drop-in for ``robotsix_llmio.openrouter.KeyUsage`` when the real
    package is not installed.
    """

    usage: float


# ---------------------------------------------------------------------------
# Autouse fixture — inject mock ``robotsix_llmio`` / ``robotsix_llmio.openrouter``
# modules before each test and remove them afterwards.  When the real package
# IS installed we must not clobber it.
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def _mock_robotsix_llmio_modules() -> Generator[None]:
    had_llmio = "robotsix_llmio" in sys.modules
    had_openrouter = "robotsix_llmio.openrouter" in sys.modules

    if not had_llmio:
        sys.modules["robotsix_llmio"] = MagicMock()
    if not had_openrouter:
        sys.modules["robotsix_llmio.openrouter"] = MagicMock()

    yield

    if not had_llmio:
        sys.modules.pop("robotsix_llmio", None)
    if not had_openrouter:
        sys.modules.pop("robotsix_llmio.openrouter", None)


def test_reconcile_status() -> None:
    # drift beyond tolerance → warning
    assert reconcile_status([{"within_tolerance": False}]) == "warning"
    # an error → warning
    assert reconcile_status([{"error": "boom"}]) == "warning"
    # every comparable project still on its first snapshot → pending
    assert reconcile_status([{"detail": "first snapshot recorded"}]) == "pending"
    # within tolerance → ok
    assert reconcile_status([{"within_tolerance": True}]) == "ok"
    # unconfigured projects are ignored → ok, not warning
    assert reconcile_status([{"configured": False}]) == "ok"
    # mixed: one clean, one drifting → warning
    assert (
        reconcile_status([{"within_tolerance": True}, {"within_tolerance": False}])
        == "warning"
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _settings(tolerance: float = 1.0) -> Settings:
    return Settings(reconcile_tolerance_usd=tolerance)


class _FrozenNow:
    """Replaces ``datetime`` in the reconcile module to freeze ``.now()``."""

    def __init__(self, now: datetime) -> None:
        self._now = now

    def now(self, tz: Any = None) -> datetime:  # noqa: ARG001
        return self._now

    @staticmethod
    def fromisoformat(s: str) -> datetime:
        return datetime.fromisoformat(s)


# ---------------------------------------------------------------------------
# reconcile_project
# ---------------------------------------------------------------------------


async def test_no_openrouter_key() -> None:
    """Project without openrouter_key returns early with detail."""
    proj = _proj("demo", openrouter_key=None)
    result = await reconcile_project(proj, _settings())
    assert result["configured"] is False
    assert "no openrouter_key" in result["detail"]


async def test_openrouter_fetch_failure() -> None:
    """OpenRouterKeyCostSource fetch_key_usage raises → result has error, no snapshot saved."""
    proj = _proj("demo")
    with patch("robotsix_llmio.openrouter.OpenRouterKeyCostSource") as orc_cls:
        mock_orc = orc_cls.return_value
        mock_orc.fetch_key_usage = Mock(side_effect=RuntimeError("boom"))

        result = await reconcile_project(proj, _settings())

    assert "OpenRouter fetch failed" in result["error"]
    assert "balance" not in result  # credits fetch is skipped after usage failure


async def test_openrouter_credits_fetch_failure_ignored(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Credits fetch failure is suppressed — reconcile still succeeds."""
    monkeypatch.setenv("COST_MONITOR_DATA", str(tmp_path))

    proj = _proj("demo")

    with (
        patch("robotsix_llmio.openrouter.OpenRouterKeyCostSource") as orc_cls,
        patch(
            "robotsix_cost_monitor.reconcile._fetch_credits",
            AsyncMock(side_effect=RuntimeError("credits-down")),
        ),
    ):
        mock_orc = orc_cls.return_value
        mock_orc.fetch_key_usage = Mock(return_value=KeyUsage(usage=5.0))

        result = await reconcile_project(proj, _settings())

    # Credits failure is suppressed — no error, no balance key
    assert "error" not in result
    assert "balance" not in result
    assert "first snapshot recorded" in result["detail"]


async def test_first_snapshot(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """No prior snapshot → records first snapshot, no drift fields."""
    monkeypatch.setenv("COST_MONITOR_DATA", str(tmp_path))

    proj = _proj("demo")
    with (
        patch("robotsix_llmio.openrouter.OpenRouterKeyCostSource") as orc_cls,
        patch(
            "robotsix_cost_monitor.reconcile._fetch_credits",
            AsyncMock(
                return_value={
                    "total_credits": 100.0,
                    "total_usage": 30.0,
                    "remaining": 70.0,
                }
            ),
        ),
    ):
        mock_orc = orc_cls.return_value
        mock_orc.fetch_key_usage = Mock(return_value=KeyUsage(usage=12.5))

        result = await reconcile_project(proj, _settings())

    assert result["configured"] is True
    assert "first snapshot recorded" in result["detail"]
    assert "drift_usd" not in result
    assert result["balance"] == {
        "total_credits": 100.0,
        "total_usage": 30.0,
        "remaining": 70.0,
    }

    # Verify snapshot was saved
    snap_path = tmp_path / "reconcile" / "demo.json"
    assert snap_path.exists()
    snap = json.loads(snap_path.read_text())
    assert snap["cumulative"] == 12.5


# ---------------------------------------------------------------------------
# Shared reconcile async context-manager — reduces boilerplate across the
# three "second-call" variant tests.
# ---------------------------------------------------------------------------


@asynccontextmanager
async def _reconcile_context(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    prior_hours_offset: float = -24,
    cumulative: float = 10.0,
    usage: float,
    langfuse_backend: dict[str, float],
    credits_return: dict[str, float],
    tolerance: float = 1.0,
    now: datetime | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """Set up shared reconcile-test boilerplate, call ``reconcile_project``, yield result.

    Creates a prior snapshot under ``.data/reconcile/demo.json``, applies the
    four ``unittest.mock.patch`` decorators, configures the OpenRouter and
    Langfuse mock return values from the keyword arguments, and yields the
    reconciliation ``result`` dict for assertions.
    """
    if now is None:
        now = datetime(2026, 1, 15, 12, 0, 0, tzinfo=UTC)

    monkeypatch.setenv("COST_MONITOR_DATA", str(tmp_path))

    prior = now + timedelta(hours=prior_hours_offset)
    snap = {"cumulative": cumulative, "at": prior.isoformat()}
    data_dir = tmp_path / "reconcile"
    data_dir.mkdir(parents=True)
    (data_dir / "demo.json").write_text(json.dumps(snap))

    proj = _proj("demo")

    with (
        patch("robotsix_cost_monitor.reconcile.datetime", _FrozenNow(now)),
        patch("robotsix_llmio.openrouter.OpenRouterKeyCostSource") as orc_cls,
        patch("robotsix_cost_monitor.reconcile.LangfuseClient") as lf_cls,
        patch(
            "robotsix_cost_monitor.reconcile._fetch_credits",
            AsyncMock(return_value=credits_return),
        ),
    ):
        mock_orc = orc_cls.return_value
        mock_orc.fetch_key_usage = Mock(return_value=KeyUsage(usage=usage))

        mock_lf = lf_cls.return_value
        mock_lf.fetch_cost_by_backend = AsyncMock(return_value=langfuse_backend)

        result = await reconcile_project(proj, _settings(tolerance=tolerance))
        yield result


async def test_second_call_within_tolerance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Prior snapshot exists → diffs against it, drift within tolerance."""
    async with _reconcile_context(
        tmp_path,
        monkeypatch,
        usage=15.0,
        langfuse_backend={"openrouter": 5.0},
        credits_return={
            "total_credits": 50.0,
            "total_usage": 20.0,
            "remaining": 30.0,
        },
    ) as result:
        pass

    assert result["interval_hours"] == 24.0
    assert result["provider_delta_usd"] == 5.0
    assert result["langfuse_cost_usd"] == 5.0
    assert result["drift_usd"] == 0.0
    assert result["within_tolerance"] is True


async def test_drift_exceeds_tolerance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Provider delta and Langfuse cost differ by more than tolerance."""
    async with _reconcile_context(
        tmp_path,
        monkeypatch,
        usage=20.0,
        langfuse_backend={"openrouter": 3.0},
        credits_return={
            "total_credits": 100.0,
            "total_usage": 0.0,
            "remaining": 100.0,
        },
        tolerance=0.5,
    ) as result:
        pass

    assert result["provider_delta_usd"] == 10.0
    assert result["langfuse_cost_usd"] == 3.0
    assert result["drift_usd"] == 7.0
    assert result["within_tolerance"] is False


async def test_negative_interval_treated_as_zero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When now is before the prior snapshot, interval_h is 0.0 (negative cap)."""
    async with _reconcile_context(
        tmp_path,
        monkeypatch,
        prior_hours_offset=+1,
        usage=8.0,
        langfuse_backend={},
        credits_return={
            "total_credits": 50.0,
            "total_usage": 10.0,
            "remaining": 40.0,
        },
    ) as result:
        pass

    assert result["interval_hours"] == 0.0
    # Cumulative went down (clock problem) → negative provider delta
    assert result["provider_delta_usd"] == -2.0
    assert result["langfuse_cost_usd"] == 0.0


async def test_missing_snapshot_file_treated_as_first(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Corrupted/missing snapshot is treated as first run."""
    monkeypatch.setenv("COST_MONITOR_DATA", str(tmp_path))

    # _load_snapshot is tested directly below; here we verify the integration
    proj = _proj("demo")
    with (
        patch("robotsix_llmio.openrouter.OpenRouterKeyCostSource") as orc_cls,
        patch(
            "robotsix_cost_monitor.reconcile._fetch_credits",
            AsyncMock(
                return_value={
                    "total_credits": 10.0,
                    "total_usage": 2.0,
                    "remaining": 8.0,
                }
            ),
        ),
    ):
        mock_orc = orc_cls.return_value
        mock_orc.fetch_key_usage = Mock(return_value=KeyUsage(usage=1.0))

        result = await reconcile_project(proj, _settings())

    assert "first snapshot recorded" in result["detail"]


# ---------------------------------------------------------------------------
# _load_snapshot / _save_snapshot
# ---------------------------------------------------------------------------


def test_load_snapshot_missing_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """_load_snapshot returns None when file does not exist."""
    monkeypatch.setenv("COST_MONITOR_DATA", str(tmp_path))
    assert _load_snapshot("nonexistent") is None


def test_load_snapshot_corrupted_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """_load_snapshot returns None on invalid JSON."""
    monkeypatch.setenv("COST_MONITOR_DATA", str(tmp_path))
    data_dir = tmp_path / "reconcile"
    data_dir.mkdir(parents=True)
    (data_dir / "bad.json").write_text("not json {{")

    assert _load_snapshot("bad") is None


def test_save_and_load_roundtrip(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """_save_snapshot then _load_snapshot returns the saved data."""
    monkeypatch.setenv("COST_MONITOR_DATA", str(tmp_path))
    now = datetime(2026, 1, 15, 12, 0, 0, tzinfo=UTC)

    _save_snapshot("demo", 42.0, now)
    loaded = _load_snapshot("demo")

    assert loaded is not None
    assert loaded["cumulative"] == 42.0
    assert loaded["at"] == now.isoformat()


def test_load_snapshot_stale_data(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """_load_snapshot returns the saved data even if old."""
    monkeypatch.setenv("COST_MONITOR_DATA", str(tmp_path))
    old = datetime(2020, 1, 1, 0, 0, 0, tzinfo=UTC)
    _save_snapshot("stale", 1.0, old)

    loaded = _load_snapshot("stale")
    assert loaded is not None
    assert loaded["cumulative"] == 1.0
    assert loaded["at"] == old.isoformat()


# ---------------------------------------------------------------------------
# safe_load_json
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
