"""Sensor platform for the İETT Home Assistant integration."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    ATTR_OPT_AMENITIES,
    ATTR_OPT_COORDS,
    ATTR_OPT_DIST_CUSTOM,
    ATTR_OPT_DIST_STOP,
    ATTR_OPT_ETA,
    ATTR_OPT_ETA_MMSS,
    ATTR_OPT_HATNO,
    ATTR_OPT_PLAKA,
    ATTR_OPT_SPEED,
    CONF_DIRECTION_FILTER,
    CONF_FEED_TYPE,
    CONF_INCLUDE_ACTIVE_BUSES,
    CONF_INCLUDE_ANNOUNCEMENTS,
    CONF_INCLUDE_SCHEDULE,
    CONF_KAPINO,
    CONF_ROUTE_CODE,
    CONF_STOP_ATTRIBUTES,
    CONF_STOP_CODE,
    CONF_STOP_NAME,
    CONF_VEHICLE_LIMIT_MODE,
    CONF_VEHICLE_LIMIT_N,
    DEFAULT_STOP_ATTRIBUTES,
    DIR_FILTER_BOTH,
    DIR_FILTER_D,
    DIR_FILTER_G,
    DOMAIN,
    FEED_ALL_FLEET,
    FEED_ROOT,
    FEED_ROUTE,
    FEED_STOP,
    FEED_VEHICLE,
    LIMIT_MODE_NEAREST_N,
)
from .coordinator import IettEntryCoordinator, IettRootCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up İETT sensors from config entry."""
    domain_data = hass.data[DOMAIN]
    coord: IettEntryCoordinator = domain_data[entry.entry_id]
    root_coord: IettRootCoordinator = domain_data["root_coordinator"]

    entities: list[SensorEntity] = []

    # 1. Guarantee 4 Root Sensors on the first entry setup
    if not domain_data.get("root_sensors_created"):
        domain_data["root_sensors_created"] = True
        domain_data["root_sensors_owner"] = entry.entry_id

        root_device = DeviceInfo(
            identifiers={(DOMAIN, "istanbul_root")},
            name="İETT İstanbul Geneli",
            manufacturer="İETT / İBB",
            model="Trafik ve Filo Göstergesi",
            entry_type=DeviceEntryType.SERVICE,
        )

        entities.extend(
            [
                IettRootTrafficSensor(
                    root_coord,
                    key="traffic_overall",
                    unique_id="iett_root_traffic_overall",
                    name="İstanbul Trafik Yoğunluğu (Genel)",
                    device_info=root_device,
                ),
                IettRootTrafficSensor(
                    root_coord,
                    key="traffic_europe",
                    unique_id="iett_root_traffic_europe",
                    name="İstanbul Trafik Yoğunluğu (Avrupa)",
                    device_info=root_device,
                ),
                IettRootTrafficSensor(
                    root_coord,
                    key="traffic_anatolia",
                    unique_id="iett_root_traffic_anatolia",
                    name="İstanbul Trafik Yoğunluğu (Anadolu)",
                    device_info=root_device,
                ),
                IettRootFleetSizeSensor(
                    root_coord,
                    unique_id="iett_root_active_fleet",
                    name="İETT Aktif Filo Boyutu",
                    device_info=root_device,
                ),
            ]
        )

    # If this entry is purely root/all_fleet, we're done
    feed_type = entry.data.get(CONF_FEED_TYPE, FEED_ROOT)
    if feed_type in (FEED_ROOT, FEED_ALL_FLEET):
        async_add_entities(entities)
        return

    # 2. 1a) Stop Sensors
    if feed_type == FEED_STOP:
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

        # General stop status sensor
        entities.append(IettStopGeneralSensor(coord, entry, stop_device))

        # Vehicle slots (1..N)
        limit_mode = entry.data.get(CONF_VEHICLE_LIMIT_MODE, LIMIT_MODE_NEAREST_N)
        slot_count = (
            int(entry.data.get(CONF_VEHICLE_LIMIT_N, 1))
            if limit_mode == LIMIT_MODE_NEAREST_N
            else 1
        )
        selected_attrs = set(entry.data.get(CONF_STOP_ATTRIBUTES, DEFAULT_STOP_ATTRIBUTES))

        for slot in range(1, slot_count + 1):
            # Main object sensor for slot
            entities.append(IettStopVehicleObjectSensor(coord, entry, stop_device, slot))

            # Individual granular attribute sensors if ticked
            if ATTR_OPT_HATNO in selected_attrs:
                entities.append(
                    IettStopSlotAttrSensor(
                        coord,
                        entry,
                        stop_device,
                        slot,
                        ATTR_OPT_HATNO,
                        f"Araç {slot} Hat No",
                        icon="mdi:bus-sign",
                    )
                )
            if ATTR_OPT_PLAKA in selected_attrs:
                entities.append(
                    IettStopSlotAttrSensor(
                        coord,
                        entry,
                        stop_device,
                        slot,
                        ATTR_OPT_PLAKA,
                        f"Araç {slot} Plaka",
                        icon="mdi:card-text-outline",
                    )
                )
            if ATTR_OPT_ETA in selected_attrs:
                entities.append(
                    IettStopSlotAttrSensor(
                        coord,
                        entry,
                        stop_device,
                        slot,
                        ATTR_OPT_ETA,
                        f"Araç {slot} ETA",
                        unit="min",
                        device_class=SensorDeviceClass.DURATION,
                        state_class=SensorStateClass.MEASUREMENT,
                    )
                )
            if ATTR_OPT_ETA_MMSS in selected_attrs:
                entities.append(
                    IettStopSlotAttrSensor(
                        coord,
                        entry,
                        stop_device,
                        slot,
                        ATTR_OPT_ETA_MMSS,
                        f"Araç {slot} Varış Saati",
                        icon="mdi:clock-outline",
                    )
                )
            if ATTR_OPT_COORDS in selected_attrs:
                entities.append(
                    IettStopSlotAttrSensor(
                        coord,
                        entry,
                        stop_device,
                        slot,
                        ATTR_OPT_COORDS,
                        f"Araç {slot} Koordinat",
                        icon="mdi:crosshairs-gps",
                    )
                )
            if ATTR_OPT_DIST_STOP in selected_attrs:
                entities.append(
                    IettStopSlotAttrSensor(
                        coord,
                        entry,
                        stop_device,
                        slot,
                        ATTR_OPT_DIST_STOP,
                        f"Araç {slot} Durağa Mesafe",
                        unit="m",
                        device_class=SensorDeviceClass.DISTANCE,
                        state_class=SensorStateClass.MEASUREMENT,
                    )
                )
            if ATTR_OPT_DIST_CUSTOM in selected_attrs:
                entities.append(
                    IettStopSlotAttrSensor(
                        coord,
                        entry,
                        stop_device,
                        slot,
                        ATTR_OPT_DIST_CUSTOM,
                        f"Araç {slot} Hedefe Mesafe",
                        unit="m",
                        device_class=SensorDeviceClass.DISTANCE,
                        state_class=SensorStateClass.MEASUREMENT,
                    )
                )
            if ATTR_OPT_SPEED in selected_attrs:
                speed_unit = "mph" if entry.data.get("speed_unit") == "mph" else "km/h"
                entities.append(
                    IettStopSlotAttrSensor(
                        coord,
                        entry,
                        stop_device,
                        slot,
                        ATTR_OPT_SPEED,
                        f"Araç {slot} Hız",
                        unit=speed_unit,
                        device_class=SensorDeviceClass.SPEED,
                        state_class=SensorStateClass.MEASUREMENT,
                    )
                )
            if ATTR_OPT_AMENITIES in selected_attrs:
                entities.append(
                    IettStopSlotAttrSensor(
                        coord,
                        entry,
                        stop_device,
                        slot,
                        "amenities_summary",
                        f"Araç {slot} Donanım",
                        icon="mdi:wifi",
                    )
                )

    # 3. 1b) Route Sensors
    elif feed_type == FEED_ROUTE:
        hat_kodu = str(entry.data.get(CONF_ROUTE_CODE, "")).strip().upper()

        route_device = DeviceInfo(
            identifiers={(DOMAIN, f"route_{hat_kodu}")},
            name=f"Hat {hat_kodu}",
            manufacturer="İETT",
            model="Otobüs Hattı",
        )

        if entry.data.get(CONF_INCLUDE_ACTIVE_BUSES, True):
            entities.append(IettRouteActiveBusesSensor(coord, entry, route_device))
        if entry.data.get(CONF_INCLUDE_ANNOUNCEMENTS, True):
            entities.append(IettRouteAnnouncementsSensor(coord, entry, route_device))
        if entry.data.get(CONF_INCLUDE_SCHEDULE, True):
            dir_filter = entry.data.get(CONF_DIRECTION_FILTER, DIR_FILTER_BOTH)
            if dir_filter in (DIR_FILTER_G, DIR_FILTER_BOTH):
                entities.append(
                    IettRouteDepartureSensor(
                        coord, entry, route_device, "G", "Sıradaki Kalkış (Gidiş)"
                    )
                )
            if dir_filter in (DIR_FILTER_D, DIR_FILTER_BOTH):
                entities.append(
                    IettRouteDepartureSensor(
                        coord, entry, route_device, "D", "Sıradaki Kalkış (Dönüş)"
                    )
                )

    # 4. 1c) Vehicle Sensors
    elif feed_type == FEED_VEHICLE:
        raw_kapi = entry.data.get(CONF_KAPINO, "")
        kapi = str(raw_kapi).strip().upper()

        vehicle_device = DeviceInfo(
            identifiers={(DOMAIN, f"vehicle_{kapi}")},
            name=f"Araç {kapi}",
            manufacturer="İETT",
            model="Belediye Otobüsü",
        )

        entities.extend(
            [
                IettVehiclePlateSensor(coord, entry, vehicle_device),
                IettVehicleCoordsSensor(coord, entry, vehicle_device),
                IettVehicleSpeedSensor(coord, entry, vehicle_device),
                IettVehicleRouteSensor(coord, entry, vehicle_device),
            ]
        )

    async_add_entities(entities)


