"""Performance benchmarks for critical cost-aggregation endpoints.

These establish a response-time baseline for the dashboard's hot-path JSON
endpoints so CI can flag regressions early. They run fully offline: the app is
built from a zero-project :func:`_config`, so every aggregation resolves to
empty results without any network or live-LLM calls (matching the rest of the
suite's no-network invariant).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from pytest_benchmark.fixture import BenchmarkFixture

from robotsix_cost_monitor.app import create_app
from tests.robotsix_cost_monitor.helpers import _config


@pytest.fixture
def client() -> TestClient:
    """A TestClient over a zero-project app (no network, no live LLM)."""
    return TestClient(create_app(_config()))


@pytest.mark.benchmark
def test_api_summary_performance(
    benchmark: BenchmarkFixture, client: TestClient
) -> None:
    """Baseline: ``/api/summary`` should stay fast under aggregation."""
    result = benchmark(lambda: client.get("/api/summary?project=all&hours=24"))
    assert result.status_code == 200


@pytest.mark.benchmark
def test_api_by_model_performance(
    benchmark: BenchmarkFixture, client: TestClient
) -> None:
    """Baseline: ``/api/by-model`` should stay fast under aggregation."""
    result = benchmark(
        lambda: client.get("/api/by-model?project=all&hours=24&limit=100")
    )
    assert result.status_code == 200
