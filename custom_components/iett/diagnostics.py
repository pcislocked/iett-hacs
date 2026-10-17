"""Diagnostics support for İETT config entries."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .coordinator import IettEntryCoordinator


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    domain_data = hass.data.get(DOMAIN, {})
    coord: IettEntryCoordinator | None = domain_data.get(entry.entry_id)

    client = domain_data.get("client")
    fleet_count = len(client._fleet_by_kapino) if client else 0
    token_valid = bool(client._token) if client else False

    return {
        "entry": {
            "entry_id": entry.entry_id,
            "version": entry.version,
            "domain": entry.domain,
            "title": entry.title,
            "data": dict(entry.data),
            "options": dict(entry.options),
        },
        "coordinator_data": coord.data if coord else None,
        "engine_status": {
            "fleet_cached_buses": fleet_count,
            "token_valid": token_valid,
        },
    }
