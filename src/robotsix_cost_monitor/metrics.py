"""Prometheus metric definitions for background tasks."""

from __future__ import annotations

from prometheus_client import Counter, Histogram

RECONCILE_TOTAL = Counter(
    "cost_monitor_reconcile_total",
    "Number of reconciliation runs",
    labelnames=["project", "status"],
)
RECONCILE_DURATION = Histogram(
    "cost_monitor_reconcile_duration_seconds",
    "Reconciliation run duration",
    labelnames=["project"],
    buckets=[1, 5, 10, 30, 60, 120, 300],
)
ANALYST_RUN_TOTAL = Counter(
    "cost_monitor_analyst_run_total",
    "Number of analyst analysis runs",
    labelnames=["analysis_type", "status"],  # fleet/ticket/stage
)
ANALYST_DURATION = Histogram(
    "cost_monitor_analyst_duration_seconds",
    "Analyst analysis run duration",
    labelnames=["analysis_type"],
    buckets=[5, 10, 30, 60, 120, 300, 600],
)
