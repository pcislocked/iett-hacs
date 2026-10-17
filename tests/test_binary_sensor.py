"""Tests for İETT binary sensor platform v2."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

from homeassistant.helpers.device_registry import DeviceInfo

from custom_components.iett.binary_sensor import IettRouteAlertBinarySensor
from custom_components.iett.const import CONF_ROUTE_CODE, DOMAIN


def _mock_coord(data: dict[str, Any]) -> MagicMock:
    coord = MagicMock()
    coord.data = data
    return coord


def _mock_entry() -> MagicMock:
    entry = MagicMock()
    entry.entry_id = "test_route_entry"
    entry.data = {CONF_ROUTE_CODE: "500T"}
    return entry


def test_route_alert_binary_sensor_on() -> None:
    coord = _mock_coord(
        {
            "has_alert": True,
            "announcements": [{"type": "Uyarı", "message": "Gecikme var"}],
        }
    )
    device = DeviceInfo(identifiers={(DOMAIN, "route_500T")})
    sensor = IettRouteAlertBinarySensor(coord, _mock_entry(), device)

    assert sensor.is_on is True
    assert len(sensor.extra_state_attributes["announcements"]) == 1


def test_route_alert_binary_sensor_off() -> None:
    coord = _mock_coord(
        {
            "has_alert": False,
            "announcements": [],
        }
    )
    device = DeviceInfo(identifiers={(DOMAIN, "route_500T")})
    sensor = IettRouteAlertBinarySensor(coord, _mock_entry(), device)

    assert sensor.is_on is False
    assert sensor.extra_state_attributes["announcements"] == []


async def test_async_setup_entry_binary_sensor(hass: MagicMock) -> None:
    from custom_components.iett.binary_sensor import async_setup_entry
    from custom_components.iett.const import CONF_FEED_TYPE, CONF_ROUTE_CODE, FEED_ROUTE

    entry = _mock_entry()
    entry.data = {CONF_FEED_TYPE: FEED_ROUTE, CONF_ROUTE_CODE: "500T"}
    coord = _mock_coord({"has_alert": False, "announcements": []})
    hass.data[DOMAIN] = {entry.entry_id: coord}

    entities: list[Any] = []
    await async_setup_entry(hass, entry, entities.extend)
    assert len(entities) == 1
