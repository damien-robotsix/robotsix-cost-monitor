"""Registry client: discovers Langfuse-enabled components from central-deploy."""

from __future__ import annotations

import httpx
import structlog
from robotsix_http import RetryClient

from .models import RegistryProject

logger = structlog.get_logger(__name__)


class RegistryClient:
    """Discovers Langfuse-enabled components from the central-deploy registry.

    The central-deploy registry exposes an authenticated endpoint that returns
    every registered component and, for each Langfuse-enabled one, its
    Langfuse host/project/read-credentials.
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
        url = f"{self._base_url}/api/registry/components"
        headers = {"Authorization": f"Bearer {self._api_key}"}
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as http_client:
                client = RetryClient(http_client)
                resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            data = resp.json()
        except Exception:
            logger.exception("registry fetch failed — keeping existing projects")
            return []

        projects: list[RegistryProject] = []
        for comp in data.get("components", []):
            lf = comp.get("langfuse")
            if not lf:
                continue
            try:
                projects.append(
                    RegistryProject(
                        name=comp["name"],
                        slug=comp.get("slug", comp["name"].lower().replace(" ", "-")),
                        langfuse_public_key=lf["public_key"],
                        langfuse_secret_key=lf["secret_key"],
                        langfuse_base_url=lf.get(
                            "base_url", "https://cloud.langfuse.com"
                        ),
                        openrouter_key=comp.get("openrouter_key"),
                    )
                )
            except KeyError, TypeError:
                logger.warning(
                    "skipping malformed registry component: %s", comp.get("name")
                )
        return projects
