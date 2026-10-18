"""Shared fixtures and mock payloads for iett-hacs v2 tests."""

from __future__ import annotations

import asyncio
import sys
from collections.abc import AsyncGenerator
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import aiohttp
import pytest

# Ensure selector event loop on Windows
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

TKM_TRAFFIC_RESPONSE: dict[str, Any] = {
    "TI": 42,
    "TI_An": 38,
    "TI_Av": 46,
}

SOAP_FLEET_XML: str = """<?xml version="1.0" encoding="utf-8"?>
<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:xsd="http://www.w3.org/2001/XMLSchema">
  <soap:Body>
    <GetFiloAracKonum_jsonResponse xmlns="http://tempuri.org/">
      <GetFiloAracKonum_jsonResult>[
        {
          "KapiNo": "C-1753",
          "Plaka": "34 HO 1234",
          "Enlem": "41.0450",
          "Boylam": "29.0020",
          "Hiz": "35",
          "Operator": "İETT",
          "Saat": "14:30:00",
          "HatKodu": "500T"
        },
        {
          "KapiNo": "A-001",
          "Plaka": "34 TP 2000",
          "Enlem": "41.0819",
          "Boylam": "29.0109",
          "Hiz": "0",
          "Operator": "ÖHO",
          "Saat": "14:29:45",
          "HatKodu": "14M"
        }
      ]</GetFiloAracKonum_jsonResult>
    </GetFiloAracKonum_jsonResponse>
  </soap:Body>
</soap:Envelope>"""

SOAP_ROUTE_FLEET_XML: str = """<?xml version="1.0" encoding="utf-8"?>
<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
  <soap:Body>
    <GetHatOtoKonum_jsonResponse xmlns="http://tempuri.org/">
      <GetHatOtoKonum_jsonResult>[
        {
          "kapino": "C-1753",
          "enlem": "41.0450",
          "boylam": "29.0020",
          "son_konum_zamani": "14:30:00",
          "hatad": "TUZLA - CEVİZLİBAĞ",
          "yon": "G",
          "guzergahkodu": "500T_G_D0",
          "yakinDurakKodu": "301341"
        }
      ]</GetHatOtoKonum_jsonResult>
    </GetHatOtoKonum_jsonResponse>
  </soap:Body>
</soap:Envelope>"""

SOAP_SCHEDULE_XML: str = """<?xml version="1.0" encoding="utf-8"?>
<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
  <soap:Body>
    <GetPlanlananSeferSaati_jsonResponse xmlns="http://tempuri.org/">
      <GetPlanlananSeferSaati_jsonResult>[
        {
          "SHATKODU": "500T",
          "HATADI": "TUZLA - CEVİZLİBAĞ",
          "SGUZERAH": "500T_G_D0",
          "SYON": "G",
          "SGUNTIPI": "H",
          "SSERVISTIPI": "ÖHO",
          "DT": "08:30"
        },
        {
          "SHATKODU": "500T",
          "HATADI": "TUZLA - CEVİZLİBAĞ",
          "SGUZERAH": "500T_G_D12",
          "SYON": "G",
          "SGUNTIPI": "H",
          "SSERVISTIPI": "ÖHO",
          "DT": "08:45"
        },
        {
          "SHATKODU": "500T",
          "HATADI": "TUZLA - CEVİZLİBAĞ",
          "SGUZERAH": "500T_D_D0",
          "SYON": "D",
          "SGUNTIPI": "H",
          "SSERVISTIPI": "ÖHO",
          "DT": "09:00"
        }
      ]</GetPlanlananSeferSaati_jsonResult>
    </GetPlanlananSeferSaati_jsonResponse>
  </soap:Body>
</soap:Envelope>"""

