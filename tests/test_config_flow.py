"""Tests for IettConfigFlow and IettOptionsFlowHandler v2."""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant import data_entry_flow

from custom_components.iett.config_flow import IettConfigFlow, IettOptionsFlowHandler
from custom_components.iett.const import (
    CONF_FEED_TYPE,
    CONF_KAPINO,
    CONF_ROUTE_CODE,
    CONF_SCAN_INTERVAL,
    CONF_SPEED_UNIT,
    CONF_STOP_ATTRIBUTES,
    CONF_STOP_CODE,
    CONF_STOP_NAME,
    CONF_VEHICLE_LIMIT_MODE,
    CONF_VEHICLE_LIMIT_N,
    DEFAULT_ROOT_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    FEED_ROOT,
    FEED_ROUTE,
    FEED_STOP,
    FEED_VEHICLE,
    LIMIT_MODE_NEAREST_N,
    SPEED_UNIT_KMH,
)
from custom_components.iett.models import RouteSearchResult, StopMetadata


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
        )
    )
    client.get_routes_at_stop = AsyncMock(return_value=["500T", "14M"])
    client.search_stops = AsyncMock(
        return_value=[
            StopMetadata(dcode="301341", name="BEŞİKTAŞ MEYDAN"),
            StopMetadata(dcode="301342", name="BEŞİKTAŞ İSKELE"),
        ]
    )
    client.search_routes = AsyncMock(
        return_value=[
            RouteSearchResult(hat_kodu="500T", name="TUZLA - CEVİZLİBAĞ"),
        ]
    )
    client.get_route_variants = AsyncMock(return_value=["500T_G_D0", "500T_D_D0"])
    return client


def _init_flow(hass: MagicMock, client: MagicMock | None = None) -> IettConfigFlow:
    flow = IettConfigFlow()
    flow.hass = hass
    flow.context = {}
    if client:
        flow._client = client
    return flow


# ---------------------------------------------------------------------------
# Page 1 Menu Tests
# ---------------------------------------------------------------------------


async def test_user_step_shows_menu_with_root(hass: MagicMock) -> None:
    flow = _init_flow(hass)
    result = await flow.async_step_user()
    assert result["type"] == data_entry_flow.FlowResultType.MENU
    assert result["step_id"] == "user"
    assert "root" in result["menu_options"]
    assert "stop" in result["menu_options"]
    assert "route" in result["menu_options"]
    assert "vehicle" in result["menu_options"]


async def test_user_step_menu_omits_root_if_already_configured(hass: MagicMock) -> None:
    entry = MagicMock()
    entry.data = {CONF_FEED_TYPE: FEED_ROOT}
    hass.config_entries.async_entries = MagicMock(return_value=[entry])

    flow = _init_flow(hass)
    result = await flow.async_step_user()
    assert result["type"] == data_entry_flow.FlowResultType.MENU
    assert "root" not in result["menu_options"]
    assert "stop" in result["menu_options"]


# ---------------------------------------------------------------------------
# Root Flow Tests
# ---------------------------------------------------------------------------


async def test_root_flow_creates_entry(hass: MagicMock) -> None:
    flow = _init_flow(hass)
    result = await flow.async_step_root()
    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert result["title"] == "İETT İstanbul Geneli"
    assert result["data"][CONF_FEED_TYPE] == FEED_ROOT
    assert result["data"][CONF_SCAN_INTERVAL] == DEFAULT_ROOT_SCAN_INTERVAL


# ---------------------------------------------------------------------------
# Stop Wizard (1a) Tests
# ---------------------------------------------------------------------------


