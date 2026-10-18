"""The İETT Istanbul Bus Tracker integration."""

from __future__ import annotations

import asyncio
import inspect
import logging
from pathlib import Path
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import CoreState, HomeAssistant, ServiceCall
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
    CONF_ROUTE_CODE,
    CONF_ROUTE_MODE,
    CONF_SCAN_INTERVAL,
    CONF_SPEED_UNIT,
    CONF_STOP_ATTRIBUTES,
    CONF_STOP_CODE,
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


async def _async_register_lovelace_resource(hass: HomeAssistant, versioned_url: str) -> bool:
    """Register or update the Lovelace storage resource for the card."""
    try:
        lovelace_data = hass.data.get("lovelace")
        resources = getattr(lovelace_data, "resources", None)
        if resources is None and isinstance(lovelace_data, dict):
            resources = lovelace_data.get("resources")

        if resources is not None and hasattr(resources, "async_items"):
            if (
                hasattr(resources, "loaded")
                and not resources.loaded
                and hasattr(resources, "async_load")
            ):
                load_res = resources.async_load()
                if inspect.isawaitable(load_res):
                    await load_res

            items = resources.async_items()
            if inspect.isawaitable(items):
                items = await items

            existing = [
                item
                for item in (items or [])
                if isinstance(item, dict) and item.get("url", "").startswith(FRONTEND_STATIC_URL)
            ]
            if not existing:
                if hasattr(resources, "async_create_item"):
                    create_res = resources.async_create_item(
                        {"res_type": "module", "url": versioned_url}
                    )
                    if inspect.isawaitable(create_res):
                        await create_res
                    _LOGGER.info("Registered İETT card Lovelace resource: %s", versioned_url)
            else:
                for item in existing:
                    if item.get("url") != versioned_url and hasattr(resources, "async_update_item"):
                        update_res = resources.async_update_item(
                            item["id"], {"res_type": "module", "url": versioned_url}
                        )
                        if inspect.isawaitable(update_res):
                            await update_res
                        _LOGGER.info(
                            "Updated İETT card Lovelace resource from %s to %s",
                            item.get("url"),
                            versioned_url,
                        )
            return True
    except Exception as err:  # noqa: BLE001
        _LOGGER.debug("Could not register Lovelace storage resource: %s", err)
    return False


