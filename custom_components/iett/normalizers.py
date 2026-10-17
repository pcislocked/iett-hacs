"""Formatters, sanitizers, and mathematical utilities for the İETT integration."""

from __future__ import annotations

import math
import re
from datetime import datetime, timezone
from typing import Any

# Strict Kapı No: 1-2 letters + dash + 3-5 digits (e.g. C-1753, A-001, M-1042)
_STRICT_KAPINO_RE = re.compile(r"^([A-Z]{1,2})-(\d{3,5})$")

# Flexible Kapı No pattern for raw API inputs (e.g. C1753, c 1753, A-001)
_FLEXIBLE_KAPINO_RE = re.compile(r"^([A-Z]{1,2})[\s-]*(\d+)$")

# Turkish vehicle plate pattern: 2 digits + 1-3 letters + 2-5 digits
_TR_PLATE_RE = re.compile(r"^(\d{2})([A-Z]{1,3})(\d{2,5})$")


def validate_strict_kapino(raw: Any) -> str | None:
    """Validate strict Kapı No format (X-NNNN / XX-NNNN).

    Returns uppercase formatted string if valid, otherwise None.
    Rejects plates, missing dashes, or invalid letter/digit combinations.
    """
    if raw is None:
        return None
    s = str(raw).strip().upper()
    if not s:
        return None
    match = _STRICT_KAPINO_RE.match(s)
    if match:
        return f"{match.group(1)}-{match.group(2)}"
    return None


def normalize_kapino(raw: Any) -> str | None:
    """Normalize raw Kapı No string into canonical X-ZZZZ format.

    Handles un-dashed or lowercase strings (e.g. 'c1753' -> 'C-1753').
    Returns clean string or None if input is empty/invalid.
    """
    if raw is None:
        return None
    s = str(raw).strip().upper()
    if not s:
        return None

    match = _FLEXIBLE_KAPINO_RE.match(s)
    if match:
        return f"{match.group(1)}-{match.group(2)}"
    return s


def normalize_plate(raw: Any) -> str | None:
    """Normalize Turkish license plate to canonical spaced format.

    Example: '34ho3448' -> '34 HO 3448', '34-tn-2229' -> '34 TN 2229'.
    """
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None

    # Handle Turkish dotted/dotless i before uppercase conversion
    clean = s.replace("i", "I").replace("ı", "I").replace("İ", "I").replace("I\u0307", "I").upper()
    alphanumeric = re.sub(r"[^A-Z0-9]", "", clean)

    match = _TR_PLATE_RE.match(alphanumeric)
    if match:
        return f"{match.group(1)} {match.group(2)} {match.group(3)}"

    # Sanitized fallback for custom or test plates
    collapsed = re.sub(r"\s+", " ", clean).strip()
    return collapsed or None


def parse_son_konum(value: Any) -> tuple[float | None, float | None]:
    """Parse NTCAPI 'lon,lat' or 'lon;lat' string into (lat, lon).

    Note: Upstream NTCAPI emits longitude first, latitude second.
    Returns (lat, lon) or (None, None) if missing or zero coordinates.
    """
    if not value:
        return None, None
    try:
        text = str(value).strip()
        if not text:
            return None, None
        parts = re.split(r"[;,]", text)
        if len(parts) < 2:
            return None, None
        lon = float(parts[0].strip())
        lat = float(parts[1].strip())
        if lat == 0.0 and lon == 0.0:
            return None, None
        return lat, lon
    except (IndexError, ValueError):
        return None, None


def haversine_meters(
    lat1: float | None,
    lon1: float | None,
    lat2: float | None,
    lon2: float | None,
) -> int | None:
    """Calculate great-circle distance between two GPS coordinates in meters.

    Returns None if any coordinate is missing, invalid, or (0.0, 0.0).
    """
    if lat1 is None or lon1 is None or lat2 is None or lon2 is None:
        return None

    try:
        f_lat1, f_lon1 = float(lat1), float(lon1)
        f_lat2, f_lon2 = float(lat2), float(lon2)
    except (ValueError, TypeError):
        return None

    if (f_lat1 == 0.0 and f_lon1 == 0.0) or (f_lat2 == 0.0 and f_lon2 == 0.0):
        return None

    r = 6_371_000.0  # Earth radius in meters
    phi1 = math.radians(f_lat1)
    phi2 = math.radians(f_lat2)
    dphi = math.radians(f_lat2 - f_lat1)
    dlambda = math.radians(f_lon2 - f_lon1)

    a = math.sin(dphi / 2.0) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2.0) ** 2
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(max(0.0, 1.0 - a)))
    return round(r * c)


def format_eta_mmss(
    eta_minutes: int | None,
    last_seen_ts: str | None = None,
    now: datetime | None = None,
) -> str | None:
    """Format ETA in MM:SS string, adjusting for seconds elapsed since last_seen_ts."""
    if eta_minutes is None:
        return None

    total_seconds = max(0, int(eta_minutes) * 60)

    if last_seen_ts:
        if now is None:
            now = datetime.now(timezone.utc)
        parsed_dt: datetime | None = None
        clean_ts = str(last_seen_ts).strip()

        # Try parsing ISO or timestamp formats
        try:
            if "T" in clean_ts:
                parsed_dt = datetime.fromisoformat(clean_ts)
                if parsed_dt.tzinfo is None:
                    parsed_dt = parsed_dt.replace(tzinfo=timezone.utc)
            elif len(clean_ts) == 8 and clean_ts.count(":") == 2:  # HH:MM:SS
                h, m, s = map(int, clean_ts.split(":"))
                parsed_dt = now.replace(hour=h, minute=m, second=s, microsecond=0)
            elif len(clean_ts) >= 19 and " " in clean_ts:  # YYYY-MM-DD HH:MM:SS
                parsed_dt = datetime.strptime(clean_ts[:19], "%Y-%m-%d %H:%M:%S").replace(
                    tzinfo=timezone.utc
                )
        except Exception:  # noqa: BLE001
            parsed_dt = None

        if parsed_dt:
            # If parsed timestamp is recent (within 0-120 seconds), discount elapsed seconds
            diff_sec = (now - parsed_dt).total_seconds()
            if 0 < diff_sec < 120:
                total_seconds = max(0, total_seconds - int(diff_sec))

    mm, ss = divmod(total_seconds, 60)
    return f"{mm:02d}:{ss:02d}"


def convert_speed(speed_kmh: float | None, unit: str = "kmh") -> int | float | None:
    """Convert speed from km/h to requested unit (kmh -> int, mph -> float rounded to 1 decimal)."""
    if speed_kmh is None:
        return None
    try:
        val = float(speed_kmh)
    except (ValueError, TypeError):
        return None

    if unit == "mph":
        return round(val * 0.621371, 1)
    return round(val)
