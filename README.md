# iett-hacs

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)
[![Tests](https://img.shields.io/badge/tests-37%20passed-brightgreen)](#development)
[![HA](https://img.shields.io/badge/Home%20Assistant-2024.1%2B-41BDF5?logo=home-assistant)](https://www.home-assistant.io/)
[![Version](https://img.shields.io/badge/version-0.1-orange)](https://github.com/pcislocked/iett-hacs/releases/tag/v0.1)

Home Assistant custom component for real-time Istanbul IETT bus tracking.
Distributed via [HACS](https://hacs.xyz/). Powered by [iett-middle](https://github.com/pcislocked/iett-middle).

Part of a three-repo stack:
[iett-middle](https://github.com/pcislocked/iett-middle) (API proxy) ·
[**iett-hacs**](https://github.com/pcislocked/iett-hacs) (this repo) ·
[iett-pwa](https://github.com/pcislocked/iett-pwa) (web app)

## Architecture

```
Home Assistant  →  iett-hacs  →  iett-middle  →  IETT/IBB APIs
```

Unlike a direct integration, **iett-hacs does zero API parsing** — it only calls
`GET /v1/…` endpoints on `iett-middle`. This means:

- No SOAP, no BeautifulSoup, no 1 MB fleet payloads in HA
- iett-middle caches and enriches data; HA just reads the diff
- Requirements: nothing new (only `aiohttp`, already bundled in HA)

## Prerequisites

A running **iett-middle** instance. See [iett-middle README](https://github.com/pcislocked/iett-middle) for setup.

Default assumption: `http://localhost:8000` (or wherever you deploy it).

## Installation

**Via HACS (recommended)**
1. Add custom repository: `https://github.com/pcislocked/iett-hacs`
2. Install "IETT"
3. Restart HA
4. Settings → Devices & Services → Add Integration → IETT

**Manual**
Copy `custom_components/iett/` into your HA `custom_components/` directory.

## Configuration

Each config entry = one feed. You can add multiple entries with different feeds.

| Feed | Params | Sensor state | Attributes |
|---|---|---|---|
| All Fleet | — | Bus count | `buses` (list) |
| Route Fleet | `hat_kodu` | Bus count on route | `buses` (list) |
| Stop Arrivals | `dcode` | Next ETA (minutes) | `arrivals` (list) |
| Route Schedule | `hat_kodu` | Minutes to next departure | `departures` (list) |
| Route Announcements | `hat_kodu` | Active alert count | `announcements` (list) |

## Lovelace Examples

```yaml
# Arrivals board using Markdown card
type: markdown
content: >
  {% set arrivals = states.sensor.iett_stop_220602_arrivals.attributes.arrivals %}
  {% for a in arrivals %}
  **{{ a.route_code }}** — {{ a.destination }} — {{ a.eta_minutes }} dk
  {% endfor %}
```

## Development

```bash
pip install -r requirements_test.txt
pytest
```