async def _async_register_frontend(hass: HomeAssistant) -> None:
    """Register the bundled iett-card.js static path and Lovelace resource."""
    domain_data = hass.data.setdefault(DOMAIN, {})
    frontend_lock: asyncio.Lock = domain_data.setdefault("_frontend_lock", asyncio.Lock())

    async with frontend_lock:
        js_file = Path(__file__).parent / "frontend" / "iett-card.js"
        if not js_file.exists():
            return

        versioned_url = f"{FRONTEND_STATIC_URL}?v={FRONTEND_VERSION}"

        # 1. Register HTTP static path (only once)
        if not domain_data.get("static_path_registered"):
            if hasattr(hass, "http") and hass.http is not None:
                try:
                    from homeassistant.components.http import StaticPathConfig

                    static_res = hass.http.async_register_static_paths(
                        [StaticPathConfig(FRONTEND_STATIC_URL, str(js_file), cache_headers=False)]
                    )
                    if inspect.isawaitable(static_res):
                        await static_res
                    domain_data["static_path_registered"] = True
                except (ImportError, AttributeError):
                    if hasattr(hass.http, "register_static_path"):
                        try:
                            hass.http.register_static_path(
                                FRONTEND_STATIC_URL, str(js_file), cache_headers=False
                            )
                            domain_data["static_path_registered"] = True
                        except RuntimeError:
                            domain_data["static_path_registered"] = True
                except RuntimeError:
                    # Route "/iett_static/iett-card.js" already registered on HTTP router
                    domain_data["static_path_registered"] = True
                    _LOGGER.debug("Static path %s already registered", FRONTEND_STATIC_URL)

                try:
                    from homeassistant.components.frontend import add_extra_js_url

                    try:
                        add_extra_js_url(hass, versioned_url, es5=False)
                        add_extra_js_url(hass, versioned_url, es5=True)
                    except TypeError:
                        add_extra_js_url(hass, versioned_url)
                except Exception:  # noqa: BLE001
                    pass

        # 2. Register Lovelace storage resource
        if not domain_data.get("lovelace_resource_registered"):
            registered = await _async_register_lovelace_resource(hass, versioned_url)
            if registered:
                domain_data["lovelace_resource_registered"] = True
            else:
                is_running = (
                    getattr(hass, "is_running", False) is True
                    or getattr(hass, "state", None) == CoreState.running
                )
                if is_running:
                    # HA already running — EVENT_HOMEASSISTANT_START will never fire.
                    # Retry in a background task after yielding to let Lovelace resource collection finish.
                    async def _retry_registration() -> None:
                        await asyncio.sleep(0.5)
                        if not domain_data.get("lovelace_resource_registered"):
                            if await _async_register_lovelace_resource(hass, versioned_url):
                                domain_data["lovelace_resource_registered"] = True

                    hass.async_create_task(_retry_registration())
                elif hasattr(hass, "bus") and not domain_data.get("lovelace_start_listener"):
                    # Lovelace not initialized yet; retry when Home Assistant has started
                    domain_data["lovelace_start_listener"] = True

                    async def _on_ha_start(_event: Any) -> None:
                        if not domain_data.get("lovelace_resource_registered"):
                            if await _async_register_lovelace_resource(hass, versioned_url):
                                domain_data["lovelace_resource_registered"] = True

                    from homeassistant.const import EVENT_HOMEASSISTANT_START

                    hass.bus.async_listen_once(EVENT_HOMEASSISTANT_START, _on_ha_start)

        domain_data["frontend_registered"] = True


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the İETT component integration level services."""

    async def handle_refresh_fleet(call: ServiceCall) -> None:
        """Force refresh the shared RAM fleet cache."""
        client: IettClient | None = hass.data.get(DOMAIN, {}).get("client")
        if client:
            await client.refresh_fleet()
            _LOGGER.info("İETT fleet cache refreshed via service call")

    hass.services.async_register(DOMAIN, SERVICE_REFRESH_FLEET, handle_refresh_fleet)

    # Register frontend static path and Lovelace resources at integration setup time
    await _async_register_frontend(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up İETT from a config entry."""
    hass_domain_data = hass.data.setdefault(DOMAIN, {})
    setup_lock: asyncio.Lock = hass_domain_data.setdefault("_setup_lock", asyncio.Lock())

    async with setup_lock:
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
            if "dcode" in new_data and CONF_STOP_CODE not in new_data:
                new_data[CONF_STOP_CODE] = new_data.pop("dcode")
            new_data.setdefault(CONF_ROUTE_MODE, ROUTE_MODE_ALL)
            new_data.setdefault(CONF_VEHICLE_LIMIT_MODE, LIMIT_MODE_NEAREST_N)
            new_data.setdefault(CONF_VEHICLE_LIMIT_N, 1)
            new_data.setdefault(CONF_STOP_ATTRIBUTES, DEFAULT_STOP_ATTRIBUTES)
            new_data.setdefault(CONF_SPEED_UNIT, SPEED_UNIT_KMH)
        elif feed_type == FEED_ROUTE:
            if "hat_kodu" in new_data and CONF_ROUTE_CODE not in new_data:
                new_data[CONF_ROUTE_CODE] = new_data.pop("hat_kodu")
            new_data.setdefault(CONF_INCLUDE_ACTIVE_BUSES, True)
            new_data.setdefault(CONF_INCLUDE_ANNOUNCEMENTS, True)
            new_data.setdefault(CONF_INCLUDE_SCHEDULE, True)
            new_data.setdefault(CONF_DIRECTION_FILTER, DIR_FILTER_BOTH)
            new_data.setdefault(CONF_DEPAR_MODE, DEPAR_MODE_ALL)

        new_data.setdefault(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)

        hass.config_entries.async_update_entry(config_entry, data=new_data, version=2)
        _LOGGER.info("Migration to v2 successful for %s", config_entry.entry_id)

    return True
