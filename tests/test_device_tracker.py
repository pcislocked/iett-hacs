"""Tests for İETT device tracker platform v2."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

from homeassistant.components.device_tracker import SourceType
from homeassistant.helpers.device_registry import DeviceInfo

from custom_components.iett.const import CONF_KAPINO, DOMAIN
from custom_components.iett.device_tracker import (
    IettStopSlotTrackerEntity,
    IettVehicleTracker,
)


def _mock_coord(data: dict[str, Any]) -> MagicMock:
    coord = MagicMock()
    coord.data = data
    return coord


def _mock_entry(data: dict[str, Any]) -> MagicMock:
    entry = MagicMock()
    entry.entry_id = "test_tracker_entry"
    entry.data = data
    return entry


def test_vehicle_tracker_online() -> None:
    coord = _mock_coord(
        {
            "online": True,
            "plate": "34 HO 1234",
            "latitude": 41.0450,
            "longitude": 29.0020,
            "speed": 35,
            "speed_unit": "km/h",
            "route_code": "500T",
        }
    )
    entry = _mock_entry({CONF_KAPINO: "C-1753"})
    device = DeviceInfo(identifiers={(DOMAIN, "vehicle_C-1753")})
    tracker = IettVehicleTracker(coord, entry, device, "C-1753")

    assert tracker.source_type == SourceType.GPS
    assert tracker.latitude == 41.0450
    assert tracker.longitude == 29.0020
    assert tracker.extra_state_attributes["kapino"] == "C-1753"
    assert tracker.extra_state_attributes["plate"] == "34 HO 1234"
    assert tracker.extra_state_attributes["online"] is True


def test_vehicle_tracker_offline() -> None:
    coord = _mock_coord(
        {
            "online": False,
            "plate": None,
            "latitude": None,
            "longitude": None,
        }
    )
    entry = _mock_entry({CONF_KAPINO: "A-001"})
    device = DeviceInfo(identifiers={(DOMAIN, "vehicle_A-001")})
    tracker = IettVehicleTracker(coord, entry, device, "A-001")

    assert tracker.latitude is None
    assert tracker.longitude is None
    assert tracker.extra_state_attributes["online"] is False


def test_stop_slot_tracker() -> None:
    coord = _mock_coord(
        {
            "vehicles": [
                {
                    "kapino": "C-1753",
                    "latitude": 41.0450,
                    "longitude": 29.0020,
                    "hatno": "500T",
                }
            ]
        }
    )
    entry = _mock_entry({})
    device = DeviceInfo(identifiers={(DOMAIN, "stop_301341")})
    tracker = IettStopSlotTrackerEntity(coord, entry, device, slot=1)

    assert tracker.source_type == SourceType.GPS
    assert tracker.latitude == 41.0450
    assert tracker.longitude == 29.0020
    assert tracker.extra_state_attributes["kapino"] == "C-1753"


async def test_async_setup_entry_vehicle_tracker(hass: MagicMock) -> None:
    from custom_components.iett.const import CONF_FEED_TYPE, CONF_KAPINO, FEED_VEHICLE
    from custom_components.iett.device_tracker import async_setup_entry

    entry = _mock_entry({CONF_FEED_TYPE: FEED_VEHICLE, CONF_KAPINO: "C-1753"})
    coord = _mock_coord({"latitude": 41.0, "longitude": 29.0})
    hass.data[DOMAIN] = {entry.entry_id: coord}

    entities: list[Any] = []
    await async_setup_entry(hass, entry, entities.extend)
    assert len(entities) == 1


async def test_async_setup_entry_stop_tracker(hass: MagicMock) -> None:
    from custom_components.iett.const import (
        ATTR_OPT_COORDS_TRACKER,
        CONF_FEED_TYPE,
        CONF_STOP_ATTRIBUTES,
        CONF_STOP_CODE,
        CONF_STOP_NAME,
        FEED_STOP,
    )
    from custom_components.iett.device_tracker import async_setup_entry

    entry = _mock_entry(
        {
            CONF_FEED_TYPE: FEED_STOP,
            CONF_STOP_CODE: "301341",
            CONF_STOP_NAME: "BEŞİKTAŞ",
            CONF_STOP_ATTRIBUTES: [ATTR_OPT_COORDS_TRACKER],
        }
    )
    coord = _mock_coord({"vehicles": [{"latitude": 41.0, "longitude": 29.0}]})
    hass.data[DOMAIN] = {entry.entry_id: coord}

    entities: list[Any] = []
    await async_setup_entry(hass, entry, entities.extend)
    assert len(entities) == 1
