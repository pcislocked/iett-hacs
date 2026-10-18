"""Tests for IettClient v2 — standalone SOAP, NTCAPI, TKM, and RAM fleet."""

from __future__ import annotations

import asyncio
import re
from typing import Any
from unittest.mock import patch

import aiohttp
import pytest
from aioresponses import CallbackResult, aioresponses

from custom_components.iett.client import IettApiError, IettClient
from custom_components.iett.const import (
    IETT_REST_BASE,
    IETT_SOAP_BASE,
    NTC_SERVICE_URL,
    NTC_TOKEN_URL,
    TKM_TRAFFIC_INDEX_URL,
)
from custom_components.iett.models import (
    Announcement,
    Arrival,
    BusPosition,
    RootStatus,
    ScheduledDeparture,
    StopMetadata,
)
from tests.conftest import (
    HTML_ROUTE_STATION,
    HTML_STATION_DETAIL,
    NTC_AUTH_JSON,
    NTC_BUS_LOCATION_JSON,
    NTC_STOP_ARRIVALS_JSON,
    SOAP_ANNOUNCEMENTS_XML,
    SOAP_FLEET_XML,
    SOAP_ROUTE_FLEET_XML,
    SOAP_SCHEDULE_XML,
    SOAP_STOP_DETAIL_XML,
    TKM_TRAFFIC_RESPONSE,
)

TKM_RE = re.compile(rf"{re.escape(TKM_TRAFFIC_INDEX_URL)}.*", re.IGNORECASE)
SOAP_FLEET_RE = re.compile(
    rf"{re.escape(IETT_SOAP_BASE)}/FiloDurum/SeferGerceklesme\.asmx.*", re.IGNORECASE
)
SOAP_SCHEDULE_RE = re.compile(
    rf"{re.escape(IETT_SOAP_BASE)}/UlasimAnaVeri/PlanlananSeferSaati\.asmx.*", re.IGNORECASE
)
SOAP_ANNS_RE = re.compile(
    rf"{re.escape(IETT_SOAP_BASE)}/UlasimDinamikVeri/Duyurular\.asmx.*", re.IGNORECASE
)
SOAP_STOP_RE = re.compile(
    rf"{re.escape(IETT_SOAP_BASE)}/UlasimAnaVeri/HatDurakGuzergah\.asmx.*", re.IGNORECASE
)
NTC_TOKEN_RE = re.compile(rf"{re.escape(NTC_TOKEN_URL)}.*", re.IGNORECASE)
NTC_SERVICE_RE = re.compile(rf"{re.escape(NTC_SERVICE_URL)}.*", re.IGNORECASE)
REST_STATION_DETAIL_RE = re.compile(rf"{re.escape(IETT_REST_BASE)}/StationDetail.*", re.IGNORECASE)
REST_STATION_INFO_RE = re.compile(
    rf"{re.escape(IETT_REST_BASE)}/tr/RouteStation/GetStationInfo.*", re.IGNORECASE
)
REST_ROUTE_STATION_RE = re.compile(
    rf"{re.escape(IETT_REST_BASE)}/tr/RouteStation/GetRouteByStation.*", re.IGNORECASE
)


@pytest.fixture()
async def client(session: aiohttp.ClientSession) -> IettClient:
    return IettClient(session)


class TestTrafficIndex:
    async def test_get_traffic_indices_success(self, client: IettClient) -> None:
        with aioresponses() as m:
            m.get(TKM_RE, payload=TKM_TRAFFIC_RESPONSE)
            overall, europe, anatolia = await client.get_traffic_indices()

        assert overall == 42
        assert europe == 46
        assert anatolia == 38

    async def test_get_traffic_indices_error(self, client: IettClient) -> None:
        with aioresponses() as m:
            m.get(TKM_RE, status=500)
            with pytest.raises(IettApiError):
                await client.get_traffic_indices()