SOAP_ANNOUNCEMENTS_XML: str = """<?xml version="1.0" encoding="utf-8"?>
<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
  <soap:Body>
    <GetDuyurular_jsonResponse xmlns="http://tempuri.org/">
      <GetDuyurular_jsonResult>[
        {
          "HATKODU": "500T",
          "HAT": "TUZLA - CEVİZLİBAĞ",
          "TIP": "Güzergah Değişikliği",
          "GUNCELLEME_SAATI": "07:30",
          "MESAJ": "Trafik yoğunluğu nedeniyle seferler gecikmeli yapılmaktadır."
        }
      ]</GetDuyurular_jsonResult>
    </GetDuyurular_jsonResponse>
  </soap:Body>
</soap:Envelope>"""

SOAP_STOP_DETAIL_XML: str = """<?xml version="1.0" encoding="utf-8"?>
<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
  <soap:Body>
    <GetDurak_jsonResponse xmlns="http://tempuri.org/">
      <GetDurak_jsonResult>[
        {
          "DurakAdi": "BEŞİKTAŞ MEYDAN",
          "SDURAKADI": "BEŞİKTAŞ MEYDAN",
          "SYON": "ZİNCİRLİKUYU YÖNÜ",
          "KOORDINAT": "POINT (29.0020 41.0450)"
        }
      ]</GetDurak_jsonResult>
    </GetDurak_jsonResponse>
  </soap:Body>
</soap:Envelope>"""

NTC_AUTH_JSON: dict[str, Any] = {
    "access_token": "mock_token_12345",
    "expires_in": 3600,
    "token_type": "Bearer",
}

NTC_STOP_ARRIVALS_JSON: list[dict[str, Any]] = [
    {
        "hatkodu": "500T",
        "hatadi": "ŞİFA MAHALLESİ",
        "dakika": 4,
        "saat": "(14:34) 4 dk",
        "kapino": "C-1753",
        "son_konum": "29.0020,41.0450",
        "son_hiz": 32,
        "son_konum_saati": "14:30:15",
        "klima": 1,
        "wifi": 1,
        "usb": 1,
        "engelli": 1,
    },
    {
        "hatkodu": "14M",
        "hatadi": "KAVACIK",
        "dakika": 12,
        "saat": "(14:42) 12 dk",
        "kapino": "A-001",
        "son_konum": "29.0109,41.0819",
        "son_hiz": 0,
        "son_konum_saati": "14:29:45",
        "klima": 1,
        "wifi": 0,
        "usb": 0,
        "engelli": 1,
    },
]

NTC_BUS_LOCATION_JSON: list[dict[str, Any]] = [
    {
        "K_ARAC_KAPINUMARASI": "C-1753",
        "K_ARAC_PLAKA": "34 HO 1234",
        "H_OTOBUSKONUM_ENLEM": 41.0450,
        "H_OTOBUSKONUM_BOYLAM": 29.0020,
        "H_OTOBUSKONUM_HIZ": 35,
        "H_OTOBUSKONUM_KAYITZAMANI": "2026-10-18 14:30:00",
    }
]

HTML_STATION_DETAIL: str = """
<div id="info">
  <div class="station-item"><b>İlçe</b><p>Beşiktaş</p></div>
  <div class="station-item"><b>Fiziki Durum</b><p>Kapalı Durak</p></div>
  <div class="station-item"><b>Akıllı Durak</b><p>VAR</p></div>
</div>
"""

HTML_ROUTE_STATION: str = """
<div class="line-item"><a href="#"><span>500T</span></a></div>
<div class="line-item"><a href="#"><span>14M</span></a></div>
<div class="line-item"><a href="#"><span>29C</span></a></div>
"""


@pytest.fixture()
async def session() -> AsyncGenerator[aiohttp.ClientSession, None]:
    async with aiohttp.ClientSession() as s:
        yield s


@pytest.fixture()
def hass() -> MagicMock:
    h = MagicMock()
    h.config = MagicMock()
    h.config.latitude = 41.0082
    h.config.longitude = 28.9784
    h.data = {}
    h.config_entries = MagicMock()
    h.config_entries.async_entries = MagicMock(return_value=[])
    h.config_entries.async_entry_for_domain_unique_id = MagicMock(return_value=None)
    h.config_entries.async_update_entry = MagicMock()
    h.config_entries.async_reload = AsyncMock()
    return h
