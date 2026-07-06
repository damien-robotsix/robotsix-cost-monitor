"""Typed exception hierarchy for cost-monitor.

Distinguishes retriable network errors from terminal configuration errors,
so catch-sites can make deliberate choices instead of blanket ``except Exception``.
"""

from __future__ import annotations


class CostMonitorError(Exception):
    """Base exception for all cost-monitor errors."""

    status_code: int = 500
    error_code: str = "INTERNAL_ERROR"
    detail: str = ""

    def __init__(self, detail: str = "", *, status_code: int | None = None) -> None:
        """Initialise with an optional detail message and status code override."""
        self.detail = detail or self.detail
        if status_code is not None:
            self.status_code = status_code
        super().__init__(self.detail)


class ExternalServiceError(CostMonitorError):
    """An external API (Langfuse, OpenRouter) returned an error.

    Transient failures (timeout, 5xx, 429) should be retried; terminal
    failures (401, 403, 404) should surface immediately.
    """

    error_code = "EXTERNAL_SERVICE_ERROR"


class ExternalAuthError(ExternalServiceError):
    """Bad API key or credentials — NOT retriable."""

    status_code = 502  # gateway shows as service-available-but-bad-credentials
    error_code = "EXTERNAL_AUTH_ERROR"


class ExternalRateLimitError(ExternalServiceError):
    """429 rate limit — retriable with backoff."""

    status_code = 429
    error_code = "RATE_LIMITED"


class ProjectConfigError(CostMonitorError):
    """A project is misconfigured (missing keys, bad URL). NOT retriable."""

    status_code = 422
    error_code = "PROJECT_CONFIG_ERROR"


class ProjectNotFoundError(CostMonitorError):
    """A project slug does not match any configured project."""

    status_code = 404
    error_code = "PROJECT_NOT_FOUND"


class CacheError(CostMonitorError):
    """Cache corruption or deadline overflow — retriable."""

    status_code = 500
    error_code = "CACHE_ERROR"
