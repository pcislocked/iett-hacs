"""Tests for IettCoordinator — mocks IettMiddleClient & HomeAssistant."""
from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.iett.const import (
    CONF_DCODE,
    CONF_HAT_KODU,
    CONF_MIDDLE_URL,
    FEED_ALL_FLEET,
    FEED_ROUTE_ANNOUNCEMENTS,
    FEED_ROUTE_FLEET,
    FEED_ROUTE_SCHEDULE,
    FEED_STOP_ARRIVALS,
)
from custom_components.iett.coordinator import IettCoordinator
from custom_components.iett.client import IettMiddleError
from tests.conftest import (
    ANNOUNCEMENTS_JSON,
    ARRIVALS_JSON,
    FLEET_JSON,
    ROUTE_FLEET_JSON,
    SCHEDULE_JSON,
)


def _make_hass() -> MagicMock:
    """Return a minimal HomeAssistant mock."""
    hass = MagicMock()
    hass.loop = MagicMock()
    hass.config = MagicMock()
    return hass


def _entry_data(feed_type: str, **extra: Any) -> dict[str, Any]:
    return {
        "feed_type": feed_type,
        CONF_MIDDLE_URL: "http://iett-middle.test",
        CONF_HAT_KODU: "500T",
        CONF_DCODE: "220602",
        **extra,
    }


@pytest.fixture()
def hass() -> MagicMock:
    return _make_hass()


# ---------------------------------------------------------------------------
# FEED_ALL_FLEET
# ---------------------------------------------------------------------------

class TestCoordinatorAllFleet:
    async def test_returns_fleet(self, hass: MagicMock) -> None:
        coord = IettCoordinator(hass, _entry_data(FEED_ALL_FLEET))
        mock_client = MagicMock()
        mock_client.get_all_buses = AsyncMock(return_value=FLEET_JSON)
        with (
            patch("custom_components.iett.coordinator.async_get_clientsession"),
            patch("custom_components.iett.coordinator.IettMiddleClient", return_value=mock_client),
        ):
            result = await coord._async_update_data()  # type: ignore[reportPrivateUsage]
        assert result == FLEET_JSON

    async def test_raises_update_failed(self, hass: MagicMock) -> None:
        from homeassistant.helpers.update_coordinator import UpdateFailed
        coord = IettCoordinator(hass, _entry_data(FEED_ALL_FLEET))
        mock_client = MagicMock()
        mock_client.get_all_buses = AsyncMock(side_effect=IettMiddleError("down"))
        with (
            patch("custom_components.iett.coordinator.async_get_clientsession"),
            patch("custom_components.iett.coordinator.IettMiddleClient", return_value=mock_client),
        ):
            with pytest.raises(UpdateFailed):
                await coord._async_update_data()  # type: ignore[reportPrivateUsage]


# ---------------------------------------------------------------------------
# FEED_ROUTE_FLEET
# ---------------------------------------------------------------------------

class TestCoordinatorRouteFleet:
    async def test_returns_route_buses(self, hass: MagicMock) -> None:
        coord = IettCoordinator(hass, _entry_data(FEED_ROUTE_FLEET))
        mock_client = MagicMock()
        mock_client.get_route_buses = AsyncMock(return_value=ROUTE_FLEET_JSON)
        with (
            patch("custom_components.iett.coordinator.async_get_clientsession"),
            patch("custom_components.iett.coordinator.IettMiddleClient", return_value=mock_client),
        ):
            result = await coord._async_update_data()  # type: ignore[reportPrivateUsage]
        assert result == ROUTE_FLEET_JSON
        mock_client.get_route_buses.assert_called_once_with("500T")

    async def test_raises_update_failed_on_error(self, hass: MagicMock) -> None:
        from homeassistant.helpers.update_coordinator import UpdateFailed
        coord = IettCoordinator(hass, _entry_data(FEED_ROUTE_FLEET))
        mock_client = MagicMock()
        mock_client.get_route_buses = AsyncMock(side_effect=IettMiddleError("bad"))
        with (
            patch("custom_components.iett.coordinator.async_get_clientsession"),
            patch("custom_components.iett.coordinator.IettMiddleClient", return_value=mock_client),
        ):
            with pytest.raises(UpdateFailed):
                await coord._async_update_data()  # type: ignore[reportPrivateUsage]


# ---------------------------------------------------------------------------
# FEED_STOP_ARRIVALS
# ---------------------------------------------------------------------------

class TestCoordinatorStopArrivals:
    async def test_returns_arrivals(self, hass: MagicMock) -> None:
        coord = IettCoordinator(hass, _entry_data(FEED_STOP_ARRIVALS))
        mock_client = MagicMock()
        mock_client.get_stop_arrivals = AsyncMock(return_value=ARRIVALS_JSON)
        with (
            patch("custom_components.iett.coordinator.async_get_clientsession"),
            patch("custom_components.iett.coordinator.IettMiddleClient", return_value=mock_client),
        ):
            result = await coord._async_update_data()  # type: ignore[reportPrivateUsage]
        assert result == ARRIVALS_JSON
        mock_client.get_stop_arrivals.assert_called_once_with("220602")


# ---------------------------------------------------------------------------
# FEED_ROUTE_SCHEDULE
# ---------------------------------------------------------------------------

class TestCoordinatorRouteSchedule:
    async def test_returns_schedule(self, hass: MagicMock) -> None:
        coord = IettCoordinator(hass, _entry_data(FEED_ROUTE_SCHEDULE))
        mock_client = MagicMock()
        mock_client.get_route_schedule = AsyncMock(return_value=SCHEDULE_JSON)
        with (
            patch("custom_components.iett.coordinator.async_get_clientsession"),
            patch("custom_components.iett.coordinator.IettMiddleClient", return_value=mock_client),
        ):
            result = await coord._async_update_data()  # type: ignore[reportPrivateUsage]
        assert result == SCHEDULE_JSON
        mock_client.get_route_schedule.assert_called_once_with("500T")


# ---------------------------------------------------------------------------
# FEED_ROUTE_ANNOUNCEMENTS
# ---------------------------------------------------------------------------

class TestCoordinatorAnnouncements:
    async def test_returns_announcements(self, hass: MagicMock) -> None:
        coord = IettCoordinator(hass, _entry_data(FEED_ROUTE_ANNOUNCEMENTS))
        mock_client = MagicMock()
        mock_client.get_announcements = AsyncMock(return_value=ANNOUNCEMENTS_JSON)
        with (
            patch("custom_components.iett.coordinator.async_get_clientsession"),
            patch("custom_components.iett.coordinator.IettMiddleClient", return_value=mock_client),
        ):
            result = await coord._async_update_data()  # type: ignore[reportPrivateUsage]
        assert result == ANNOUNCEMENTS_JSON

    async def test_raises_on_unknown_feed(self, hass: MagicMock) -> None:
        with pytest.raises(ValueError, match="Unknown feed type"):
            IettCoordinator(hass, _entry_data("unknown_feed"))
