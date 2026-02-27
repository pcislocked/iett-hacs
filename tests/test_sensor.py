"""Tests for IettSensor — focuses on _state_value pure function."""
from __future__ import annotations

from custom_components.iett.const import (
    FEED_ALL_FLEET,
    FEED_ROUTE_ANNOUNCEMENTS,
    FEED_ROUTE_FLEET,
    FEED_ROUTE_SCHEDULE,
    FEED_STOP_ARRIVALS,
)
from custom_components.iett.models import Announcement, Arrival, BusPosition, ScheduledDeparture
from custom_components.iett.sensor import _state_value  # type: ignore[reportPrivateUsage]


# ---------------------------------------------------------------------------
# _state_value — pure function tests (no HA needed)
# ---------------------------------------------------------------------------

class TestStateValueEmptyData:
    def test_all_feed_types_return_zero_on_empty(self) -> None:
        for feed in (FEED_ALL_FLEET, FEED_ROUTE_FLEET, FEED_STOP_ARRIVALS,
                     FEED_ROUTE_SCHEDULE, FEED_ROUTE_ANNOUNCEMENTS):
            assert _state_value(feed, []) == 0, f"{feed} should return 0 for empty list"


class TestStateValueFleet:
    def _bus(self, kapino: str = "A-001") -> BusPosition:
        return BusPosition(
            kapino=kapino,
            latitude=41.0,
            longitude=29.0,
            speed=0,
            last_seen="00:00:00",
        )

    def test_all_fleet_returns_count(self) -> None:
        buses = [self._bus("A-001"), self._bus("B-002"), self._bus("C-003")]
        assert _state_value(FEED_ALL_FLEET, buses) == 3

    def test_route_fleet_returns_count(self) -> None:
        buses = [self._bus("A-001")]
        assert _state_value(FEED_ROUTE_FLEET, buses) == 1

    def test_single_bus(self) -> None:
        assert _state_value(FEED_ALL_FLEET, [self._bus()]) == 1


class TestStateValueArrivals:
    def _arrival(self, eta: int | None, route: str = "500T") -> Arrival:
        return Arrival(
            route_code=route,
            destination="Test",
            eta_raw=f"{eta} dk" if eta is not None else "?",
            eta_minutes=eta,
        )

    def test_returns_minimum_eta(self) -> None:
        arrivals = [self._arrival(12), self._arrival(4), self._arrival(7)]
        assert _state_value(FEED_STOP_ARRIVALS, arrivals) == 4

    def test_returns_none_when_all_eta_are_none(self) -> None:
        arrivals = [self._arrival(None), self._arrival(None)]
        assert _state_value(FEED_STOP_ARRIVALS, arrivals) is None

    def test_ignores_none_eta_in_minimum(self) -> None:
        arrivals = [self._arrival(None), self._arrival(5)]
        assert _state_value(FEED_STOP_ARRIVALS, arrivals) == 5

    def test_single_arrival(self) -> None:
        assert _state_value(FEED_STOP_ARRIVALS, [self._arrival(8)]) == 8


class TestStateValueSchedule:
    def _dep(self, hh: int, mm: int) -> ScheduledDeparture:
        return ScheduledDeparture(
            route_code="500T",
            route_name="TUZLA - LEVENT",
            route_variant="500T_D_D0",
            direction="D",
            day_type="H",
            service_type="ÖHO",
            departure_time=f"{hh:02d}:{mm:02d}",
        )

    def test_returns_minutes_to_next(self) -> None:
        from datetime import datetime
        now = datetime.now()
        future_hh = (now.hour + 1) % 24
        deps = [self._dep(future_hh, now.minute)]
        result = _state_value(FEED_ROUTE_SCHEDULE, deps)
        # ~60 minutes away, allow ±2 min for clock drift in test
        assert result is not None
        assert 55 <= result <= 65

    def test_returns_none_on_parse_error(self) -> None:
        bad = ScheduledDeparture(
            route_code="X",
            route_name="X",
            route_variant="X",
            direction="D",
            day_type="H",
            service_type="X",
            departure_time="INVALID",
        )
        result = _state_value(FEED_ROUTE_SCHEDULE, [bad])
        assert result is None

    def test_wraps_past_to_next_day(self) -> None:
        # Departure at 00:01 is always in the future or 1439 mins away
        deps = [self._dep(0, 1)]
        result = _state_value(FEED_ROUTE_SCHEDULE, deps)
        assert result is not None
        assert 0 <= result <= 1440


class TestStateValueAnnouncements:
    def _ann(self, route: str = "500T") -> Announcement:
        return Announcement(
            route_code=route,
            route_name="TUZLA - LEVENT",
            type="Günlük",
            updated_at="09:00",
            message="Test announcement",
        )

    def test_returns_count(self) -> None:
        anns = [self._ann(), self._ann(), self._ann()]
        assert _state_value(FEED_ROUTE_ANNOUNCEMENTS, anns) == 3

    def test_single_announcement(self) -> None:
        assert _state_value(FEED_ROUTE_ANNOUNCEMENTS, [self._ann()]) == 1
