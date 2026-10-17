"""Standalone asynchronous client for İETT, NTCAPI, and İBB services.

Handles direct SOAP, REST, and OAuth2 calls with in-memory caching and
fault-tolerant parsing. No external middleware required.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from typing import Any, cast
from xml.etree import ElementTree as ET
from xml.sax.saxutils import escape as xml_escape

import aiohttp
from bs4 import BeautifulSoup

from .const import (
    ANNOUNCEMENT_RAM_CACHE_TTL,
    FLEET_RAM_CACHE_TTL,
    IETT_REST_BASE,
    IETT_SOAP_BASE,
    NTC_CLIENT_ID,
    NTC_CLIENT_SECRET,
    NTC_SCOPE,
    NTC_SERVICE_URL,
    NTC_TOKEN_URL,
    NTC_YBS_PASS,
    NTC_YBS_USER,
    SCHEDULE_RAM_CACHE_TTL,
    TKM_TRAFFIC_INDEX_URL,
)
from .models import (
    Amenities,
    Announcement,
    Arrival,
    BusPosition,
    RootStatus,
    RouteSearchResult,
    ScheduledDeparture,
    StopMetadata,
)
from .normalizers import (
    normalize_kapino,
    normalize_plate,
    parse_son_konum,
)

_LOGGER = logging.getLogger(__name__)

_TEMPURI = "http://tempuri.org/"
_SOAP_ENV = (
    '<?xml version="1.0" encoding="utf-8"?>'
    '<soap:Envelope xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"'
    ' xmlns:xsd="http://www.w3.org/2001/XMLSchema"'
    ' xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">'
    "<soap:Body>{body}</soap:Body></soap:Envelope>"
)


class IettApiError(Exception):
    """Raised when an IETT, NTCAPI, or IBB service call fails."""


class IettClient:
    """Main client communicating directly with official upstream endpoints."""

    def __init__(self, session: aiohttp.ClientSession) -> None:
        self._session = session

        # Locks must be created inside instance to prevent cross-loop errors in pytest
        self._token_lock = asyncio.Lock()
        self._fleet_lock = asyncio.Lock()

        # In-memory caches (RAM only — never written to SQLite)
        self._token: str | None = None
        self._token_expiry: float = 0.0

        self._fleet_by_kapino: dict[str, BusPosition] = {}
        self._fleet_updated_mono: float = 0.0

        self._schedule_cache: dict[str, tuple[float, list[ScheduledDeparture]]] = {}
        self._announcements_cache: tuple[float, list[Announcement]] | None = None
        self._stop_metadata_cache: dict[str, tuple[float, StopMetadata]] = {}
        self._routes_at_stop_cache: dict[str, tuple[float, list[str]]] = {}
        self._hat_id_cache: dict[str, int | None] = {}

    # ------------------------------------------------------------------
    # HTTP and SOAP Helpers
    # ------------------------------------------------------------------

    async def _soap_post(self, url: str, body: str, action: str) -> str:
        """Execute a SOAP POST request and return raw XML response."""
        envelope = _SOAP_ENV.format(body=body)
        headers = {
            "Content-Type": "text/xml; charset=utf-8",
            "SOAPAction": action,
            "User-Agent": "HomeAssistant-IETT/2.0",
        }
        try:
            async with self._session.post(
                url,
                data=envelope.encode("utf-8"),
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=20),
            ) as resp:
                resp.raise_for_status()
                return await resp.text()
        except Exception as exc:
            raise IettApiError(f"SOAP POST to {url} failed: {exc}") from exc

    async def _get_json(self, url: str, params: dict[str, Any] | None = None) -> Any:
        """Execute a GET request expecting JSON."""
        try:
            async with self._session.get(
                url,
                params=params,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                resp.raise_for_status()
                return await resp.json(content_type=None)
        except Exception as exc:
            raise IettApiError(f"GET JSON {url} failed: {exc}") from exc

    async def _get_text(self, url: str, params: dict[str, Any] | None = None) -> str:
        """Execute a GET request expecting HTML or plain text."""
        try:
            async with self._session.get(
                url,
                params=params,
                headers={"User-Agent": "Mozilla/5.0 (HomeAssistant; Linux x86_64)"},
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                resp.raise_for_status()
                return await resp.text()
        except Exception as exc:
            raise IettApiError(f"GET text {url} failed: {exc}") from exc

    def _extract_soap_json(self, xml_text: str, result_tag: str) -> list[dict[str, Any]]:
        """Extract and JSON-parse payload embedded inside SOAP XML."""
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError:
            return []
        el = root.find(f".//{{{_TEMPURI}}}{result_tag}")
        if el is None or not el.text:
            return []
        try:
            data = json.loads(el.text)
        except json.JSONDecodeError:
            return []
        return cast(list[dict[str, Any]], data) if isinstance(data, list) else []

    # ------------------------------------------------------------------
    # NTCAPI OAuth2 and Service Calls
    # ------------------------------------------------------------------

    async def _ensure_token(self) -> str:
        """Fetch and cache NTCAPI Bearer token, refreshing before expiry."""
        if self._token and time.monotonic() < self._token_expiry - 60:
            return self._token

        async with self._token_lock:
            if self._token and time.monotonic() < self._token_expiry - 60:
                return self._token

            payload = {
                "client_id": NTC_CLIENT_ID,
                "client_secret": NTC_CLIENT_SECRET,
                "grant_type": "client_credentials",
                "scope": NTC_SCOPE,
            }
            try:
                async with self._session.post(
                    NTC_TOKEN_URL,
                    json=payload,
                    headers={"User-Agent": "okhttp/5.0.0-alpha.11"},
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    resp.raise_for_status()
                    data = await resp.json()
            except Exception as exc:
                raise IettApiError(f"NTCAPI auth failed: {exc}") from exc

            token = data.get("access_token")
            if not token:
                raise IettApiError(f"NTCAPI auth missing access_token: {data}")

            expires_in = data.get("expires_in", 3600)
            self._token = token
            self._token_expiry = time.monotonic() + expires_in
            return token

    async def _ntc_call(self, alias: str, data: dict[str, Any]) -> Any:
        """Execute POST call to NTCAPI /service with automatic token refresh."""
        token = await self._ensure_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=UTF-8",
            "User-Agent": "okhttp/5.0.0-alpha.11",
        }
        payload = {"alias": alias, "data": data}
        try:
            async with self._session.post(
                NTC_SERVICE_URL,
                json=payload,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                if resp.status == 401:
                    # Token expired or invalidated — clear and retry once
                    self._token = None
                    token = await self._ensure_token()
                    headers["Authorization"] = f"Bearer {token}"
                    async with self._session.post(
                        NTC_SERVICE_URL,
                        json=payload,
                        headers=headers,
                        timeout=aiohttp.ClientTimeout(total=15),
                    ) as retry_resp:
                        retry_resp.raise_for_status()
                        return await retry_resp.json()
                resp.raise_for_status()
                return await resp.json()
        except Exception as exc:
            raise IettApiError(f"NTCAPI service '{alias}' failed: {exc}") from exc

    # ------------------------------------------------------------------
    # Root Status: TKM Traffic Index and SOAP Fleet Size
    # ------------------------------------------------------------------

    async def get_traffic_indices(self) -> tuple[int, int, int]:
        """Fetch Istanbul city-wide, European, and Anatolian traffic congestion index.

        Returns (TI, TI_Av, TI_An) as integer percentages (0-100).
        """
        try:
            data = await self._get_json(TKM_TRAFFIC_INDEX_URL)
            if not isinstance(data, dict):
                return (0, 0, 0)
            overall = int(data.get("TI", 0))
            europe = int(data.get("TI_Av", 0))
            anatolia = int(data.get("TI_An", 0))
            return (overall, europe, anatolia)
        except Exception as exc:
            _LOGGER.warning("Failed to fetch TKM traffic index: %s", exc)
            raise IettApiError(f"TKM traffic index failed: {exc}") from exc

    async def ensure_fleet_fresh(self, force: bool = False) -> int:
        """Ensure RAM fleet cache is up-to-date and return active bus count.

        Never writes full fleet to database. Only updates in-memory dictionary.
        """
        now_mono = time.monotonic()
        if (
            not force
            and self._fleet_updated_mono > 0
            and (now_mono - self._fleet_updated_mono) < FLEET_RAM_CACHE_TTL
        ):
            return len(self._fleet_by_kapino)

        async with self._fleet_lock:
            now_mono = time.monotonic()
            if (
                not force
                and self._fleet_updated_mono > 0
                and (now_mono - self._fleet_updated_mono) < FLEET_RAM_CACHE_TTL
            ):
                return len(self._fleet_by_kapino)

            try:
                xml = await self._soap_post(
                    f"{IETT_SOAP_BASE}/FiloDurum/SeferGerceklesme.asmx",
                    '<GetFiloAracKonum_json xmlns="http://tempuri.org/"/>',
                    '"http://tempuri.org/GetFiloAracKonum_json"',
                )
            except Exception as exc:
                if self._fleet_by_kapino:
                    _LOGGER.warning(
                        "Fleet refresh failed; using cached fleet (%d buses): %s",
                        len(self._fleet_by_kapino),
                        exc,
                    )
                    return len(self._fleet_by_kapino)
                raise IettApiError(f"Fleet fetch failed: {exc}") from exc

            records = self._extract_soap_json(xml, "GetFiloAracKonum_jsonResult")
            new_dict: dict[str, BusPosition] = {}

            for r in records:
                kapi = normalize_kapino(r.get("KapiNo"))
                if not kapi:
                    continue
                speed_raw = next(
                    (r[k] for k in ("Hiz", "H\u0131z", "HIZ", "hiz", "h\u0131z") if k in r),
                    None,
                )
                speed = int(float(speed_raw)) if speed_raw is not None else None
                try:
                    lat = float(r.get("Enlem", 0.0))
                    lon = float(r.get("Boylam", 0.0))
                except (ValueError, TypeError):
                    lat, lon = 0.0, 0.0

                new_dict[kapi] = BusPosition(
                    kapino=kapi,
                    plate=normalize_plate(r.get("Plaka")),
                    latitude=lat if lat != 0.0 else None,
                    longitude=lon if lon != 0.0 else None,
                    speed=speed,
                    operator=r.get("Operator"),
                    last_seen=r.get("Saat", ""),
                    route_code=(r.get("HatKodu") or r.get("HATKODU") or r.get("hatkodu") or None),
                )

            self._fleet_by_kapino = new_dict
            self._fleet_updated_mono = time.monotonic()
            return len(self._fleet_by_kapino)

    async def get_root_status(self) -> RootStatus:
        """Fetch 4 root parameters: 3 traffic percentages + active fleet count."""
        results = await asyncio.gather(
            self.get_traffic_indices(),
            self.ensure_fleet_fresh(),
            return_exceptions=True,
        )

        traffic_res, fleet_res = results[0], results[1]
        if isinstance(traffic_res, Exception) and isinstance(fleet_res, Exception):
            raise IettApiError(f"Root status failed: traffic={traffic_res}, fleet={fleet_res}")

        if not isinstance(traffic_res, Exception):
            overall, europe, anatolia = traffic_res
        else:
            overall = europe = anatolia = 0

        fleet_count = (
            fleet_res if not isinstance(fleet_res, Exception) else len(self._fleet_by_kapino)
        )

        return RootStatus(
            traffic_overall=overall,
            traffic_europe=europe,
            traffic_anatolia=anatolia,
            active_fleet_count=fleet_count,
        )

    # ------------------------------------------------------------------
    # Stop Methods (1a)
    # ------------------------------------------------------------------

    async def search_stops(self, query: str) -> list[StopMetadata]:
        """Search stops by code or name using NTCAPI."""
        q = str(query or "").strip().upper()
        if not q:
            return []

        search_arg = f"{q}%"
        try:
            res = await self._ntc_call(
                "mainGetBusStop_basic_search", {"HATYONETIM.DURAK.ADI": search_arg}
            )
            if not isinstance(res, list) or not res:
                res = await self._ntc_call(
                    "mainGetBusStop_basic_search", {"HATYONETIM.DURAK.DURAK_KODU": search_arg}
                )
        except Exception as exc:
            _LOGGER.warning("NTCAPI search_stops failed: %s", exc)
            res = []

        if not isinstance(res, list):
            res = []

        results: list[StopMetadata] = []
        for r in res:
            dcode = str(r.get("DURAK_DURAK_KODU") or "").strip()
            name = str(r.get("DURAK_ADI") or "").strip()
            if dcode:
                results.append(StopMetadata(dcode=dcode, name=name))
        return results

    async def get_stop_metadata(self, dcode: str) -> StopMetadata:
        """Fetch static stop information (name, coordinates, direction, district, type)."""
        clean_dcode = str(dcode).strip()
        cached = self._stop_metadata_cache.get(clean_dcode)
        if cached and (time.monotonic() - cached[0]) < 86400:  # 24 hour cache
            return cached[1]

        safe_dcode = xml_escape(clean_dcode)

        async def fetch_ntc() -> dict[str, Any] | None:
            try:
                res = await self._ntc_call(
                    "mainGetBusStop", {"HATYONETIM.DURAK.DURAK_KODU": clean_dcode}
                )
                if isinstance(res, list) and res:
                    return res[0]
            except Exception:  # noqa: BLE001
                pass
            return None

        async def fetch_soap() -> dict[str, Any] | None:
            try:
                xml = await self._soap_post(
                    f"{IETT_SOAP_BASE}/UlasimAnaVeri/HatDurakGuzergah.asmx",
                    f'<GetDurak_json xmlns="http://tempuri.org/"><DurakKodu>{safe_dcode}</DurakKodu></GetDurak_json>',
                    '"http://tempuri.org/GetDurak_json"',
                )
                recs = self._extract_soap_json(xml, "GetDurak_jsonResult")
                return recs[0] if recs else None
            except Exception:  # noqa: BLE001
                return None

        async def fetch_html_detail() -> dict[str, Any]:
            try:
                html = await self._get_text(
                    f"{IETT_REST_BASE}/StationDetail", params={"dkod": clean_dcode}
                )
                soup = BeautifulSoup(html, "html.parser")
                info: dict[str, Any] = {"district": None, "stop_type": None, "smart_stop": None}
                tab = soup.find(id="info")
                if tab:
                    for item in tab.find_all("div", class_="station-item"):
                        b_tag, p_tag = item.find("b"), item.find("p")
                        if b_tag and p_tag:
                            k, v = b_tag.get_text(strip=True), p_tag.get_text(strip=True)
                            if "İlçe" in k:
                                info["district"] = v
                            elif "Fiziki Durum" in k:
                                info["stop_type"] = v
                            elif "Akıllı Durak" in k:
                                info["smart_stop"] = v == "VAR"
                return info
            except Exception:  # noqa: BLE001
                return {"district": None, "stop_type": None, "smart_stop": None}

        ntc_res, soap_res, html_res = await asyncio.gather(
            fetch_ntc(), fetch_soap(), fetch_html_detail()
        )

        name = f"Durak {clean_dcode}"
        lat: float | None = None
        lon: float | None = None
        direction: str | None = None
        district: str | None = html_res.get("district")
        stop_type: str | None = html_res.get("stop_type")
        smart_stop: bool | None = html_res.get("smart_stop")

        if ntc_res:
            name = ntc_res.get("DURAK_ADI") or name
            direction = ntc_res.get("DURAK_YON_BILGISI") or direction
            geoloc = ntc_res.get("DURAK_GEOLOC") or {}
            try:
                lat = float(geoloc.get("y")) if geoloc.get("y") else None
                lon = float(geoloc.get("x")) if geoloc.get("x") else None
            except (ValueError, TypeError):
                pass

        if soap_res:
            name = soap_res.get("DurakAdi") or soap_res.get("SDURAKADI") or name
            direction = soap_res.get("SYON") or direction
            if lat is None or lon is None:
                coord_str = str(soap_res.get("KOORDINAT", ""))
                pt_match = re.match(r"POINT \(([\d.]+) ([\d.]+)\)", coord_str)
                if pt_match:
                    lon = float(pt_match.group(1))
                    lat = float(pt_match.group(2))
                else:
                    try:
                        lon = float(
                            str(soap_res.get("KoordinatX") or soap_res.get("Boylam", "")).replace(
                                ",", "."
                            )
                        )
                        lat = float(
                            str(soap_res.get("KoordinatY") or soap_res.get("Enlem", "")).replace(
                                ",", "."
                            )
                        )
                    except (ValueError, TypeError):
                        pass

        meta = StopMetadata(
            dcode=clean_dcode,
            name=name,
            latitude=lat if lat != 0.0 else None,
            longitude=lon if lon != 0.0 else None,
            direction=direction,
            district=district,
            stop_type=stop_type,
            smart_stop=smart_stop,
        )

        # Cap cache size to avoid leaks
        if len(self._stop_metadata_cache) >= 200:
            self._stop_metadata_cache.pop(next(iter(self._stop_metadata_cache)))
        self._stop_metadata_cache[clean_dcode] = (time.monotonic(), meta)
        return meta

    async def get_routes_at_stop(self, dcode: str) -> list[str]:
        """Fetch list of route codes passing through a stop."""
        clean_dcode = str(dcode).strip()
        cached = self._routes_at_stop_cache.get(clean_dcode)
        if cached and (time.monotonic() - cached[0]) < 86400:
            return cached[1]

        try:
            html = await self._get_text(
                f"{IETT_REST_BASE}/tr/RouteStation/GetRouteByStation",
                params={"dcode": clean_dcode, "langid": "1"},
            )
            soup = BeautifulSoup(html, "html.parser")
            routes = sorted(
                {
                    span.text.strip().upper()
                    for item in soup.select("div.line-item")
                    for span in item.select("a > span:first-child")
                    if span.text.strip()
                }
            )
        except Exception as exc:
            _LOGGER.warning("Failed to get routes at stop %s: %s", clean_dcode, exc)
            routes = []

        if len(self._routes_at_stop_cache) >= 200:
            self._routes_at_stop_cache.pop(next(iter(self._routes_at_stop_cache)))
        self._routes_at_stop_cache[clean_dcode] = (time.monotonic(), routes)
        return routes

    async def get_stop_arrivals(self, dcode: str) -> list[Arrival]:
        """Fetch live bus arrivals at stop *dcode*, enriched with fleet plate/telemetry."""
        clean_dcode = str(dcode).strip()
        arrivals: list[Arrival] = []

        # 1. Try NTCAPI ybs
        try:
            payload = {
                "data": {
                    "password": NTC_YBS_PASS,
                    "username": NTC_YBS_USER,
                },
                "method": "POST",
                "path": ["real-time-information", "stop-arrivals", clean_dcode],
            }
            raw = await self._ntc_call("ybs", payload)
            if isinstance(raw, list):
                for item in raw:
                    if not isinstance(item, dict):
                        continue
                    route_code = str(item.get("hatkodu") or "").strip().upper()
                    if not route_code:
                        continue
                    destination = str(item.get("hattip") or item.get("hatadi") or "").strip()
                    try:
                        dakika = int(item.get("dakika")) if item.get("dakika") is not None else None
                    except (ValueError, TypeError):
                        dakika = None

                    saat = str(item.get("saat") or "")
                    lat, lon = parse_son_konum(item.get("son_konum"))
                    try:
                        hiz = int(item.get("son_hiz")) if item.get("son_hiz") is not None else None
                    except (ValueError, TypeError):
                        hiz = None

                    amenities = Amenities(
                        usb=bool(int(item["usb"])) if item.get("usb") is not None else None,
                        wifi=bool(int(item["wifi"])) if item.get("wifi") is not None else None,
                        ac=bool(int(item["klima"])) if item.get("klima") is not None else None,
                        accessible=bool(int(item["engelli"]))
                        if item.get("engelli") is not None
                        else None,
                    )
                    arrivals.append(
                        Arrival(
                            route_code=route_code,
                            destination=destination,
                            eta_minutes=dakika,
                            eta_raw=saat,
                            kapino=normalize_kapino(item.get("kapino")),
                            lat=lat,
                            lon=lon,
                            speed_kmh=hiz,
                            last_seen_ts=item.get("son_konum_saati") or None,
                            amenities=amenities,
                        )
                    )
        except Exception as exc:
            _LOGGER.debug(
                "NTCAPI stop-arrivals failed for %s (%s); falling back to HTML", clean_dcode, exc
            )

        # 2. Fallback to HTML if NTCAPI returned nothing
        if not arrivals:
            try:
                html = await self._get_text(
                    f"{IETT_REST_BASE}/tr/RouteStation/GetStationInfo",
                    params={"dcode": clean_dcode, "langid": "1"},
                )
                soup = BeautifulSoup(html, "html.parser")
                for item in soup.select("div.line-item div.content:not(.content-header)"):
                    route_el = item.select_one("span")
                    b = item.select_one("b")
                    p = item.select_one("p")
                    if not route_el or not b or not p:
                        continue
                    eta_m = re.search(r"(\d+)\s*dk", b.text)
                    eta_min = int(eta_m.group(1)) if eta_m else None
                    kapi_m = re.search(r"\b[A-Z]+-?\d+\b", item.get_text(" ", strip=True))
                    arrivals.append(
                        Arrival(
                            route_code=route_el.text.strip().upper(),
                            destination=p.text.replace(b.text, "").strip(),
                            eta_minutes=eta_min,
                            eta_raw=b.text.strip(),
                            kapino=normalize_kapino(kapi_m.group(0)) if kapi_m else None,
                        )
                    )
            except Exception as exc:
                _LOGGER.warning("HTML fallback failed for %s: %s", clean_dcode, exc)

        # 3. Enrich with in-memory RAM fleet data (plate, coords, speed)
        try:
            await self.ensure_fleet_fresh()
        except Exception:  # noqa: BLE001
            pass

        for arr in arrivals:
            if arr.kapino and arr.kapino in self._fleet_by_kapino:
                bus = self._fleet_by_kapino[arr.kapino]
                if not arr.plate:
                    arr.plate = bus.plate
                if arr.lat is None and bus.latitude is not None:
                    arr.lat = bus.latitude
                    arr.lon = bus.longitude
                if arr.speed_kmh is None and bus.speed is not None:
                    arr.speed_kmh = bus.speed

        return arrivals

    # ------------------------------------------------------------------
    # Route Methods (1b)
    # ------------------------------------------------------------------

    async def search_routes(self, query: str) -> list[RouteSearchResult]:
        """Search routes by code or name using NTCAPI."""
        q = str(query or "").strip().upper()
        if not q:
            return []

        search_arg = f"{q}%"
        try:
            res = await self._ntc_call(
                "mainGetLine_basic_search", {"HATYONETIM.HAT.HAT_KODU": search_arg}
            )
            if not isinstance(res, list) or not res:
                res = await self._ntc_call(
                    "mainGetLine_basic_search", {"HATYONETIM.HAT.HAT_ADI": search_arg}
                )
        except Exception as exc:
            _LOGGER.warning("NTCAPI search_routes failed: %s", exc)
            res = []

        if not isinstance(res, list):
            res = []

        results: list[RouteSearchResult] = []
        for r in res:
            hk = str(r.get("HAT_HAT_KODU") or "").strip().upper()
            nm = str(r.get("HAT_HAT_ADI") or "").strip()
            if hk:
                results.append(RouteSearchResult(hat_kodu=hk, name=nm))
        return results

    async def _get_hat_id(self, hat_kodu: str) -> int | None:
        """Resolve numeric internal HAT_ID for a route code."""
        hk = hat_kodu.upper().strip()
        if hk in self._hat_id_cache:
            return self._hat_id_cache[hk]

        try:
            res = await self._ntc_call(
                "mainGetRoute",
                {"HATYONETIM.GUZERGAH.YON": "119", "HATYONETIM.HAT.HAT_KODU": hk},
            )
            if isinstance(res, list):
                for item in res:
                    if item.get("HAT_ID"):
                        val = int(item["HAT_ID"])
                        if len(self._hat_id_cache) >= 200:
                            self._hat_id_cache.pop(next(iter(self._hat_id_cache)))
                        self._hat_id_cache[hk] = val
                        return val
        except Exception:  # noqa: BLE001
            pass

        self._hat_id_cache[hk] = None
        return None

    async def get_route_buses(self, hat_kodu: str) -> list[BusPosition]:
        """Fetch active buses operating on route *hat_kodu*."""
        hk = hat_kodu.upper().strip()
        safe_hat = xml_escape(hk)

        async def fetch_soap() -> list[BusPosition]:
            try:
                xml = await self._soap_post(
                    f"{IETT_SOAP_BASE}/FiloDurum/SeferGerceklesme.asmx",
                    f'<GetHatOtoKonum_json xmlns="http://tempuri.org/"><HatKodu>{safe_hat}</HatKodu></GetHatOtoKonum_json>',
                    '"http://tempuri.org/GetHatOtoKonum_json"',
                )
                recs = self._extract_soap_json(xml, "GetHatOtoKonum_jsonResult")
                buses: list[BusPosition] = []
                for r in recs:
                    kapi = normalize_kapino(r.get("kapino"))
                    if not kapi:
                        continue
                    guzergah = str(r.get("guzergahkodu") or "")
                    parts = guzergah.split("_")
                    dir_letter = parts[1] if len(parts) > 1 and parts[1] in ("G", "D") else None
                    buses.append(
                        BusPosition(
                            kapino=kapi,
                            latitude=float(r.get("enlem", 0.0)) or None,
                            longitude=float(r.get("boylam", 0.0)) or None,
                            last_seen=str(r.get("son_konum_zamani", "")),
                            route_code=hk,
                            route_name=r.get("hatad"),
                            direction=r.get("yon"),
                            direction_letter=dir_letter,
                            nearest_stop=r.get("yakinDurakKodu"),
                        )
                    )
                return buses
            except Exception:  # noqa: BLE001
                return []

        async def fetch_ntc() -> list[BusPosition]:
            hat_id = await self._get_hat_id(hk)
            if not hat_id:
                return []
            try:
                payload = {
                    "method": "POST",
                    "path": ["real-time-information", "point-passing", str(hat_id)],
                    "data": {"password": NTC_YBS_PASS, "username": NTC_YBS_USER},
                }
                raw = await self._ntc_call("ybs", payload)
                if not isinstance(raw, list):
                    return []
                buses: list[BusPosition] = []
                for r in raw:
                    if not isinstance(r, dict):
                        continue
                    kapi = normalize_kapino(r.get("K_ARAC_KAPINUMARASI"))
                    if not kapi:
                        continue
                    guzergah = str(r.get("K_GUZERGAH_GUZERGAHKODU") or "")
                    parts = guzergah.split("_")
                    dir_letter = parts[1] if len(parts) > 1 and parts[1] in ("G", "D") else None
                    try:
                        seq = int(r.get("H_GOREV_DURAK_GECIS_SIRANO"))
                    except (ValueError, TypeError):
                        seq = None
                    buses.append(
                        BusPosition(
                            kapino=kapi,
                            latitude=float(r.get("ENLEM", 0.0)) or None,
                            longitude=float(r.get("BOYLAM", 0.0)) or None,
                            last_seen=str(r.get("SISTEMSAATI", "")),
                            route_code=hk,
                            direction_letter=dir_letter,
                            stop_sequence=seq,
                        )
                    )
                return buses
            except Exception:  # noqa: BLE001
                return []

        soap_buses, ntc_buses = await asyncio.gather(fetch_soap(), fetch_ntc())

        merged: dict[str, BusPosition] = {}
        for b in ntc_buses:
            merged[b.kapino] = b
        for b in soap_buses:
            if b.kapino in merged:
                # Merge fields
                ex = merged[b.kapino]
                merged[b.kapino] = BusPosition(
                    kapino=b.kapino,
                    plate=ex.plate or b.plate,
                    latitude=ex.latitude or b.latitude,
                    longitude=ex.longitude or b.longitude,
                    speed=ex.speed or b.speed,
                    operator=ex.operator or b.operator,
                    last_seen=ex.last_seen or b.last_seen,
                    route_code=hk,
                    route_name=b.route_name or ex.route_name,
                    direction=b.direction or ex.direction,
                    direction_letter=b.direction_letter or ex.direction_letter,
                    nearest_stop=b.nearest_stop or ex.nearest_stop,
                    stop_sequence=ex.stop_sequence or b.stop_sequence,
                )
            else:
                merged[b.kapino] = b

        # Enrich with RAM fleet plate & speed
        try:
            await self.ensure_fleet_fresh()
        except Exception:  # noqa: BLE001
            pass

        for bus in merged.values():
            if bus.kapino in self._fleet_by_kapino:
                fl = self._fleet_by_kapino[bus.kapino]
                if not bus.plate:
                    bus.plate = fl.plate
                if bus.speed is None:
                    bus.speed = fl.speed
                if not bus.operator:
                    bus.operator = fl.operator

        return list(merged.values())

    async def get_route_schedule(self, hat_kodu: str) -> list[ScheduledDeparture]:
        """Fetch timetable departures for route *hat_kodu* (cached 1 hour)."""
        hk = hat_kodu.upper().strip()
        now_mono = time.monotonic()
        cached = self._schedule_cache.get(hk)
        if cached and (now_mono - cached[0]) < SCHEDULE_RAM_CACHE_TTL:
            return cached[1]

        safe_hat = xml_escape(hk)
        try:
            xml = await self._soap_post(
                f"{IETT_SOAP_BASE}/UlasimAnaVeri/PlanlananSeferSaati.asmx",
                f'<GetPlanlananSeferSaati_json xmlns="http://tempuri.org/"><HatKodu>{safe_hat}</HatKodu></GetPlanlananSeferSaati_json>',
                '"http://tempuri.org/GetPlanlananSeferSaati_json"',
            )
            records = self._extract_soap_json(xml, "GetPlanlananSeferSaati_jsonResult")
            deps: list[ScheduledDeparture] = []
            for r in records:
                deps.append(
                    ScheduledDeparture.from_dict(
                        {
                            "route_code": r.get("SHATKODU", hk),
                            "route_name": r.get("HATADI", ""),
                            "route_variant": r.get("SGUZERAH", ""),
                            "direction": r.get("SYON", ""),
                            "day_type": r.get("SGUNTIPI", ""),
                            "service_type": r.get("SSERVISTIPI", ""),
                            "departure_time": r.get("DT", ""),
                        }
                    )
                )
        except Exception as exc:
            _LOGGER.warning("Failed to fetch route schedule for %s: %s", hk, exc)
            deps = []

        if len(self._schedule_cache) >= 200:
            self._schedule_cache.pop(next(iter(self._schedule_cache)))
        self._schedule_cache[hk] = (now_mono, deps)
        return deps

    async def get_route_variants(self, hat_kodu: str) -> list[str]:
        """Return distinct variant codes (e.g. ['500T_G_D0', '500T_D_D0']) for route."""
        schedule = await self.get_route_schedule(hat_kodu)
        variants: set[str] = {s.route_variant for s in schedule if s.route_variant}
        return sorted(variants)

    async def get_announcements(self, hat_kodu: str | None = None) -> list[Announcement]:
        """Fetch active disruption announcements (cached 10 minutes)."""
        now_mono = time.monotonic()
        if (
            self._announcements_cache is None
            or (now_mono - self._announcements_cache[0]) >= ANNOUNCEMENT_RAM_CACHE_TTL
        ):
            try:
                xml = await self._soap_post(
                    f"{IETT_SOAP_BASE}/UlasimDinamikVeri/Duyurular.asmx",
                    '<GetDuyurular_json xmlns="http://tempuri.org/"/>',
                    '"http://tempuri.org/GetDuyurular_json"',
                )
                records = self._extract_soap_json(xml, "GetDuyurular_jsonResult")
                all_ann: list[Announcement] = []
                for r in records:
                    all_ann.append(
                        Announcement.from_dict(
                            {
                                "route_code": str(r.get("HATKODU", "")).strip().upper(),
                                "route_name": str(r.get("HAT", "")).strip(),
                                "type": str(r.get("TIP", "")).strip(),
                                "updated_at": str(r.get("GUNCELLEME_SAATI", "")).strip(),
                                "message": str(r.get("MESAJ", "")).strip(),
                            }
                        )
                    )
                self._announcements_cache = (now_mono, all_ann)
            except Exception as exc:
                _LOGGER.warning("Failed to fetch announcements: %s", exc)
                if self._announcements_cache is None:
                    self._announcements_cache = (now_mono, [])

        ann_list = self._announcements_cache[1]
        if hat_kodu:
            target = hat_kodu.strip().upper()
            return [a for a in ann_list if a.route_code == target]
        return ann_list

    # ------------------------------------------------------------------
    # Single Vehicle Tracking (1c)
    # ------------------------------------------------------------------

    async def get_vehicle_status(self, kapino: str) -> BusPosition | None:
        """Fetch single vehicle position & metadata by Kapı No.

        Queries RAM fleet cache and NTCAPI mainGetBusLocation_basic in parallel.
        Returns None if bus is not found or currently offline.
        """
        kapi = normalize_kapino(kapino) or str(kapino).strip().upper()
        if not kapi:
            return None

        # 1. Update fleet cache if stale
        try:
            await self.ensure_fleet_fresh()
        except Exception:  # noqa: BLE001
            pass

        bus_fleet = self._fleet_by_kapino.get(kapi)

        # 2. Query NTCAPI for live position
        async def fetch_ntc_location() -> dict[str, Any] | None:
            for variant in (kapi, kapi.replace("-", "")):
                try:
                    payload = {"AKYOLBILYENI.K_ARAC.KAPINUMARASI": variant}
                    res = await self._ntc_call("mainGetBusLocation_basic", payload)
                    if isinstance(res, list) and res:
                        item = res[0]
                        try:
                            lat = float(item.get("H_OTOBUSKONUM_ENLEM", 0.0))
                            lon = float(item.get("H_OTOBUSKONUM_BOYLAM", 0.0))
                        except (ValueError, TypeError):
                            lat, lon = 0.0, 0.0
                        try:
                            speed = (
                                int(item.get("H_OTOBUSKONUM_HIZ"))
                                if item.get("H_OTOBUSKONUM_HIZ") is not None
                                else None
                            )
                        except (ValueError, TypeError):
                            speed = None

                        return {
                            "plate": normalize_plate(item.get("K_ARAC_PLAKA")),
                            "latitude": lat if lat != 0.0 else None,
                            "longitude": lon if lon != 0.0 else None,
                            "speed": speed,
                            "last_seen": str(item.get("H_OTOBUSKONUM_KAYITZAMANI") or ""),
                        }
                except Exception:  # noqa: BLE001
                    pass
            return None

        ntc_data = await fetch_ntc_location()

        if not bus_fleet and not ntc_data:
            return None

        plate = (ntc_data and ntc_data.get("plate")) or (bus_fleet and bus_fleet.plate)
        lat = (ntc_data and ntc_data.get("latitude")) or (bus_fleet and bus_fleet.latitude)
        lon = (ntc_data and ntc_data.get("longitude")) or (bus_fleet and bus_fleet.longitude)
        speed = (
            (ntc_data and ntc_data.get("speed"))
            if (ntc_data and ntc_data.get("speed") is not None)
            else (bus_fleet and bus_fleet.speed)
        )
        last_seen = (
            (ntc_data and ntc_data.get("last_seen")) or (bus_fleet and bus_fleet.last_seen) or ""
        )
        route_code = bus_fleet.route_code if bus_fleet else None
        operator = bus_fleet.operator if bus_fleet else None

        return BusPosition(
            kapino=kapi,
            plate=plate,
            latitude=lat,
            longitude=lon,
            speed=speed,
            operator=operator,
            last_seen=last_seen,
            route_code=route_code,
        )

    async def refresh_fleet(self) -> bool:
        """Force refresh fleet in RAM (called by iett.refresh_fleet service)."""
        await self.ensure_fleet_fresh(force=True)
        return True


# Backwards compatibility aliases for existing tests
IettMiddleError = IettApiError
IettMiddleClient = IettClient
