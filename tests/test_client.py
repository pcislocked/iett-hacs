"""Tests for IettMiddleClient — all HTTP mocked with aioresponses."""
from __future__ import annotations

import re

import aiohttp
import pytest
from aioresponses import aioresponses

from custom_components.iett.client import IettMiddleClient, IettMiddleError
from custom_components.iett.models import Arrival, Announcement, BusPosition, ScheduledDeparture
from tests.conftest import (
    ANNOUNCEMENTS_JSON,
    ARRIVALS_JSON,
    FLEET_JSON,
    GARAGE_LIST_JSON,
    MIDDLE_BASE,
    NEARBY_STOPS_JSON,
    ROUTE_FLEET_JSON,
    ROUTE_STOPS_JSON,
    SCHEDULE_JSON,
    STOP_DETAIL_JSON,
)

FLEET_RE    = re.compile(rf"{re.escape(MIDDLE_BASE)}/v1/fleet.*")
BUSES_RE    = re.compile(rf"{re.escape(MIDDLE_BASE)}/v1/routes/.*?/buses.*")
ARRIVES_RE  = re.compile(rf"{re.escape(MIDDLE_BASE)}/v1/stops/.*?/arrivals.*")
SCHED_RE    = re.compile(rf"{re.escape(MIDDLE_BASE)}/v1/routes/.*?/schedule.*")
ANNS_RE     = re.compile(rf"{re.escape(MIDDLE_BASE)}/v1/routes/.*?/announcements.*")
DETAIL_RE   = re.compile(rf"{re.escape(MIDDLE_BASE)}/v1/stops/\w+$")
NEARBY_RE   = re.compile(rf"{re.escape(MIDDLE_BASE)}/v1/stops/nearby.*")
GARAGES_RE  = re.compile(rf"{re.escape(MIDDLE_BASE)}/v1/garages.*")
RSTOPS_RE   = re.compile(rf"{re.escape(MIDDLE_BASE)}/v1/routes/.*?/stops.*")


@pytest.fixture()
async def client(session: aiohttp.ClientSession) -> IettMiddleClient:
    return IettMiddleClient(session, MIDDLE_BASE)


class TestGetAllBuses:
    async def test_returns_fleet(self, client: IettMiddleClient) -> None:
        with aioresponses() as m:
            m.get(FLEET_RE, payload=FLEET_JSON)  # type: ignore[misc]
            buses = await client.get_all_buses()
        assert len(buses) == 1
        assert isinstance(buses[0], BusPosition)
        assert buses[0].kapino == "A-001"

    async def test_raises_on_error(self, client: IettMiddleClient) -> None:
        with aioresponses() as m:
            m.get(FLEET_RE, status=500)  # type: ignore[misc]
            with pytest.raises(IettMiddleError):
                await client.get_all_buses()


class TestGetRouteBuses:
    async def test_returns_buses(self, client: IettMiddleClient) -> None:
        with aioresponses() as m:
            m.get(BUSES_RE, payload=ROUTE_FLEET_JSON)  # type: ignore[misc]
            buses = await client.get_route_buses("500T")
        assert buses[0].route_code == "500T"
        assert buses[0].speed == 42


class TestGetStopArrivals:
    async def test_returns_arrivals(self, client: IettMiddleClient) -> None:
        with aioresponses() as m:
            m.get(ARRIVES_RE, payload=ARRIVALS_JSON)  # type: ignore[misc]
            arrivals = await client.get_stop_arrivals("220602")
        assert len(arrivals) == 2
        assert isinstance(arrivals[0], Arrival)
        assert arrivals[0].eta_minutes == 4

    async def test_returns_empty_list(self, client: IettMiddleClient) -> None:
        with aioresponses() as m:
            m.get(ARRIVES_RE, payload=[])  # type: ignore[misc]
            arrivals = await client.get_stop_arrivals("000000")
        assert arrivals == []


class TestGetRouteSchedule:
    async def test_returns_schedule(self, client: IettMiddleClient) -> None:
        with aioresponses() as m:
            m.get(SCHED_RE, payload=SCHEDULE_JSON)  # type: ignore[misc]
            deps = await client.get_route_schedule("500T")
        assert isinstance(deps[0], ScheduledDeparture)
        assert deps[0].departure_time == "05:55"


class TestGetAnnouncements:
    async def test_returns_announcements(self, client: IettMiddleClient) -> None:
        with aioresponses() as m:
            m.get(ANNS_RE, payload=ANNOUNCEMENTS_JSON)  # type: ignore[misc]
            anns = await client.get_announcements("500T")
        assert isinstance(anns[0], Announcement)
        assert "500T" in anns[0].route_code

    async def test_empty(self, client: IettMiddleClient) -> None:
        with aioresponses() as m:
            m.get(ANNS_RE, payload=[])  # type: ignore[misc]
            anns = await client.get_announcements("NOTEXIST")
        assert anns == []


