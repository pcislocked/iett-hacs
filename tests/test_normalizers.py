"""Unit tests for normalizers and mathematical helpers."""

from __future__ import annotations

from datetime import datetime, timezone

from custom_components.iett.normalizers import (
    convert_speed,
    format_eta_mmss,
    haversine_meters,
    normalize_kapino,
    normalize_plate,
    parse_son_konum,
    validate_strict_kapino,
)


class TestValidateStrictKapino:
    def test_valid_patterns(self) -> None:
        assert validate_strict_kapino("C-1753") == "C-1753"
        assert validate_strict_kapino("c-1753") == "C-1753"
        assert validate_strict_kapino("A-001") == "A-001"
        assert validate_strict_kapino("OA-1024") == "OA-1024"
        assert validate_strict_kapino("  m-999  ") == "M-999"

    def test_invalid_patterns(self) -> None:
        assert validate_strict_kapino("C1753") is None  # Missing dash
        assert validate_strict_kapino("1753") is None  # No letters
        assert validate_strict_kapino("34 HO 1234") is None  # Plate rejected
        assert validate_strict_kapino("C-12") is None  # Too few digits
        assert validate_strict_kapino("") is None
        assert validate_strict_kapino(None) is None


class TestNormalizeKapino:
    def test_normalizes_flexible_formats(self) -> None:
        assert normalize_kapino("c1753") == "C-1753"
        assert normalize_kapino("C 1753") == "C-1753"
        assert normalize_kapino("A-001") == "A-001"
        assert normalize_kapino("OA1024") == "OA-1024"
        assert normalize_kapino(None) is None
        assert normalize_kapino("") is None


class TestNormalizePlate:
    def test_valid_turkish_plates(self) -> None:
        assert normalize_plate("34ho1234") == "34 HO 1234"
        assert normalize_plate("34 HO 1234") == "34 HO 1234"
        assert normalize_plate("34-tn-2229") == "34 TN 2229"
        assert normalize_plate("41br123") == "41 BR 123"
        assert normalize_plate("06BJK123") == "06 BJK 123"
        assert normalize_plate("34a12345") == "34 A 12345"

    def test_turkish_dotted_i(self) -> None:
        assert normalize_plate("34ı1234") == "34 I 1234"
        assert normalize_plate("34i1234") == "34 I 1234"
        assert normalize_plate("34İ1234") == "34 I 1234"

    def test_fallback_or_none(self) -> None:
        assert normalize_plate(None) is None
        assert normalize_plate("") is None
        assert normalize_plate("TEST 1") == "TEST 1"


class TestParseSonKonum:
    def test_parses_swapped_lat_lon(self) -> None:
        # Input is lon,lat -> output must be (lat, lon)
        lat, lon = parse_son_konum("29.0020,41.0450")
        assert lat == 41.0450
        assert lon == 29.0020

    def test_semicolon_separator(self) -> None:
        lat, lon = parse_son_konum("29.0020;41.0450")
        assert lat == 41.0450
        assert lon == 29.0020

    def test_zero_or_invalid(self) -> None:
        assert parse_son_konum("0,0") == (None, None)
        assert parse_son_konum("0.0,0.0") == (None, None)
        assert parse_son_konum("") == (None, None)
        assert parse_son_konum("invalid") == (None, None)
        assert parse_son_konum(None) == (None, None)


class TestHaversineMeters:
    def test_calculates_distance(self) -> None:
        # Distance between Besiktas (41.0450, 29.0020) and Levent (41.0819, 29.0109)
        dist = haversine_meters(41.0450, 29.0020, 41.0819, 29.0109)
        assert dist is not None
        assert 4000 < dist < 4500  # ~4.1 km

    def test_same_point(self) -> None:
        assert haversine_meters(41.0450, 29.0020, 41.0450, 29.0020) == 0

    def test_none_or_zero_guards(self) -> None:
        assert haversine_meters(None, 29.0, 41.0, 29.0) is None
        assert haversine_meters(41.0, 29.0, 0.0, 0.0) is None
        assert haversine_meters("bad", 29.0, 41.0, 29.0) is None


class TestFormatEtaMmss:
    def test_format_without_ts(self) -> None:
        assert format_eta_mmss(4) == "04:00"
        assert format_eta_mmss(12) == "12:00"
        assert format_eta_mmss(0) == "00:00"
        assert format_eta_mmss(None) is None

    def test_format_with_recent_last_seen(self) -> None:
        now = datetime(2026, 10, 18, 14, 30, 30, tzinfo=timezone.utc)
        # Last seen was 30 seconds ago
        last_seen = "2026-10-18 14:30:00"
        formatted = format_eta_mmss(4, last_seen, now=now)
        # 4 minutes = 240 sec - 30 sec = 210 sec = 03:30
        assert formatted == "03:30"


class TestConvertSpeed:
    def test_kmh_and_mph(self) -> None:
        assert convert_speed(40, "kmh") == 40
        assert convert_speed(40.4, "kmh") == 40
        assert convert_speed(40, "mph") == 24.9
        assert convert_speed(None) is None
        assert convert_speed("bad") is None
