"""Constants for the İETT Home Assistant integration."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Final

DOMAIN: Final = "iett"

# Upstream Endpoints (100% Standalone — No external middleware required)
IETT_SOAP_BASE: Final = "https://api.ibb.gov.tr/iett"
IETT_REST_BASE: Final = "https://iett.istanbul"
NTC_TOKEN_URL: Final = "https://ntcapi.iett.istanbul/oauth2/v2/auth"
NTC_SERVICE_URL: Final = "https://ntcapi.iett.istanbul/service"
TKM_TRAFFIC_INDEX_URL: Final = (
    "https://tkmservices.ibb.gov.tr/web/api/TrafficData/v1/TrafficIndex_Sc1_Cont"
)

# Public Mobile App Credentials for NTCAPI
NTC_CLIENT_ID: Final = "pLwqtobYHTBshBWRrEZdSWsngOywQvHa"
NTC_CLIENT_SECRET: Final = "JERLUJgaZSygMTqoCtrhrVnvqeVGGVznktlwuOfHqmQTzjnC"
NTC_SCOPE: Final = "VLCn2qErUdrr1Ehg0yxWObMW9krFb7RC service"
NTC_YBS_USER: Final = "netuce"
NTC_YBS_PASS: Final = "n1!t8c7M1"

# Feed Types
CONF_FEED_TYPE: Final = "feed_type"
FEED_ROOT: Final = "root"  # 4 Kök Sensör (Genel, Avrupa, Anadolu Trafik + Filo Sayısı)
FEED_STOP: Final = "stop"  # 1a: Durak Takibi
FEED_ROUTE: Final = "route"  # 1b: Hat Takibi
FEED_VEHICLE: Final = "vehicle"  # 1c: Tekil Araç Takibi (Strict Kapı No)
FEED_ALL_FLEET: Final = "all_fleet"  # Legacy v1 migration constant

# Legacy v1 Config Key (removed during v1->v2 migration)
CONF_BASE_URL: Final = "base_url"

# Common Config Keys
CONF_SCAN_INTERVAL: Final = "scan_interval"
CONF_SPEED_UNIT: Final = "speed_unit"
SPEED_UNIT_KMH: Final = "kmh"
SPEED_UNIT_MPH: Final = "mph"

# 1a) Stop Config Keys
CONF_STOP_CODE: Final = "stop_code"
CONF_STOP_NAME: Final = "stop_name"
CONF_STOP_LAT: Final = "stop_lat"
CONF_STOP_LON: Final = "stop_lon"
CONF_STOP_DIRECTION: Final = "stop_direction"
CONF_STOP_DISTRICT: Final = "stop_district"
CONF_STOP_TYPE: Final = "stop_type"
CONF_STOP_SMART: Final = "stop_smart"

CONF_ROUTE_MODE: Final = "route_mode"
ROUTE_MODE_ALL: Final = "all"
ROUTE_MODE_SELECTED: Final = "selected"
CONF_SELECTED_ROUTES: Final = "selected_routes"

CONF_VEHICLE_LIMIT_MODE: Final = "vehicle_limit_mode"
LIMIT_MODE_ALL: Final = "all"
LIMIT_MODE_NEAREST_N: Final = "nearest_n"
CONF_VEHICLE_LIMIT_N: Final = "vehicle_limit_n"

CONF_STOP_ATTRIBUTES: Final = "stop_attributes"
ATTR_OPT_HATNO: Final = "hatno"
ATTR_OPT_PLAKA: Final = "plaka"
ATTR_OPT_ETA: Final = "eta"
ATTR_OPT_ETA_MMSS: Final = "eta_mmss"
ATTR_OPT_COORDS: Final = "coords"
ATTR_OPT_COORDS_TRACKER: Final = "coords_tracker"
ATTR_OPT_DIST_STOP: Final = "dist_stop"
ATTR_OPT_DIST_CUSTOM: Final = "dist_custom"
ATTR_OPT_SPEED: Final = "speed"
ATTR_OPT_AMENITIES: Final = "amenities"

ALL_STOP_ATTRIBUTE_OPTIONS: Final[list[str]] = [
    ATTR_OPT_HATNO,
    ATTR_OPT_PLAKA,
    ATTR_OPT_ETA,
    ATTR_OPT_ETA_MMSS,
    ATTR_OPT_COORDS,
    ATTR_OPT_COORDS_TRACKER,
    ATTR_OPT_DIST_STOP,
    ATTR_OPT_DIST_CUSTOM,
    ATTR_OPT_SPEED,
    ATTR_OPT_AMENITIES,
]

DEFAULT_STOP_ATTRIBUTES: Final[list[str]] = [
    ATTR_OPT_HATNO,
    ATTR_OPT_PLAKA,
    ATTR_OPT_ETA,
    ATTR_OPT_ETA_MMSS,
    ATTR_OPT_DIST_STOP,
]

CONF_CUSTOM_LAT: Final = "custom_lat"
CONF_CUSTOM_LON: Final = "custom_lon"

# 1b) Route Config Keys
CONF_ROUTE_CODE: Final = "route_code"
CONF_ROUTE_NAME: Final = "route_name"
CONF_INCLUDE_ACTIVE_BUSES: Final = "include_active_buses"
CONF_INCLUDE_ANNOUNCEMENTS: Final = "include_announcements"
CONF_INCLUDE_SCHEDULE: Final = "include_schedule"

CONF_DIRECTION_FILTER: Final = "direction_filter"
DIR_FILTER_BOTH: Final = "both"
DIR_FILTER_G: Final = "G"
DIR_FILTER_D: Final = "D"

CONF_DEPAR_MODE: Final = "depar_mode"
DEPAR_MODE_ALL: Final = "all"
DEPAR_MODE_BASE_ONLY: Final = "base_only"
DEPAR_MODE_SELECTED: Final = "selected"
CONF_SELECTED_DEPARS: Final = "selected_depars"

# 1c) Vehicle Config Keys
CONF_KAPINO: Final = "kapino"

# Intervals & Cache TTLs (seconds)
DEFAULT_SCAN_INTERVAL: Final = 45
DEFAULT_ROOT_SCAN_INTERVAL: Final = 120
MIN_SCAN_INTERVAL: Final = 20
MAX_SCAN_INTERVAL: Final = 600

FLEET_RAM_CACHE_TTL: Final = 60
SCHEDULE_RAM_CACHE_TTL: Final = 3600
ANNOUNCEMENT_RAM_CACHE_TTL: Final = 600


# Services & Frontend
def _get_frontend_version() -> str:
    """Calculate frontend version string from manifest and card JS hash."""
    base_dir = Path(__file__).parent
    version = "2.1.1"
    try:
        manifest_path = base_dir / "manifest.json"
        if manifest_path.exists():
            manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
            version = manifest_data.get("version", version)
    except Exception:  # noqa: BLE001
        pass

    try:
        js_path = base_dir / "frontend" / "iett-card.js"
        if js_path.exists():
            content = js_path.read_bytes().replace(b"\r\n", b"\n")
            digest = hashlib.md5(content).hexdigest()[:8]
            return f"{version}.{digest}"
    except Exception:  # noqa: BLE001
        pass

    return version


SERVICE_REFRESH_FLEET: Final = "refresh_fleet"
FRONTEND_STATIC_URL: Final = "/iett_static/iett-card.js"
FRONTEND_VERSION: Final = _get_frontend_version()
