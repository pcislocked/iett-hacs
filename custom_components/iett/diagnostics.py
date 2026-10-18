"""Diagnostics support for İETT config entries."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import (
    ATTR_OPT_COORDS,
    CONF_CUSTOM_LAT,
    CONF_CUSTOM_LON,
    CONF_STOP_LAT,
    CONF_STOP_LON,
    DOMAIN,
)
from .coordinator import IettEntryCoordinator

TO_REDACT: set[str] = {
    CONF_CUSTOM_LAT,
    CONF_CUSTOM_LON,
    CONF_STOP_LAT,
    CONF_STOP_LON,
    ATTR_OPT_COORDS,
    "latitude",
    "longitude",
    "lat",
    "lon",
    "access_token",
}


def _redact_data(data: Any, to_redact: set[str]) -> Any:
    """Recursively redact sensitive keys from dictionaries and lists."""
    try:
        from homeassistant.components.diagnostics import async_redact_data

        return async_redact_data(data, to_redact)
    except ImportError:
        if isinstance(data, dict):
            return {
                k: "**REDACTED**" if k in to_redact else _redact_data(v, to_redact)
                for k, v in data.items()
            }
        if isinstance(data, list):
            return [_redact_data(item, to_redact) for item in data]
        return data


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry with sensitive location data redacted."""
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
            "data": _redact_data(dict(entry.data), TO_REDACT),
            "options": _redact_data(dict(entry.options), TO_REDACT),
        },
        "coordinator_data": _redact_data(coord.data, TO_REDACT) if coord and coord.data else None,
        "engine_status": {
            "fleet_cached_buses": fleet_count,
            "token_valid": token_valid,
        },
    }
