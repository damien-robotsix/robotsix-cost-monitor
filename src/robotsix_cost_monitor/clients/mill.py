"""Mill board client: queries the robotsix-mill ticket API for stuck tickets.

Queries ``GET /tickets`` with ``include_closed=false`` and checks each
ticket's ``updated_at`` against the configured threshold to identify
tickets that have been sitting in a non-terminal state too long.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import httpx
import structlog
from robotsix_http import RetryClient

from ..config import Settings, resolve_mill_api_key

logger = structlog.get_logger(__name__)


class MillAPIError(RuntimeError):
    """The mill board API could not be queried (network or HTTP error).

    Raised instead of returning an empty result so callers can tell a
    *failed* check apart from a successful check that found nothing.
    Callers must treat this as "unknown": preserve the last known
    stuck-ticket state rather than overwriting it with an empty list.
    """


#: Non-terminal ticket states — tickets in any of these states are
#: candidates for stuck-ticket detection.  Excludes terminal states
#: (CLOSED, DONE, ANSWERED, EPIC_CLOSED).
NON_TERMINAL_STATES: frozenset[str] = frozenset(
    {
        "draft",
        "human_issue_approval",
        "ready",
        "documenting",
        "code_review",
        "deliverable",
        "implement_complete",
        "waiting_auto_merge",
        "rebasing",
        "fixing_ci",
        "addressing_review",
        "human_mr_approval",
        "errored",
        "blocked",
        "asked",
        "awaiting_user_reply",
        "epic_open",
    }
)


@dataclass
class StuckTicket:
    """A ticket that has been in a non-terminal state longer than the threshold."""

    ticket_id: str
    title: str
    state: str
    kind: str
    source: str
    created_at: str
    updated_at: str
    stuck_for_hours: float


@dataclass
class MillClient:
    """HTTP client for the robotsix-mill board API.

    Used by the stuck-ticket background loop to periodically query the
    mill's ``GET /tickets`` endpoint and identify tickets that have been
    in a non-terminal state longer than the configured threshold.
    """

    settings: Settings
    _http: httpx.AsyncClient | None = field(default=None, repr=False, init=False)

    def __post_init__(self) -> None:
        """Initialise lazy HTTP client holder to None."""
        self._http = None

    @property
    def base_url(self) -> str:
        """Return the mill API base URL with trailing slash stripped."""
        return self.settings.mill_base_url.rstrip("/")

    @property
    def _api_key(self) -> str:
        """Return the effective mill API key (env var or config)."""
        return resolve_mill_api_key(self.settings)

    @property
    def _threshold_hours(self) -> int:
        """Return the stuck-ticket threshold in hours."""
        return self.settings.stuck_ticket_threshold_hours

    @property
    def _enabled(self) -> bool:
        """Return True when stuck-ticket detection is configured and active."""
        return bool(self.base_url) and self._threshold_hours > 0

    async def _client(self) -> httpx.AsyncClient:
        """Lazy-init the HTTP client so it's not created at import time."""
        if self._http is None:
            self._http = httpx.AsyncClient(timeout=30.0)
        return self._http

    async def fetch_stuck_tickets(self) -> list[StuckTicket]:
        """Query the mill for tickets stuck in non-terminal states.

        Calls ``GET /tickets`` (``include_closed=false`` is the default,
        so terminal states are already excluded).  Each returned ticket
        whose ``updated_at`` is older than the configured threshold is
        flagged as stuck.

        Returns an empty list when detection is disabled.  Raises
        :class:`MillAPIError` when the mill API is unreachable, returns
        an error status, or returns an unexpected payload — the caller
        must then keep the previous results instead of treating the
        check as a clean empty result.
        """
        if not self._enabled:
            return []

        threshold = timedelta(hours=self._threshold_hours)
        cutoff = datetime.now(UTC) - threshold

        url = f"{self.base_url}/tickets"
        headers = {"X-API-Key": self._api_key} if self._api_key else {}
        try:
            client = await self._client()
            retry = RetryClient(client)
            resp = await retry.get(url, headers=headers)
            resp.raise_for_status()
            tickets = resp.json()
        except Exception as exc:
            logger.exception(
                "mill stuck-ticket check failed — keeping previous results"
            )
            raise MillAPIError(
                "mill board API unavailable — previous stuck-ticket results kept"
            ) from exc

        stuck: list[StuckTicket] = []
        if not isinstance(tickets, list):
            logger.warning("mill /tickets returned non-list payload: %s", type(tickets))
            raise MillAPIError(
                "mill board API returned an unexpected payload — "
                "previous stuck-ticket results kept"
            )

        for raw in tickets:
            if not isinstance(raw, dict):
                continue
            state = raw.get("state", "")
            if state not in NON_TERMINAL_STATES:
                continue
            updated_raw = raw.get("updated_at", "")
            try:
                updated = datetime.fromisoformat(updated_raw.replace("Z", "+00:00"))
            except ValueError, TypeError:
                continue
            if updated > cutoff:
                continue
            stuck_for = (datetime.now(UTC) - updated).total_seconds() / 3600.0
            stuck.append(
                StuckTicket(
                    ticket_id=raw.get("id", ""),
                    title=raw.get("title", ""),
                    state=state,
                    kind=raw.get("kind", ""),
                    source=raw.get("source", ""),
                    created_at=raw.get("created_at", ""),
                    updated_at=updated_raw,
                    stuck_for_hours=round(stuck_for, 1),
                )
            )
        return stuck

    async def close(self) -> None:
        """Release the underlying HTTP client."""
        if self._http is not None:
            await self._http.aclose()
            self._http = None