# =====================================================================
# Root Entities (City Traffic + Active Fleet Size)
# =====================================================================


class IettRootTrafficSensor(CoordinatorEntity[IettRootCoordinator], SensorEntity):
    """Sensor for Istanbul traffic congestion percentage (Genel, Avrupa, Anadolu)."""

    _attr_native_unit_of_measurement = "%"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:traffic-light"

    def __init__(
        self,
        coordinator: IettRootCoordinator,
        key: str,
        unique_id: str,
        name: str,
        device_info: DeviceInfo,
    ) -> None:
        super().__init__(coordinator)
        self._key = key
        self._attr_unique_id = unique_id
        self._attr_name = name
        self._attr_device_info = device_info

    @property
    def native_value(self) -> int | None:
        if not self.coordinator.data:
            return None
        return self.coordinator.data.get(self._key)


class IettRootFleetSizeSensor(CoordinatorEntity[IettRootCoordinator], SensorEntity):
    """Sensor for total active buses on Istanbul roads.

    Strict guardrail: Returns integer bus count only.
    extra_state_attributes MUST be empty dict to protect SQLite Recorder.
    """

    _attr_native_unit_of_measurement = "araç"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:bus-multiple"

    def __init__(
        self,
        coordinator: IettRootCoordinator,
        unique_id: str,
        name: str,
        device_info: DeviceInfo,
    ) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = unique_id
        self._attr_name = name
        self._attr_device_info = device_info

    @property
    def native_value(self) -> int | None:
        if not self.coordinator.data:
            return None
        return self.coordinator.data.get("active_fleet_count")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Strictly empty dictionary — no operator summary or fleet array."""
        return {}


# =====================================================================
# 1a) Stop Entities
# =====================================================================


class IettStopGeneralSensor(CoordinatorEntity[IettEntryCoordinator], SensorEntity):
    """General stop sensor reporting approaching bus count and static metadata."""

    _attr_native_unit_of_measurement = "araç"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:bus-stop"

    def __init__(
        self,
        coordinator: IettEntryCoordinator,
        entry: ConfigEntry,
        device_info: DeviceInfo,
    ) -> None:
        super().__init__(coordinator)
        self.entry = entry
        self._attr_unique_id = f"{entry.entry_id}_general"
        self._attr_name = "Yaklaşan Araç Sayısı"
        self._attr_device_info = device_info

    @property
    def native_value(self) -> int:
        if not self.coordinator.data:
            return 0
        return int(self.coordinator.data.get("arriving_count", 0))

    def _filter_vehicle_attrs(self, veh: dict[str, Any]) -> dict[str, Any]:
        """Return only user-selected attributes plus core identification keys."""
        selected = set(self.entry.data.get(CONF_STOP_ATTRIBUTES, DEFAULT_STOP_ATTRIBUTES))
        out: dict[str, Any] = {
            "kapino": veh.get("kapino"),
            "destination": veh.get("destination"),
        }
        if ATTR_OPT_HATNO in selected:
            out[ATTR_OPT_HATNO] = veh.get(ATTR_OPT_HATNO)
        if ATTR_OPT_PLAKA in selected:
            out[ATTR_OPT_PLAKA] = veh.get(ATTR_OPT_PLAKA)
        if ATTR_OPT_ETA in selected:
            out[ATTR_OPT_ETA] = veh.get(ATTR_OPT_ETA)
            out["eta_raw"] = veh.get("eta_raw")
        if ATTR_OPT_ETA_MMSS in selected:
            out[ATTR_OPT_ETA_MMSS] = veh.get(ATTR_OPT_ETA_MMSS)
        if ATTR_OPT_COORDS in selected:
            out[ATTR_OPT_COORDS] = veh.get(ATTR_OPT_COORDS)
            out["latitude"] = veh.get("latitude")
            out["longitude"] = veh.get("longitude")
        if ATTR_OPT_DIST_STOP in selected:
            out[ATTR_OPT_DIST_STOP] = veh.get(ATTR_OPT_DIST_STOP)
        if ATTR_OPT_DIST_CUSTOM in selected:
            out[ATTR_OPT_DIST_CUSTOM] = veh.get(ATTR_OPT_DIST_CUSTOM)
        if ATTR_OPT_SPEED in selected:
            out[ATTR_OPT_SPEED] = veh.get(ATTR_OPT_SPEED)
            out["speed_unit"] = veh.get("speed_unit")
        if ATTR_OPT_AMENITIES in selected:
            out["amenities"] = veh.get("amenities")
            out["amenities_summary"] = veh.get("amenities_summary")
        return out

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        attrs: dict[str, Any] = {
            "stop_code": self.entry.data.get(CONF_STOP_CODE),
            "stop_name": self.entry.data.get(CONF_STOP_NAME),
            "latitude": self.entry.data.get("stop_lat"),
            "longitude": self.entry.data.get("stop_lon"),
            "direction": self.entry.data.get("stop_direction"),
            "district": self.entry.data.get("stop_district"),
            "stop_type": self.entry.data.get("stop_type"),
            "smart_stop": self.entry.data.get("stop_smart"),
            "route_mode": self.entry.data.get("route_mode", "all"),
            "selected_routes": self.entry.data.get("selected_routes", []),
        }
        if self.coordinator.data and self.entry.data.get(CONF_VEHICLE_LIMIT_MODE) == "all":
            raw_vehicles = self.coordinator.data.get("vehicles", [])
            attrs["vehicles"] = [self._filter_vehicle_attrs(v) for v in raw_vehicles]
        return attrs


class IettStopVehicleObjectSensor(CoordinatorEntity[IettEntryCoordinator], SensorEntity):
    """Master object sensor for vehicle slot N (e.g. 'Araç 1')."""

    _attr_icon = "mdi:bus"

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
        self._attr_unique_id = f"{entry.entry_id}_v{slot}_obj"
        self._attr_name = f"Araç {slot}"
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
    def native_value(self) -> str:
        veh = self._get_vehicle()
        if not veh:
            return "Yok"
        route = veh.get(ATTR_OPT_HATNO, "")
        eta = veh.get(ATTR_OPT_ETA)
        if eta is not None:
            if eta <= 0:
                return f"{route} (Yaklaşıyor)" if route else "Yaklaşıyor"
            return f"{route} ({eta} dk)"
        return str(route) or "Yaklaşıyor"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        veh = self._get_vehicle()
        if not veh:
            return {}
        selected = set(self.entry.data.get(CONF_STOP_ATTRIBUTES, DEFAULT_STOP_ATTRIBUTES))
        out: dict[str, Any] = {
            "kapino": veh.get("kapino"),
            "destination": veh.get("destination"),
            "last_seen_ts": veh.get("last_seen_ts"),
        }
        if ATTR_OPT_HATNO in selected:
            out[ATTR_OPT_HATNO] = veh.get(ATTR_OPT_HATNO)
        if ATTR_OPT_PLAKA in selected:
            out[ATTR_OPT_PLAKA] = veh.get(ATTR_OPT_PLAKA)
        if ATTR_OPT_ETA in selected:
            out[ATTR_OPT_ETA] = veh.get(ATTR_OPT_ETA)
            out["eta_raw"] = veh.get("eta_raw")
        if ATTR_OPT_ETA_MMSS in selected:
            out[ATTR_OPT_ETA_MMSS] = veh.get(ATTR_OPT_ETA_MMSS)
        if ATTR_OPT_COORDS in selected:
            out[ATTR_OPT_COORDS] = veh.get(ATTR_OPT_COORDS)
            out["latitude"] = veh.get("latitude")
            out["longitude"] = veh.get("longitude")
        if ATTR_OPT_DIST_STOP in selected:
            out[ATTR_OPT_DIST_STOP] = veh.get(ATTR_OPT_DIST_STOP)
        if ATTR_OPT_DIST_CUSTOM in selected:
            out[ATTR_OPT_DIST_CUSTOM] = veh.get(ATTR_OPT_DIST_CUSTOM)
        if ATTR_OPT_SPEED in selected:
            out[ATTR_OPT_SPEED] = veh.get(ATTR_OPT_SPEED)
            out["speed_unit"] = veh.get("speed_unit")
        if ATTR_OPT_AMENITIES in selected:
            out["amenities"] = veh.get("amenities")
            out["amenities_summary"] = veh.get("amenities_summary")
        return out


class IettStopSlotAttrSensor(CoordinatorEntity[IettEntryCoordinator], SensorEntity):
    """Granular attribute sensor for vehicle slot N."""

    def __init__(
        self,
        coordinator: IettEntryCoordinator,
        entry: ConfigEntry,
        device_info: DeviceInfo,
        slot: int,
        attr_key: str,
        name: str,
        unit: str | None = None,
        device_class: SensorDeviceClass | None = None,
        state_class: SensorStateClass | None = None,
        icon: str | None = None,
    ) -> None:
        super().__init__(coordinator)
        self.entry = entry
        self.slot = slot
        self.attr_key = attr_key
        self._attr_unique_id = f"{entry.entry_id}_v{slot}_{attr_key}"
        self._attr_name = name
        self._attr_device_info = device_info
        if unit:
            self._attr_native_unit_of_measurement = unit
        if device_class:
            self._attr_device_class = device_class
        if state_class:
            self._attr_state_class = state_class
        if icon:
            self._attr_icon = icon

    @property
    def native_value(self) -> Any:
        if not self.coordinator.data:
            return None
        vehicles = self.coordinator.data.get("vehicles", [])
        idx = self.slot - 1
        if 0 <= idx < len(vehicles):
            return vehicles[idx].get(self.attr_key)
        return None


# =====================================================================
# 1b) Route Entities
# =====================================================================


class IettRouteActiveBusesSensor(CoordinatorEntity[IettEntryCoordinator], SensorEntity):
    """Sensor for active buses operating on route."""

    _attr_native_unit_of_measurement = "araç"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:bus-multiple"

    def __init__(
        self,
        coordinator: IettEntryCoordinator,
        entry: ConfigEntry,
        device_info: DeviceInfo,
    ) -> None:
        super().__init__(coordinator)
        self.entry = entry
        self._attr_unique_id = f"{entry.entry_id}_active_buses"
        self._attr_name = "Aktif Araç Sayısı"
        self._attr_device_info = device_info

    @property
    def native_value(self) -> int:
        if not self.coordinator.data:
            return 0
        return int(self.coordinator.data.get("active_buses_count", 0))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        if not self.coordinator.data:
            return {}
        return {
            "gidis_count": self.coordinator.data.get("gidis_count", 0),
            "donus_count": self.coordinator.data.get("donus_count", 0),
            "buses": self.coordinator.data.get("buses", []),
        }


class IettRouteAnnouncementsSensor(CoordinatorEntity[IettEntryCoordinator], SensorEntity):
    """Sensor for route disruption announcements."""

    _attr_native_unit_of_measurement = "duyuru"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:bullhorn"

    def __init__(
        self,
        coordinator: IettEntryCoordinator,
        entry: ConfigEntry,
        device_info: DeviceInfo,
    ) -> None:
        super().__init__(coordinator)
        self.entry = entry
        self._attr_unique_id = f"{entry.entry_id}_announcements"
        self._attr_name = "Duyuru Sayısı"
        self._attr_device_info = device_info

    @property
    def native_value(self) -> int:
        if not self.coordinator.data:
            return 0
        return int(self.coordinator.data.get("announcement_count", 0))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        if not self.coordinator.data:
            return {}
        return {
            "announcements": self.coordinator.data.get("announcements", []),
        }


class IettRouteDepartureSensor(CoordinatorEntity[IettEntryCoordinator], SensorEntity):
    """Sensor for minutes remaining until next timetable departure."""

    _attr_native_unit_of_measurement = "min"
    _attr_device_class = SensorDeviceClass.DURATION
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:clock-outline"

    def __init__(
        self,
        coordinator: IettEntryCoordinator,
        entry: ConfigEntry,
        device_info: DeviceInfo,
        direction: str,
        name: str,
    ) -> None:
        super().__init__(coordinator)
        self.entry = entry
        self.direction = direction.lower()
        self._attr_unique_id = f"{entry.entry_id}_dep_{self.direction}"
        self._attr_name = name
        self._attr_device_info = device_info

    @property
    def native_value(self) -> int | None:
        if not self.coordinator.data:
            return None
        key = f"next_dep_{self.direction}_min"
        return self.coordinator.data.get(key)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        if not self.coordinator.data:
            return {}
        time_key = f"next_dep_{self.direction}_time"
        return {
            "departure_time": self.coordinator.data.get(time_key),
            "upcoming_departures": self.coordinator.data.get("upcoming_departures", []),
        }


# =====================================================================
# 1c) Vehicle Entities
# =====================================================================


class IettVehiclePlateSensor(CoordinatorEntity[IettEntryCoordinator], SensorEntity):
    """Sensor for vehicle license plate."""

    _attr_icon = "mdi:card-text-outline"

    def __init__(
        self,
        coordinator: IettEntryCoordinator,
        entry: ConfigEntry,
        device_info: DeviceInfo,
    ) -> None:
        super().__init__(coordinator)
        self.entry = entry
        self._attr_unique_id = f"{entry.entry_id}_plate"
        self._attr_name = "Plaka"
        self._attr_device_info = device_info

    @property
    def native_value(self) -> str | None:
        if not self.coordinator.data:
            return None
        return self.coordinator.data.get("plate")


class IettVehicleCoordsSensor(CoordinatorEntity[IettEntryCoordinator], SensorEntity):
    """Sensor for vehicle coordinates."""

    _attr_icon = "mdi:crosshairs-gps"

    def __init__(
        self,
        coordinator: IettEntryCoordinator,
        entry: ConfigEntry,
        device_info: DeviceInfo,
    ) -> None:
        super().__init__(coordinator)
        self.entry = entry
        self._attr_unique_id = f"{entry.entry_id}_coords"
        self._attr_name = "Koordinat"
        self._attr_device_info = device_info

    @property
    def native_value(self) -> str | None:
        if not self.coordinator.data or not self.coordinator.data.get("online"):
            return "Bilinmiyor"
        lat = self.coordinator.data.get("latitude")
        lon = self.coordinator.data.get("longitude")
        if lat and lon:
            return f"{lat}, {lon}"
        return "Bilinmiyor"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        if not self.coordinator.data:
            return {}
        return {
            "latitude": self.coordinator.data.get("latitude"),
            "longitude": self.coordinator.data.get("longitude"),
            "online": self.coordinator.data.get("online", False),
            "last_seen": self.coordinator.data.get("last_seen"),
        }


class IettVehicleSpeedSensor(CoordinatorEntity[IettEntryCoordinator], SensorEntity):
    """Sensor for vehicle speed."""

    _attr_device_class = SensorDeviceClass.SPEED
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self,
        coordinator: IettEntryCoordinator,
        entry: ConfigEntry,
        device_info: DeviceInfo,
    ) -> None:
        super().__init__(coordinator)
        self.entry = entry
        self._attr_unique_id = f"{entry.entry_id}_speed"
        self._attr_name = "Hız"
        self._attr_device_info = device_info

    @property
    def native_unit_of_measurement(self) -> str:
        if self.coordinator.data:
            return self.coordinator.data.get("speed_unit", "km/h")
        return "km/h"

    @property
    def native_value(self) -> int | float | None:
        if not self.coordinator.data:
            return None
        return self.coordinator.data.get("speed")


class IettVehicleRouteSensor(CoordinatorEntity[IettEntryCoordinator], SensorEntity):
    """Sensor for vehicle active line."""

    _attr_icon = "mdi:bus-sign"

    def __init__(
        self,
        coordinator: IettEntryCoordinator,
        entry: ConfigEntry,
        device_info: DeviceInfo,
    ) -> None:
        super().__init__(coordinator)
        self.entry = entry
        self._attr_unique_id = f"{entry.entry_id}_route"
        self._attr_name = "Aktif Hat"
        self._attr_device_info = device_info

    @property
    def native_value(self) -> str:
        if not self.coordinator.data:
            return "Bilinmiyor"
        if not self.coordinator.data.get("online"):
            return "Seferde Değil"
        return str(self.coordinator.data.get("route_code") or "Boşta")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        if not self.coordinator.data:
            return {}
        return {
            "operator": self.coordinator.data.get("operator"),
            "online": self.coordinator.data.get("online", False),
            "last_seen": self.coordinator.data.get("last_seen"),
        }
