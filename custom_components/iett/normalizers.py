"""Formatters, sanitizers, and mathematical utilities for the İETT integration."""

from __future__ import annotations

import math
import re
from datetime import datetime, timedelta, timezone
from typing import Any

ISTANBUL_TZ = timezone(timedelta(hours=3))

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


_HHMM_RE = re.compile(r"\b([01]\d|2[0-3]):([0-5]\d)\b")


def format_arrival_time(
    eta_minutes: int | None,
    eta_raw: str | None = None,
    now: datetime | None = None,
) -> str | None:
    """Format estimated arrival as absolute 24-hour clock time (HH:MM) in Istanbul time.

    Extracts HH:MM directly from upstream ``eta_raw`` (``saat``) if present,
    otherwise calculates ``now + eta_minutes`` in ``ISTANBUL_TZ`` (UTC+3).
    """
    if eta_raw:
        match = _HHMM_RE.search(str(eta_raw))
        if match:
            return f"{match.group(1)}:{match.group(2)}"

    if eta_minutes is None:
        return None

    try:
        mins = max(0, int(eta_minutes))
    except (ValueError, TypeError):
        return None

    if now is None:
        base_now = datetime.now(ISTANBUL_TZ)
    elif now.tzinfo is None:
        base_now = now.replace(tzinfo=ISTANBUL_TZ)
    else:
        base_now = now.astimezone(ISTANBUL_TZ)

    arrival_dt = base_now + timedelta(minutes=mins)
    return arrival_dt.strftime("%H:%M")


def format_eta_mmss(
    eta_minutes: int | None,
    last_seen_ts: str | None = None,
    now: datetime | None = None,
    eta_raw: str | None = None,
) -> str | None:
    """Return estimated arrival clock time (HH:MM) in Istanbul time.

    Note: Kept under the ``format_eta_mmss`` symbol for backward compatibility with
    existing config entries; İETT only provides minute-level ETA precision, so this
    returns the absolute arrival time ``HH:MM`` rather than a synthetic ``MM:SS``.
    """
    return format_arrival_time(eta_minutes, eta_raw=eta_raw, now=now)


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
