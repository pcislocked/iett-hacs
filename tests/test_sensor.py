"""Tests for İETT sensor platform v2."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

from homeassistant.helpers.device_registry import DeviceInfo

from custom_components.iett.const import (
    ATTR_OPT_DIST_STOP,
    ATTR_OPT_ETA,
    ATTR_OPT_ETA_MMSS,
    ATTR_OPT_HATNO,
    ATTR_OPT_PLAKA,
    ATTR_OPT_SPEED,
    CONF_FEED_TYPE,
    CONF_STOP_CODE,
    CONF_STOP_NAME,
    DOMAIN,
    FEED_STOP,
)
from custom_components.iett.sensor import (
    IettRootFleetSizeSensor,
    IettRootTrafficSensor,
    IettRouteActiveBusesSensor,
    IettRouteAnnouncementsSensor,
    IettRouteDepartureSensor,
    IettStopGeneralSensor,
    IettStopSlotAttrSensor,
    IettStopVehicleObjectSensor,
    IettVehicleCoordsSensor,
    IettVehiclePlateSensor,
    IettVehicleRouteSensor,
    IettVehicleSpeedSensor,
)


def _mock_coord(data: dict[str, Any]) -> MagicMock:
    coord = MagicMock()
    coord.data = data
    return coord


def _mock_device() -> DeviceInfo:
    return DeviceInfo(identifiers={(DOMAIN, "test")})


def _mock_entry(data: dict[str, Any]) -> MagicMock:
    entry = MagicMock()
    entry.entry_id = "test_entry"
    entry.data = data
    return entry


# ---------------------------------------------------------------------------
# 4 Root Sensors Tests
# ---------------------------------------------------------------------------


class TestRootSensors:
    def test_root_traffic_sensors(self) -> None:
        coord = _mock_coord(
            {
                "traffic_overall": 42,
                "traffic_europe": 46,
                "traffic_anatolia": 38,
                "active_fleet_count": 3500,
            }
        )
        s_gen = IettRootTrafficSensor(
            coord, "traffic_overall", "u_gen", "Genel Trafik", _mock_device()
        )
        s_av = IettRootTrafficSensor(
            coord, "traffic_europe", "u_av", "Avrupa Trafik", _mock_device()
        )
        s_an = IettRootTrafficSensor(
            coord, "traffic_anatolia", "u_an", "Anadolu Trafik", _mock_device()
        )

        assert s_gen.native_value == 42
        assert s_av.native_value == 46
        assert s_an.native_value == 38

    def test_root_active_fleet_strict_recorder_guardrail(self) -> None:
        coord = _mock_coord(
            {
                "active_fleet_count": 3500,
            }
        )
        fleet_sensor = IettRootFleetSizeSensor(
            coord, "u_fleet", "İETT Aktif Filo Boyutu", _mock_device()
        )

        assert fleet_sensor.native_value == 3500
        # CRITICAL RECORDER GUARDRAIL: extra_state_attributes MUST be empty dict!
        assert fleet_sensor.extra_state_attributes == {}


# ---------------------------------------------------------------------------
# 1a Stop Sensors Tests
# ---------------------------------------------------------------------------


class TestStopSensors:
    def test_stop_general_sensor(self) -> None:
        entry = _mock_entry(
            {
                CONF_FEED_TYPE: FEED_STOP,
                CONF_STOP_CODE: "220602",
                CONF_STOP_NAME: "BEŞİKTAŞ MEYDAN",
            }
        )
        coord = _mock_coord(
            {
                "arriving_count": 4,
                "vehicles": [{"hatno": "500T", "eta": 3}],
            }
        )
        sensor = IettStopGeneralSensor(coord, entry, _mock_device())
        assert sensor.native_value == 4

    def test_stop_vehicle_slot_object_and_attr_sensors(self) -> None:
        entry = _mock_entry({CONF_FEED_TYPE: FEED_STOP, CONF_STOP_CODE: "220602"})
        coord = _mock_coord(
            {
                "vehicles": [
                    {
                        ATTR_OPT_HATNO: "500T",
                        ATTR_OPT_PLAKA: "34 HO 1234",
                        ATTR_OPT_ETA: 5,
                        ATTR_OPT_ETA_MMSS: "05:00",
                        ATTR_OPT_SPEED: 35,
                        ATTR_OPT_DIST_STOP: 1200,
                        "destination": "CEVİZLİBAĞ",
                        "kapino": "C-1753",
                        "latitude": 41.0450,
                        "longitude": 29.0020,
                    }
                ]
            }
        )
        # Main slot object sensor
        slot_obj = IettStopVehicleObjectSensor(coord, entry, _mock_device(), slot=1)
        assert slot_obj.native_value == "500T (5 dk)"
        assert slot_obj.extra_state_attributes["kapino"] == "C-1753"
        assert slot_obj.extra_state_attributes["speed"] == 35

        # Granular attribute sensors
        s_hat = IettStopSlotAttrSensor(
            coord, entry, _mock_device(), slot=1, attr_key=ATTR_OPT_HATNO, name="Hat No"
        )
        assert s_hat.native_value == "500T"

        s_eta = IettStopSlotAttrSensor(
            coord, entry, _mock_device(), slot=1, attr_key=ATTR_OPT_ETA, name="ETA"
        )
        assert s_eta.native_value == 5

        s_mmss = IettStopSlotAttrSensor(
            coord, entry, _mock_device(), slot=1, attr_key=ATTR_OPT_ETA_MMSS, name="ETA mm:ss"
        )
        assert s_mmss.native_value == "05:00"

        s_plate = IettStopSlotAttrSensor(
            coord, entry, _mock_device(), slot=1, attr_key=ATTR_OPT_PLAKA, name="Plaka"
        )
        assert s_plate.native_value == "34 HO 1234"

        s_dist = IettStopSlotAttrSensor(
            coord, entry, _mock_device(), slot=1, attr_key=ATTR_OPT_DIST_STOP, name="Mesafe"
        )
        assert s_dist.native_value == 1200


# ---------------------------------------------------------------------------
# 1b Route Sensors Tests
# ---------------------------------------------------------------------------


class TestRouteSensors:
    def test_route_sensors(self) -> None:
        entry = _mock_entry({CONF_FEED_TYPE: "route", "route_code": "500T"})
        coord = _mock_coord(
            {
                "active_buses_count": 8,
                "announcement_count": 2,
                "next_dep_g_min": 14,
                "next_dep_g_time": "14:45",
            }
        )
        buses_s = IettRouteActiveBusesSensor(coord, entry, _mock_device())
        assert buses_s.native_value == 8

        ann_s = IettRouteAnnouncementsSensor(coord, entry, _mock_device())
        assert ann_s.native_value == 2

        dep_s = IettRouteDepartureSensor(
            coord, entry, _mock_device(), "G", "Sıradaki Kalkış (Gidiş)"
        )
        assert dep_s.native_value == 14
        assert dep_s.extra_state_attributes["departure_time"] == "14:45"


# ---------------------------------------------------------------------------
# 1c Vehicle Sensors Tests
# ---------------------------------------------------------------------------


class TestVehicleSensors:
    def test_vehicle_sensors_online(self) -> None:
        entry = _mock_entry({"feed_type": "vehicle", "kapino": "C-1753"})
        coord = _mock_coord(
            {
                "online": True,
                "plate": "34 HO 1234",
                "latitude": 41.0450,
                "longitude": 29.0020,
                "speed": 35,
                "route_code": "500T",
            }
        )
        plate_s = IettVehiclePlateSensor(coord, entry, _mock_device())
        coords_s = IettVehicleCoordsSensor(coord, entry, _mock_device())
        speed_s = IettVehicleSpeedSensor(coord, entry, _mock_device())
        route_s = IettVehicleRouteSensor(coord, entry, _mock_device())

        assert plate_s.native_value == "34 HO 1234"
        assert coords_s.native_value == "41.045, 29.002"
        assert speed_s.native_value == 35
        assert route_s.native_value == "500T"

    def test_vehicle_sensors_offline(self) -> None:
        entry = _mock_entry({"feed_type": "vehicle", "kapino": "C-1753"})
        coord = _mock_coord(
            {
                "online": False,
                "plate": None,
                "latitude": None,
                "longitude": None,
                "speed": None,
                "route_code": None,
            }
        )
        plate_s = IettVehiclePlateSensor(coord, entry, _mock_device())
        coords_s = IettVehicleCoordsSensor(coord, entry, _mock_device())
        speed_s = IettVehicleSpeedSensor(coord, entry, _mock_device())

        assert plate_s.native_value is None
        assert coords_s.native_value == "Bilinmiyor"
        assert speed_s.native_value is None
