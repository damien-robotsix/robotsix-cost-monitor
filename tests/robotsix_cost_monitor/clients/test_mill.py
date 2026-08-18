"""Tests for MillClient — exercises the robotsix-mill ``GET /tickets`` endpoint."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx
import pytest

from robotsix_cost_monitor.clients.mill import NON_TERMINAL_STATES, MillClient
from robotsix_cost_monitor.config import Settings


class TestMillClient:
    """Unit tests for the mill board API client."""

    @staticmethod
    def _settings(
        *,
        mill_base_url: str = "http://mill:8080",
        threshold: int = 48,
    ) -> Settings:
        """Build Settings with stuck-ticket detection enabled."""
        return Settings(
            mill_base_url=mill_base_url,
            mill_api_key="test-key",  # noqa: S106
            stuck_ticket_threshold_hours=threshold,
        )

    @staticmethod
    def _settings_disabled() -> Settings:
        """Build Settings with stuck-ticket detection disabled."""
        return Settings(
            mill_base_url="",
            stuck_ticket_threshold_hours=0,
        )

    # ------------------------------------------------------------------
    # enabled / disabled
    # ------------------------------------------------------------------

    def test_disabled_when_no_base_url(self) -> None:
        """fetch_stuck_tickets returns empty list when mill_base_url is empty."""
        client = MillClient(settings=self._settings_disabled())
        assert client._enabled is False

    @pytest.mark.asyncio
    async def test_fetch_returns_empty_when_disabled(self) -> None:
        """fetch_stuck_tickets returns [] without making HTTP calls."""
        client = MillClient(settings=self._settings_disabled())
        result = await client.fetch_stuck_tickets()
        assert result == []

    # ------------------------------------------------------------------
    # normal operation
    # ------------------------------------------------------------------

    @pytest.mark.asyncio
    async def test_no_stuck_tickets(self, respx_mock) -> None:
        """When all tickets are recently updated, returns empty list."""
        settings = self._settings()
        client = MillClient(settings=settings)

        now = datetime.now(UTC)
        respx_mock.get("http://mill:8080/tickets").respond(
            json=[
                {
                    "id": "T1",
                    "title": "recent ticket",
                    "state": "draft",
                    "kind": "task",
                    "source": "user",
                    "created_at": (now - timedelta(hours=2)).isoformat(),
                    "updated_at": (now - timedelta(hours=1)).isoformat(),
                },
            ],
        )

        result = await client.fetch_stuck_tickets()
        assert result == []

    @pytest.mark.asyncio
    async def test_stuck_ticket_detected(self, respx_mock) -> None:
        """A ticket updated beyond the threshold is flagged as stuck."""
        settings = self._settings(threshold=24)
        client = MillClient(settings=settings)

        now = datetime.now(UTC)
        stuck_updated = now - timedelta(hours=30)
        respx_mock.get("http://mill:8080/tickets").respond(
            json=[
                {
                    "id": "T2",
                    "title": "stuck ticket",
                    "state": "draft",
                    "kind": "task",
                    "source": "user",
                    "created_at": (now - timedelta(hours=35)).isoformat(),
                    "updated_at": stuck_updated.isoformat(),
                },
            ],
        )

        result = await client.fetch_stuck_tickets()
        assert len(result) == 1
        assert result[0].ticket_id == "T2"
        assert result[0].state == "draft"
        assert result[0].stuck_for_hours > 24

    @pytest.mark.asyncio
    async def test_terminal_states_excluded(self, respx_mock) -> None:
        """Tickets in terminal states (CLOSED, DONE, etc.) are excluded."""
        settings = self._settings(threshold=1)
        client = MillClient(settings=settings)

        now = datetime.now(UTC)
        old = now - timedelta(hours=5)
        respx_mock.get("http://mill:8080/tickets").respond(
            json=[
                {
                    "id": "T3",
                    "title": "closed ticket",
                    "state": "closed",
                    "kind": "task",
                    "source": "user",
                    "created_at": old.isoformat(),
                    "updated_at": old.isoformat(),
                },
                {
                    "id": "T4",
                    "title": "done ticket",
                    "state": "done",
                    "kind": "task",
                    "source": "user",
                    "created_at": old.isoformat(),
                    "updated_at": old.isoformat(),
                },
            ],
        )

        result = await client.fetch_stuck_tickets()
        assert result == []

    @pytest.mark.asyncio
    async def test_http_error_returns_empty(self, respx_mock) -> None:
        """When the mill API returns an error, return empty list gracefully."""
        settings = self._settings()
        client = MillClient(settings=settings)

        respx_mock.get("http://mill:8080/tickets").respond(
            status_code=500,
        )

        result = await client.fetch_stuck_tickets()
        assert result == []

    @pytest.mark.asyncio
    async def test_non_json_response_returns_empty(self, respx_mock) -> None:
        """When the mill API returns non-list JSON, return empty list."""
        settings = self._settings()
        client = MillClient(settings=settings)

        respx_mock.get("http://mill:8080/tickets").respond(
            json={"error": "not a list"},
        )

        result = await client.fetch_stuck_tickets()
        assert result == []

    @pytest.mark.asyncio
    async def test_api_key_sent_in_headers(self, respx_mock) -> None:
        """When mill_api_key is set, it is sent as X-API-Key header."""
        settings = self._settings()
        client = MillClient(settings=settings)

        route = respx_mock.get("http://mill:8080/tickets").respond(
            json=[],
        )

        await client.fetch_stuck_tickets()
        assert route.called
        request = route.calls.last.request
        assert request.headers.get("X-API-Key") == "test-key"

    @pytest.mark.asyncio
    async def test_close_cleans_up_client(self) -> None:
        """close() releases the underlying HTTP client."""
        settings = self._settings()
        client = MillClient(settings=settings)
        # Force client creation
        _ = await client._client()
        assert client._http is not None
        await client.close()
        assert client._http is None

    # ------------------------------------------------------------------
    # NON_TERMINAL_STATES completeness
    # ------------------------------------------------------------------

    def test_non_terminal_states_known(self) -> None:
        """Verify the known non-terminal states match expected set."""
        assert "draft" in NON_TERMINAL_STATES
        assert "human_issue_approval" in NON_TERMINAL_STATES
        assert "blocked" in NON_TERMINAL_STATES
        assert "errored" in NON_TERMINAL_STATES
        assert "awaiting_user_reply" in NON_TERMINAL_STATES
        assert "closed" not in NON_TERMINAL_STATES
        assert "done" not in NON_TERMINAL_STATES
        assert "answered" not in NON_TERMINAL_STATES
        assert "epic_closed" not in NON_TERMINAL_STATES