async def test_stop_flow_exact_6_digit_code(hass: MagicMock, mock_client: MagicMock) -> None:
    flow = _init_flow(hass, mock_client)

    result = await flow.async_step_stop()
    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == "stop"

    # Enter exact 6-digit code
    result2 = await flow.async_step_stop({"stop_query": "301341"})
    assert result2["type"] == data_entry_flow.FlowResultType.FORM
    assert result2["step_id"] == "stop_config"

    # Complete stop config
    result3 = await flow.async_step_stop_config(
        {
            CONF_VEHICLE_LIMIT_MODE: LIMIT_MODE_NEAREST_N,
            CONF_VEHICLE_LIMIT_N: 2,
            CONF_STOP_ATTRIBUTES: ["hatno", "plaka", "eta"],
            CONF_SPEED_UNIT: SPEED_UNIT_KMH,
        }
    )
    assert result3["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert result3["data"][CONF_FEED_TYPE] == FEED_STOP
    assert result3["data"][CONF_STOP_CODE] == "301341"
    assert result3["data"][CONF_STOP_NAME] == "BEŞİKTAŞ MEYDAN"


async def test_stop_flow_search_and_select(hass: MagicMock, mock_client: MagicMock) -> None:
    flow = _init_flow(hass, mock_client)

    result = await flow.async_step_stop({"stop_query": "Beşiktaş"})
    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == "stop_select"

    result2 = await flow.async_step_stop_select({"selected_stop": "301341"})
    assert result2["type"] == data_entry_flow.FlowResultType.FORM
    assert result2["step_id"] == "stop_config"


async def test_stop_flow_errors(hass: MagicMock, mock_client: MagicMock) -> None:
    mock_client.search_stops = AsyncMock(return_value=[])
    flow = _init_flow(hass, mock_client)

    # Empty query
    result = await flow.async_step_stop({"stop_query": ""})
    assert result["errors"]["base"] == "invalid_stop_query"

    # Not found query
    result2 = await flow.async_step_stop({"stop_query": "NonExistentStop"})
    assert result2["errors"]["base"] == "no_stops_found"


# ---------------------------------------------------------------------------
# Route Wizard (1b) Tests
# ---------------------------------------------------------------------------


async def test_route_flow_success(hass: MagicMock, mock_client: MagicMock) -> None:
    flow = _init_flow(hass, mock_client)

    result = await flow.async_step_route({"route_query": "500T"})
    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == "route_config"

    result2 = await flow.async_step_route_config({})
    assert result2["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert result2["title"] == "Hat 500T"
    assert result2["data"][CONF_FEED_TYPE] == FEED_ROUTE
    assert result2["data"][CONF_ROUTE_CODE] == "500T"


async def test_route_flow_ambiguous_select(hass: MagicMock, mock_client: MagicMock) -> None:
    """Test route flow when search returns multiple routes prompting route_select."""
    from custom_components.iett.models import RouteSearchResult

    mock_client.search_routes = AsyncMock(
        return_value=[
            RouteSearchResult(hat_kodu="14B", name="KADIKÖY - BİRLİK"),
            RouteSearchResult(hat_kodu="14ES", name="KADIKÖY - ESENKENT"),
        ]
    )
    mock_client.get_route_variants = AsyncMock(return_value=[])
    flow = _init_flow(hass, mock_client)

    result = await flow.async_step_route({"route_query": "KADIKÖY"})
    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == "route_select"

    result2 = await flow.async_step_route_select({"selected_route": "14B"})
    assert result2["type"] == data_entry_flow.FlowResultType.FORM
    assert result2["step_id"] == "route_config"

    result3 = await flow.async_step_route_config({})
    assert result3["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert result3["title"] == "Hat 14B"
    assert result3["data"][CONF_ROUTE_CODE] == "14B"


# ---------------------------------------------------------------------------
# Vehicle Wizard (1c) Tests (Strict Kapı No Only)
# ---------------------------------------------------------------------------


async def test_vehicle_flow_strict_kapino_success(hass: MagicMock) -> None:
    flow = _init_flow(hass)

    result = await flow.async_step_vehicle(
        {
            CONF_KAPINO: "c-1753",
            CONF_SPEED_UNIT: SPEED_UNIT_KMH,
        }
    )
    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert result["title"] == "Araç C-1753"
    assert result["data"][CONF_FEED_TYPE] == FEED_VEHICLE
    assert result["data"][CONF_KAPINO] == "C-1753"


async def test_vehicle_flow_rejects_plates_and_unhyphenated(hass: MagicMock) -> None:
    flow = _init_flow(hass)

    # 1. Reject unhyphenated "C1753"
    result = await flow.async_step_vehicle({CONF_KAPINO: "C1753"})
    assert result["errors"]["base"] == "invalid_kapino_strict"

    # 2. Reject plate "34 HO 1234"
    result2 = await flow.async_step_vehicle({CONF_KAPINO: "34 HO 1234"})
    assert result2["errors"]["base"] == "invalid_kapino_strict"

    # 3. Reject empty
    result3 = await flow.async_step_vehicle({CONF_KAPINO: ""})
    assert result3["errors"]["base"] == "invalid_kapino_strict"


# ---------------------------------------------------------------------------
# Options Flow Tests
# ---------------------------------------------------------------------------


async def test_options_flow(hass: MagicMock) -> None:
    entry = MagicMock()
    entry.entry_id = "test_entry_id"
    entry.data = {
        CONF_FEED_TYPE: FEED_STOP,
        CONF_STOP_CODE: "301341",
        CONF_SCAN_INTERVAL: DEFAULT_SCAN_INTERVAL,
        CONF_STOP_ATTRIBUTES: ["hatno", "eta"],
    }

    options_flow = IettOptionsFlowHandler(entry)
    options_flow.hass = hass

    result = await options_flow.async_step_init()
    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == "init"

    result2 = await options_flow.async_step_init(
        user_input={
            CONF_SCAN_INTERVAL: 45,
            CONF_STOP_ATTRIBUTES: ["hatno", "plaka", "eta"],
        }
    )
    assert result2["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    hass.config_entries.async_update_entry.assert_called_once()
    hass.config_entries.async_reload.assert_not_called()


async def test_options_flow_update_listener_no_duplicate_reload(hass: MagicMock) -> None:
    """Verify options flow delegates reload solely to update_listener without duplicate reload."""
    from custom_components.iett import async_reload_entry

    entry = MagicMock()
    entry.entry_id = "test_entry_id_opt"
    entry.data = {
        CONF_FEED_TYPE: FEED_STOP,
        CONF_STOP_CODE: "301341",
        CONF_SCAN_INTERVAL: DEFAULT_SCAN_INTERVAL,
    }

    # Simulate HA's async_update_entry triggering update_listener
    reload_calls = 0

    async def _mock_reload(entry_id: str) -> None:
        nonlocal reload_calls
        reload_calls += 1

    hass.config_entries.async_reload = AsyncMock(side_effect=_mock_reload)

    def _mock_update_entry(_entry: Any, data: dict[str, Any]) -> None:
        _entry.data = data
        # HA triggers registered update listeners
        asyncio.create_task(async_reload_entry(hass, _entry))

    hass.config_entries.async_update_entry = MagicMock(side_effect=_mock_update_entry)

    options_flow = IettOptionsFlowHandler(entry)
    options_flow.hass = hass

    result = await options_flow.async_step_init(user_input={CONF_SCAN_INTERVAL: 60})
    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY

    # Yield event loop to allow listener task to execute
    await asyncio.sleep(0.01)
    assert reload_calls == 1


async def test_options_flow_route_and_vehicle(hass: MagicMock) -> None:
    route_entry = MagicMock()
    route_entry.entry_id = "route_entry_id"
    route_entry.data = {
        CONF_FEED_TYPE: FEED_ROUTE,
        CONF_ROUTE_CODE: "500T",
        CONF_SCAN_INTERVAL: DEFAULT_SCAN_INTERVAL,
    }
    route_opt = IettOptionsFlowHandler(route_entry)
    route_opt.hass = hass
    res_route = await route_opt.async_step_init()
    assert res_route["type"] == data_entry_flow.FlowResultType.FORM

    veh_entry = MagicMock()
    veh_entry.entry_id = "veh_entry_id"
    veh_entry.data = {
        CONF_FEED_TYPE: FEED_VEHICLE,
        CONF_KAPINO: "C-1753",
        CONF_SPEED_UNIT: SPEED_UNIT_KMH,
    }
    veh_opt = IettOptionsFlowHandler(veh_entry)
    veh_opt.hass = hass
    res_veh = await veh_opt.async_step_init()
    assert res_veh["type"] == data_entry_flow.FlowResultType.FORM
