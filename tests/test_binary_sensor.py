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
            "announcements": [
                {
                    "route_code": "500T",
                    "type": "Uyarı",
                    "message": "Gecikme var",
                    "updated_at": "27.10.2026 14:30:00",
                }
            ],
        }
    )
    device = DeviceInfo(identifiers={(DOMAIN, "route_500T")})
    sensor = IettRouteAlertBinarySensor(coord, _mock_entry(), device)

    assert sensor.is_on is True
    attrs = sensor.extra_state_attributes
    assert len(attrs["announcements"]) == 1
    assert attrs["duyuru_sayisi"] == 1
    assert attrs["announcement_count"] == 1
    assert attrs["sorun"] == "[Uyarı] Gecikme var"
    assert attrs["problem"] == "[Uyarı] Gecikme var"
    assert attrs["son_duyuru"] == "Gecikme var"
    assert attrs["duyuru_tipi"] == "Uyarı"
    assert attrs["guncelleme_saati"] == "27.10.2026 14:30:00"
    assert attrs["duyurular"] == ["[Uyarı] Gecikme var"]


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
    attrs = sensor.extra_state_attributes
    assert attrs["announcements"] == []
    assert attrs["duyuru_sayisi"] == 0
    assert attrs["announcement_count"] == 0
    assert attrs["sorun"] == "Aktif sefer sorunu / duyuru bulunmuyor"
    assert attrs["son_duyuru"] is None
    assert attrs["duyuru_tipi"] is None
    assert attrs["duyurular"] == []


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
