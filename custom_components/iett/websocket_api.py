"""WebSocket API handlers for on-demand Lovelace card data (zero sensor dependency)."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback

from .client import IettApiError, IettClient
from .const import DOMAIN
from .normalizers import format_eta_mmss, haversine_meters, normalize_kapino

_LOGGER = logging.getLogger(__name__)


@callback
def async_register_websocket_handlers(hass: HomeAssistant) -> None:
    """Register İETT WebSocket commands once."""
    if hass.data.get(DOMAIN, {}).get("ws_registered"):
        return
    websocket_api.async_register_command(hass, ws_get_stop_board)
    websocket_api.async_register_command(hass, ws_get_route_board)
    websocket_api.async_register_command(hass, ws_get_vehicle_card)
    websocket_api.async_register_command(hass, ws_search)
    hass.data.setdefault(DOMAIN, {})["ws_registered"] = True


def _get_client(hass: HomeAssistant) -> IettClient | None:
    return hass.data.get(DOMAIN, {}).get("client")


@websocket_api.websocket_command(
    {
        vol.Required("type"): "iett/get_stop_board",
        vol.Required("stop_code"): vol.All(str, vol.Length(min=1, max=16)),
        vol.Optional("route_filter", default=[]): [str],
        vol.Optional("max_items", default=10): vol.All(int, vol.Range(min=1, max=30)),
    }
)
@websocket_api.async_response
async def ws_get_stop_board(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Return live stop board data on-demand for Lovelace card."""
    client = _get_client(hass)
    if client is None:
        connection.send_error(msg["id"], "not_loaded", "İETT integration is not loaded")
        return

    stop_code = msg["stop_code"].strip()
    route_filter = {r.strip().upper() for r in msg.get("route_filter", []) if r.strip()}
    max_items = msg.get("max_items", 10)

    try:
        meta = await client.get_stop_metadata(stop_code)
        arrivals = await client.get_stop_arrivals(stop_code)
    except IettApiError as exc:
        connection.send_error(msg["id"], "api_error", str(exc))
        return

    if route_filter:
        arrivals = [a for a in arrivals if a.route_code.upper() in route_filter]

    arrivals.sort(key=lambda a: (a.eta_minutes is None, a.eta_minutes or 9999))

    items: list[dict[str, Any]] = []
    for arr in arrivals[:max_items]:
        dist_m = haversine_meters(arr.lat, arr.lon, meta.latitude, meta.longitude)
        arrival_time = format_eta_mmss(arr.eta_minutes, arr.last_seen_ts, eta_raw=arr.eta_raw)
        items.append(
            {
                "route_code": arr.route_code,
                "destination": arr.destination,
                "eta_minutes": arr.eta_minutes,
                "eta_mmss": arrival_time,
                "eta_time": arrival_time,
                "eta_raw": arr.eta_raw,
                "kapino": arr.kapino,
                "plate": arr.plate,
                "speed_kmh": arr.speed_kmh,
                "distance_to_stop_m": dist_m,
                "amenities": arr.amenities.to_dict(),
            }
        )

    connection.send_result(
        msg["id"],
        {
            "stop_code": stop_code,
            "stop_name": meta.name,
            "direction": meta.direction,
            "district": meta.district,
            "arrivals": items,
        },
    )


@websocket_api.websocket_command(
    {
        vol.Required("type"): "iett/get_route_board",
        vol.Required("route_code"): vol.All(str, vol.Length(min=1, max=16)),
    }
)
@websocket_api.async_response
async def ws_get_route_board(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Return live route status, departures, and announcements on-demand."""
    client = _get_client(hass)
    if client is None:
        connection.send_error(msg["id"], "not_loaded", "İETT integration is not loaded")
        return

    hat_kodu = msg["route_code"].strip().upper()
    try:
        buses = await client.get_route_buses(hat_kodu)
        schedule = await client.get_route_schedule(hat_kodu)
        announcements = await client.get_announcements(hat_kodu)
    except IettApiError as exc:
        connection.send_error(msg["id"], "api_error", str(exc))
        return

    connection.send_result(
        msg["id"],
        {
            "route_code": hat_kodu,
            "active_buses": len(buses),
            "buses": [b.to_dict() for b in buses[:40]],
            "schedule": [s.to_dict() for s in schedule[:30]],
            "announcements": [a.to_dict() for a in announcements[:10]],
        },
    )


@websocket_api.websocket_command(
    {
        vol.Required("type"): "iett/get_vehicle_card",
        vol.Required("kapino"): vol.All(str, vol.Length(min=2, max=16)),
    }
)
@websocket_api.async_response
async def ws_get_vehicle_card(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Return single vehicle status on-demand by kapino."""
    client = _get_client(hass)
    if client is None:
        connection.send_error(msg["id"], "not_loaded", "İETT integration is not loaded")
        return

    kapino = normalize_kapino(msg["kapino"]) or msg["kapino"].strip().upper()
    try:
        bus = await client.get_vehicle_status(kapino)
    except IettApiError as exc:
        connection.send_error(msg["id"], "api_error", str(exc))
        return

    connection.send_result(
        msg["id"],
        {
            "kapino": kapino,
            "online": bus is not None,
            "vehicle": bus.to_dict() if bus else None,
        },
    )


@websocket_api.websocket_command(
    {
        vol.Required("type"): "iett/search",
        vol.Required("query"): vol.All(str, vol.Length(min=2, max=64)),
        vol.Required("search_type"): vol.In(["stop", "route"]),
    }
)
@websocket_api.async_response
async def ws_search(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Search stops or routes on-demand for the Lovelace card editor."""
    client = _get_client(hass)
    if client is None:
        connection.send_error(msg["id"], "not_loaded", "İETT integration is not loaded")
        return

    try:
        if msg["search_type"] == "stop":
            stops = await client.search_stops(msg["query"])
            connection.send_result(
                msg["id"],
                {"results": [{"code": s.dcode, "name": s.name} for s in stops[:25]]},
            )
        else:
            routes = await client.search_routes(msg["query"])
            connection.send_result(
                msg["id"],
                {"results": [{"code": r.hat_kodu, "name": r.name} for r in routes[:25]]},
            )
    except IettApiError as exc:
        connection.send_error(msg["id"], "api_error", str(exc))
