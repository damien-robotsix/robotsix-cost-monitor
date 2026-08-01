"""Unit tests for the CLI entrypoint (cli.py)."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pytest import CaptureFixture

from robotsix_cost_monitor.cli import main

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _cfg(
    default_window_hours: int = 168,
) -> MagicMock:
    """Return a mock config with the given settings."""
    cfg = MagicMock()
    cfg.settings = MagicMock()
    cfg.settings.default_window_hours = default_window_hours
    return cfg


# ---------------------------------------------------------------------------
# serve
# ---------------------------------------------------------------------------


def test_serve_default_host_port() -> None:
    """``serve`` subcommand reads host/port from config when no CLI flags given."""
    cfg = _cfg()
    cfg.settings.server_host = "0.0.0.0"
    cfg.settings.server_port = 8080

    with (
        patch("robotsix_cost_monitor.cli.load_config", return_value=cfg),
        patch("robotsix_cost_monitor.cli.uvicorn.run") as mock_run,
    ):
        exit_code = main(["serve"])

    assert exit_code == 0
    mock_run.assert_called_once_with(
        "robotsix_cost_monitor.app:create_app",
        host="0.0.0.0",
        port=8080,
        factory=True,
        log_config=None,
    )


def test_serve_custom_host_port() -> None:
    """``serve`` subcommand CLI --host/--port override config values."""
    cfg = _cfg()
    cfg.settings.server_host = "0.0.0.0"
    cfg.settings.server_port = 8080

    with (
        patch("robotsix_cost_monitor.cli.load_config", return_value=cfg),
        patch("robotsix_cost_monitor.cli.uvicorn.run") as mock_run,
    ):
        exit_code = main(["serve", "--host", "127.0.0.1", "--port", "3000"])

    assert exit_code == 0
    mock_run.assert_called_once_with(
        "robotsix_cost_monitor.app:create_app",
        host="127.0.0.1",
        port=3000,
        factory=True,
        log_config=None,
    )


# ---------------------------------------------------------------------------
# no-args default (serve path)
# ---------------------------------------------------------------------------


def test_no_args_defaults_to_serve() -> None:
    """No subcommand → acts like serve (reads host/port from config)."""
    cfg = _cfg()
    cfg.settings.server_host = "0.0.0.0"
    cfg.settings.server_port = 8080

    with (
        patch("robotsix_cost_monitor.cli.load_config", return_value=cfg),
        patch("robotsix_cost_monitor.cli.uvicorn.run") as mock_run,
    ):
        exit_code = main([])

    assert exit_code == 0
    mock_run.assert_called_once_with(
        "robotsix_cost_monitor.app:create_app",
        host="0.0.0.0",
        port=8080,
        factory=True,
        log_config=None,
    )


# ---------------------------------------------------------------------------
# unknown subcommand
# ---------------------------------------------------------------------------


def test_unknown_subcommand_exits_1() -> None:
    """Unknown subcommand → exit code 1 (print_help path)."""
    with pytest.raises(SystemExit) as exc_info:
        main(["bogus"])
    # argparse exits with code 2 for invalid choice in Python ≥3.14
    assert exc_info.value.code == 2


# ---------------------------------------------------------------------------
# summary
# ---------------------------------------------------------------------------


def test_summary_default_project_all() -> None:
    """``summary`` (no --project) passes 'all' to CostService.summary()."""
    mock_svc = MagicMock()
    mock_svc.summary = MagicMock(return_value={"total": 42.0})
    cfg = _cfg()

    with (
        patch("robotsix_cost_monitor.cli.load_config", return_value=cfg),
        patch("robotsix_cost_monitor.cli.CostService", return_value=mock_svc),
        patch("robotsix_cost_monitor.cli.asyncio.run", side_effect=lambda c: c),
    ):
        exit_code = main(["summary"])

    assert exit_code == 0
    mock_svc.summary.assert_called_once_with("all", 168)


def test_summary_project_specific() -> None:
    """``summary --project <slug>`` passes the slug to CostService.summary()."""
    mock_svc = MagicMock()
    mock_svc.summary = MagicMock(return_value={"total": 10.0})
    cfg = _cfg()

    with (
        patch("robotsix_cost_monitor.cli.load_config", return_value=cfg),
        patch("robotsix_cost_monitor.cli.CostService", return_value=mock_svc),
        patch("robotsix_cost_monitor.cli.asyncio.run", side_effect=lambda c: c),
    ):
        exit_code = main(["summary", "--project", "myproj"])

    assert exit_code == 0
    mock_svc.summary.assert_called_once_with("myproj", 168)


def test_summary_custom_hours() -> None:
    """``summary --hours N`` passes the window to CostService.summary()."""
    mock_svc = MagicMock()
    mock_svc.summary = MagicMock(return_value={"total": 5.0})
    cfg = _cfg()

    with (
        patch("robotsix_cost_monitor.cli.load_config", return_value=cfg),
        patch("robotsix_cost_monitor.cli.CostService", return_value=mock_svc),
        patch("robotsix_cost_monitor.cli.asyncio.run", side_effect=lambda c: c),
    ):
        exit_code = main(["summary", "--hours", "24"])

    assert exit_code == 0
    mock_svc.summary.assert_called_once_with("all", 24)


def test_summary_prints_json(capsys: CaptureFixture[str]) -> None:
    """``summary`` prints the JSON output returned by CostService.summary()."""
    expected = {"demo": 12.5, "total": 12.5}
    mock_svc = MagicMock()
    mock_svc.summary = MagicMock(return_value=expected)
    cfg = _cfg()

    with (
        patch("robotsix_cost_monitor.cli.load_config", return_value=cfg),
        patch("robotsix_cost_monitor.cli.CostService", return_value=mock_svc),
        patch("robotsix_cost_monitor.cli.asyncio.run", side_effect=lambda c: c),
    ):
        exit_code = main(["summary", "--project", "demo"])

    assert exit_code == 0
    stdout = capsys.readouterr().out
    assert json.loads(stdout) == expected


# ---------------------------------------------------------------------------
# reconcile
# ---------------------------------------------------------------------------


def test_reconcile_project_all() -> None:
    """``reconcile --project all`` calls reconcile_all."""
    cfg = _cfg()
    cfg.settings.registry_base_url = ""  # skip refresh_projects

    mock_ra = AsyncMock(return_value={"status": "ok", "results": []})

    with (
        patch("robotsix_cost_monitor.cli.load_config", return_value=cfg),
        patch("robotsix_cost_monitor.cli.reconcile_all", mock_ra),
    ):
        exit_code = main(["reconcile", "--project", "all"])

    assert exit_code == 0
    mock_ra.assert_called_once()


def test_reconcile_project_specific_slug() -> None:
    """``reconcile --project <slug>`` calls reconcile_project for matching project."""
    cfg = _cfg()
    cfg.settings.registry_base_url = ""  # skip refresh_projects

    mock_svc = MagicMock()
    mock_svc._project_map = {"y": MagicMock(slug="y", name="yproj")}
    mock_svc.refresh_projects = AsyncMock()

    mock_rp = AsyncMock(return_value={"status": "ok"})

    with (
        patch("robotsix_cost_monitor.cli.load_config", return_value=cfg),
        patch("robotsix_cost_monitor.cli.CostService", return_value=mock_svc),
        patch("robotsix_cost_monitor.cli.reconcile_project", mock_rp),
    ):
        exit_code = main(["reconcile", "--project", "y"])

    assert exit_code == 0
    assert mock_rp.call_count == 1
    assert mock_rp.call_args[0][0].slug == "y"


def test_reconcile_prints_json(capsys: CaptureFixture[str]) -> None:
    """``reconcile`` prints JSON result."""
    cfg = _cfg()
    cfg.settings.registry_base_url = ""

    mock_svc = MagicMock()
    mock_svc._project_map = {"demo": MagicMock(slug="demo", name="demo")}
    mock_svc.refresh_projects = AsyncMock()

    expected = {"project": "demo", "status": "reconciled"}
    mock_rp = AsyncMock(return_value=expected)

    with (
        patch("robotsix_cost_monitor.cli.load_config", return_value=cfg),
        patch("robotsix_cost_monitor.cli.CostService", return_value=mock_svc),
        patch("robotsix_cost_monitor.cli.reconcile_project", mock_rp),
    ):
        exit_code = main(["reconcile", "--project", "demo"])

    assert exit_code == 0
    stdout = capsys.readouterr().out
    parsed = json.loads(stdout)
    assert parsed == [expected]
