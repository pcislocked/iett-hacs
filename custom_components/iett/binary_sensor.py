"""Binary sensor platform for the İETT integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CONF_FEED_TYPE,
    CONF_INCLUDE_ANNOUNCEMENTS,
    CONF_ROUTE_CODE,
    DOMAIN,
    FEED_ROUTE,
)
from .coordinator import IettEntryCoordinator
from .normalizers import format_announcement_attributes


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up İETT binary sensors from config entry."""
    coord: IettEntryCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities: list[BinarySensorEntity] = []

    if entry.data.get(CONF_FEED_TYPE) == FEED_ROUTE:
        if entry.data.get(CONF_INCLUDE_ANNOUNCEMENTS, True):
            hat_kodu = str(entry.data.get(CONF_ROUTE_CODE, "")).strip().upper()
            route_device = DeviceInfo(
                identifiers={(DOMAIN, f"route_{hat_kodu}")},
                name=f"Hat {hat_kodu}",
                manufacturer="İETT",
                model="Otobüs Hattı",
            )
            entities.append(IettRouteAlertBinarySensor(coord, entry, route_device))

    async_add_entities(entities)


class IettRouteAlertBinarySensor(CoordinatorEntity[IettEntryCoordinator], BinarySensorEntity):
    """Binary sensor turning ON when active route disruptions or announcements exist."""

    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(
        self,
        coordinator: IettEntryCoordinator,
        entry: ConfigEntry,
        device_info: DeviceInfo,
    ) -> None:
        super().__init__(coordinator)
        self.entry = entry
        self._attr_unique_id = f"{entry.entry_id}_alert"
        self._attr_name = "Sefer Uyarısı"
        self._attr_device_info = device_info

    @property
    def is_on(self) -> bool:
        if not self.coordinator.data:
            return False
        return bool(self.coordinator.data.get("has_alert", False))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return format_announcement_attributes(
            self.coordinator.data,
            empty_detail_msg="Aktif sefer sorunu / duyuru bulunmuyor",
            is_active_sensor=False,
        )
