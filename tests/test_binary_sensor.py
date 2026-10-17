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
