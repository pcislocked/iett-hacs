"""Tests for İETT WebSocket API handlers (on-demand data for Lovelace card)."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.iett.client import IettApiError
from custom_components.iett.const import DOMAIN
from custom_components.iett.models import (
    Amenities,
    Announcement,
    Arrival,
    BusPosition,
    RouteSearchResult,
    ScheduledDeparture,
    StopMetadata,
)
from custom_components.iett.websocket_api import (
    async_register_websocket_handlers,
    ws_get_route_board,
    ws_get_stop_board,
    ws_get_vehicle_card,
    ws_search,
)


async def _call_ws(handler: Any, hass: Any, conn: Any, msg: Any) -> None:
    """Helper to unwrap and await @websocket_api.async_response handler."""
    fn = getattr(handler, "__wrapped__", handler)
    await fn(hass, conn, msg)


@pytest.fixture()
def mock_connection() -> MagicMock:
    conn = MagicMock()
    conn.send_result = MagicMock()
    conn.send_error = MagicMock()
    return conn


@pytest.fixture()
def mock_client() -> MagicMock:
    client = MagicMock()
    client.get_stop_metadata = AsyncMock(
        return_value=StopMetadata(
            dcode="301341",
            name="BEŞİKTAŞ MEYDAN",
            latitude=41.0450,
            longitude=29.0020,
            district="Beşiktaş",
            direction="ZİNCİRLİKUYU YÖNÜ",
        )
    )
    client.get_stop_arrivals = AsyncMock(
        return_value=[
            Arrival(
                route_code="500T",
                destination="CEVİZLİBAĞ",
                eta_minutes=4,
                eta_raw="14:34",
                kapino="C-1753",
                plate="34 HO 1234",
                lat=41.0480,
                lon=29.0050,
                speed_kmh=30,
                last_seen_ts="14:30:00",
                amenities=Amenities(ac=True, wifi=True),
            ),
            Arrival(
                route_code="14M",
                destination="KAVACIK",
                eta_minutes=15,
                eta_raw="14:45",
                kapino="A-001",
                plate="34 TP 2000",
                lat=41.0800,
                lon=29.0100,
                speed_kmh=0,
                last_seen_ts="14:30:00",
            ),
        ]
    )
    client.get_route_buses = AsyncMock(
        return_value=[BusPosition(kapino="C-1753", route_code="500T", plate="34 HO 1234", speed=35)]
    )
    client.get_route_schedule = AsyncMock(
        return_value=[
            ScheduledDeparture(
                route_code="500T",
                direction="G",
                departure_time="14:50",
            )
        ]
    )
    client.get_announcements = AsyncMock(
        return_value=[Announcement(route_code="500T", message="Trafik yoğunluğu")]
    )
    client.get_vehicle_status = AsyncMock(
        return_value=BusPosition(
            kapino="C-1753",
            plate="34 HO 1234",
            latitude=41.0450,
            longitude=29.0020,
            speed=35,
        )
    )
    client.search_stops = AsyncMock(
        return_value=[StopMetadata(dcode="301341", name="BEŞİKTAŞ MEYDAN")]
    )
    client.search_routes = AsyncMock(
        return_value=[RouteSearchResult(hat_kodu="500T", name="TUZLA - CEVİZLİBAĞ")]
    )
    return client


# ---------------------------------------------------------------------------
# Stop Board WS Tests
# ---------------------------------------------------------------------------


async def test_ws_get_stop_board_success(
    hass: MagicMock, mock_connection: MagicMock, mock_client: MagicMock
) -> None:
    hass.data[DOMAIN] = {"client": mock_client}

    msg = {
        "id": 1,
        "type": "iett/get_stop_board",
        "stop_code": "301341",
        "route_filter": [],
        "max_items": 10,
    }
    await _call_ws(ws_get_stop_board, hass, mock_connection, msg)

    mock_connection.send_result.assert_called_once()
    args, _ = mock_connection.send_result.call_args
    assert args[0] == 1
    result = args[1]
    assert result["stop_code"] == "301341"
    assert result["stop_name"] == "BEŞİKTAŞ MEYDAN"
    assert len(result["arrivals"]) == 2

    a1 = result["arrivals"][0]
    assert a1["route_code"] == "500T"
    assert a1["kapino"] == "C-1753"
    assert a1["eta_minutes"] == 4
    assert a1["eta_mmss"] == "14:34"
    assert a1["eta_time"] == "14:34"
    assert a1["distance_to_stop_m"] is not None
    assert a1["amenities"]["ac"] is True


async def test_ws_get_stop_board_filter(
    hass: MagicMock, mock_connection: MagicMock, mock_client: MagicMock
) -> None:
    hass.data[DOMAIN] = {"client": mock_client}

    msg = {
        "id": 2,
        "type": "iett/get_stop_board",
        "stop_code": "301341",
        "route_filter": ["14M"],
        "max_items": 10,
    }
    await _call_ws(ws_get_stop_board, hass, mock_connection, msg)

    mock_connection.send_result.assert_called_once()
    _, result = mock_connection.send_result.call_args[0]
    assert len(result["arrivals"]) == 1
    assert result["arrivals"][0]["route_code"] == "14M"


async def test_ws_get_stop_board_filter_case_insensitive_and_no_match(
    hass: MagicMock, mock_connection: MagicMock, mock_client: MagicMock
) -> None:
    hass.data[DOMAIN] = {"client": mock_client}

    # Case-insensitive matching e.g. "500t" -> "500T"
    msg_case = {
        "id": 3,
        "type": "iett/get_stop_board",
        "stop_code": "301341",
        "route_filter": ["500t"],
        "max_items": 10,
    }
    await _call_ws(ws_get_stop_board, hass, mock_connection, msg_case)
    _, result = mock_connection.send_result.call_args[0]
    assert len(result["arrivals"]) == 1
    assert result["arrivals"][0]["route_code"] == "500T"

    # Filter with no matching routes
    mock_connection.send_result.reset_mock()
    msg_none = {
        "id": 4,
        "type": "iett/get_stop_board",
        "stop_code": "301341",
        "route_filter": ["NONEXISTENT"],
        "max_items": 10,
    }
    await _call_ws(ws_get_stop_board, hass, mock_connection, msg_none)
    _, result_none = mock_connection.send_result.call_args[0]
    assert len(result_none["arrivals"]) == 0


async def test_ws_get_stop_board_api_error(
    hass: MagicMock, mock_connection: MagicMock, mock_client: MagicMock
) -> None:
    mock_client.get_stop_arrivals = AsyncMock(side_effect=IettApiError("Upstream timeout"))
    hass.data[DOMAIN] = {"client": mock_client}

    msg = {
        "id": 3,
        "type": "iett/get_stop_board",
        "stop_code": "301341",
    }
    await _call_ws(ws_get_stop_board, hass, mock_connection, msg)

    mock_connection.send_error.assert_called_once_with(3, "api_error", "Upstream timeout")


# ---------------------------------------------------------------------------
# Route Board WS Tests
# ---------------------------------------------------------------------------


async def test_ws_get_route_board_success(
    hass: MagicMock, mock_connection: MagicMock, mock_client: MagicMock
) -> None:
    hass.data[DOMAIN] = {"client": mock_client}

    msg = {
        "id": 4,
        "type": "iett/get_route_board",
        "route_code": "500T",
    }
    await _call_ws(ws_get_route_board, hass, mock_connection, msg)

    mock_connection.send_result.assert_called_once()
    _, result = mock_connection.send_result.call_args[0]
    assert result["route_code"] == "500T"
    assert result["active_buses"] == 1
    assert len(result["buses"]) == 1
    assert len(result["schedule"]) == 1
    assert len(result["announcements"]) == 1


# ---------------------------------------------------------------------------
# Vehicle Card WS Tests
# ---------------------------------------------------------------------------


async def test_ws_get_vehicle_card_online(
    hass: MagicMock, mock_connection: MagicMock, mock_client: MagicMock
) -> None:
    hass.data[DOMAIN] = {"client": mock_client}

    msg = {
        "id": 5,
        "type": "iett/get_vehicle_card",
        "kapino": "c-1753",
    }
    await _call_ws(ws_get_vehicle_card, hass, mock_connection, msg)

    mock_connection.send_result.assert_called_once()
    _, result = mock_connection.send_result.call_args[0]
    assert result["kapino"] == "C-1753"
    assert result["online"] is True
    assert result["vehicle"]["plate"] == "34 HO 1234"


async def test_ws_get_vehicle_card_offline(
    hass: MagicMock, mock_connection: MagicMock, mock_client: MagicMock
) -> None:
    mock_client.get_vehicle_status = AsyncMock(return_value=None)
    hass.data[DOMAIN] = {"client": mock_client}

    msg = {
        "id": 6,
        "type": "iett/get_vehicle_card",
        "kapino": "A-001",
    }
    await _call_ws(ws_get_vehicle_card, hass, mock_connection, msg)

    mock_connection.send_result.assert_called_once()
    _, result = mock_connection.send_result.call_args[0]
    assert result["online"] is False
    assert result["vehicle"] is None


# ---------------------------------------------------------------------------
# Search WS Tests
# ---------------------------------------------------------------------------


async def test_ws_search_stop(
    hass: MagicMock, mock_connection: MagicMock, mock_client: MagicMock
) -> None:
    hass.data[DOMAIN] = {"client": mock_client}

    msg = {
        "id": 7,
        "type": "iett/search",
        "query": "Beşiktaş",
        "search_type": "stop",
    }
    await _call_ws(ws_search, hass, mock_connection, msg)

    mock_connection.send_result.assert_called_once()
    _, result = mock_connection.send_result.call_args[0]
    assert len(result["results"]) == 1
    assert result["results"][0]["code"] == "301341"


async def test_ws_search_route(
    hass: MagicMock, mock_connection: MagicMock, mock_client: MagicMock
) -> None:
    hass.data[DOMAIN] = {"client": mock_client}

    msg = {
        "id": 8,
        "type": "iett/search",
        "query": "500T",
        "search_type": "route",
    }
    await _call_ws(ws_search, hass, mock_connection, msg)

    mock_connection.send_result.assert_called_once()
    _, result = mock_connection.send_result.call_args[0]
    assert len(result["results"]) == 1
    assert result["results"][0]["code"] == "500T"


# ---------------------------------------------------------------------------
# Handler Registration Tests
# ---------------------------------------------------------------------------


def test_async_register_websocket_handlers(hass: MagicMock) -> None:
    from unittest.mock import patch

    with patch("homeassistant.components.websocket_api.async_register_command") as mock_reg:
        async_register_websocket_handlers(hass)
        assert mock_reg.call_count == 4
        assert hass.data[DOMAIN]["ws_registered"] is True

        # Second call should be a no-op
        async_register_websocket_handlers(hass)
        assert mock_reg.call_count == 4
