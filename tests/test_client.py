"""Tests for IettMiddleClient — all HTTP mocked with aioresponses."""
from __future__ import annotations

import re
import pytest
from aioresponses import aioresponses

from custom_components.iett.client import IettMiddleClient, IettMiddleError
from custom_components.iett.models import Arrival, Announcement, BusPosition, ScheduledDeparture
from tests.conftest import (
    ANNOUNCEMENTS_JSON,
    ARRIVALS_JSON,
    FLEET_JSON,
    MIDDLE_BASE,
    ROUTE_FLEET_JSON,
    SCHEDULE_JSON,
)

FLEET_RE   = re.compile(rf"{re.escape(MIDDLE_BASE)}/v1/fleet.*")
BUSES_RE   = re.compile(rf"{re.escape(MIDDLE_BASE)}/v1/routes/.*?/buses.*")
ARRIVES_RE = re.compile(rf"{re.escape(MIDDLE_BASE)}/v1/stops/.*?/arrivals.*")
SCHED_RE   = re.compile(rf"{re.escape(MIDDLE_BASE)}/v1/routes/.*?/schedule.*")
ANNS_RE    = re.compile(rf"{re.escape(MIDDLE_BASE)}/v1/routes/.*?/announcements.*")


@pytest.fixture()
async def client(session):
    return IettMiddleClient(session, MIDDLE_BASE)


class TestGetAllBuses:
    async def test_returns_fleet(self, client):
        with aioresponses() as m:
            m.get(FLEET_RE, payload=FLEET_JSON)
            buses = await client.get_all_buses()
        assert len(buses) == 1
        assert isinstance(buses[0], BusPosition)
        assert buses[0].kapino == "A-001"

    async def test_raises_on_error(self, client):
        with aioresponses() as m:
            m.get(FLEET_RE, status=500)
            with pytest.raises(IettMiddleError):
                await client.get_all_buses()


class TestGetRouteBuses:
    async def test_returns_buses(self, client):
        with aioresponses() as m:
            m.get(BUSES_RE, payload=ROUTE_FLEET_JSON)
            buses = await client.get_route_buses("500T")
        assert buses[0].route_code == "500T"
        assert buses[0].speed == 42


class TestGetStopArrivals:
    async def test_returns_arrivals(self, client):
        with aioresponses() as m:
            m.get(ARRIVES_RE, payload=ARRIVALS_JSON)
            arrivals = await client.get_stop_arrivals("220602")
        assert len(arrivals) == 2
        assert isinstance(arrivals[0], Arrival)
        assert arrivals[0].eta_minutes == 4

    async def test_returns_empty_list(self, client):
        with aioresponses() as m:
            m.get(ARRIVES_RE, payload=[])
            arrivals = await client.get_stop_arrivals("000000")
        assert arrivals == []


class TestGetRouteSchedule:
    async def test_returns_schedule(self, client):
        with aioresponses() as m:
            m.get(SCHED_RE, payload=SCHEDULE_JSON)
            deps = await client.get_route_schedule("500T")
        assert isinstance(deps[0], ScheduledDeparture)
        assert deps[0].departure_time == "05:55"


class TestGetAnnouncements:
    async def test_returns_announcements(self, client):
        with aioresponses() as m:
            m.get(ANNS_RE, payload=ANNOUNCEMENTS_JSON)
            anns = await client.get_announcements("500T")
        assert isinstance(anns[0], Announcement)
        assert "500T" in anns[0].route_code

    async def test_empty(self, client):
        with aioresponses() as m:
            m.get(ANNS_RE, payload=[])
            anns = await client.get_announcements("NOTEXIST")
        assert anns == []
