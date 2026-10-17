"""Tests for İETT integration lifecycle (__init__.py) v2."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

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
        "dcode": "220602",
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
    assert new_data[CONF_ROUTE_MODE] == "all"
    assert CONF_STOP_ATTRIBUTES in new_data


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
