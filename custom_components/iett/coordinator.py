"""One generic IettCoordinator for all feed types."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .client import IettMiddleClient, IettMiddleError
from .const import (
    CONF_DCODE,
    CONF_HAT_KODU,
    CONF_MIDDLE_URL,
    DOMAIN,
    FEED_ALL_FLEET,
    FEED_ROUTE_ANNOUNCEMENTS,
    FEED_ROUTE_FLEET,
    FEED_ROUTE_SCHEDULE,
    FEED_STOP_ARRIVALS,
    UPDATE_INTERVALS,
)

_LOGGER = logging.getLogger(__name__)


class IettCoordinator(DataUpdateCoordinator[list[Any]]):
    """Single coordinator parameterised by feed type."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry_data: dict[str, Any],
    ) -> None:
        self.feed_type: str = entry_data["feed_type"]
        self._middle_url: str = entry_data[CONF_MIDDLE_URL]
        self._hat_kodu: str = entry_data.get(CONF_HAT_KODU, "")
        self._dcode: str = entry_data.get(CONF_DCODE, "")

        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{self.feed_type}",
            update_interval=UPDATE_INTERVALS[self.feed_type],
        )

    async def _async_update_data(self) -> list[Any]:
        client = IettMiddleClient(
            async_get_clientsession(self.hass),
            self._middle_url,
        )
        try:
            if self.feed_type == FEED_ALL_FLEET:
                return await client.get_all_buses()  # type: ignore[return-value]
            if self.feed_type == FEED_ROUTE_FLEET:
                return await client.get_route_buses(self._hat_kodu)  # type: ignore[return-value]
            if self.feed_type == FEED_STOP_ARRIVALS:
                return await client.get_stop_arrivals(self._dcode)  # type: ignore[return-value]
            if self.feed_type == FEED_ROUTE_SCHEDULE:
                return await client.get_route_schedule(self._hat_kodu)  # type: ignore[return-value]
            if self.feed_type == FEED_ROUTE_ANNOUNCEMENTS:
                return await client.get_announcements(self._hat_kodu)  # type: ignore[return-value]
        except IettMiddleError as err:
            raise UpdateFailed(f"iett-middle error: {err}") from err
        raise UpdateFailed(f"Unknown feed type: {self.feed_type}")
