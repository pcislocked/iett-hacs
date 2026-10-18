"""Device tracker platform for the İETT integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.device_tracker import SourceType, TrackerEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    ATTR_OPT_COORDS_TRACKER,
    CONF_FEED_TYPE,
    CONF_KAPINO,
    CONF_STOP_ATTRIBUTES,
    CONF_STOP_CODE,
    CONF_STOP_NAME,
    CONF_VEHICLE_LIMIT_MODE,
    CONF_VEHICLE_LIMIT_N,
    DEFAULT_STOP_ATTRIBUTES,
    DOMAIN,
    FEED_STOP,
    FEED_VEHICLE,
    LIMIT_MODE_NEAREST_N,
)
from .coordinator import IettEntryCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up İETT device trackers from config entry."""
    coord: IettEntryCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities: list[TrackerEntity] = []
    feed_type = entry.data.get(CONF_FEED_TYPE)

    # 1. 1c) Single Vehicle GPS Tracker
    if feed_type == FEED_VEHICLE:
        raw_kapi = entry.data.get(CONF_KAPINO, "")
        kapi = str(raw_kapi).strip().upper()
        vehicle_device = DeviceInfo(
            identifiers={(DOMAIN, f"vehicle_{kapi}")},
            name=f"Araç {kapi}",
            manufacturer="İETT",
            model="Belediye Otobüsü",
        )
        entities.append(IettVehicleTracker(coord, entry, vehicle_device, kapi))

    # 2. 1a) Stop Approaching Vehicle Tracker (if ticked)
    elif feed_type == FEED_STOP:
        selected_attrs = set(entry.data.get(CONF_STOP_ATTRIBUTES, DEFAULT_STOP_ATTRIBUTES))
        if ATTR_OPT_COORDS_TRACKER in selected_attrs:
            dcode = str(entry.data.get(CONF_STOP_CODE, "")).strip()
            stop_name = str(entry.data.get(CONF_STOP_NAME, dcode)).strip()
            stop_dir = str(entry.data.get("stop_direction") or "").strip()
            dir_suffix = f" - {stop_dir} Yönü" if stop_dir else ""
            stop_device = DeviceInfo(
                identifiers={(DOMAIN, f"stop_{dcode}")},
                name=f"Durak {dcode} ({stop_name}{dir_suffix})",
                manufacturer="İETT",
                model=f"Akıllı Durak ({stop_dir} Yönü)" if stop_dir else "Akıllı Durak",
            )
            limit_mode = entry.data.get(CONF_VEHICLE_LIMIT_MODE, LIMIT_MODE_NEAREST_N)
            slot_count = (
                int(entry.data.get(CONF_VEHICLE_LIMIT_N, 1))
                if limit_mode == LIMIT_MODE_NEAREST_N
                else 1
            )
            for slot in range(1, slot_count + 1):
                entities.append(IettStopSlotTrackerEntity(coord, entry, stop_device, slot))

    async_add_entities(entities)


class IettVehicleTracker(CoordinatorEntity[IettEntryCoordinator], TrackerEntity):
    """GPS device tracker for a single tracked bus."""

    _attr_icon = "mdi:bus"

    def __init__(
        self,
        coordinator: IettEntryCoordinator,
        entry: ConfigEntry,
        device_info: DeviceInfo,
        kapino: str,
    ) -> None:
        super().__init__(coordinator)
        self.entry = entry
        self.kapino = kapino
        self._attr_unique_id = f"{entry.entry_id}_tracker"
        self._attr_name = "Konum"
        self._attr_device_info = device_info

    @property
    def source_type(self) -> SourceType:
        return SourceType.GPS

    @property
    def latitude(self) -> float | None:
        if not self.coordinator.data:
            return None
        return self.coordinator.data.get("latitude")

    @property
    def longitude(self) -> float | None:
        if not self.coordinator.data:
            return None
        return self.coordinator.data.get("longitude")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        if not self.coordinator.data:
            return {}
        return {
            "kapino": self.kapino,
            "plate": self.coordinator.data.get("plate"),
            "route_code": self.coordinator.data.get("route_code"),
            "speed": self.coordinator.data.get("speed"),
            "speed_unit": self.coordinator.data.get("speed_unit"),
            "operator": self.coordinator.data.get("operator"),
            "last_seen": self.coordinator.data.get("last_seen"),
            "online": self.coordinator.data.get("online", False),
        }


class IettStopSlotTrackerEntity(CoordinatorEntity[IettEntryCoordinator], TrackerEntity):
    """GPS device tracker for vehicle approaching in slot N."""

    _attr_icon = "mdi:bus-marker"

    def __init__(
        self,
        coordinator: IettEntryCoordinator,
        entry: ConfigEntry,
        device_info: DeviceInfo,
        slot: int,
    ) -> None:
        super().__init__(coordinator)
        self.entry = entry
        self.slot = slot
        self._attr_unique_id = f"{entry.entry_id}_v{slot}_tracker"
        self._attr_name = f"Araç {slot} Konum"
        self._attr_device_info = device_info

    def _get_vehicle(self) -> dict[str, Any] | None:
        if not self.coordinator.data:
            return None
        vehicles = self.coordinator.data.get("vehicles", [])
        idx = self.slot - 1
        if 0 <= idx < len(vehicles):
            return vehicles[idx]
        return None

    @property
    def source_type(self) -> SourceType:
        return SourceType.GPS

    @property
    def latitude(self) -> float | None:
        veh = self._get_vehicle()
        return veh.get("latitude") if veh else None

    @property
    def longitude(self) -> float | None:
        veh = self._get_vehicle()
        return veh.get("longitude") if veh else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        veh = self._get_vehicle()
        return veh or {}
