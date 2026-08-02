"""Registry client: discovers Langfuse-enabled components from central-deploy.

Queries the central-deploy ``GET /fleet/langfuse`` endpoint, which returns
every registered component and, for each Langfuse-enabled one, its shared
``langfuse_host`` and a list of projects with read-only credentials.
"""

from __future__ import annotations

from typing import Any

import httpx
import structlog
from robotsix_http import RetryClient

from .models import RegistryProject

logger = structlog.get_logger(__name__)


class RegistryClient:
    """Discovers Langfuse-enabled components from the central-deploy registry.

    The central-deploy registry exposes an authenticated ``GET /fleet/langfuse``
    endpoint that returns every registered component and, for each
    Langfuse-enabled one, its ``langfuse_host`` and ``projects``
    (each with ``alias``, ``public_key``, ``secret_key``).
    """

    def __init__(self, base_url: str, api_key: str, timeout: float = 30.0) -> None:
        """Initialise with the central-deploy registry URL and API key."""
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._timeout = timeout

    async def fetch_projects(self) -> list[RegistryProject]:
        """Query the registry for all Langfuse-enabled components.

        Returns a (possibly empty) list of RegistryProject instances.
        Logs and returns empty on any transient failure — the service
        keeps its last-known-good project list.
        """
        url = f"{self._base_url}/fleet/langfuse"
        headers = {"X-API-Key": self._api_key}
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as http_client:
                client = RetryClient(http_client)
                resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            payload = resp.json()
        except Exception:
            logger.exception("registry fetch failed — keeping existing projects")
            return []

        # 7af1 schema: the response is a list of component objects, each with
        # `langfuse_host` and `projects[] = {alias, public_key, secret_key}`.
        raw_components: Any = (
            payload if isinstance(payload, list) else payload.get("components", [])
        )

        projects: list[RegistryProject] = []
        for comp in raw_components:
            langfuse_host = comp.get("langfuse_host") or "https://cloud.langfuse.com"
            component_id = comp.get("component_id") or comp.get("name") or ""
            for proj in comp.get("projects", []):
                try:
                    alias = proj["alias"]
                    projects.append(
                        RegistryProject(
                            name=alias,
                            slug=alias,
                            component_id=str(component_id),
                            langfuse_public_key=proj["public_key"],
                            langfuse_secret_key=proj["secret_key"],
                            langfuse_base_url=langfuse_host,
                            # Present when the fleet knows which provider key
                            # paid for this LLM function; enables reconciliation.
                            openrouter_key=proj.get("openrouter_key") or None,
                        )
                    )
                except KeyError, TypeError:  # PEP 758 (py3.14): KeyError OR TypeError
                    logger.warning(
                        "skipping malformed registry project: %s",
                        proj.get("alias", repr(proj)),
                    )
        return projects
