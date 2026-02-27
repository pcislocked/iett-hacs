# IETT — Istanbul Bus Tracker for Home Assistant

Real-time Istanbul IETT bus data via **iett-middle** backend.

## Prerequisites

You need a running [iett-middle](https://github.com/pcislocked/iett-middle) instance.

## Features

- Track all 7,000+ Istanbul buses
- Monitor buses on specific routes
- Real-time ETAs at any stop
- Departure schedules
- Service disruption alerts

## Installation via HACS

1. Add this repo to HACS as a custom repository
2. Install "IETT"
3. Restart Home Assistant
4. **Settings → Devices & Services → Add Integration → IETT**
5. Enter your iett-middle URL and choose a feed type
