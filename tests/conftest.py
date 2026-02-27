"""Shared fixtures for iett-hacs tests.

Uses real-shape JSON responses that match iett-middle's output format.
"""
from __future__ import annotations

import sys
import asyncio

import pytest

# Ensure selector event loop on Windows
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# ── Captured iett-middle API responses ──────────────────────────────────────

FLEET_JSON = [
    {
        "kapino": "A-001",
        "plate": "34 HO 1000",
        "latitude": 41.1073516666667,
        "longitude": 29.0155733333333,
        "speed": 0,
        "operator": "İstanbul Halk Ulaşım",
        "last_seen": "00:19:57",
        "route_code": None,
        "route_name": None,
        "direction": None,
        "nearest_stop": None,
    }
]

ROUTE_FLEET_JSON = [
    {
        "kapino": "C-325",
        "plate": None,
        "latitude": 41.0819,
        "longitude": 29.0109,
        "speed": 42,
        "operator": None,
        "last_seen": "2026-02-27 00:05:54",
        "route_code": "500T",
        "route_name": "TUZLA ŞİFA MAHALLESİ - 4. LEVENT METRO",
        "direction": "ŞİFA SONDURAK",
        "nearest_stop": "113333",
    }
]

ARRIVALS_JSON = [
    {
        "route_code": "500T",
        "destination": "4.LEVENT METRO - ŞİFA SONDURAK",
        "eta_minutes": 4,
        "eta_raw": "(00:10) 4 dk",
    },
    {
        "route_code": "14M",
        "destination": "YENİ CAMİİ",
        "eta_minutes": 12,
        "eta_raw": "(00:25) 12 dk",
    },
]

SCHEDULE_JSON = [
    {
        "route_code": "500T",
        "route_name": "TUZLA ŞİFA MAHALLESİ - CEVİZLİBAĞ",
        "route_variant": "500T_D_D0",
        "direction": "D",
        "day_type": "H",
        "service_type": "ÖHO",
        "departure_time": "05:55",
    }
]

ANNOUNCEMENTS_JSON = [
    {
        "route_code": "500T",
        "route_name": "TUZLA ŞİFA MAHALLESİ - 4. LEVENT METRO",
        "type": "Günlük",
        "updated_at": "Kayit Saati: 09:00",
        "message": "YOĞUN TRAFİK NEDENİYLE GÜZERGAH DEĞİŞİKLİĞİ.",
    }
]

MIDDLE_BASE = "http://iett-middle.test"


@pytest.fixture()
async def session():
    import aiohttp
    async with aiohttp.ClientSession() as s:
        yield s
