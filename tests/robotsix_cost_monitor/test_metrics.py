"""Smoke tests for custom Prometheus metrics and the /metrics endpoint."""

from __future__ import annotations

from fastapi.testclient import TestClient
from prometheus_client import REGISTRY

from robotsix_cost_monitor import metrics as m
from robotsix_cost_monitor.app import create_app
from robotsix_cost_monitor.config import Config


def _empty_app() -> TestClient:
    return TestClient(create_app(Config()))


# ---------------------------------------------------------------------------
# Module-level: metric declarations exist with the expected names
# ---------------------------------------------------------------------------


def test_metric_names_are_registered() -> None:
    """Every custom metric should be discoverable via the Prometheus registry."""
    # Generate a sample so each metric appears in collect() output.
    m.reconcile_runs.inc()
    m.reconcile_duration.set(1.0)
    m.cache_warm_success.inc()
    m.cache_warm_failure.inc()

    names = {metric.name for metric in REGISTRY.collect()}
    # Counter base names omit the _total suffix in collect() output.
    assert "robotsix_cost_monitor_reconcile_runs" in names
    assert "robotsix_cost_monitor_reconcile_duration_seconds" in names
    assert "robotsix_cost_monitor_cache_warm_success" in names
    assert "robotsix_cost_monitor_cache_warm_failure" in names


def test_reconcile_runs_is_counter() -> None:
    assert m.reconcile_runs._type == "counter"


def test_reconcile_duration_is_gauge() -> None:
    assert m.reconcile_duration._type == "gauge"


def test_cache_warm_success_is_counter() -> None:
    assert m.cache_warm_success._type == "counter"


def test_cache_warm_failure_is_counter() -> None:
    assert m.cache_warm_failure._type == "counter"


# ---------------------------------------------------------------------------
# Counter / gauge mutation
# ---------------------------------------------------------------------------


def test_counter_increment() -> None:
    before = m.reconcile_runs._value.get()
    m.reconcile_runs.inc()
    assert m.reconcile_runs._value.get() == before + 1


def test_gauge_set() -> None:
    m.reconcile_duration.set(12.5)
    assert m.reconcile_duration._value.get() == 12.5


def test_cache_warm_success_increment() -> None:
    before = m.cache_warm_success._value.get()
    m.cache_warm_success.inc()
    assert m.cache_warm_success._value.get() == before + 1


def test_cache_warm_failure_increment() -> None:
    before = m.cache_warm_failure._value.get()
    m.cache_warm_failure.inc()
    assert m.cache_warm_failure._value.get() == before + 1


# ---------------------------------------------------------------------------
# /metrics endpoint (integration)
# ---------------------------------------------------------------------------


def test_metrics_endpoint_returns_200() -> None:
    client = _empty_app()
    r = client.get("/metrics")
    assert r.status_code == 200


def test_metrics_endpoint_contains_custom_metric_names() -> None:
    client = _empty_app()
    r = client.get("/metrics")
    body = r.text
    assert "robotsix_cost_monitor_reconcile_runs_total" in body
    assert "robotsix_cost_monitor_reconcile_duration_seconds" in body
    assert "robotsix_cost_monitor_cache_warm_success_total" in body
    assert "robotsix_cost_monitor_cache_warm_failure_total" in body
