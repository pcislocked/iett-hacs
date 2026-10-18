"""Data models for the İETT integration.

All models tolerate unknown extra fields from upstream payloads.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from .normalizers import normalize_kapino, normalize_plate


@dataclass(slots=True)
class RootStatus:
    """Snapshot for Istanbul city traffic and active fleet size."""

    traffic_overall: int = 0
    traffic_europe: int = 0
    traffic_anatolia: int = 0
    active_fleet_count: int = 0

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RootStatus:
        return cls(
            traffic_overall=int(data.get("traffic_overall", 0)),
            traffic_europe=int(data.get("traffic_europe", 0)),
            traffic_anatolia=int(data.get("traffic_anatolia", 0)),
            active_fleet_count=int(data.get("active_fleet_count", 0)),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "traffic_overall": self.traffic_overall,
            "traffic_europe": self.traffic_europe,
            "traffic_anatolia": self.traffic_anatolia,
            "active_fleet_count": self.active_fleet_count,
        }


def _parse_amenity(val: Any) -> bool | None:
    """Safely parse boolean amenity flags from heterogeneous upstream types."""
    if val is None:
        return None
    if isinstance(val, bool):
        return val
    s = str(val).strip().lower()
    if s in ("1", "true", "var", "evet", "yes"):
        return True
    if s in ("0", "false", "yok", "hayir", "hayır", "no"):
        return False
    try:
        return bool(int(s))
    except (ValueError, TypeError):
        return None


@dataclass(slots=True)
class Amenities:
    """Bus equipment and accessibility features."""

    usb: bool | None = None
    wifi: bool | None = None
    ac: bool | None = None
    accessible: bool | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> Amenities:
        if not data:
            return cls()
        return cls(
            usb=_parse_amenity(data.get("usb")),
            wifi=_parse_amenity(data.get("wifi")),
            ac=_parse_amenity(data.get("ac") or data.get("klima")),
            accessible=_parse_amenity(data.get("accessible") or data.get("engelli")),
        )

    def to_dict(self) -> dict[str, bool | None]:
        return {
            "usb": self.usb,
            "wifi": self.wifi,
            "ac": self.ac,
            "accessible": self.accessible,
        }


@dataclass(slots=True)
class Arrival:
    """Live arrival of a bus at a stop."""

    route_code: str
    destination: str = ""
    eta_minutes: int | None = None
    eta_raw: str = ""
    kapino: str | None = None
    plate: str | None = None
    lat: float | None = None
    lon: float | None = None
    speed_kmh: int | None = None
    last_seen_ts: str | None = None
    amenities: Amenities = field(default_factory=Amenities)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Arrival:
        amenities_data = data.get("amenities")
        amenities = (
            Amenities.from_dict(amenities_data) if isinstance(amenities_data, dict) else Amenities()
        )
        eta_raw = str(data.get("eta_raw", ""))
        eta_min = data.get("eta_minutes")
        try:
            eta_minutes_int = int(eta_min) if eta_min is not None else None
        except (ValueError, TypeError):
            eta_minutes_int = None

        speed_raw = data.get("speed_kmh")
        try:
            speed_int = int(speed_raw) if speed_raw is not None else None
        except (ValueError, TypeError):
            speed_int = None

        raw_dest = str(data.get("destination", "")).strip()
        cleaned_dest = re.sub(r"\s+", " ", raw_dest)

        return cls(
            route_code=str(data.get("route_code", "")).strip(),
            destination=cleaned_dest,
            eta_minutes=eta_minutes_int,
            eta_raw=eta_raw,
            kapino=normalize_kapino(data.get("kapino")),
            plate=normalize_plate(data.get("plate")),
            lat=float(data["lat"]) if data.get("lat") not in (None, 0.0) else None,
            lon=float(data["lon"]) if data.get("lon") not in (None, 0.0) else None,
            speed_kmh=speed_int,
            last_seen_ts=str(data["last_seen_ts"]) if data.get("last_seen_ts") else None,
            amenities=amenities,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "route_code": self.route_code,
            "destination": self.destination,
            "eta_minutes": self.eta_minutes,
            "eta_raw": self.eta_raw,
            "kapino": self.kapino,
            "plate": self.plate,
            "lat": self.lat,
            "lon": self.lon,
            "speed_kmh": self.speed_kmh,
            "last_seen_ts": self.last_seen_ts,
            "amenities": self.amenities.to_dict(),
        }


@dataclass(slots=True)
class BusPosition:
    """Bus telemetry and live positioning."""

    kapino: str
    plate: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    speed: int | None = None
    operator: str | None = None
    last_seen: str = ""
    route_code: str | None = None
    route_name: str | None = None
    direction: str | None = None
    direction_letter: str | None = None
    nearest_stop: str | None = None
    stop_sequence: int | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> BusPosition:
        try:
            lat = float(data["latitude"]) if data.get("latitude") not in (None, 0.0) else None
        except (ValueError, TypeError):
            lat = None

        try:
            lon = float(data["longitude"]) if data.get("longitude") not in (None, 0.0) else None
        except (ValueError, TypeError):
            lon = None

        try:
            speed = int(data["speed"]) if data.get("speed") is not None else None
        except (ValueError, TypeError):
            speed = None

        try:
            seq = int(data["stop_sequence"]) if data.get("stop_sequence") is not None else None
        except (ValueError, TypeError):
            seq = None

        return cls(
            kapino=normalize_kapino(data.get("kapino")) or str(data.get("kapino", "")),
            plate=normalize_plate(data.get("plate")),
            latitude=lat,
            longitude=lon,
            speed=speed,
            operator=str(data["operator"]) if data.get("operator") else None,
            last_seen=str(data.get("last_seen", "")),
            route_code=str(data["route_code"]) if data.get("route_code") else None,
            route_name=str(data["route_name"]) if data.get("route_name") else None,
            direction=str(data["direction"]) if data.get("direction") else None,
            direction_letter=str(data["direction_letter"])
            if data.get("direction_letter")
            else None,
            nearest_stop=str(data["nearest_stop"]) if data.get("nearest_stop") else None,
            stop_sequence=seq,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "kapino": self.kapino,
            "plate": self.plate,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "speed": self.speed,
            "operator": self.operator,
            "last_seen": self.last_seen,
            "route_code": self.route_code,
            "route_name": self.route_name,
            "direction": self.direction,
            "direction_letter": self.direction_letter,
            "nearest_stop": self.nearest_stop,
            "stop_sequence": self.stop_sequence,
        }


@dataclass(slots=True)
class ScheduledDeparture:
    """Planned timetable departure for a route."""

    route_code: str
    route_name: str = ""
    route_variant: str = ""
    direction: str = ""
    day_type: str = ""
    service_type: str = ""
    departure_time: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ScheduledDeparture:
        raw_day = str(data.get("day_type", "")).strip()
        # Normalize Turkish 'İ' / 'I' to 'H' (Hafta içi)
        day_norm = {"I": "H", "İ": "H", "i": "H", "ı": "H"}
        norm_day = day_norm.get(raw_day, raw_day)

        return cls(
            route_code=str(data.get("route_code", "")).strip(),
            route_name=str(data.get("route_name", "")).strip(),
            route_variant=str(data.get("route_variant", "")).strip(),
            direction=str(data.get("direction", "")).strip(),
            day_type=norm_day,
            service_type=str(data.get("service_type", "")).strip(),
            departure_time=str(data.get("departure_time", "")).strip(),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "route_code": self.route_code,
            "route_name": self.route_name,
            "route_variant": self.route_variant,
            "direction": self.direction,
            "day_type": self.day_type,
            "service_type": self.service_type,
            "departure_time": self.departure_time,
        }


@dataclass(slots=True)
class Announcement:
    """Route disruption or notice."""

    route_code: str
    route_name: str = ""
    type: str = ""
    updated_at: str = ""
    message: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Announcement:
        return cls(
            route_code=str(data.get("route_code", "")).strip(),
            route_name=str(data.get("route_name", "")).strip(),
            type=str(data.get("type", "")).strip(),
            updated_at=str(data.get("updated_at", "")).strip(),
            message=str(data.get("message", "")).strip(),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "route_code": self.route_code,
            "route_name": self.route_name,
            "type": self.type,
            "updated_at": self.updated_at,
            "message": self.message,
        }


@dataclass(slots=True)
class StopMetadata:
    """Physical and static metadata for a stop."""

    dcode: str
    name: str
    latitude: float | None = None
    longitude: float | None = None
    direction: str | None = None
    district: str | None = None
    stop_type: str | None = None
    smart_stop: bool | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> StopMetadata:
        try:
            lat = float(data["latitude"]) if data.get("latitude") not in (None, 0.0) else None
        except (ValueError, TypeError):
            lat = None

        try:
            lon = float(data["longitude"]) if data.get("longitude") not in (None, 0.0) else None
        except (ValueError, TypeError):
            lon = None

        smart = data.get("smart_stop")
        return cls(
            dcode=str(data.get("dcode", "")).strip(),
            name=str(data.get("name", "")).strip(),
            latitude=lat,
            longitude=lon,
            direction=str(data["direction"]) if data.get("direction") else None,
            district=str(data["district"]) if data.get("district") else None,
            stop_type=str(data["stop_type"]) if data.get("stop_type") else None,
            smart_stop=bool(smart) if smart is not None else None,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "dcode": self.dcode,
            "name": self.name,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "direction": self.direction,
            "district": self.district,
            "stop_type": self.stop_type,
            "smart_stop": self.smart_stop,
        }


@dataclass(slots=True)
class RouteSearchResult:
    """Search result for a route query."""

    hat_kodu: str
    name: str

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RouteSearchResult:
        return cls(
            hat_kodu=str(data.get("hat_kodu", "")).strip(),
            name=str(data.get("name", "")).strip(),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "hat_kodu": self.hat_kodu,
            "name": self.name,
        }
