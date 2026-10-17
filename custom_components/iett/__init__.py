"""The İETT Istanbul Bus Tracker integration."""

from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .client import IettClient
from .const import (
    CONF_BASE_URL,
    CONF_DEPAR_MODE,
    CONF_DIRECTION_FILTER,
    CONF_FEED_TYPE,
    CONF_INCLUDE_ACTIVE_BUSES,
    CONF_INCLUDE_ANNOUNCEMENTS,
    CONF_INCLUDE_SCHEDULE,
    CONF_ROUTE_MODE,
    CONF_SCAN_INTERVAL,
    CONF_SPEED_UNIT,
    CONF_STOP_ATTRIBUTES,
    CONF_VEHICLE_LIMIT_MODE,
    CONF_VEHICLE_LIMIT_N,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_STOP_ATTRIBUTES,
    DEPAR_MODE_ALL,
    DIR_FILTER_BOTH,
    DOMAIN,
    FEED_ALL_FLEET,
    FEED_ROOT,
    FEED_ROUTE,
    FEED_STOP,
    FRONTEND_STATIC_URL,
    FRONTEND_VERSION,
    LIMIT_MODE_NEAREST_N,
    ROUTE_MODE_ALL,
    SERVICE_REFRESH_FLEET,
    SPEED_UNIT_KMH,
)
from .coordinator import IettEntryCoordinator, IettRootCoordinator
from .websocket_api import async_register_websocket_handlers

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.DEVICE_TRACKER,
]


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the İETT component integration level services."""

    async def handle_refresh_fleet(call: ServiceCall) -> None:
        """Force refresh the shared RAM fleet cache."""
        client: IettClient | None = hass.data.get(DOMAIN, {}).get("client")
        if client:
            await client.refresh_fleet()
            _LOGGER.info("İETT fleet cache refreshed via service call")

    hass.services.async_register(DOMAIN, SERVICE_REFRESH_FLEET, handle_refresh_fleet)
    return True


async def _async_register_frontend(hass: HomeAssistant) -> None:
    """Register the bundled iett-card.js static path and Lovelace resource."""
    if hass.data.get(DOMAIN, {}).get("frontend_registered"):
        return

    js_file = Path(__file__).parent / "frontend" / "iett-card.js"
    if not js_file.exists():
        return

    if hasattr(hass, "http") and hass.http is not None:
        try:
            from homeassistant.components.http import StaticPathConfig

            await hass.http.async_register_static_paths(
                [StaticPathConfig(FRONTEND_STATIC_URL, str(js_file), cache_headers=False)]
            )
        except (ImportError, AttributeError):
            if hasattr(hass.http, "register_static_path"):
                hass.http.register_static_path(
                    FRONTEND_STATIC_URL, str(js_file), cache_headers=False
                )

        try:
            from homeassistant.components.frontend import add_extra_js_url

            add_extra_js_url(hass, f"{FRONTEND_STATIC_URL}?v={FRONTEND_VERSION}")
        except Exception:  # noqa: BLE001
            pass

    hass.data.setdefault(DOMAIN, {})["frontend_registered"] = True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up İETT from a config entry."""
    hass_domain_data = hass.data.setdefault(DOMAIN, {})

    # 1. Initialize shared standalone IettClient
    if "client" not in hass_domain_data:
        session = async_get_clientsession(hass)
        hass_domain_data["client"] = IettClient(session)
    client: IettClient = hass_domain_data["client"]

    # 2. Initialize shared singleton Root Coordinator for the 4 root sensors
    if "root_coordinator" not in hass_domain_data:
        root_coord = IettRootCoordinator(hass, client)
        await root_coord.async_config_entry_first_refresh()
        hass_domain_data["root_coordinator"] = root_coord

    # 3. Register WebSocket API commands for on-demand Lovelace card
    async_register_websocket_handlers(hass)

    # 4. Register bundled frontend Lovelace card resource
    await _async_register_frontend(hass)

    # 5. Initialize Entry Coordinator
    coord = IettEntryCoordinator(hass, entry, client)
    await coord.async_config_entry_first_refresh()
    hass_domain_data[entry.entry_id] = coord

    # 6. Forward entry setups to platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # 7. Add reload listener for options flow
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))

    return True


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload config entry when options are updated."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload an İETT config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        domain_data = hass.data.get(DOMAIN, {})
        domain_data.pop(entry.entry_id, None)

        # If this entry was the root sensors creator, allow another entry to adopt them
        if domain_data.get("root_sensors_owner") == entry.entry_id:
            domain_data.pop("root_sensors_created", None)
            domain_data.pop("root_sensors_owner", None)

    return unload_ok


async def async_migrate_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Migrate legacy v1 config entries to v2."""
    if config_entry.version == 1:
        _LOGGER.info("Migrating İETT entry %s from v1 to v2", config_entry.entry_id)
        new_data = {**config_entry.data}
        new_data.pop(CONF_BASE_URL, None)

        feed_type = new_data.get(CONF_FEED_TYPE)
        if feed_type in (FEED_ALL_FLEET, "all_fleet"):
            new_data[CONF_FEED_TYPE] = FEED_ROOT
        elif feed_type == FEED_STOP:
            new_data.setdefault(CONF_ROUTE_MODE, ROUTE_MODE_ALL)
            new_data.setdefault(CONF_VEHICLE_LIMIT_MODE, LIMIT_MODE_NEAREST_N)
            new_data.setdefault(CONF_VEHICLE_LIMIT_N, 1)
            new_data.setdefault(CONF_STOP_ATTRIBUTES, DEFAULT_STOP_ATTRIBUTES)
            new_data.setdefault(CONF_SPEED_UNIT, SPEED_UNIT_KMH)
        elif feed_type == FEED_ROUTE:
            new_data.setdefault(CONF_INCLUDE_ACTIVE_BUSES, True)
            new_data.setdefault(CONF_INCLUDE_ANNOUNCEMENTS, True)
            new_data.setdefault(CONF_INCLUDE_SCHEDULE, True)
            new_data.setdefault(CONF_DIRECTION_FILTER, DIR_FILTER_BOTH)
            new_data.setdefault(CONF_DEPAR_MODE, DEPAR_MODE_ALL)

        new_data.setdefault(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)

        hass.config_entries.async_update_entry(config_entry, data=new_data, version=2)
        _LOGGER.info("Migration to v2 successful for %s", config_entry.entry_id)

    return True