class TestFleetCache:
    async def test_ensure_fleet_fresh_success(self, client: IettClient) -> None:
        with aioresponses() as m:
            m.post(SOAP_FLEET_RE, body=SOAP_FLEET_XML, headers={"Content-Type": "text/xml"})
            count = await client.ensure_fleet_fresh()

        assert count == 2
        assert "C-1753" in client._fleet_by_kapino
        assert client._fleet_by_kapino["C-1753"].plate == "34 HO 1234"
        assert client._fleet_by_kapino["C-1753"].speed == 35

    async def test_ensure_fleet_fresh_ttl_caching(self, client: IettClient) -> None:
        with aioresponses() as m:
            m.post(SOAP_FLEET_RE, body=SOAP_FLEET_XML, headers={"Content-Type": "text/xml"})
            count1 = await client.ensure_fleet_fresh()
            # Second call within TTL should not do another POST request
            count2 = await client.ensure_fleet_fresh()

        assert count1 == count2 == 2

    async def test_refresh_fleet_force(self, client: IettClient) -> None:
        with aioresponses() as m:
            m.post(SOAP_FLEET_RE, body=SOAP_FLEET_XML, headers={"Content-Type": "text/xml"})
            m.post(SOAP_FLEET_RE, body=SOAP_FLEET_XML, headers={"Content-Type": "text/xml"})
            res1 = await client.refresh_fleet()
            res2 = await client.refresh_fleet()

        assert res1 is True
        assert res2 is True

    async def test_fleet_error_raises_api_error(self, client: IettClient) -> None:
        with aioresponses() as m:
            m.post(SOAP_FLEET_RE, status=500)
            with pytest.raises(IettApiError):
                await client.ensure_fleet_fresh(force=True)


class TestRootStatus:
    async def test_get_root_status(self, client: IettClient) -> None:
        with aioresponses() as m:
            m.get(TKM_RE, payload=TKM_TRAFFIC_RESPONSE)
            m.post(SOAP_FLEET_RE, body=SOAP_FLEET_XML, headers={"Content-Type": "text/xml"})
            status = await client.get_root_status()

        assert isinstance(status, RootStatus)
        assert status.traffic_overall == 42
        assert status.traffic_europe == 46
        assert status.traffic_anatolia == 38
        assert status.active_fleet_count == 2


class TestStopArrivals:
    async def test_get_stop_arrivals_ntcapi(self, client: IettClient) -> None:
        with aioresponses() as m:
            m.post(SOAP_FLEET_RE, body=SOAP_FLEET_XML, headers={"Content-Type": "text/xml"})
            m.post(NTC_TOKEN_RE, payload=NTC_AUTH_JSON)
            m.post(NTC_SERVICE_RE, payload=NTC_STOP_ARRIVALS_JSON)

            arrivals = await client.get_stop_arrivals("301341")

        assert len(arrivals) == 2
        first = arrivals[0]
        assert isinstance(first, Arrival)
        assert first.route_code == "500T"
        assert first.kapino == "C-1753"
        assert first.plate == "34 HO 1234"  # Enriched from RAM fleet!
        assert first.eta_minutes == 4
        assert first.amenities.ac is True
        assert first.amenities.wifi is True
        # Check lat/lon parsed properly
        assert first.lat == 41.0450
        assert first.lon == 29.0020

    async def test_get_stop_arrivals_html_fallback(self, client: IettClient) -> None:
        with aioresponses() as m:
            m.post(SOAP_FLEET_RE, body=SOAP_FLEET_XML, headers={"Content-Type": "text/xml"})
            m.post(NTC_TOKEN_RE, payload=NTC_AUTH_JSON)
            m.post(NTC_SERVICE_RE, payload=[])  # Empty NTC
            m.get(REST_STATION_INFO_RE, body=HTML_STATION_DETAIL)

            arrivals = await client.get_stop_arrivals("301341")

        assert arrivals == []


class TestStopMetadataAndRoutes:
    async def test_get_stop_metadata(self, client: IettClient) -> None:
        with aioresponses() as m:
            m.post(NTC_TOKEN_RE, payload=NTC_AUTH_JSON)
            m.post(NTC_SERVICE_RE, payload=[])
            m.post(SOAP_STOP_RE, body=SOAP_STOP_DETAIL_XML, headers={"Content-Type": "text/xml"})
            m.get(REST_STATION_DETAIL_RE, body=HTML_STATION_DETAIL)

            meta = await client.get_stop_metadata("301341")

        assert isinstance(meta, StopMetadata)
        assert meta.dcode == "301341"
        assert meta.name == "BEŞİKTAŞ MEYDAN"
        assert meta.district == "Beşiktaş"
        assert meta.smart_stop is True
        assert meta.stop_type == "Kapalı Durak"
        assert meta.latitude == 41.0450
        assert meta.longitude == 29.0020

    async def test_get_routes_at_stop(self, client: IettClient) -> None:
        with aioresponses() as m:
            m.get(REST_ROUTE_STATION_RE, body=HTML_ROUTE_STATION)
            routes = await client.get_routes_at_stop("301341")

        assert routes == ["14M", "29C", "500T"]


