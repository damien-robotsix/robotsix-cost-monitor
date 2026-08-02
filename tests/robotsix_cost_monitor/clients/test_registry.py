"""Tests for RegistryClient — exercises the 7af1 ``GET /fleet/langfuse`` schema."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from robotsix_cost_monitor.clients.models import RegistryProject
from robotsix_cost_monitor.clients.registry import RegistryClient


def _mock_response(status_code: int, json_body: object) -> httpx.Response:
    """Build an httpx.Response with a JSON body."""
    resp = httpx.Response(status_code=status_code, json=json_body)
    resp._request = MagicMock()  # noqa: SLF001 — needed by raise_for_status
    return resp


# ---------------------------------------------------------------------------
# 7af1 schema: list-of-components response
# ---------------------------------------------------------------------------


_SAMPLE_7AF1_RESPONSE = [
    {
        "name": "robotsix-chat-deploy",
        "langfuse_host": "https://custom.langfuse.example.com",
        "projects": [
            {
                "alias": "robotsix-chat",
                "public_key": "pk-chat-abc123",
                "secret_key": "sk-chat-xyz789",
            },
            {
                "alias": "robotsix-mill",
                "public_key": "pk-mill-def456",
                "secret_key": "sk-mill-uvw012",
            },
        ],
    },
    {
        "name": "another-component",
        "langfuse_host": "https://cloud.langfuse.com",
        "projects": [
            {
                "alias": "robotsix-auto-mail",
                "public_key": "pk-mail-ghi",
                "secret_key": "sk-mail-jkl",
            },
        ],
    },
]


class TestFetchProjects:
    """Integration-level tests for ``RegistryClient.fetch_projects()``."""

    # -- happy path: 7af1 list schema ---------------------------------------

    @pytest.mark.asyncio
    async def test_parses_list_schema(self) -> None:
        """A list-of-components response (7af1 shape) yields correct projects."""
        with patch(
            "robotsix_cost_monitor.clients.registry.RetryClient.get",
            new_callable=AsyncMock,
        ) as mock_get:
            mock_get.return_value = _mock_response(200, _SAMPLE_7AF1_RESPONSE)

            client = RegistryClient(
                base_url="http://central-deploy:8080", api_key="test-key"
            )
            projects = await client.fetch_projects()

            assert len(projects) == 3

            # robotsix-chat
            assert projects[0].name == "robotsix-chat"
            assert projects[0].slug == "robotsix-chat"
            assert projects[0].langfuse_public_key == "pk-chat-abc123"
            assert projects[0].langfuse_secret_key == "sk-chat-xyz789"
            assert (
                projects[0].langfuse_base_url == "https://custom.langfuse.example.com"
            )
            assert projects[0].openrouter_key is None

            # robotsix-mill (same component, different project)
            assert projects[1].name == "robotsix-mill"
            assert projects[1].slug == "robotsix-mill"
            assert projects[1].langfuse_public_key == "pk-mill-def456"
            assert projects[1].langfuse_secret_key == "sk-mill-uvw012"
            assert (
                projects[1].langfuse_base_url == "https://custom.langfuse.example.com"
            )

            # robotsix-auto-mail
            assert projects[2].name == "robotsix-auto-mail"
            assert projects[2].langfuse_base_url == "https://cloud.langfuse.com"

            # Verify the correct endpoint + auth header were used
            mock_get.assert_awaited_once()
            call_args = mock_get.call_args
            assert call_args[0][0] == "http://central-deploy:8080/fleet/langfuse"
            assert call_args[1]["headers"] == {"X-API-Key": "test-key"}

    # -- happy path: dict wrapper schema ------------------------------------

    @pytest.mark.asyncio
    async def test_parses_dict_wrapper_schema(self) -> None:
        """A ``{"components": [...]}`` wrapper also works."""
        with patch(
            "robotsix_cost_monitor.clients.registry.RetryClient.get",
            new_callable=AsyncMock,
        ) as mock_get:
            mock_get.return_value = _mock_response(
                200, {"components": _SAMPLE_7AF1_RESPONSE}
            )

            client = RegistryClient(
                base_url="http://central-deploy:8080", api_key="key"
            )
            projects = await client.fetch_projects()

            assert len(projects) == 3
            assert projects[0].name == "robotsix-chat"
            assert projects[1].name == "robotsix-mill"
            assert projects[2].name == "robotsix-auto-mail"

    # -- empty responses ----------------------------------------------------

    @pytest.mark.asyncio
    async def test_empty_list_yields_no_projects(self) -> None:
        with patch(
            "robotsix_cost_monitor.clients.registry.RetryClient.get",
            new_callable=AsyncMock,
        ) as mock_get:
            mock_get.return_value = _mock_response(200, [])

            client = RegistryClient(
                base_url="http://central-deploy:8080", api_key="key"
            )
            projects = await client.fetch_projects()
            assert projects == []

    @pytest.mark.asyncio
    async def test_component_without_projects_is_skipped(self) -> None:
        with patch(
            "robotsix_cost_monitor.clients.registry.RetryClient.get",
            new_callable=AsyncMock,
        ) as mock_get:
            mock_get.return_value = _mock_response(
                200,
                [
                    {
                        "name": "no-langfuse-comp",
                        "langfuse_host": "https://cloud.langfuse.com",
                        "projects": [],
                    },
                ],
            )

            client = RegistryClient(
                base_url="http://central-deploy:8080", api_key="key"
            )
            projects = await client.fetch_projects()
            assert projects == []

    # -- error tolerance ----------------------------------------------------

    @pytest.mark.asyncio
    async def test_http_error_returns_empty(self) -> None:
        with patch(
            "robotsix_cost_monitor.clients.registry.RetryClient.get",
            new_callable=AsyncMock,
        ) as mock_get:
            mock_get.side_effect = httpx.HTTPStatusError(
                "not found", request=MagicMock(), response=_mock_response(404, {})
            )

            client = RegistryClient(
                base_url="http://central-deploy:8080", api_key="key"
            )
            projects = await client.fetch_projects()
            assert projects == []

    @pytest.mark.asyncio
    async def test_network_error_returns_empty(self) -> None:
        with patch(
            "robotsix_cost_monitor.clients.registry.RetryClient.get",
            new_callable=AsyncMock,
        ) as mock_get:
            mock_get.side_effect = httpx.ConnectError("connection refused")

            client = RegistryClient(
                base_url="http://central-deploy:8080", api_key="key"
            )
            projects = await client.fetch_projects()
            assert projects == []

    @pytest.mark.asyncio
    async def test_malformed_project_is_skipped(self) -> None:
        """A project dict missing required keys is skipped without crashing."""
        with patch(
            "robotsix_cost_monitor.clients.registry.RetryClient.get",
            new_callable=AsyncMock,
        ) as mock_get:
            mock_get.return_value = _mock_response(
                200,
                [
                    {
                        "name": "bad-comp",
                        "langfuse_host": "https://cloud.langfuse.com",
                        "projects": [
                            {"alias": "good", "public_key": "pk", "secret_key": "sk"},
                            {},  # missing all required keys
                            {
                                "alias": "also-good",
                                "public_key": "pk2",
                                "secret_key": "sk2",
                            },
                        ],
                    },
                ],
            )

            client = RegistryClient(
                base_url="http://central-deploy:8080", api_key="key"
            )
            projects = await client.fetch_projects()
            assert len(projects) == 2
            assert projects[0].name == "good"
            assert projects[1].name == "also-good"

    # -- default langfuse_host ----------------------------------------------

    @pytest.mark.asyncio
    async def test_missing_langfuse_host_defaults_to_cloud(self) -> None:
        with patch(
            "robotsix_cost_monitor.clients.registry.RetryClient.get",
            new_callable=AsyncMock,
        ) as mock_get:
            mock_get.return_value = _mock_response(
                200,
                [
                    {
                        "name": "no-host-comp",
                        "projects": [
                            {"alias": "svc", "public_key": "pk", "secret_key": "sk"},
                        ],
                    },
                ],
            )

            client = RegistryClient(
                base_url="http://central-deploy:8080", api_key="key"
            )
            projects = await client.fetch_projects()
            assert len(projects) == 1
            assert projects[0].langfuse_base_url == "https://cloud.langfuse.com"


async def _fetch(payload: object) -> list[RegistryProject]:
    """Run fetch_projects() against a stubbed registry response."""
    with patch(
        "robotsix_cost_monitor.clients.registry.RetryClient.get",
        new_callable=AsyncMock,
    ) as mock_get:
        mock_get.return_value = _mock_response(200, payload)
        client = RegistryClient(base_url="http://central-deploy:8080", api_key="k")
        return await client.fetch_projects()


@pytest.mark.asyncio
class TestRegistryComponentAndOpenRouter:
    """Discovery must carry component ownership and the provider key through.

    Dropping either is what made the dashboard unable to group by component
    and left reconciliation permanently unconfigured.
    """

    async def test_component_id_and_openrouter_key_are_carried(self) -> None:
        payload = {
            "components": [
                {
                    "component_id": "chat",
                    "langfuse_host": "https://lf.example.com",
                    "projects": [
                        {
                            "alias": "robotsix-chat",
                            "public_key": "pk-1",
                            "secret_key": "sk-1",
                            "openrouter_key": "sk-or-1",
                        },
                        {
                            "alias": "robotsix-chat-cognee",
                            "public_key": "pk-2",
                            "secret_key": "sk-2",
                        },
                    ],
                }
            ]
        }
        projects = await _fetch(payload)
        assert [p.slug for p in projects] == ["robotsix-chat", "robotsix-chat-cognee"]
        assert {p.component_id for p in projects} == {"chat"}
        assert projects[0].openrouter_key == "sk-or-1"
        # Absent key stays None rather than inheriting a sibling's.
        assert projects[1].openrouter_key is None

    async def test_missing_component_id_falls_back_to_name(self) -> None:
        payload = {
            "components": [
                {
                    "name": "legacy-comp",
                    "projects": [
                        {"alias": "p", "public_key": "pk", "secret_key": "sk"}
                    ],
                }
            ]
        }
        assert (await _fetch(payload))[0].component_id == "legacy-comp"

    async def test_empty_openrouter_key_becomes_none(self) -> None:
        """An empty string must not read as a configured key downstream."""
        payload = {
            "components": [
                {
                    "component_id": "c",
                    "projects": [
                        {
                            "alias": "p",
                            "public_key": "pk",
                            "secret_key": "sk",
                            "openrouter_key": "",
                        }
                    ],
                }
            ]
        }
        assert (await _fetch(payload))[0].openrouter_key is None
