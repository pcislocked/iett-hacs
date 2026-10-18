"""Tests for İETT integration lifecycle (__init__.py) v2."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.iett import (
    async_migrate_entry,
    async_setup,
    async_setup_entry,
    async_unload_entry,
)
from custom_components.iett.const import (
    CONF_BASE_URL,
    CONF_FEED_TYPE,
    CONF_ROUTE_MODE,
    CONF_STOP_ATTRIBUTES,
    DOMAIN,
    FEED_ALL_FLEET,
    FEED_ROOT,
    FEED_STOP,
    SERVICE_REFRESH_FLEET,
)
from custom_components.iett.models import RootStatus


def _mock_entry(entry_id: str, data: dict[str, Any], version: int = 2) -> MagicMock:
    entry = MagicMock()
    entry.entry_id = entry_id
    entry.data = data
    entry.version = version
    entry.add_update_listener = MagicMock()
    entry.async_on_unload = MagicMock()
    return entry


# ---------------------------------------------------------------------------
# Migration Tests (v1 -> v2)
# ---------------------------------------------------------------------------


async def test_migration_v1_to_v2_all_fleet(hass: MagicMock) -> None:
    old_data = {
        CONF_FEED_TYPE: FEED_ALL_FLEET,
        CONF_BASE_URL: "http://old-iett-middle:8000",
    }
    entry = _mock_entry("mig_entry_1", old_data, version=1)

    result = await async_migrate_entry(hass, entry)
    assert result is True

    hass.config_entries.async_update_entry.assert_called_once()
    _, kwargs = hass.config_entries.async_update_entry.call_args
    new_data = kwargs["data"]
    assert kwargs["version"] == 2
    assert CONF_BASE_URL not in new_data
    assert new_data[CONF_FEED_TYPE] == FEED_ROOT


async def test_migration_v1_to_v2_stop(hass: MagicMock) -> None:
    old_data = {
        CONF_FEED_TYPE: FEED_STOP,
        "dcode": "301341",
        CONF_BASE_URL: "http://old-iett-middle:8000",
    }
    entry = _mock_entry("mig_entry_2", old_data, version=1)

    result = await async_migrate_entry(hass, entry)
    assert result is True

    hass.config_entries.async_update_entry.assert_called_once()
    _, kwargs = hass.config_entries.async_update_entry.call_args
    new_data = kwargs["data"]
    assert kwargs["version"] == 2
    assert CONF_BASE_URL not in new_data
    assert "dcode" not in new_data
    assert new_data["stop_code"] == "301341"
    assert new_data[CONF_ROUTE_MODE] == "all"
    assert CONF_STOP_ATTRIBUTES in new_data


async def test_migration_v1_to_v2_route(hass: MagicMock) -> None:
    old_data = {
        CONF_FEED_TYPE: "route",
        "hat_kodu": "500T",
        CONF_BASE_URL: "http://old-iett-middle:8000",
    }
    entry = _mock_entry("mig_entry_3", old_data, version=1)

    result = await async_migrate_entry(hass, entry)
    assert result is True

    hass.config_entries.async_update_entry.assert_called_once()
    _, kwargs = hass.config_entries.async_update_entry.call_args
    new_data = kwargs["data"]
    assert kwargs["version"] == 2
    assert "hat_kodu" not in new_data
    assert new_data["route_code"] == "500T"


async def test_diagnostics_redacts_gps_coordinates(hass: MagicMock) -> None:
    from custom_components.iett.diagnostics import async_get_config_entry_diagnostics

    entry = _mock_entry(
        "diag_entry_1",
        {
            CONF_FEED_TYPE: FEED_STOP,
            "stop_code": "301341",
            "stop_lat": 41.0450,
            "stop_lon": 29.0020,
            "custom_lat": 41.0082,
            "custom_lon": 28.9784,
        },
    )
    entry.domain = DOMAIN
    entry.title = "Durak 301341"
    entry.options = {"custom_lat": 41.0082}

    coord = MagicMock()
    coord.data = {
        "stop_code": "301341",
        "vehicles": [
            {
                "kapino": "C-1753",
                "latitude": 41.0450,
                "longitude": 29.0020,
                "coords": "41.045, 29.002",
            }
        ],
    }
    client = MagicMock()
    client._fleet_by_kapino = {"C-1753": MagicMock()}
    client._token = "secret_token"

    hass.data[DOMAIN] = {
        "client": client,
        "diag_entry_1": coord,
    }

    diag = await async_get_config_entry_diagnostics(hass, entry)
    assert diag["entry"]["data"]["stop_code"] == "301341"
    assert diag["entry"]["data"]["custom_lat"] == "**REDACTED**"
    assert diag["entry"]["data"]["custom_lon"] == "**REDACTED**"
    assert diag["entry"]["data"]["stop_lat"] == "**REDACTED**"
    assert diag["entry"]["data"]["stop_lon"] == "**REDACTED**"
    assert diag["entry"]["options"]["custom_lat"] == "**REDACTED**"
    veh_diag = diag["coordinator_data"]["vehicles"][0]
    assert veh_diag["kapino"] == "C-1753"
    assert veh_diag["latitude"] == "**REDACTED**"
    assert veh_diag["longitude"] == "**REDACTED**"
    assert veh_diag["coords"] == "**REDACTED**"


# ---------------------------------------------------------------------------
# Setup & Unload Tests
# ---------------------------------------------------------------------------


async def test_async_setup_service_registration(hass: MagicMock) -> None:
    client = MagicMock()
    client.refresh_fleet = AsyncMock(return_value=True)
    hass.data[DOMAIN] = {"client": client}

    registered_services: dict[str, Any] = {}

    def mock_reg(domain: str, service: str, handler: Any) -> None:
        registered_services[service] = handler

    hass.services.async_register = mock_reg

    assert await async_setup(hass, {}) is True
    assert SERVICE_REFRESH_FLEET in registered_services

    # Call service handler
    await registered_services[SERVICE_REFRESH_FLEET](MagicMock())
    client.refresh_fleet.assert_called_once()


async def test_async_setup_and_unload_entry(hass: MagicMock) -> None:
    entry = _mock_entry("test_root_entry", {CONF_FEED_TYPE: FEED_ROOT})
    hass.config_entries.async_forward_entry_setups = AsyncMock(return_value=True)
    hass.config_entries.async_unload_platforms = AsyncMock(return_value=True)

    with (
        patch("custom_components.iett.async_get_clientsession", return_value=MagicMock()),
        patch("custom_components.iett.IettClient") as mock_client_cls,
        patch(
            "custom_components.iett.IettRootCoordinator.async_config_entry_first_refresh",
            new=AsyncMock(),
        ),
        patch(
            "custom_components.iett.IettEntryCoordinator.async_config_entry_first_refresh",
            new=AsyncMock(),
        ),
        patch("custom_components.iett._async_register_frontend", new=AsyncMock()),
    ):
        mock_client = mock_client_cls.return_value
        mock_client.get_root_status = AsyncMock(return_value=RootStatus(42, 46, 38, 2500))

        # 1. Setup entry
        setup_ok = await async_setup_entry(hass, entry)
        assert setup_ok is True
        assert DOMAIN in hass.data
        assert "client" in hass.data[DOMAIN]
        assert "root_coordinator" in hass.data[DOMAIN]
        assert entry.entry_id in hass.data[DOMAIN]

        # 2. Unload entry
        unload_ok = await async_unload_entry(hass, entry)
        assert unload_ok is True
        assert entry.entry_id not in hass.data[DOMAIN]


async def test_concurrent_setup_entries_does_not_duplicate_static_route(hass: MagicMock) -> None:
    import asyncio

    entry1 = _mock_entry("stop_entry_1", {CONF_FEED_TYPE: FEED_STOP, "stop_code": "301341"})
    entry2 = _mock_entry("stop_entry_2", {CONF_FEED_TYPE: FEED_STOP, "stop_code": "117382"})
    hass.config_entries.async_forward_entry_setups = AsyncMock(return_value=True)

    register_calls = 0

    async def slow_register_static_paths(configs: Any) -> None:
        nonlocal register_calls
        register_calls += 1
        await asyncio.sleep(0.02)
        if register_calls > 1:
            raise RuntimeError(
                "Added route will never be executed, method GET is already registered"
            )

    hass.http = MagicMock()
    hass.http.async_register_static_paths = slow_register_static_paths

    with (
        patch("custom_components.iett.async_get_clientsession", return_value=MagicMock()),
        patch("custom_components.iett.IettClient"),
        patch(
            "custom_components.iett.IettRootCoordinator.async_config_entry_first_refresh",
            new=AsyncMock(),
        ),
        patch(
            "custom_components.iett.IettEntryCoordinator.async_config_entry_first_refresh",
            new=AsyncMock(),
        ),
    ):
        res1, res2 = await asyncio.gather(
            async_setup_entry(hass, entry1),
            async_setup_entry(hass, entry2),
        )
        assert res1 is True
        assert res2 is True
        assert register_calls == 1


async def test_setup_entry_root_first_refresh_failure_raises_not_ready(hass: MagicMock) -> None:
    """Verify that root coordinator first refresh failure raises ConfigEntryNotReady and releases lock cleanly."""
    from homeassistant.exceptions import ConfigEntryNotReady

    entry = _mock_entry("test_root_entry_fail", {CONF_FEED_TYPE: FEED_ROOT})
    with (
        patch("custom_components.iett.async_get_clientsession", return_value=MagicMock()),
        patch("custom_components.iett.IettClient"),
        patch(
            "custom_components.iett.IettRootCoordinator.async_config_entry_first_refresh",
            side_effect=ConfigEntryNotReady("Network unreachable"),
        ),
        patch("custom_components.iett._async_register_frontend", new=AsyncMock()),
    ):
        with pytest.raises(ConfigEntryNotReady):
            await async_setup_entry(hass, entry)

        assert entry.entry_id not in hass.data.get(DOMAIN, {})


async def test_frontend_version_has_manifest_and_hash() -> None:
    from custom_components.iett.const import FRONTEND_VERSION

    assert FRONTEND_VERSION.startswith("2.1.1.")
    parts = FRONTEND_VERSION.split(".")
    assert len(parts) >= 4
    assert len(parts[3]) == 8


async def test_lovelace_resource_registration_creates_item(hass: MagicMock) -> None:
    from custom_components.iett import _async_register_lovelace_resource
    from custom_components.iett.const import FRONTEND_STATIC_URL, FRONTEND_VERSION

    mock_resources = MagicMock()
    mock_resources.loaded = True
    mock_resources.async_items = MagicMock(return_value=[])
    mock_resources.async_create_item = AsyncMock()

    hass.data["lovelace"] = {"resources": mock_resources}
    expected_url = f"{FRONTEND_STATIC_URL}?v={FRONTEND_VERSION}"

    success = await _async_register_lovelace_resource(hass, expected_url)
    assert success is True
    mock_resources.async_create_item.assert_called_once_with(
        {"res_type": "module", "url": expected_url}
    )


async def test_lovelace_resource_registration_updates_outdated_item(hass: MagicMock) -> None:
    from custom_components.iett import _async_register_lovelace_resource
    from custom_components.iett.const import FRONTEND_STATIC_URL, FRONTEND_VERSION

    mock_resources = MagicMock()
    mock_resources.loaded = True
    mock_resources.async_items = MagicMock(
        return_value=[{"id": "res_123", "url": f"{FRONTEND_STATIC_URL}?v=2.0.2", "type": "module"}]
    )
    mock_resources.async_update_item = AsyncMock()

    hass.data["lovelace"] = {"resources": mock_resources}
    expected_url = f"{FRONTEND_STATIC_URL}?v={FRONTEND_VERSION}"

    success = await _async_register_lovelace_resource(hass, expected_url)
    assert success is True
    mock_resources.async_update_item.assert_called_once_with(
        "res_123", {"res_type": "module", "url": expected_url}
    )


async def test_lovelace_resource_already_current_no_update(hass: MagicMock) -> None:
    from custom_components.iett import _async_register_lovelace_resource
    from custom_components.iett.const import FRONTEND_STATIC_URL, FRONTEND_VERSION

    expected_url = f"{FRONTEND_STATIC_URL}?v={FRONTEND_VERSION}"
    mock_resources = MagicMock()
    mock_resources.loaded = True
    mock_resources.async_items = MagicMock(
        return_value=[{"id": "res_123", "url": expected_url, "type": "module"}]
    )
    mock_resources.async_update_item = AsyncMock()
    mock_resources.async_create_item = AsyncMock()

    hass.data["lovelace"] = {"resources": mock_resources}

    success = await _async_register_lovelace_resource(hass, expected_url)
    assert success is True
    mock_resources.async_create_item.assert_not_called()
    mock_resources.async_update_item.assert_not_called()


async def test_frontend_registration_when_ha_already_running(hass: MagicMock) -> None:
    """Verify that when HA is already running, registration does not wait for EVENT_HOMEASSISTANT_START."""
    from custom_components.iett import _async_register_frontend

    hass.is_running = True
    hass.bus = MagicMock()
    hass.bus.async_listen_once = MagicMock()

    with patch(
        "custom_components.iett._async_register_lovelace_resource", AsyncMock(return_value=False)
    ):
        await _async_register_frontend(hass)

    # EVENT_HOMEASSISTANT_START listener should NOT be attached because HA is already running
    hass.bus.async_listen_once.assert_not_called()
    # async_create_task should be called to retry asynchronously
    assert hass.async_create_task.called
