"""Self-contained async OpenRouter cost/credit client.

OpenRouter does not expose a simple per-window cost endpoint, so reconciliation
works by snapshotting the key's *cumulative* usage and diffing over time. The
credits endpoint also gives the remaining balance (useful for low-credit
warnings).
"""

from __future__ import annotations

from typing import Any

import httpx

_BASE = "https://openrouter.ai/api/v1"


class OpenRouterClient:
    """Read-only OpenRouter client (credits + key usage)."""

    def __init__(self, api_key: str, *, timeout: float = 30.0) -> None:
        self._key = api_key
        self._timeout = timeout

    async def _get(self, path: str) -> dict[str, Any]:
        headers = {"Authorization": f"Bearer {self._key}"}
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.get(f"{_BASE}{path}", headers=headers)
            resp.raise_for_status()
            data: dict[str, Any] = resp.json()
            return data

    async def fetch_credits(self) -> dict[str, float]:
        """Return ``{total_credits, total_usage, remaining}`` for the key.

        Uses ``GET /credits`` (cumulative usage + granted credits).
        """
        data = (await self._get("/credits")).get("data") or {}
        total_credits = float(data.get("total_credits") or 0.0)
        total_usage = float(data.get("total_usage") or 0.0)
        return {
            "total_credits": round(total_credits, 6),
            "total_usage": round(total_usage, 6),
            "remaining": round(total_credits - total_usage, 6),
        }
