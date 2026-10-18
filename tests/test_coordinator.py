"""Tests for IettCoordinator v2 — IettRootCoordinator and IettEntryCoordinator."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components.iett.client import IettApiError
from custom_components.iett.const import (
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
    CONF_SELECTED_ROUTES,
    CONF_SPEED_UNIT,
    CONF_STOP_CODE,
    CONF_STOP_LAT,
    CONF_STOP_LON,
    CONF_STOP_NAME,
    CONF_VEHICLE_LIMIT_MODE,
    CONF_VEHICLE_LIMIT_N,
    DEPAR_MODE_BASE_ONLY,
    FEED_ROUTE,
    FEED_STOP,
    FEED_VEHICLE,
    LIMIT_MODE_NEAREST_N,
    ROUTE_MODE_SELECTED,
    SPEED_UNIT_KMH,
    SPEED_UNIT_MPH,
)
from custom_components.iett.coordinator import IettEntryCoordinator, IettRootCoordinator
from custom_components.iett.models import (
    Amenities,
    Announcement,
    Arrival,
    BusPosition,
    RootStatus,
    ScheduledDeparture,
)


def _make_hass() -> MagicMock:
    hass = MagicMock()
    hass.loop = MagicMock()
    hass.config = MagicMock()
    return hass


def _make_entry(entry_id: str, data: dict[str, Any]) -> MagicMock:
    entry = MagicMock()
    entry.entry_id = entry_id
    entry.data = data
    return entry


@pytest.fixture()
def hass() -> MagicMock:
    return _make_hass()


# ---------------------------------------------------------------------------
# Root Coordinator Tests
# ---------------------------------------------------------------------------


class TestRootCoordinator:
    async def test_update_success(self, hass: MagicMock) -> None:
        client = MagicMock()
        client.get_root_status = AsyncMock(
            return_value=RootStatus(
                traffic_overall=42,
                traffic_europe=46,
                traffic_anatolia=38,
                active_fleet_count=2500,
            )
        )
        coord = IettRootCoordinator(hass, client)
        data = await coord._async_update_data()

        assert data["traffic_overall"] == 42
        assert data["traffic_europe"] == 46
        assert data["traffic_anatolia"] == 38
        assert data["active_fleet_count"] == 2500

    async def test_update_failed_on_error(self, hass: MagicMock) -> None:
        client = MagicMock()
        client.get_root_status = AsyncMock(side_effect=IettApiError("Server Down"))
        coord = IettRootCoordinator(hass, client)

        with pytest.raises(UpdateFailed):
            await coord._async_update_data()


# ---------------------------------------------------------------------------
# Stop Coordinator (1a) Tests
# ---------------------------------------------------------------------------


class TestStopCoordinator:
    async def test_stop_with_derived_attributes(self, hass: MagicMock) -> None:
        client = MagicMock()
        arrivals = [
            Arrival(
                route_code="500T",
                destination="CEVİZLİBAĞ",
                eta_minutes=5,
                eta_raw="14:35",
                kapino="C-1753",
                plate="34 HO 1234",
                lat=41.0450,
                lon=29.0020,
                speed_kmh=36,
                last_seen_ts="14:30:00",
                amenities=Amenities(ac=True, wifi=True, usb=True, accessible=True),
            ),
            Arrival(
                route_code="14M",
                destination="KAVACIK",
                eta_minutes=12,
                eta_raw="14:42",
                kapino="A-001",
                plate="34 TP 2000",
                lat=41.0819,
                lon=29.0109,
                speed_kmh=0,
                last_seen_ts="14:29:45",
                amenities=Amenities(ac=True),
            ),
        ]
        client.get_stop_arrivals = AsyncMock(return_value=arrivals)

        entry = _make_entry(
            "stop_entry_1",
            {
                CONF_FEED_TYPE: FEED_STOP,
                CONF_STOP_CODE: "301341",
                CONF_STOP_NAME: "BEŞİKTAŞ MEYDAN",
                CONF_STOP_LAT: 41.0428,
                CONF_STOP_LON: 29.0069,
                CONF_CUSTOM_LAT: 41.0500,
                CONF_CUSTOM_LON: 29.0100,
                CONF_SPEED_UNIT: SPEED_UNIT_KMH,
                CONF_VEHICLE_LIMIT_MODE: LIMIT_MODE_NEAREST_N,
                CONF_VEHICLE_LIMIT_N: 2,
            },
        )
        coord = IettEntryCoordinator(hass, entry, client)
        data = await coord._async_update_data()

        assert data["feed_type"] == FEED_STOP
        assert data["stop_code"] == "301341"
        assert data["arriving_count"] == 2
        assert len(data["vehicles"]) == 2

        v1 = data["vehicles"][0]
        assert v1[ATTR_OPT_HATNO] == "500T"
        assert v1[ATTR_OPT_PLAKA] == "34 HO 1234"
        assert v1[ATTR_OPT_ETA] == 5
        assert v1[ATTR_OPT_ETA_MMSS] == "14:35"
        assert v1["eta_time"] == "14:35"
        assert v1[ATTR_OPT_SPEED] == 36
        assert v1[ATTR_OPT_DIST_STOP] is not None
        assert v1[ATTR_OPT_DIST_CUSTOM] is not None
        assert "Klima" in v1["amenities_summary"]
        assert "WiFi" in v1["amenities_summary"]

    async def test_stop_route_filter(self, hass: MagicMock) -> None:
        client = MagicMock()
        client.get_stop_arrivals = AsyncMock(
            return_value=[
                Arrival(route_code="500T", eta_minutes=3, kapino="C-1753"),
                Arrival(route_code="14M", eta_minutes=7, kapino="A-001"),
            ]
        )
        entry = _make_entry(
            "stop_entry_filter",
            {
                CONF_FEED_TYPE: FEED_STOP,
                CONF_STOP_CODE: "301341",
                CONF_ROUTE_MODE: ROUTE_MODE_SELECTED,
                CONF_SELECTED_ROUTES: ["500T"],
            },
        )
        coord = IettEntryCoordinator(hass, entry, client)
        data = await coord._async_update_data()

        assert len(data["vehicles"]) == 1
        assert data["vehicles"][0][ATTR_OPT_HATNO] == "500T"


# ---------------------------------------------------------------------------
# Route Coordinator (1b) Tests
# ---------------------------------------------------------------------------


class TestRouteCoordinator:
    async def test_route_update_and_depar_filter(self, hass: MagicMock) -> None:
        client = MagicMock()
        client.get_route_buses = AsyncMock(
            return_value=[
                BusPosition(kapino="C-1753", route_code="500T", direction_letter="G"),
                BusPosition(kapino="A-001", route_code="500T", direction_letter="D"),
            ]
        )
        client.get_route_schedule = AsyncMock(
            return_value=[
                ScheduledDeparture(
                    route_code="500T",
                    route_variant="500T_G_D0",
                    direction="G",
                    departure_time="23:59",
                ),
                ScheduledDeparture(
                    route_code="500T",
                    route_variant="500T_G_D12",
                    direction="G",
                    departure_time="23:45",
                ),
                ScheduledDeparture(
                    route_code="500T",
                    route_variant="500T_D_D0",
                    direction="D",
                    departure_time="23:30",
                ),
            ]
        )
        client.get_announcements = AsyncMock(
            return_value=[
                Announcement(
                    route_code="500T",
                    type="Uyarı",
                    message="Sefer gecikmeli",
                )
            ]
        )

        entry = _make_entry(
            "route_entry_1",
            {
                CONF_FEED_TYPE: FEED_ROUTE,
                CONF_ROUTE_CODE: "500T",
                CONF_INCLUDE_ACTIVE_BUSES: True,
                CONF_INCLUDE_SCHEDULE: True,
                CONF_INCLUDE_ANNOUNCEMENTS: True,
                CONF_DEPAR_MODE: DEPAR_MODE_BASE_ONLY,
            },
        )
        coord = IettEntryCoordinator(hass, entry, client)
        data = await coord._async_update_data()

        assert data["feed_type"] == FEED_ROUTE
        assert data["route_code"] == "500T"
        assert data["active_buses_count"] == 2
        assert data["gidis_count"] == 1
        assert data["donus_count"] == 1
        assert data["has_alert"] is True
        assert data["announcement_count"] == 1
        assert len(data["upcoming_departures"]) == 2  # D0 only


# ---------------------------------------------------------------------------
# Vehicle Coordinator (1c) Tests
# ---------------------------------------------------------------------------


class TestVehicleCoordinator:
    async def test_vehicle_online_mph_conversion(self, hass: MagicMock) -> None:
        client = MagicMock()
        client.get_vehicle_status = AsyncMock(
            return_value=BusPosition(
                kapino="C-1753",
                plate="34 HO 1234",
                latitude=41.0450,
                longitude=29.0020,
                speed=36,
                route_code="500T",
                operator="İETT",
                last_seen="14:30:00",
            )
        )
        entry = _make_entry(
            "veh_entry_1",
            {
                CONF_FEED_TYPE: FEED_VEHICLE,
                CONF_KAPINO: "C-1753",
                CONF_SPEED_UNIT: SPEED_UNIT_MPH,
            },
        )
        coord = IettEntryCoordinator(hass, entry, client)
        data = await coord._async_update_data()

        assert data["feed_type"] == FEED_VEHICLE
        assert data["kapino"] == "C-1753"
        assert data["online"] is True
        assert data["plate"] == "34 HO 1234"
        assert data["speed"] == 22.4  # 36 km/h * 0.621371 = 22.4 mph
        assert data["speed_unit"] == "mph"
        assert data["route_code"] == "500T"

    async def test_vehicle_offline(self, hass: MagicMock) -> None:
        client = MagicMock()
        client.get_vehicle_status = AsyncMock(return_value=None)
        entry = _make_entry(
            "veh_entry_offline",
            {
                CONF_FEED_TYPE: FEED_VEHICLE,
                CONF_KAPINO: "A-001",
                CONF_SPEED_UNIT: SPEED_UNIT_KMH,
            },
        )
        coord = IettEntryCoordinator(hass, entry, client)
        data = await coord._async_update_data()

        assert data["feed_type"] == FEED_VEHICLE
        assert data["kapino"] == "A-001"
        assert data["online"] is False
        assert data["plate"] is None
        assert data["latitude"] is None
        assert data["speed"] is None
