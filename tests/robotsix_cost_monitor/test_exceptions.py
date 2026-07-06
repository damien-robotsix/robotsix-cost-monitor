"""Tests for the cost-monitor exception hierarchy."""

from __future__ import annotations

from robotsix_cost_monitor.exceptions import (
    CacheError,
    CostMonitorError,
    ExternalAuthError,
    ExternalRateLimitError,
    ExternalServiceError,
    ProjectConfigError,
    ProjectNotFoundError,
)


class TestCostMonitorError:
    def test_default_attrs(self) -> None:
        err = CostMonitorError()
        assert err.status_code == 500
        assert err.error_code == "INTERNAL_ERROR"
        assert err.detail == ""

    def test_custom_detail_and_status(self) -> None:
        err = CostMonitorError("bad thing", status_code=400)
        assert err.detail == "bad thing"
        assert err.status_code == 400
        assert str(err) == "bad thing"

    def test_class_default_detail_preserved(self) -> None:
        err = CostMonitorError()
        assert err.detail == ""


class TestExternalServiceError:
    def test_defaults(self) -> None:
        err = ExternalServiceError("langfuse timeout")
        assert err.status_code == 500
        assert err.error_code == "EXTERNAL_SERVICE_ERROR"
        assert err.detail == "langfuse timeout"

    def test_override_status(self) -> None:
        err = ExternalServiceError("gone", status_code=410)
        assert err.status_code == 410


class TestExternalAuthError:
    def test_defaults(self) -> None:
        err = ExternalAuthError("bad key")
        assert err.status_code == 502
        assert err.error_code == "EXTERNAL_AUTH_ERROR"


class TestExternalRateLimitError:
    def test_defaults(self) -> None:
        err = ExternalRateLimitError("too many")
        assert err.status_code == 429
        assert err.error_code == "RATE_LIMITED"


class TestProjectConfigError:
    def test_defaults(self) -> None:
        err = ProjectConfigError("missing key")
        assert err.status_code == 422
        assert err.error_code == "PROJECT_CONFIG_ERROR"


class TestProjectNotFoundError:
    def test_defaults(self) -> None:
        err = ProjectNotFoundError("no such project")
        assert err.status_code == 404
        assert err.error_code == "PROJECT_NOT_FOUND"


class TestCacheError:
    def test_defaults(self) -> None:
        err = CacheError("deadline overflow")
        assert err.status_code == 500
        assert err.error_code == "CACHE_ERROR"


class TestMRO:
    """Verify the inheritance chain so that ``except`` clauses behave as expected."""

    def test_auth_is_service_is_cost_monitor(self) -> None:
        err = ExternalAuthError("x")
        assert isinstance(err, ExternalServiceError)
        assert isinstance(err, CostMonitorError)
        assert isinstance(err, Exception)

    def test_rate_limit_is_service_is_cost_monitor(self) -> None:
        err = ExternalRateLimitError("x")
        assert isinstance(err, ExternalServiceError)
        assert isinstance(err, CostMonitorError)

    def test_cache_is_cost_monitor_not_service(self) -> None:
        err = CacheError("x")
        assert isinstance(err, CostMonitorError)
        assert not isinstance(err, ExternalServiceError)

    def test_config_is_cost_monitor_not_service(self) -> None:
        err = ProjectConfigError("x")
        assert isinstance(err, CostMonitorError)
        assert not isinstance(err, ExternalServiceError)
