"""App background loop tests: reconcile, warm-cache, cache-refresh, stuck-ticket."""

# mypy: disable-error-code="arg-type"

from __future__ import annotations

import asyncio
import contextlib
from unittest.mock import AsyncMock, Mock, patch

import pytest

from robotsix_cost_monitor.app import (
    _cache_refresh_loop,
    _reconcile_loop,
    _stuck_ticket_loop,
    _warm_cache,
)
from robotsix_cost_monitor.config import Config
from robotsix_cost_monitor.metrics import cache_warm_failure, cache_warm_success

# ---------------------------------------------------------------------------
# _reconcile_loop — schedule + error tolerance
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reconcile_loop_continues_after_failure() -> None:
    """A failing reconcile call does not kill the loop — it sleeps and retries."""
    cfg = Config()

    reconcile_calls = 0

    async def fail_then_pass(_cfg: object, _svc: object) -> None:
        nonlocal reconcile_calls
        reconcile_calls += 1
        if reconcile_calls <= 1:
            raise RuntimeError("reconcile failed")

    sleep_args: list[float] = []
    _real_sleep = asyncio.sleep

    async def fake_sleep(seconds: float) -> None:
        sleep_args.append(seconds)
        await _real_sleep(0)

    with (
        patch("robotsix_cost_monitor.app.asyncio.sleep", fake_sleep),
        patch("robotsix_cost_monitor.app.reconcile_all", fail_then_pass),
    ):
        svc = Mock()
        task = asyncio.create_task(_reconcile_loop(cfg, svc, hours=1))
        while reconcile_calls < 2:
            await _real_sleep(0)
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    assert reconcile_calls >= 2
    assert len(sleep_args) >= 2
    assert sleep_args[0] == 3600.0
    assert sleep_args[1] == 3600.0


@pytest.mark.asyncio
async def test_reconcile_loop_clamps_interval_at_one_hour() -> None:
    """When ``hours`` < 1 the reconcile interval is clamped to 1 hour."""
    cfg = Config()
    svc = Mock()

    sleep_args: list[float] = []
    _real_sleep = asyncio.sleep

    async def fake_sleep(seconds: float) -> None:
        sleep_args.append(seconds)
        await _real_sleep(0)

    with (
        patch("robotsix_cost_monitor.app.asyncio.sleep", fake_sleep),
        patch("robotsix_cost_monitor.app.reconcile_all", AsyncMock()),
    ):
        task = asyncio.create_task(_reconcile_loop(cfg, svc, hours=0.01))
        while len(sleep_args) < 2:
            await _real_sleep(0)
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    for s in sleep_args[:2]:
        assert s == 3600.0


@pytest.mark.asyncio
async def test_reconcile_loop_cancellation() -> None:
    """Cancelling the reconcile loop task raises ``CancelledError``."""
    cfg = Config()
    svc = Mock()

    async def blocked(_cfg: object, _svc: object) -> None:
        await asyncio.Event().wait()

    with (
        patch("robotsix_cost_monitor.app.asyncio.sleep", AsyncMock()),
        patch("robotsix_cost_monitor.app.reconcile_all", blocked),
    ):
        task = asyncio.create_task(_reconcile_loop(cfg, svc, hours=1))
        await asyncio.sleep(0)  # let the loop enter reconcile_all
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task


# ---------------------------------------------------------------------------
# _warm_cache — counter logic
# ---------------------------------------------------------------------------


def _mock_service(*, with_projects: bool = True) -> Mock:
    """Return a mock CostService with controlled ``_project_map``."""
    svc = Mock()
    svc._project_map = {"proj-a": Mock()} if with_projects else {}
    svc.summary = AsyncMock(return_value=[])
    svc.by_model = AsyncMock(return_value=[])
    svc.trend = AsyncMock(return_value=[])
    return svc


@pytest.mark.asyncio
async def test_warm_cache_increments_success_when_all_windows_succeed() -> None:
    """When every window warms without error, ``cache_warm_success`` is incremented."""
    cfg = Config()
    svc = _mock_service()

    before_success = cache_warm_success._value.get()
    before_failure = cache_warm_failure._value.get()

    await _warm_cache(cfg, svc)

    assert cache_warm_success._value.get() == before_success + 1
    assert cache_warm_failure._value.get() == before_failure


@pytest.mark.asyncio
async def test_warm_cache_increments_failure_when_window_raises() -> None:
    """When any window warm-up raises, ``cache_warm_failure`` is incremented."""
    cfg = Config()
    svc = _mock_service()
    svc.by_model.side_effect = RuntimeError("simulated cache fetch failure")

    before_success = cache_warm_success._value.get()
    before_failure = cache_warm_failure._value.get()

    await _warm_cache(cfg, svc)

    assert cache_warm_success._value.get() == before_success
    assert cache_warm_failure._value.get() == before_failure + 1


@pytest.mark.asyncio
async def test_warm_cache_noop_when_no_projects() -> None:
    """When ``_project_map`` is empty the function returns immediately —
    no counters are touched and no service calls are made.
    """
    cfg = Config()
    svc = _mock_service(with_projects=False)

    before_success = cache_warm_success._value.get()
    before_failure = cache_warm_failure._value.get()

    await _warm_cache(cfg, svc)

    assert cache_warm_success._value.get() == before_success
    assert cache_warm_failure._value.get() == before_failure
    svc.summary.assert_not_called()
    svc.by_model.assert_not_called()
    svc.trend.assert_not_called()