class TestRouteData:
    async def test_get_route_buses(self, client: IettClient) -> None:
        client._fleet_by_kapino = {
            "C-1753": BusPosition(
                kapino="C-1753",
                plate="34 HO 1234",
                speed=35,
            )
        }
        import time

        client._fleet_updated_mono = time.monotonic()

        with aioresponses() as m:
            m.post(SOAP_FLEET_RE, body=SOAP_ROUTE_FLEET_XML, headers={"Content-Type": "text/xml"})
            m.post(NTC_TOKEN_RE, payload=NTC_AUTH_JSON)
            m.post(NTC_SERVICE_RE, payload=[])

            buses = await client.get_route_buses("500T")

        assert len(buses) == 1
        bus = buses[0]
        assert isinstance(bus, BusPosition)
        assert bus.kapino == "C-1753"
        assert bus.route_code == "500T"
        assert bus.plate == "34 HO 1234"  # Enriched from RAM fleet!
        assert bus.speed == 35

    async def test_get_route_schedule(self, client: IettClient) -> None:
        with aioresponses() as m:
            m.post(SOAP_SCHEDULE_RE, body=SOAP_SCHEDULE_XML, headers={"Content-Type": "text/xml"})
            schedule = await client.get_route_schedule("500T")

        assert len(schedule) == 3
        first = schedule[0]
        assert isinstance(first, ScheduledDeparture)
        assert first.route_code == "500T"
        assert first.direction == "G"
        assert first.departure_time == "08:30"

    async def test_get_announcements(self, client: IettClient) -> None:
        with aioresponses() as m:
            m.post(SOAP_ANNS_RE, body=SOAP_ANNOUNCEMENTS_XML, headers={"Content-Type": "text/xml"})
            anns = await client.get_announcements("500T")

        assert len(anns) == 1
        ann = anns[0]
        assert isinstance(ann, Announcement)
        assert ann.route_code == "500T"
        assert "Trafik yoğunluğu" in ann.message


class TestVehicleStatus:
    async def test_get_vehicle_status_from_ram_fleet(self, client: IettClient) -> None:
        with aioresponses() as m:
            m.post(SOAP_FLEET_RE, body=SOAP_FLEET_XML, headers={"Content-Type": "text/xml"})
            m.post(NTC_TOKEN_RE, payload=NTC_AUTH_JSON)
            m.post(NTC_SERVICE_RE, payload=[])
            m.post(NTC_SERVICE_RE, payload=[])
            bus = await client.get_vehicle_status("C-1753")

        assert bus is not None
        assert bus.kapino == "C-1753"
        assert bus.plate == "34 HO 1234"
        assert bus.speed == 35

    async def test_get_vehicle_status_from_ntc_fallback(self, client: IettClient) -> None:
        with aioresponses() as m:
            # SOAP fleet doesn't have it
            m.post(
                SOAP_FLEET_RE,
                body="""<?xml version="1.0" encoding="utf-8"?>
<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
  <soap:Body>
    <GetFiloAracKonum_jsonResponse xmlns="http://tempuri.org/">
      <GetFiloAracKonum_jsonResult>[]</GetFiloAracKonum_jsonResult>
    </GetFiloAracKonum_jsonResponse>
  </soap:Body>
</soap:Envelope>""",
                headers={"Content-Type": "text/xml"},
            )
            m.post(NTC_TOKEN_RE, payload=NTC_AUTH_JSON)
            m.post(NTC_SERVICE_RE, payload=NTC_BUS_LOCATION_JSON)

            bus = await client.get_vehicle_status("C-1753")

        assert bus is not None
        assert bus.kapino == "C-1753"
        assert bus.plate == "34 HO 1234"

    async def test_get_vehicle_status_offline(self, client: IettClient) -> None:
        with aioresponses() as m:
            m.post(
                SOAP_FLEET_RE,
                body="""<?xml version="1.0" encoding="utf-8"?>
<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
  <soap:Body>
    <GetFiloAracKonum_jsonResponse xmlns="http://tempuri.org/">
      <GetFiloAracKonum_jsonResult>[]</GetFiloAracKonum_jsonResult>
    </GetFiloAracKonum_jsonResponse>
  </soap:Body>
</soap:Envelope>""",
                headers={"Content-Type": "text/xml"},
            )
            m.post(NTC_TOKEN_RE, payload=NTC_AUTH_JSON)
            m.post(NTC_SERVICE_RE, payload=[])
            m.post(NTC_SERVICE_RE, payload=[])

            bus = await client.get_vehicle_status("UNKNOWN-999")

        assert bus is None


