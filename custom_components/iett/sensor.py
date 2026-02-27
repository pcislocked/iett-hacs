"""One generic IettSensor that reads any IettCoordinator."""
from __future__ import annotations

import logging
from dataclasses import asdict
from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DATA_KEY,
    DOMAIN,
    FEED_ALL_FLEET,
    FEED_ROUTE_ANNOUNCEMENTS,
    FEED_ROUTE_FLEET,
    FEED_ROUTE_SCHEDULE,
    FEED_STOP_ARRIVALS,
    SENSOR_ICON,
    SENSOR_UNIT,
)
from .coordinator import IettCoordinator
from .models import Arrival, ScheduledDeparture

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: IettCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([IettSensor(coordinator, entry)])


def _state_value(feed_type: str, data: list[Any]) -> int | None:
    """Compute the sensor's native_value from the coordinator data."""
    if not data:
        return 0
    if feed_type in (FEED_ALL_FLEET, FEED_ROUTE_FLEET):
        return len(data)
    if feed_type == FEED_STOP_ARRIVALS:
        arrivals: list[Arrival] = data  # type: ignore[assignment]
        etas = [a.eta_minutes for a in arrivals if a.eta_minutes is not None]
        return min(etas) if etas else None
    if feed_type == FEED_ROUTE_SCHEDULE:
        deps: list[ScheduledDeparture] = data  # type: ignore[assignment]
        from datetime import datetime
        now = datetime.now()
        now_min = now.hour * 60 + now.minute
        diffs: list[int] = []
        for d in deps:
            try:
                h, m = map(int, d.departure_time.split(":"))
                dep_min = h * 60 + m
                diff = dep_min - now_min
                if diff < 0:
                    diff += 1440  # next day
                diffs.append(diff)
            except (ValueError, AttributeError):
                continue
        return min(diffs) if diffs else None
    if feed_type == FEED_ROUTE_ANNOUNCEMENTS:
        return len(data)
    return len(data)


class IettSensor(CoordinatorEntity[IettCoordinator], SensorEntity):
    """Single sensor for any IETT feed type."""

    def __init__(self, coordinator: IettCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._entry = entry
        ft = coordinator.feed_type
        self._attr_unique_id = entry.unique_id or entry.entry_id
        self._attr_name = entry.title
        self._attr_icon = SENSOR_ICON[ft]
        self._attr_native_unit_of_measurement = SENSOR_UNIT[ft]

    @property
    def native_value(self) -> int | None:
        return _state_value(self.coordinator.feed_type, self.coordinator.data or [])

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data = self.coordinator.data or []
        data_key = DATA_KEY[self.coordinator.feed_type]
        return {
            "feed_type": self.coordinator.feed_type,
            data_key: [asdict(item) for item in data],  # type: ignore[call-overload]
            "count": len(data),
        }
