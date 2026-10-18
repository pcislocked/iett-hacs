"""Config flow for the İETT Home Assistant integration."""

from __future__ import annotations

import logging
import re
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import selector
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .client import IettClient
from .const import (
    ALL_STOP_ATTRIBUTE_OPTIONS,
    CONF_CUSTOM_LAT,
    CONF_CUSTOM_LON,
    CONF_DEPAR_MODE,
    CONF_DIRECTION_FILTER,
    CONF_FEED_TYPE,
    CONF_INCLUDE_ACTIVE_BUSES,
    CONF_INCLUDE_ANNOUNCEMENTS,
    CONF_INCLUDE_SCHEDULE,
    CONF_KAPINO,
    CONF_ROUTE_CODE,
    CONF_ROUTE_MODE,
    CONF_SCAN_INTERVAL,
    CONF_SELECTED_DEPARS,
    CONF_SELECTED_ROUTES,
    CONF_SPEED_UNIT,
    CONF_STOP_ATTRIBUTES,
    CONF_STOP_CODE,
    CONF_STOP_DIRECTION,
    CONF_STOP_DISTRICT,
    CONF_STOP_LAT,
    CONF_STOP_LON,
    CONF_STOP_NAME,
    CONF_STOP_SMART,
    CONF_STOP_TYPE,
    CONF_VEHICLE_LIMIT_MODE,
    CONF_VEHICLE_LIMIT_N,
    DEFAULT_ROOT_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_STOP_ATTRIBUTES,
    DEPAR_MODE_ALL,
    DEPAR_MODE_BASE_ONLY,
    DEPAR_MODE_SELECTED,
    DIR_FILTER_BOTH,
    DIR_FILTER_D,
    DIR_FILTER_G,
    DOMAIN,
    FEED_ROOT,
    FEED_ROUTE,
    FEED_STOP,
    FEED_VEHICLE,
    LIMIT_MODE_ALL,
    LIMIT_MODE_NEAREST_N,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
    ROUTE_MODE_ALL,
    ROUTE_MODE_SELECTED,
    SPEED_UNIT_KMH,
    SPEED_UNIT_MPH,
)
from .models import RouteSearchResult, StopMetadata
from .normalizers import validate_strict_kapino

_LOGGER = logging.getLogger(__name__)


class IettConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for İETT."""

    VERSION = 2

    def __init__(self) -> None:
        self._client: IettClient | None = None
        self._stop_results: list[StopMetadata] = []
        self._selected_stop_code: str = ""
        self._selected_stop_meta: StopMetadata | None = None
        self._available_routes: list[str] = []

        self._route_results: list[RouteSearchResult] = []
        self._selected_route_code: str = ""
        self._available_variants: list[str] = []

    def _get_client(self) -> IettClient:
        """Get or initialize standalone IettClient."""
        if self._client is None:
            self._client = self.hass.data.get(DOMAIN, {}).get("client")
        if self._client is None:
            session = async_get_clientsession(self.hass)
            self._client = IettClient(session)
        return self._client

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Page 1: Select feed type to configure."""
        root_exists = any(
            entry.data.get(CONF_FEED_TYPE) == FEED_ROOT for entry in self._async_current_entries()
        )

        menu_options: list[str] = []
        if not root_exists:
            menu_options.append("root")
        menu_options.extend(["stop", "route", "vehicle"])

        return self.async_show_menu(step_id="user", menu_options=menu_options)

    # ------------------------------------------------------------------
    # Root Setup (City Traffic & Fleet Size)
    # ------------------------------------------------------------------

    async def async_step_root(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Setup the 4 city-wide root sensors."""
        await self.async_set_unique_id("root")
        self._abort_if_unique_id_configured()

        return self.async_create_entry(
            title="İETT İstanbul Geneli",
            data={
                CONF_FEED_TYPE: FEED_ROOT,
                CONF_SCAN_INTERVAL: DEFAULT_ROOT_SCAN_INTERVAL,
            },
        )

    # ------------------------------------------------------------------
    # 1a) Stop Wizard
    # ------------------------------------------------------------------

    async def async_step_stop(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Step 1a-1: Enter stop code or name."""
        errors: dict[str, str] = {}
        client = self._get_client()

        if user_input is not None:
            query = user_input.get("stop_query", "").strip()
            if not query:
                errors["base"] = "invalid_stop_query"
            elif re.match(r"^\d{6}$", query):
                # Exact 6-digit code entered
                self._selected_stop_code = query
                try:
                    self._selected_stop_meta = await client.get_stop_metadata(query)
                    self._available_routes = await client.get_routes_at_stop(query)
                    return await self.async_step_stop_config()
                except Exception as exc:  # noqa: BLE001
                    _LOGGER.warning("Failed to fetch stop %s: %s", query, exc)
                    errors["base"] = "stop_fetch_failed"
            else:
                # Text query — search stops
                try:
                    self._stop_results = await client.search_stops(query)
                    if not self._stop_results:
                        errors["base"] = "no_stops_found"
                    elif len(self._stop_results) == 1:
                        self._selected_stop_code = self._stop_results[0].dcode
                        self._selected_stop_meta = await client.get_stop_metadata(
                            self._selected_stop_code
                        )
                        self._available_routes = await client.get_routes_at_stop(
                            self._selected_stop_code
                        )
                        return await self.async_step_stop_config()
                    else:
                        return await self.async_step_stop_select()
                except Exception as exc:  # noqa: BLE001
                    _LOGGER.warning("Search stops failed: %s", exc)
                    errors["base"] = "search_failed"

        return self.async_show_form(
            step_id="stop",
            data_schema=vol.Schema({vol.Required("stop_query"): str}),
            errors=errors,
        )

    async def async_step_stop_select(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Select stop from search results."""
        client = self._get_client()
        if user_input is not None:
            self._selected_stop_code = user_input["selected_stop"]
            self._selected_stop_meta = await client.get_stop_metadata(self._selected_stop_code)
            self._available_routes = await client.get_routes_at_stop(self._selected_stop_code)
            return await self.async_step_stop_config()

        def _format_stop_option(s: StopMetadata) -> str:
            parts: list[str] = []
            if s.direction:
                parts.append(f"➔ {s.direction}")
            if s.district:
                parts.append(s.district)
            suffix = f" ({' • '.join(parts)})" if parts else ""
            return f"{s.dcode} - {s.name}{suffix}"

        options = [
            selector.SelectOptionDict(
                value=s.dcode,
                label=_format_stop_option(s),
            )
            for s in self._stop_results[:30]
        ]

        return self.async_show_form(
            step_id="stop_select",
            data_schema=vol.Schema(
                {
                    vol.Required("selected_stop"): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=options,
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    )
                }
            ),
        )

    async def async_step_stop_config(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Step 1a-2: Configure route filters, vehicle count, and attributes."""
        dcode = self._selected_stop_code
        meta = self._selected_stop_meta or StopMetadata(dcode=dcode, name=f"Durak {dcode}")

        await self.async_set_unique_id(f"stop_{dcode}")
        self._abort_if_unique_id_configured()

        dir_suffix = f" - {meta.direction} Yönü" if meta.direction else ""
        entry_title = f"Durak {dcode} ({meta.name}{dir_suffix})"

        if user_input is not None:
            selected_attrs = user_input.get(CONF_STOP_ATTRIBUTES, DEFAULT_STOP_ATTRIBUTES)
            route_mode = user_input.get(CONF_ROUTE_MODE, ROUTE_MODE_ALL)
            selected_routes = user_input.get(CONF_SELECTED_ROUTES, [])

            return self.async_create_entry(
                title=entry_title,
                data={
                    CONF_FEED_TYPE: FEED_STOP,
                    CONF_STOP_CODE: dcode,
                    CONF_STOP_NAME: meta.name,
                    CONF_STOP_LAT: meta.latitude,
                    CONF_STOP_LON: meta.longitude,
                    CONF_STOP_DIRECTION: meta.direction,
                    CONF_STOP_DISTRICT: meta.district,
                    CONF_STOP_TYPE: meta.stop_type,
                    CONF_STOP_SMART: meta.smart_stop,
                    CONF_ROUTE_MODE: route_mode,
                    CONF_SELECTED_ROUTES: selected_routes,
                    CONF_VEHICLE_LIMIT_MODE: user_input.get(
                        CONF_VEHICLE_LIMIT_MODE, LIMIT_MODE_NEAREST_N
                    ),
                    CONF_VEHICLE_LIMIT_N: int(user_input.get(CONF_VEHICLE_LIMIT_N, 1)),
                    CONF_STOP_ATTRIBUTES: selected_attrs,
                    CONF_SPEED_UNIT: user_input.get(CONF_SPEED_UNIT, SPEED_UNIT_KMH),
                    CONF_CUSTOM_LAT: user_input.get(CONF_CUSTOM_LAT),
                    CONF_CUSTOM_LON: user_input.get(CONF_CUSTOM_LON),
                    CONF_SCAN_INTERVAL: user_input.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
                },
            )

        route_options = [
            selector.SelectOptionDict(value=r, label=r) for r in self._available_routes
        ]

        schema_dict: dict[Any, Any] = {
            vol.Required(CONF_ROUTE_MODE, default=ROUTE_MODE_ALL): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[
                        selector.SelectOptionDict(value=ROUTE_MODE_ALL, label="Tüm Hatlar"),
                        selector.SelectOptionDict(value=ROUTE_MODE_SELECTED, label="Belli Hatlar"),
                    ],
                    mode=selector.SelectSelectorMode.DROPDOWN,
                    translation_key="route_mode",
                )
            ),
        }

        if route_options:
            schema_dict[vol.Optional(CONF_SELECTED_ROUTES, default=[])] = selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=route_options,
                    multiple=True,
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            )

        schema_dict.update(
            {
                vol.Required(
                    CONF_VEHICLE_LIMIT_MODE, default=LIMIT_MODE_NEAREST_N
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            selector.SelectOptionDict(
                                value=LIMIT_MODE_NEAREST_N, label="En Yakın N Sayıda Araç"
                            ),
                            selector.SelectOptionDict(value=LIMIT_MODE_ALL, label="Tüm Araçlar"),
                        ],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                        translation_key="vehicle_limit_mode",
                    )
                ),
                vol.Required(CONF_VEHICLE_LIMIT_N, default=1): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=1,
                        max=10,
                        step=1,
                        mode=selector.NumberSelectorMode.BOX,
                    )
                ),
                vol.Required(
                    CONF_STOP_ATTRIBUTES, default=DEFAULT_STOP_ATTRIBUTES
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            selector.SelectOptionDict(value=opt, label=opt)
                            for opt in ALL_STOP_ATTRIBUTE_OPTIONS
                        ],
                        multiple=True,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                        translation_key="stop_attributes",
                    )
                ),
                vol.Required(CONF_SPEED_UNIT, default=SPEED_UNIT_KMH): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            selector.SelectOptionDict(value=SPEED_UNIT_KMH, label="km/h"),
                            selector.SelectOptionDict(value=SPEED_UNIT_MPH, label="mph"),
                        ],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Optional(
                    CONF_CUSTOM_LAT, default=self.hass.config.latitude
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(mode=selector.NumberSelectorMode.BOX, step="any")
                ),
                vol.Optional(
                    CONF_CUSTOM_LON, default=self.hass.config.longitude
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(mode=selector.NumberSelectorMode.BOX, step="any")
                ),
                vol.Optional(
                    CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=MIN_SCAN_INTERVAL,
                        max=MAX_SCAN_INTERVAL,
                        step=5,
                        mode=selector.NumberSelectorMode.BOX,
                    )
                ),
            }
        )

        return self.async_show_form(
            step_id="stop_config",
            data_schema=vol.Schema(schema_dict),
            description_placeholders={
                "stop_name": meta.name,
                "stop_code": dcode,
                "stop_direction": meta.direction or "-",
            },
        )

    # ------------------------------------------------------------------
    # 1b) Route Wizard
    # ------------------------------------------------------------------

    async def async_step_route(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Step 1b-1: Enter route code or name."""
        errors: dict[str, str] = {}
        client = self._get_client()

        if user_input is not None:
            query = user_input.get("route_query", "").strip().upper()
            if not query:
                errors["base"] = "invalid_route_query"
            else:
                try:
                    self._route_results = await client.search_routes(query)
                    exact_matches = [r for r in self._route_results if r.hat_kodu == query]
                    if exact_matches:
                        self._selected_route_code = query
                        self._available_variants = await client.get_route_variants(query)
                        return await self.async_step_route_config()
                    if len(self._route_results) == 1:
                        self._selected_route_code = self._route_results[0].hat_kodu
                        self._available_variants = await client.get_route_variants(
                            self._selected_route_code
                        )
                        return await self.async_step_route_config()
                    if self._route_results:
                        return await self.async_step_route_select()
                    # If search returned nothing but query looks like a code, try it directly
                    self._selected_route_code = query
                    self._available_variants = await client.get_route_variants(query)
                    return await self.async_step_route_config()
                except Exception as exc:  # noqa: BLE001
                    _LOGGER.warning("Route search failed: %s", exc)
                    errors["base"] = "route_search_failed"

        return self.async_show_form(
            step_id="route",
            data_schema=vol.Schema({vol.Required("route_query"): str}),
            errors=errors,
        )

    async def async_step_route_select(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Select route from search results."""
        client = self._get_client()
        if user_input is not None:
            self._selected_route_code = user_input["selected_route"]
            self._available_variants = await client.get_route_variants(self._selected_route_code)
            return await self.async_step_route_config()

        options = [
            selector.SelectOptionDict(value=r.hat_kodu, label=f"{r.hat_kodu} - {r.name}")
            for r in self._route_results[:30]
        ]

        return self.async_show_form(
            step_id="route_select",
            data_schema=vol.Schema(
                {
                    vol.Required("selected_route"): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=options,
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    )
                }
            ),
        )

    async def async_step_route_config(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Step 1b-2: Configure direction, schedule, and depar filters."""
        hat_kodu = self._selected_route_code

        await self.async_set_unique_id(f"route_{hat_kodu}")
        self._abort_if_unique_id_configured()

        if user_input is not None:
            return self.async_create_entry(
                title=f"Hat {hat_kodu}",
                data={
                    CONF_FEED_TYPE: FEED_ROUTE,
                    CONF_ROUTE_CODE: hat_kodu,
                    CONF_INCLUDE_ACTIVE_BUSES: user_input.get(CONF_INCLUDE_ACTIVE_BUSES, True),
                    CONF_INCLUDE_ANNOUNCEMENTS: user_input.get(CONF_INCLUDE_ANNOUNCEMENTS, True),
                    CONF_INCLUDE_SCHEDULE: user_input.get(CONF_INCLUDE_SCHEDULE, True),
                    CONF_DIRECTION_FILTER: user_input.get(CONF_DIRECTION_FILTER, DIR_FILTER_BOTH),
                    CONF_DEPAR_MODE: user_input.get(CONF_DEPAR_MODE, DEPAR_MODE_ALL),
                    CONF_SELECTED_DEPARS: user_input.get(CONF_SELECTED_DEPARS, []),
                    CONF_SCAN_INTERVAL: user_input.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
                },
            )

        variant_options = [
            selector.SelectOptionDict(value=v, label=v) for v in self._available_variants
        ]

        schema_dict: dict[Any, Any] = {
            vol.Required(CONF_INCLUDE_ACTIVE_BUSES, default=True): bool,
            vol.Required(CONF_INCLUDE_ANNOUNCEMENTS, default=True): bool,
            vol.Required(CONF_INCLUDE_SCHEDULE, default=True): bool,
            vol.Required(CONF_DIRECTION_FILTER, default=DIR_FILTER_BOTH): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[
                        selector.SelectOptionDict(
                            value=DIR_FILTER_BOTH, label="Her İki Yön (G ve D)"
                        ),
                        selector.SelectOptionDict(value=DIR_FILTER_G, label="Sadece Gidiş (G)"),
                        selector.SelectOptionDict(value=DIR_FILTER_D, label="Sadece Dönüş (D)"),
                    ],
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            ),
            vol.Required(CONF_DEPAR_MODE, default=DEPAR_MODE_ALL): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[
                        selector.SelectOptionDict(
                            value=DEPAR_MODE_ALL, label="Tüm Deparları Dahil Et"
                        ),
                        selector.SelectOptionDict(
                            value=DEPAR_MODE_BASE_ONLY, label="Deparları Hariç Tut (Sadece Ana Hat)"
                        ),
                        selector.SelectOptionDict(
                            value=DEPAR_MODE_SELECTED, label="Sadece Seçili Depar(lar)"
                        ),
                    ],
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            ),
        }

        if variant_options:
            schema_dict[vol.Optional(CONF_SELECTED_DEPARS, default=[])] = selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=variant_options,
                    multiple=True,
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            )

        schema_dict[vol.Optional(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL)] = (
            selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=MIN_SCAN_INTERVAL,
                    max=MAX_SCAN_INTERVAL,
                    step=5,
                    mode=selector.NumberSelectorMode.BOX,
                )
            )
        )

        return self.async_show_form(
            step_id="route_config",
            data_schema=vol.Schema(schema_dict),
            description_placeholders={"route_code": hat_kodu},
        )

    # ------------------------------------------------------------------
    # 1c) Vehicle Wizard (Strict Kapı No only)
    # ------------------------------------------------------------------

    async def async_step_vehicle(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Step 1c: Configure single vehicle by strict Kapı No."""
        errors: dict[str, str] = {}

        if user_input is not None:
            raw_kapi = user_input.get(CONF_KAPINO, "")
            valid_kapi = validate_strict_kapino(raw_kapi)
            if not valid_kapi:
                errors["base"] = "invalid_kapino_strict"
            else:
                await self.async_set_unique_id(f"vehicle_{valid_kapi}")
                self._abort_if_unique_id_configured()

                return self.async_create_entry(
                    title=f"Araç {valid_kapi}",
                    data={
                        CONF_FEED_TYPE: FEED_VEHICLE,
                        CONF_KAPINO: valid_kapi,
                        CONF_SPEED_UNIT: user_input.get(CONF_SPEED_UNIT, SPEED_UNIT_KMH),
                        CONF_SCAN_INTERVAL: user_input.get(
                            CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
                        ),
                    },
                )

        schema = vol.Schema(
            {
                vol.Required(CONF_KAPINO): str,
                vol.Required(CONF_SPEED_UNIT, default=SPEED_UNIT_KMH): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            selector.SelectOptionDict(value=SPEED_UNIT_KMH, label="km/h"),
                            selector.SelectOptionDict(value=SPEED_UNIT_MPH, label="mph"),
                        ],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                vol.Optional(
                    CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=MIN_SCAN_INTERVAL,
                        max=MAX_SCAN_INTERVAL,
                        step=5,
                        mode=selector.NumberSelectorMode.BOX,
                    )
                ),
            }
        )

        return self.async_show_form(
            step_id="vehicle",
            data_schema=schema,
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Return options flow handler."""
        return IettOptionsFlowHandler(config_entry)


class IettOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options updates for an existing config entry."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self._config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Manage options for Stop (1a), Route (1b), Vehicle (1c), or Root entries."""
        if user_input is not None:
            new_data = {**self._config_entry.data, **user_input}
            if CONF_VEHICLE_LIMIT_N in new_data:
                new_data[CONF_VEHICLE_LIMIT_N] = int(new_data[CONF_VEHICLE_LIMIT_N])
            self.hass.config_entries.async_update_entry(self._config_entry, data=new_data)
            return self.async_create_entry(title="", data={})

        data = self._config_entry.data
        feed_type = data.get(CONF_FEED_TYPE)
        current_scan = data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)

        schema_dict: dict[Any, Any] = {}

        if feed_type == FEED_STOP:
            schema_dict[
                vol.Optional(
                    CONF_ROUTE_MODE,
                    default=data.get(CONF_ROUTE_MODE, ROUTE_MODE_ALL),
                )
            ] = selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[
                        selector.SelectOptionDict(value=ROUTE_MODE_ALL, label="Tüm Hatlar"),
                        selector.SelectOptionDict(value=ROUTE_MODE_SELECTED, label="Belli Hatlar"),
                    ],
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            )
            schema_dict[
                vol.Optional(
                    CONF_VEHICLE_LIMIT_MODE,
                    default=data.get(CONF_VEHICLE_LIMIT_MODE, LIMIT_MODE_NEAREST_N),
                )
            ] = selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[
                        selector.SelectOptionDict(
                            value=LIMIT_MODE_NEAREST_N, label="En Yakın N Sayıda Araç"
                        ),
                        selector.SelectOptionDict(value=LIMIT_MODE_ALL, label="Tüm Araçlar"),
                    ],
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            )
            schema_dict[
                vol.Optional(
                    CONF_VEHICLE_LIMIT_N,
                    default=int(data.get(CONF_VEHICLE_LIMIT_N, 1)),
                )
            ] = selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=1,
                    max=10,
                    step=1,
                    mode=selector.NumberSelectorMode.BOX,
                )
            )
            current_attrs = data.get(CONF_STOP_ATTRIBUTES, DEFAULT_STOP_ATTRIBUTES)
            schema_dict[vol.Optional(CONF_STOP_ATTRIBUTES, default=current_attrs)] = (
                selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            selector.SelectOptionDict(value=opt, label=opt)
                            for opt in ALL_STOP_ATTRIBUTE_OPTIONS
                        ],
                        multiple=True,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                )
            )
            schema_dict[
                vol.Optional(
                    CONF_SPEED_UNIT,
                    default=data.get(CONF_SPEED_UNIT, SPEED_UNIT_KMH),
                )
            ] = selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[
                        selector.SelectOptionDict(value=SPEED_UNIT_KMH, label="km/h"),
                        selector.SelectOptionDict(value=SPEED_UNIT_MPH, label="mph"),
                    ],
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            )
            schema_dict[
                vol.Optional(
                    CONF_CUSTOM_LAT,
                    default=float(data.get(CONF_CUSTOM_LAT, self.hass.config.latitude or 41.0082)),
                )
            ] = selector.NumberSelector(
                selector.NumberSelectorConfig(mode=selector.NumberSelectorMode.BOX, step="any")
            )
            schema_dict[
                vol.Optional(
                    CONF_CUSTOM_LON,
                    default=float(data.get(CONF_CUSTOM_LON, self.hass.config.longitude or 28.9784)),
                )
            ] = selector.NumberSelector(
                selector.NumberSelectorConfig(mode=selector.NumberSelectorMode.BOX, step="any")
            )
        elif feed_type == FEED_ROUTE:
            schema_dict[
                vol.Optional(
                    CONF_INCLUDE_ACTIVE_BUSES,
                    default=data.get(CONF_INCLUDE_ACTIVE_BUSES, True),
                )
            ] = bool
            schema_dict[
                vol.Optional(
                    CONF_INCLUDE_ANNOUNCEMENTS,
                    default=data.get(CONF_INCLUDE_ANNOUNCEMENTS, True),
                )
            ] = bool
            schema_dict[
                vol.Optional(
                    CONF_INCLUDE_SCHEDULE,
                    default=data.get(CONF_INCLUDE_SCHEDULE, True),
                )
            ] = bool
            schema_dict[
                vol.Optional(
                    CONF_DIRECTION_FILTER,
                    default=data.get(CONF_DIRECTION_FILTER, DIR_FILTER_BOTH),
                )
            ] = selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[
                        selector.SelectOptionDict(value=DIR_FILTER_BOTH, label="Her İki Yön (G+D)"),
                        selector.SelectOptionDict(value=DIR_FILTER_G, label="Sadece Gidiş (G)"),
                        selector.SelectOptionDict(value=DIR_FILTER_D, label="Sadece Dönüş (D)"),
                    ],
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            )
            schema_dict[
                vol.Optional(
                    CONF_DEPAR_MODE,
                    default=data.get(CONF_DEPAR_MODE, DEPAR_MODE_ALL),
                )
            ] = selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[
                        selector.SelectOptionDict(
                            value=DEPAR_MODE_ALL, label="Tüm Deparları Dahil Et"
                        ),
                        selector.SelectOptionDict(
                            value=DEPAR_MODE_BASE_ONLY, label="Deparları Hariç Tut (Ana Hat D0)"
                        ),
                        selector.SelectOptionDict(
                            value=DEPAR_MODE_SELECTED, label="Sadece Seçili Deparlar"
                        ),
                    ],
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            )
        elif feed_type == FEED_VEHICLE:
            schema_dict[
                vol.Optional(
                    CONF_SPEED_UNIT,
                    default=data.get(CONF_SPEED_UNIT, SPEED_UNIT_KMH),
                )
            ] = selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=[
                        selector.SelectOptionDict(value=SPEED_UNIT_KMH, label="km/h"),
                        selector.SelectOptionDict(value=SPEED_UNIT_MPH, label="mph"),
                    ],
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            )

        schema_dict[vol.Optional(CONF_SCAN_INTERVAL, default=current_scan)] = (
            selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=MIN_SCAN_INTERVAL,
                    max=MAX_SCAN_INTERVAL,
                    step=5,
                    mode=selector.NumberSelectorMode.BOX,
                )
            )
        )

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(schema_dict),
        )
