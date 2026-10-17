"""Tests for İETT diagnostics platform."""

from __future__ import annotations

from unittest.mock import MagicMock

from custom_components.iett.const import CONF_FEED_TYPE, DOMAIN, FEED_ROOT
from custom_components.iett.diagnostics import async_get_config_entry_diagnostics


async def test_diagnostics(hass: MagicMock) -> None:
    """Test diagnostics export for a config entry."""
    entry = MagicMock()
    entry.entry_id = "diag_entry"
    entry.version = 2
    entry.domain = DOMAIN
    entry.title = "İETT İstanbul Geneli"
    entry.data = {CONF_FEED_TYPE: FEED_ROOT}
    entry.options = {}

    coord = MagicMock()
    coord.data = {"active_fleet_count": 3000}

    client = MagicMock()
    client._fleet_by_kapino = {"C-1753": MagicMock()}
    client._token = "some_token"

    hass.data[DOMAIN] = {
        "client": client,
        "diag_entry": coord,
    }

    res = await async_get_config_entry_diagnostics(hass, entry)
    assert res["entry"]["entry_id"] == "diag_entry"
    assert res["coordinator_data"] == {"active_fleet_count": 3000}
    assert res["engine_status"]["fleet_cached_buses"] == 1
    assert res["engine_status"]["token_valid"] is True
