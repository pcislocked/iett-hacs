"""Dataclass models matching iett-middle REST API response shapes.

Zero Home Assistant imports — usable in plain Python tests.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict


@dataclass
class BusPosition:
    kapino: str
    latitude: float
    longitude: float
    speed: int
    last_seen: str
    plate: str | None = None
    operator: str | None = None
    route_code: str | None = None
    route_name: str | None = None
    direction: str | None = None
    nearest_stop: str | None = None

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class Arrival:
    route_code: str
    destination: str
    eta_raw: str
    eta_minutes: int | None = None

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class ScheduledDeparture:
    route_code: str
    route_name: str
    route_variant: str
    direction: str
    day_type: str
    service_type: str
    departure_time: str

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class Announcement:
    route_code: str
    route_name: str
    type: str
    updated_at: str
    message: str

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class RouteStop:
    route_code: str
    direction: str
    sequence: int
    stop_code: str
    stop_name: str
    latitude: float
    longitude: float
    district: str | None = None

    def as_dict(self) -> dict:
        return asdict(self)


# Type alias for the coordinator payload
FeedData = list[BusPosition] | list[Arrival] | list[ScheduledDeparture] | list[Announcement]
