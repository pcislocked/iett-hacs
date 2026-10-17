"""DataUpdateCoordinators for the İETT integration."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .client import IettApiError, IettClient
from .const import (
    ATTR_OPT_COORDS,
    ATTR_OPT_DIST_CUSTOM,
    ATTR_OPT_DIST_STOP,
    ATTR_OPT_ETA,
    ATTR_OPT_ETA_MMSS,
    ATTR_OPT_HATNO,
    ATTR_OPT_PLAKA,
    ATTR_OPT_SPEED,
    CONF_CUSTOM_LAT,
    CONF_CUSTOM_LON,
    CONF_DEPAR_MODE,
    CONF_FEED_TYPE,
    CONF_INCLUDE_ACTIVE_BUSES,
    CONF_INCLUDE_ANNOUNCEMENTS,
    CONF_INCLUDE_SCHEDULE,
    CONF_KAPINO,
    CONF_ROUTE_CODE,
    CONF_ROUTE_MODE,
    CONF_SCAN_INTERVAL,
    CONF_SELECTED_DEPARS,
    CONF_SELECTED_ROUTES,
    CONF_SPEED_UNIT,
    CONF_STOP_CODE,
    CONF_STOP_LAT,
    CONF_STOP_LON,
    CONF_STOP_NAME,
    CONF_VEHICLE_LIMIT_MODE,
    CONF_VEHICLE_LIMIT_N,
    DEFAULT_ROOT_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DEPAR_MODE_BASE_ONLY,
    DEPAR_MODE_SELECTED,
    DOMAIN,
    FEED_ALL_FLEET,
    FEED_ROOT,
    FEED_ROUTE,
    FEED_STOP,
    FEED_VEHICLE,
    LIMIT_MODE_NEAREST_N,
    ROUTE_MODE_SELECTED,
    SPEED_UNIT_KMH,
    SPEED_UNIT_MPH,
)
from .models import ScheduledDeparture
from .normalizers import (
    convert_speed,
    format_eta_mmss,
    haversine_meters,
    normalize_kapino,
)

_LOGGER = logging.getLogger(__name__)


class IettRootCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator for the 4 city-wide root sensors (Traffic + Fleet Size)."""

    def __init__(self, hass: HomeAssistant, client: IettClient) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_root_coordinator",
            update_interval=timedelta(seconds=DEFAULT_ROOT_SCAN_INTERVAL),
        )
        self.client = client

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch root status from TKM and SOAP fleet."""
        try:
            status = await self.client.get_root_status()
            return {
                "traffic_overall": status.traffic_overall,
                "traffic_europe": status.traffic_europe,
                "traffic_anatolia": status.traffic_anatolia,
                "active_fleet_count": status.active_fleet_count,
            }
        except IettApiError as exc:
            raise UpdateFailed(f"Root update failed: {exc}") from exc


class IettEntryCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator for a specific ConfigEntry (Stop, Route, Vehicle, or Root)."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client: IettClient,
    ) -> None:
        scan_sec = entry.data.get(
            CONF_SCAN_INTERVAL,
            DEFAULT_ROOT_SCAN_INTERVAL
            if entry.data.get(CONF_FEED_TYPE) in (FEED_ROOT, FEED_ALL_FLEET)
            else DEFAULT_SCAN_INTERVAL,
        )
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{entry.entry_id}",
            update_interval=timedelta(seconds=scan_sec),
        )
        self.entry = entry
        self.client = client

    async def _async_update_data(self) -> dict[str, Any]:
        """Route to appropriate update handler based on feed_type."""
        feed_type = self.entry.data.get(CONF_FEED_TYPE, FEED_ROOT)
        try:
            if feed_type in (FEED_ROOT, FEED_ALL_FLEET):
                return await self._update_root()
            if feed_type == FEED_STOP:
                return await self._update_stop()
            if feed_type == FEED_ROUTE:
                return await self._update_route()
            if feed_type == FEED_VEHICLE:
                return await self._update_vehicle()
            raise UpdateFailed(f"Unknown feed_type: {feed_type}")
        except IettApiError as exc:
            raise UpdateFailed(f"Update failed for {feed_type}: {exc}") from exc

    async def _update_root(self) -> dict[str, Any]:
        """Fetch 4 root parameters."""
        status = await self.client.get_root_status()
        return {
            "feed_type": FEED_ROOT,
            "traffic_overall": status.traffic_overall,
            "traffic_europe": status.traffic_europe,
            "traffic_anatolia": status.traffic_anatolia,
            "active_fleet_count": status.active_fleet_count,
        }

    async def _update_stop(self) -> dict[str, Any]:
        """Fetch and process live stop arrivals with derived attributes."""
        dcode = str(self.entry.data.get(CONF_STOP_CODE, "")).strip()
        stop_name = str(self.entry.data.get(CONF_STOP_NAME, dcode)).strip()
        stop_lat = self.entry.data.get(CONF_STOP_LAT)
        stop_lon = self.entry.data.get(CONF_STOP_LON)
        custom_lat = self.entry.data.get(CONF_CUSTOM_LAT)
        custom_lon = self.entry.data.get(CONF_CUSTOM_LON)
        speed_unit = self.entry.data.get(CONF_SPEED_UNIT, SPEED_UNIT_KMH)

        arrivals = await self.client.get_stop_arrivals(dcode)

        # Apply route filter if selected
        if self.entry.data.get(CONF_ROUTE_MODE) == ROUTE_MODE_SELECTED:
            allowed = {
                r.strip().upper()
                for r in self.entry.data.get(CONF_SELECTED_ROUTES, [])
                if r.strip()
            }
            if allowed:
                arrivals = [a for a in arrivals if a.route_code.upper() in allowed]

        # Sort by ETA
        arrivals.sort(key=lambda a: (a.eta_minutes is None, a.eta_minutes or 9999))

        processed: list[dict[str, Any]] = []
        for arr in arrivals:
            dist_stop = haversine_meters(arr.lat, arr.lon, stop_lat, stop_lon)
            dist_custom = haversine_meters(arr.lat, arr.lon, custom_lat, custom_lon)
            speed_conv = convert_speed(arr.speed_kmh, speed_unit)

            amenities_parts: list[str] = []
            if arr.amenities.ac:
                amenities_parts.append("Klima")
            if arr.amenities.wifi:
                amenities_parts.append("WiFi")
            if arr.amenities.usb:
                amenities_parts.append("USB")
            if arr.amenities.accessible:
                amenities_parts.append("Engelli")

            processed.append(
                {
                    ATTR_OPT_HATNO: arr.route_code,
                    ATTR_OPT_PLAKA: arr.plate,
                    ATTR_OPT_ETA: arr.eta_minutes,
                    ATTR_OPT_ETA_MMSS: format_eta_mmss(arr.eta_minutes, arr.last_seen_ts),
                    "eta_raw": arr.eta_raw,
                    "destination": arr.destination,
                    "kapino": arr.kapino,
                    ATTR_OPT_COORDS: f"{arr.lat}, {arr.lon}" if arr.lat and arr.lon else None,
                    "latitude": arr.lat,
                    "longitude": arr.lon,
                    ATTR_OPT_DIST_STOP: dist_stop,
                    ATTR_OPT_DIST_CUSTOM: dist_custom,
                    ATTR_OPT_SPEED: speed_conv,
                    "speed_unit": "mph" if speed_unit == SPEED_UNIT_MPH else "km/h",
                    "amenities": arr.amenities.to_dict(),
                    "amenities_summary": ", ".join(amenities_parts) or None,
                    "last_seen_ts": arr.last_seen_ts,
                }
            )

        limit_mode = self.entry.data.get(CONF_VEHICLE_LIMIT_MODE, LIMIT_MODE_NEAREST_N)
        limit_n = int(self.entry.data.get(CONF_VEHICLE_LIMIT_N, 1))

        return {
            "feed_type": FEED_STOP,
            "stop_code": dcode,
            "stop_name": stop_name,
            "arriving_count": len(arrivals),
            "limit_mode": limit_mode,
            "limit_n": limit_n,
            "vehicles": processed[:20],  # Recorder 16KB guardrail
        }

    async def _update_route(self) -> dict[str, Any]:
        """Fetch active buses, departures, and announcements for route."""
        hat_kodu = str(self.entry.data.get(CONF_ROUTE_CODE, "")).strip().upper()
        inc_buses = self.entry.data.get(CONF_INCLUDE_ACTIVE_BUSES, True)
        inc_ann = self.entry.data.get(CONF_INCLUDE_ANNOUNCEMENTS, True)
        inc_sched = self.entry.data.get(CONF_INCLUDE_SCHEDULE, True)

        buses: list[Any] = []
        schedule: list[ScheduledDeparture] = []
        announcements: list[Any] = []

        if inc_buses:
            buses = await self.client.get_route_buses(hat_kodu)
        if inc_sched:
            schedule = await self.client.get_route_schedule(hat_kodu)
        if inc_ann:
            announcements = await self.client.get_announcements(hat_kodu)

        # Depar filtering for schedule
        depar_mode = self.entry.data.get(CONF_DEPAR_MODE, "all")
        selected_depars = set(self.entry.data.get(CONF_SELECTED_DEPARS, []))

        filtered_schedule: list[ScheduledDeparture] = []
        for s in schedule:
            if depar_mode == DEPAR_MODE_BASE_ONLY:
                if s.route_variant.endswith("_D0") or not s.route_variant:
                    filtered_schedule.append(s)
            elif depar_mode == DEPAR_MODE_SELECTED:
                if s.route_variant in selected_depars:
                    filtered_schedule.append(s)
            else:
                filtered_schedule.append(s)

        if not filtered_schedule and schedule:
            filtered_schedule = schedule

        # Compute next departure for G and D
        now_dt = datetime.now().astimezone()
        cur_min = now_dt.hour * 60 + now_dt.minute

        def next_dep(direction: str) -> tuple[int | None, str | None]:
            deps_dir = [
                s
                for s in filtered_schedule
                if s.direction.upper() == direction.upper()
                and s.departure_time
                and ":" in s.departure_time
            ]
            if not deps_dir:
                return (None, None)
            parsed: list[tuple[int, str]] = []
            for d in deps_dir:
                try:
                    h, m = map(int, d.departure_time.split(":")[:2])
                    parsed.append((h * 60 + m, d.departure_time))
                except (ValueError, TypeError):
                    continue
            if not parsed:
                return (None, None)
            parsed.sort()
            future = [p for p in parsed if p[0] >= cur_min]
            target = future[0] if future else parsed[0]
            diff_min = target[0] - cur_min if future else (1440 - cur_min + target[0])
            return (diff_min, target[1])

        dep_g_min, dep_g_time = next_dep("G")
        dep_d_min, dep_d_time = next_dep("D")

        return {
            "feed_type": FEED_ROUTE,
            "route_code": hat_kodu,
            "active_buses_count": len(buses),
            "gidis_count": sum(1 for b in buses if getattr(b, "direction_letter", None) == "G"),
            "donus_count": sum(1 for b in buses if getattr(b, "direction_letter", None) == "D"),
            "buses": [b.to_dict() for b in buses[:40]],
            "announcements": [a.to_dict() for a in announcements[:10]],
            "announcement_count": len(announcements),
            "has_alert": len(announcements) > 0,
            "next_dep_g_min": dep_g_min,
            "next_dep_g_time": dep_g_time,
            "next_dep_d_min": dep_d_min,
            "next_dep_d_time": dep_d_time,
            "upcoming_departures": [s.to_dict() for s in filtered_schedule[:10]],
        }

    async def _update_vehicle(self) -> dict[str, Any]:
        """Fetch single vehicle status."""
        raw_kapi = self.entry.data.get(CONF_KAPINO, "")
        kapi = normalize_kapino(raw_kapi) or str(raw_kapi).strip().upper()
        speed_unit = self.entry.data.get(CONF_SPEED_UNIT, SPEED_UNIT_KMH)

        bus = await self.client.get_vehicle_status(kapi)

        speed_val = convert_speed(bus.speed, speed_unit) if bus and bus.speed is not None else None

        return {
            "feed_type": FEED_VEHICLE,
            "kapino": kapi,
            "online": bus is not None,
            "plate": bus.plate if bus else None,
            "latitude": bus.latitude if bus else None,
            "longitude": bus.longitude if bus else None,
            "speed": speed_val,
            "speed_unit": "mph" if speed_unit == SPEED_UNIT_MPH else "km/h",
            "route_code": bus.route_code if bus else None,
            "operator": bus.operator if bus else None,
            "last_seen": bus.last_seen if bus else None,
        }


# Backwards compatibility alias
IettCoordinator = IettEntryCoordinator
