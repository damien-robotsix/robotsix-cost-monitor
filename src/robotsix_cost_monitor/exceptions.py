"""Typed exception hierarchy for cost-monitor.

Distinguishes retriable network errors from terminal configuration errors,
so catch-sites can make deliberate choices instead of blanket ``except Exception``.

The HTTP exception classes inherit from both :class:`CostMonitorError` (for
the FastAPI exception handler and local catch-blocks) and the corresponding
:mod:`robotsix_http` exception classes (so the shared :class:`RetryClient`
can raise them directly while existing ``except`` clauses still match).
"""

from __future__ import annotations

import httpx
from robotsix_http import (
    ExternalAuthError as _ExternalAuthError,
)
from robotsix_http import (
    ExternalRateLimitError as _ExternalRateLimitError,
)
from robotsix_http import (
    ExternalServiceError as _ExternalServiceError,
)


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


class ExternalServiceError(CostMonitorError, _ExternalServiceError):  # type: ignore[misc]
    """An external API (Langfuse, OpenRouter) returned an error.

    Transient failures (timeout, 5xx, 429) should be retried; terminal
    failures (401, 403, 404) should surface immediately.
    """

    error_code = "EXTERNAL_SERVICE_ERROR"

    def __init__(
        self,
        detail: str = "",
        *,
        status_code: int | None = None,
        response: object | None = None,
    ) -> None:
        """Initialise from a detail string, optionally with an HTTP response.

        When *response* is ``None`` (constructed locally), a synthetic
        :class:`httpx.Response` with the class-level ``status_code`` is
        created to satisfy :class:`ExternalHTTPError`'s required keyword
        arguments.
        """
        self.detail = detail or self.detail
        if status_code is not None:
            self.status_code = status_code
        if response is None:
            # Constructed locally without an HTTP response — use the
            # class-level status_code as the default for the robotsix-http
            # base class.  We must call both parent __init__s explicitly
            # because CostMonitorError's super().__init__ would land on
            # ExternalHTTPError which requires keyword arguments.
            Exception.__init__(self, self.detail)
            _ExternalServiceError.__init__(
                self,
                message=self.detail,
                status_code=self.status_code,
                response=httpx.Response(status_code=self.status_code),
            )
        else:
            Exception.__init__(self, self.detail)
            _ExternalServiceError.__init__(
                self,
                message=self.detail,
                status_code=status_code or self.status_code,
                response=response,
            )


class ExternalAuthError(ExternalServiceError, _ExternalAuthError):  # type: ignore[misc]
    """Bad API key or credentials — NOT retriable."""

    status_code = 502  # gateway shows as service-available-but-bad-credentials
    error_code = "EXTERNAL_AUTH_ERROR"


class ExternalRateLimitError(ExternalServiceError, _ExternalRateLimitError):  # type: ignore[misc]
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
