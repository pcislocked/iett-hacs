"""Constants for the IETT integration."""
from __future__ import annotations

from datetime import timedelta

DOMAIN = "iett"

# ── Feed type keys ──────────────────────────────────────────────────────────
FEED_ALL_FLEET          = "all_fleet"
FEED_ROUTE_FLEET        = "route_fleet"
FEED_STOP_ARRIVALS      = "stop_arrivals"
FEED_ROUTE_SCHEDULE     = "route_schedule"
FEED_ROUTE_ANNOUNCEMENTS = "route_announcements"

FEED_TYPES = [
    FEED_ALL_FLEET,
    FEED_ROUTE_FLEET,
    FEED_STOP_ARRIVALS,
    FEED_ROUTE_SCHEDULE,
    FEED_ROUTE_ANNOUNCEMENTS,
]

# Human-readable labels for config flow UI
FEED_LABELS: dict[str, str] = {
    FEED_ALL_FLEET:          "All Fleet (entire Istanbul)",
    FEED_ROUTE_FLEET:        "Route Fleet (buses on a specific line)",
    FEED_STOP_ARRIVALS:      "Arrivals at Stop (real-time ETAs)",
    FEED_ROUTE_SCHEDULE:     "Route Schedule (planned departures)",
    FEED_ROUTE_ANNOUNCEMENTS: "Route Announcements (disruption alerts)",
}

# Coordinator update intervals
UPDATE_INTERVALS: dict[str, timedelta] = {
    FEED_ALL_FLEET:          timedelta(seconds=15),
    FEED_ROUTE_FLEET:        timedelta(seconds=15),
    FEED_STOP_ARRIVALS:      timedelta(seconds=30),
    FEED_ROUTE_SCHEDULE:     timedelta(seconds=3600),
    FEED_ROUTE_ANNOUNCEMENTS: timedelta(seconds=300),
}

# ── Config entry keys ───────────────────────────────────────────────────────
CONF_MIDDLE_URL  = "middle_url"
CONF_FEED_TYPE   = "feed_type"
CONF_HAT_KODU    = "hat_kodu"
CONF_DCODE       = "dcode"

DEFAULT_MIDDLE_URL = "http://localhost:8000"

# ── Sensor attribute data keys ──────────────────────────────────────────────
DATA_KEY: dict[str, str] = {
    FEED_ALL_FLEET:          "buses",
    FEED_ROUTE_FLEET:        "buses",
    FEED_STOP_ARRIVALS:      "arrivals",
    FEED_ROUTE_SCHEDULE:     "departures",
    FEED_ROUTE_ANNOUNCEMENTS: "announcements",
}

# Sensor icons (MDI)
SENSOR_ICON: dict[str, str] = {
    FEED_ALL_FLEET:          "mdi:bus-multiple",
    FEED_ROUTE_FLEET:        "mdi:bus",
    FEED_STOP_ARRIVALS:      "mdi:bus-clock",
    FEED_ROUTE_SCHEDULE:     "mdi:timetable",
    FEED_ROUTE_ANNOUNCEMENTS: "mdi:alert-circle-outline",
}

# Sensor units of measurement
SENSOR_UNIT: dict[str, str | None] = {
    FEED_ALL_FLEET:          None,
    FEED_ROUTE_FLEET:        None,
    FEED_STOP_ARRIVALS:      "min",
    FEED_ROUTE_SCHEDULE:     "min",
    FEED_ROUTE_ANNOUNCEMENTS: None,
}