# ---------------------------------------------------------------------------
# _cache_refresh_loop — schedule + error tolerance
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cache_refresh_loop_sleeps_and_calls_warm_cache() -> None:
    """The refresh loop sleeps for *interval_s* seconds and then calls
    ``_warm_cache`` on each iteration.
    """
    cfg = Config()
    svc = _mock_service()

    warm_calls = 0
    _real_sleep = asyncio.sleep

    async def fake_warm(_cfg: Config, _svc: object) -> None:
        nonlocal warm_calls
        warm_calls += 1

    sleep_args: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleep_args.append(seconds)
        await _real_sleep(0)

    with (
        patch("robotsix_cost_monitor.app._warm_cache", fake_warm),
        patch("robotsix_cost_monitor.app.asyncio.sleep", fake_sleep),
    ):
        task = asyncio.create_task(_cache_refresh_loop(cfg, svc, interval_s=120))
        while warm_calls < 2:
            await _real_sleep(0)
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    assert warm_calls >= 2
    assert len(sleep_args) >= 2
    assert sleep_args[0] == 120
    assert sleep_args[1] == 120


@pytest.mark.asyncio
async def test_cache_refresh_loop_cancellation() -> None:
    """Cancelling the cache-refresh loop raises ``CancelledError``."""
    cfg = Config()
    svc = Mock()

    async def blocked(_cfg: Config, _svc: object) -> None:
        await asyncio.Event().wait()

    with (
        patch("robotsix_cost_monitor.app.asyncio.sleep", AsyncMock()),
        patch("robotsix_cost_monitor.app._warm_cache", blocked),
    ):
        task = asyncio.create_task(_cache_refresh_loop(cfg, svc, interval_s=60))
        await asyncio.sleep(0)  # let loop enter _warm_cache
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task


# ---------------------------------------------------------------------------
# stuck-ticket loop — gauge handling
# ---------------------------------------------------------------------------


async def _run_one_stuck_check(mill: Mock, expected_gauge: float) -> None:
    """Run ``_stuck_ticket_loop`` for one iteration, asserting the gauge value.

    The loop sleeps 3600s between checks; this helper cancels the task
    after the first iteration and returns once the gauge matches.
    """
    from robotsix_cost_monitor.metrics import stuck_ticket_count

    task = asyncio.create_task(_stuck_ticket_loop(mill, 3600))
    try:
        for _ in range(100):
            if stuck_ticket_count._value.get() == expected_gauge:
                return
            await asyncio.sleep(0)
        pytest.fail(
            f"stuck_ticket_count never reached {expected_gauge} "
            f"(got {stuck_ticket_count._value.get()})"
        )
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await asyncio.gather(task)


@pytest.mark.asyncio
async def test_stuck_ticket_loop_keeps_gauge_on_mill_api_error() -> None:
    """A failed mill check must NOT reset stuck_ticket_count to zero.

    Regression test: during a mill API outage the loop previously treated
    the empty fallback list as a clean result and zeroed the gauge, which
    would silently clear downstream stuck-ticket alerting.
    """
    from robotsix_cost_monitor.clients.mill import MillAPIError
    from robotsix_cost_monitor.metrics import stuck_ticket_count

    stuck_ticket_count.set(3)  # previous known state
    mill = Mock()
    mill.fetch_stuck_tickets = AsyncMock(side_effect=MillAPIError("mill down"))

    await _run_one_stuck_check(mill, 3)

    # The gauge still holds the previous value.
    assert stuck_ticket_count._value.get() == 3


@pytest.mark.asyncio
async def test_stuck_ticket_loop_updates_gauge_on_success() -> None:
    """A clean check still updates the gauge — stuck tickets raise it to N."""
    from robotsix_cost_monitor.clients.mill import StuckTicket
    from robotsix_cost_monitor.metrics import stuck_ticket_count

    stuck_ticket_count.set(0)
    mill = Mock()
    mill.fetch_stuck_tickets = AsyncMock(
        return_value=[
            StuckTicket(
                ticket_id="T1",
                title="stuck draft",
                state="draft",
                kind="task",
                source="user",
                created_at="2026-08-16T00:00:00Z",
                updated_at="2026-08-16T00:00:00Z",
                stuck_for_hours=49.0,
            )
        ]
    )

    await _run_one_stuck_check(mill, 1)

    assert stuck_ticket_count._value.get() == 1


@pytest.mark.asyncio
async def test_stuck_ticket_loop_zeroes_gauge_when_none_stuck() -> None:
    """A clean empty check resets the gauge to zero."""
    from robotsix_cost_monitor.metrics import stuck_ticket_count

    stuck_ticket_count.set(4)
    mill = Mock()
    mill.fetch_stuck_tickets = AsyncMock(return_value=[])

    await _run_one_stuck_check(mill, 0)

    assert stuck_ticket_count._value.get() == 0
