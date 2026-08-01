"""Custom Prometheus metrics for self-observability.

These counters and gauges instrument the background loops that
``prometheus-fastapi-instrumentator`` does not cover (reconciliation
runs and dashboard cache warm-ups).
"""

from prometheus_client import Counter, Gauge

reconcile_runs = Counter(
    "robotsix_cost_monitor_reconcile_runs_total",
    "Total number of reconciliation runs.",
)

reconcile_duration = Gauge(
    "robotsix_cost_monitor_reconcile_duration_seconds",
    "Duration of the last reconciliation run in seconds.",
)

cache_warm_success = Counter(
    "robotsix_cost_monitor_cache_warm_success_total",
    "Total number of successful dashboard cache warm-ups.",
)

cache_warm_failure = Counter(
    "robotsix_cost_monitor_cache_warm_failure_total",
    "Total number of failed dashboard cache warm-ups.",
)
