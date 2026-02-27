"""HTTP client for iett-middle REST API.

Replaces all direct IETT SOAP/HTML calls with simple GET requests to the
iett-middle backend. No parsing of IETT responses here — the middle-end
handles everything.

Zero Home Assistant imports — fully testable with aioresponses.
"""
from __future__ import annotations

import logging

import aiohttp

from .models import Announcement, Arrival, BusPosition, ScheduledDeparture

_LOGGER = logging.getLogger(__name__)


class IettMiddleError(Exception):
    """Raised when an iett-middle API call fails."""


class IettMiddleClient:
    """Simple REST client for iett-middle v1 API."""

    def __init__(self, session: aiohttp.ClientSession, base_url: str) -> None:
        self._session = session
        self._base = base_url.rstrip("/")

    async def _get(self, path: str) -> list:
        url = f"{self._base}{path}"
        try:
            async with self._session.get(
                url, timeout=aiohttp.ClientTimeout(total=20)
            ) as resp:
                resp.raise_for_status()
                return await resp.json()  # type: ignore[return-value]
        except Exception as exc:
            raise IettMiddleError(f"GET {url} failed: {exc}") from exc

    # ── Fleet ──────────────────────────────────────────────────────────────

    async def get_all_buses(self) -> list[BusPosition]:
        """All active Istanbul buses (~7,000)."""
        data = await self._get("/v1/fleet")
        return [BusPosition(**item) for item in data]

    async def get_route_buses(self, hat_kodu: str) -> list[BusPosition]:
        """Live positions of buses on a specific route."""
        data = await self._get(f"/v1/routes/{hat_kodu}/buses")
        return [BusPosition(**item) for item in data]

    # ── Stops ──────────────────────────────────────────────────────────────

    async def get_stop_arrivals(
        self, dcode: str, via: str | None = None
    ) -> list[Arrival]:
        """Real-time ETAs at a stop, optionally filtered by via stop."""
        path = f"/v1/stops/{dcode}/arrivals"
        if via:
            path += f"?via={via}"
        data = await self._get(path)
        return [Arrival(**item) for item in data]

    # ── Routes ─────────────────────────────────────────────────────────────

    async def get_route_schedule(self, hat_kodu: str) -> list[ScheduledDeparture]:
        """Planned departure schedule for a route."""
        data = await self._get(f"/v1/routes/{hat_kodu}/schedule")
        return [ScheduledDeparture(**item) for item in data]

    async def get_announcements(self, hat_kodu: str) -> list[Announcement]:
        """Active service announcements/disruptions for a route."""
        data = await self._get(f"/v1/routes/{hat_kodu}/announcements")
        return [Announcement(**item) for item in data]