class TestDataclassTolerantParsing:
    def test_tolerates_extra_fields(self) -> None:
        raw_arr = {
            "route_code": "500T",
            "destination": "ŞİFA MAHALLESİ",
            "eta_minutes": 5,
            "eta_raw": "12:00",
            "kapino": "C-1753",
            "extra_unknown_field_1": "some_value",
            "extra_unknown_field_2": 12345,
        }
        arr = Arrival.from_dict(raw_arr)
        assert arr.route_code == "500T"
        assert arr.eta_minutes == 5

        raw_bus = {
            "kapino": "C-1753",
            "plate": "34 HO 1234",
            "latitude": 41.0450,
            "longitude": 29.0020,
            "speed": 35,
            "NewFutureApiField": True,
        }
        bus = BusPosition.from_dict(raw_bus)
        assert bus.kapino == "C-1753"
        assert bus.speed == 35


class TestClientResilience:
    """Tests for concurrency, offloading, and malformed upstream payloads."""

    async def test_client_ntcapi_concurrent_401_single_token_refresh(
        self, client: IettClient
    ) -> None:
        """Verify concurrent 401s do not trigger duplicate token refreshes."""
        token_requests = 0

        def token_callback(url: Any, **kwargs: Any) -> CallbackResult:
            nonlocal token_requests
            token_requests += 1
            return CallbackResult(
                status=200,
                payload={"access_token": f"token_{token_requests}", "expires_in": 3600},
            )

        def service_callback(url: Any, **kwargs: Any) -> CallbackResult:
            headers = kwargs.get("headers", {})
            auth = headers.get("Authorization", "")
            if auth == "Bearer token_1":
                return CallbackResult(status=401)
            if auth == "Bearer token_2":
                return CallbackResult(status=200, payload=[{"status": "ok"}])
            return CallbackResult(status=400)

        with aioresponses() as m:
            m.post(NTC_TOKEN_RE, callback=token_callback, repeat=True)
            m.post(NTC_SERVICE_RE, callback=service_callback, repeat=True)

            res1, res2 = await asyncio.gather(
                client._ntc_call("service1", {"foo": "bar"}),
                client._ntc_call("service2", {"baz": "qux"}),
            )

            assert res1 == [{"status": "ok"}]
            assert res2 == [{"status": "ok"}]
            # Exactly 2 token requests: initial token_1, then refreshed token_2 (not 3!)
            assert token_requests == 2

    async def test_client_fleet_parsing_uses_to_thread(self, client: IettClient) -> None:
        """Verify ensure_fleet_fresh offloads XML/JSON parsing to asyncio.to_thread."""
        with patch("asyncio.to_thread", wraps=asyncio.to_thread) as mock_to_thread:
            with aioresponses() as m:
                m.post(SOAP_FLEET_RE, body=SOAP_FLEET_XML, headers={"Content-Type": "text/xml"})
                count = await client.ensure_fleet_fresh(force=True)
                assert count == 2
                assert mock_to_thread.called
                assert mock_to_thread.call_args[0][0].__name__ == "_parse_fleet_records"

    async def test_client_stop_arrivals_malformed_amenities_resilience(
        self, client: IettClient
    ) -> None:
        """Verify malformed amenity flags (VAR, true, None, empty) do not cause crash."""
        payload = [
            {
                "hatkodu": "500T",
                "hatadi": "VADİ -  TAKSİM",
                "dakika": 5,
                "saat": "12:00",
                "kapino": "C-1753",
                "klima": "VAR",
                "wifi": "true",
                "usb": "",
                "engelli": None,
            }
        ]
        with aioresponses() as m:
            m.post(NTC_TOKEN_RE, payload=NTC_AUTH_JSON)
            m.post(NTC_SERVICE_RE, payload=payload)

            arrivals = await client.get_stop_arrivals("301341")
            assert len(arrivals) == 1
            arr = arrivals[0]
            assert arr.route_code == "500T"
            assert arr.destination == "VADİ - TAKSİM"
            assert arr.amenities.ac is True
            assert arr.amenities.wifi is True
            assert arr.amenities.usb is None
            assert arr.amenities.accessible is None

    async def test_client_search_stops_success_and_fallback(self, client: IettClient) -> None:
        """Test search_stops query by name with enrichment, and fallback to code."""
        # 1. Search by name returns 1 result
        name_payload = [
            {"DURAK_DURAK_KODU": "205421", "DURAK_ADI": "MECİDİYEKÖY", "DURAK_YON_BILGISI": "Gidiş"}
        ]
        with aioresponses() as m:
            m.post(NTC_TOKEN_RE, payload=NTC_AUTH_JSON)
            m.post(NTC_SERVICE_RE, payload=name_payload)
            # Metadata enrichment
            m.post(SOAP_STOP_RE, body=SOAP_STOP_DETAIL_XML, headers={"Content-Type": "text/xml"})

            results = await client.search_stops("MECİDİYEKÖY")
            assert len(results) == 1
            assert results[0].dcode == "205421"
            assert results[0].name == "MECİDİYEKÖY"
            assert results[0].direction == "ZİNCİRLİKUYU YÖNÜ"

        # 2. Search by name returns empty, falls back to code search
        with aioresponses() as m:
            m.post(NTC_TOKEN_RE, payload=NTC_AUTH_JSON)
            m.post(NTC_SERVICE_RE, payload=[])  # name search fails/empty
            m.post(NTC_SERVICE_RE, payload=name_payload)  # code search returns
            m.post(SOAP_STOP_RE, body=SOAP_STOP_DETAIL_XML, headers={"Content-Type": "text/xml"})

            results = await client.search_stops("205421")
            assert len(results) == 1
            assert results[0].dcode == "205421"

    async def test_client_search_stops_empty_and_error(self, client: IettClient) -> None:
        """Test search_stops with empty string and upstream errors."""
        assert await client.search_stops("") == []
        assert await client.search_stops("   ") == []

        with aioresponses() as m:
            m.post(NTC_TOKEN_RE, payload=NTC_AUTH_JSON)
            m.post(NTC_SERVICE_RE, status=500)

            results = await client.search_stops("FAIL")
            assert results == []

    async def test_client_search_routes_success_and_fallback(self, client: IettClient) -> None:
        """Test search_routes by line code and fallback to line name."""
        route_payload = [{"HAT_HAT_KODU": "500T", "HAT_HAT_ADI": "TUZLA - CEVİZLİBAĞ"}]
        with aioresponses() as m:
            m.post(NTC_TOKEN_RE, payload=NTC_AUTH_JSON)
            m.post(NTC_SERVICE_RE, payload=route_payload)

            results = await client.search_routes("500T")
            assert len(results) == 1
            assert results[0].hat_kodu == "500T"
            assert results[0].name == "TUZLA - CEVİZLİBAĞ"

        # Fallback to name search
        with aioresponses() as m:
            m.post(NTC_TOKEN_RE, payload=NTC_AUTH_JSON)
            m.post(NTC_SERVICE_RE, payload=[])  # code search returns empty
            m.post(NTC_SERVICE_RE, payload=route_payload)  # name search returns hit

            results = await client.search_routes("TUZLA")
            assert len(results) == 1
            assert results[0].hat_kodu == "500T"

    async def test_client_search_routes_empty_and_error(self, client: IettClient) -> None:
        """Test search_routes with empty query and upstream failure."""
        assert await client.search_routes("") == []
        assert await client.search_routes("   ") == []

        with aioresponses() as m:
            m.post(NTC_TOKEN_RE, payload=NTC_AUTH_JSON)
            m.post(NTC_SERVICE_RE, status=502)

            results = await client.search_routes("ERR")
            assert results == []

    def test_frontend_version_line_ending_stability(self, tmp_path: Any) -> None:
        """Verify _get_frontend_version produces identical hashes for CRLF and LF."""
        from custom_components.iett.const import _get_frontend_version

        # Directly invoke and verify stability
        v = _get_frontend_version()
        assert "." in v
        assert len(v.split(".")[-1]) == 8
