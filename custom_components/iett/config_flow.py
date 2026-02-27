"""Config flow for the IETT integration."""
from __future__ import annotations

from typing import Any

import aiohttp
import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    CONF_DCODE,
    CONF_FEED_TYPE,
    CONF_HAT_KODU,
    CONF_MIDDLE_URL,
    DEFAULT_MIDDLE_URL,
    DOMAIN,
    FEED_ALL_FLEET,
    FEED_LABELS,
    FEED_ROUTE_ANNOUNCEMENTS,
    FEED_ROUTE_FLEET,
    FEED_ROUTE_SCHEDULE,
    FEED_STOP_ARRIVALS,
    FEED_TYPES,
)

_FEED_REQUIRES_HAT = {FEED_ROUTE_FLEET, FEED_ROUTE_SCHEDULE, FEED_ROUTE_ANNOUNCEMENTS}
_FEED_REQUIRES_DCODE = {FEED_STOP_ARRIVALS}

STEP_1_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_MIDDLE_URL, default=DEFAULT_MIDDLE_URL): str,
        vol.Required(CONF_FEED_TYPE): vol.In(
            {k: v for k, v in FEED_LABELS.items()}
        ),
    }
)


def _step2_schema(feed_type: str) -> vol.Schema:
    if feed_type in _FEED_REQUIRES_HAT:
        return vol.Schema({vol.Required(CONF_HAT_KODU): str})
    if feed_type in _FEED_REQUIRES_DCODE:
        return vol.Schema({vol.Required(CONF_DCODE): str})
    return vol.Schema({})


def _unique_id(data: dict[str, Any]) -> str:
    ft = data[CONF_FEED_TYPE]
    if ft in _FEED_REQUIRES_HAT:
        return f"{ft}_{data[CONF_HAT_KODU].upper()}"
    if ft in _FEED_REQUIRES_DCODE:
        return f"{ft}_{data[CONF_DCODE]}"
    return ft  # all_fleet


def _entry_title(data: dict[str, Any]) -> str:
    ft = data[CONF_FEED_TYPE]
    label = FEED_LABELS[ft]
    if ft in _FEED_REQUIRES_HAT:
        return f"IETT — {data[CONF_HAT_KODU].upper()} {label.split('(')[0].strip()}"
    if ft in _FEED_REQUIRES_DCODE:
        return f"IETT — Stop {data[CONF_DCODE]} Arrivals"
    return f"IETT — {label}"


class IettConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for IETT."""

    VERSION = 1

    def __init__(self) -> None:
        self._step1_data: dict[str, Any] = {}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            # Quick connectivity check
            session = async_get_clientsession(self.hass)
            try:
                async with session.get(
                    f"{user_input[CONF_MIDDLE_URL].rstrip('/')}/health",
                    timeout=aiohttp.ClientTimeout(total=5),
                ) as resp:
                    if resp.status != 200:
                        errors["base"] = "cannot_connect"
            except Exception:
                errors["base"] = "cannot_connect"

            if not errors:
                self._step1_data = user_input
                feed_type = user_input[CONF_FEED_TYPE]
                if feed_type == FEED_ALL_FLEET:
                    return self._create_entry({})
                return await self.async_step_params()

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_1_SCHEMA,
            errors=errors,
        )

    async def async_step_params(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        ft = self._step1_data[CONF_FEED_TYPE]
        if user_input is not None:
            return self._create_entry(user_input)
        return self.async_show_form(
            step_id="params",
            data_schema=_step2_schema(ft),
        )

    def _create_entry(self, params: dict[str, Any]) -> ConfigFlowResult:
        data = {**self._step1_data, **params, "feed_type": self._step1_data[CONF_FEED_TYPE]}
        unique_id = _unique_id(data)
        self._async_abort_entries_match({"feed_type": data["feed_type"], **params})
        return self.async_create_entry(title=_entry_title(data), data=data)