class TestGetStopDetail:
    async def test_returns_detail(self, client: IettMiddleClient) -> None:
        with aioresponses() as m:
            m.get(DETAIL_RE, payload=STOP_DETAIL_JSON)  # type: ignore[misc]
            detail = await client.get_stop_detail("220602")
        assert detail["dcode"] == "220602"
        assert detail["stop_name"] == "AHMET MİTHAT EFENDİ"

    async def test_raises_on_error(self, client: IettMiddleClient) -> None:
        with aioresponses() as m:
            m.get(DETAIL_RE, status=404)  # type: ignore[misc]
            with pytest.raises(IettMiddleError):
                await client.get_stop_detail("000000")


class TestGetNearbyStops:
    async def test_returns_nearby(self, client: IettMiddleClient) -> None:
        with aioresponses() as m:
            m.get(NEARBY_RE, payload=NEARBY_STOPS_JSON)  # type: ignore[misc]
            stops = await client.get_nearby_stops(41.0842, 29.0073)
        assert len(stops) == 1
        assert stops[0]["stop_code"] == "301341"

    async def test_empty_when_none_nearby(self, client: IettMiddleClient) -> None:
        with aioresponses() as m:
            m.get(NEARBY_RE, payload=[])  # type: ignore[misc]
            stops = await client.get_nearby_stops(0.0, 0.0)
        assert stops == []


class TestGetGarages:
    async def test_returns_garages(self, client: IettMiddleClient) -> None:
        with aioresponses() as m:
            m.get(GARAGES_RE, payload=GARAGE_LIST_JSON)  # type: ignore[misc]
            garages = await client.get_garages()
        assert len(garages) == 1
        assert garages[0]["name"] == "IKITELLI GARAJ"

    async def test_raises_on_error(self, client: IettMiddleClient) -> None:
        with aioresponses() as m:
            m.get(GARAGES_RE, status=502)  # type: ignore[misc]
            with pytest.raises(IettMiddleError):
                await client.get_garages()


class TestGetRouteStops:
    async def test_returns_stops(self, client: IettMiddleClient) -> None:
        with aioresponses() as m:
            m.get(RSTOPS_RE, payload=ROUTE_STOPS_JSON)  # type: ignore[misc]
            stops = await client.get_route_stops("500T")
        assert stops[0]["stop_code"] == "301341"

    async def test_raises_on_error(self, client: IettMiddleClient) -> None:
        with aioresponses() as m:
            m.get(RSTOPS_RE, status=503)  # type: ignore[misc]
            with pytest.raises(IettMiddleError):
                await client.get_route_stops("500T")



@pytest.fixture()
async def client(session: aiohttp.ClientSession) -> IettMiddleClient:
    return IettMiddleClient(session, MIDDLE_BASE)


class TestGetAllBuses:
    async def test_returns_fleet(self, client: IettMiddleClient) -> None:
        with aioresponses() as m:
            m.get(FLEET_RE, payload=FLEET_JSON)  # type: ignore[misc]
            buses = await client.get_all_buses()
        assert len(buses) == 1
        assert isinstance(buses[0], BusPosition)
        assert buses[0].kapino == "A-001"

    async def test_raises_on_error(self, client: IettMiddleClient) -> None:
        with aioresponses() as m:
            m.get(FLEET_RE, status=500)  # type: ignore[misc]
            with pytest.raises(IettMiddleError):
                await client.get_all_buses()


class TestGetRouteBuses:
    async def test_returns_buses(self, client: IettMiddleClient) -> None:
        with aioresponses() as m:
            m.get(BUSES_RE, payload=ROUTE_FLEET_JSON)  # type: ignore[misc]
            buses = await client.get_route_buses("500T")
        assert buses[0].route_code == "500T"
        assert buses[0].speed == 42


class TestGetStopArrivals:
    async def test_returns_arrivals(self, client: IettMiddleClient) -> None:
        with aioresponses() as m:
            m.get(ARRIVES_RE, payload=ARRIVALS_JSON)  # type: ignore[misc]
            arrivals = await client.get_stop_arrivals("220602")
        assert len(arrivals) == 2
        assert isinstance(arrivals[0], Arrival)
        assert arrivals[0].eta_minutes == 4

    async def test_returns_empty_list(self, client: IettMiddleClient) -> None:
        with aioresponses() as m:
            m.get(ARRIVES_RE, payload=[])  # type: ignore[misc]
            arrivals = await client.get_stop_arrivals("000000")
        assert arrivals == []


class TestGetRouteSchedule:
    async def test_returns_schedule(self, client: IettMiddleClient) -> None:
        with aioresponses() as m:
            m.get(SCHED_RE, payload=SCHEDULE_JSON)  # type: ignore[misc]
            deps = await client.get_route_schedule("500T")
        assert isinstance(deps[0], ScheduledDeparture)
        assert deps[0].departure_time == "05:55"


class TestGetAnnouncements:
    async def test_returns_announcements(self, client: IettMiddleClient) -> None:
        with aioresponses() as m:
            m.get(ANNS_RE, payload=ANNOUNCEMENTS_JSON)  # type: ignore[misc]
            anns = await client.get_announcements("500T")
        assert isinstance(anns[0], Announcement)
        assert "500T" in anns[0].route_code

    async def test_empty(self, client: IettMiddleClient) -> None:
        with aioresponses() as m:
            m.get(ANNS_RE, payload=[])  # type: ignore[misc]
            anns = await client.get_announcements("NOTEXIST")
        assert anns == []
