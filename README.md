# İETT — Istanbul Bus Tracker for Home Assistant (v2.0)

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)
[![Tests](https://img.shields.io/badge/tests-75%20passed-brightgreen)](#development)
[![HA](https://img.shields.io/badge/Home%20Assistant-2024.1%2B-41BDF5?logo=home-assistant)](https://www.home-assistant.io/)
[![Version](https://img.shields.io/badge/version-2.0.0-blue)](https://github.com/pcislocked/iett-hacs/releases)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

A **100% Standalone & Serverless** Home Assistant custom integration for real-time Istanbul public transport tracking. Communicates directly with official İETT SOAP, NTCAPI, and İBB TKM endpoints without requiring any external proxy or middleware.

---

## Architecture (v2.0 Standalone)

```
┌──────────────────────────────────────────────────────────┐
│                   Home Assistant Core                    │
│                                                          │
│  ┌──────────────────────┐      ┌──────────────────────┐  │
│  │   IettRootCoordinator │      │ IettEntryCoordinator │  │
│  │   (Traffic + Fleet)  │      │ (Stop/Route/Vehicle) │  │
│  └──────────┬───────────┘      └──────────┬───────────┘  │
│             │                             │              │
│             └──────────────┬──────────────┘              │
│                            │                             │
│                  ┌─────────▼─────────┐                   │
│                  │  IettClient (RAM) │                   │
│                  └─────────┬─────────┘                   │
│                            │                             │
│    ┌──────────────┬────────┴───────┬──────────────┐      │
│    │              │                │              │      │
│ ┌──▼───┐     ┌────▼─────┐     ┌────▼─────┐   ┌────▼────┐ │
│ │ TKM  │     │İETT SOAP │     │  NTCAPI  │   │İETT Web │ │
│ │(REST)│     │(XML/JSON)│     │ (OAuth2) │   │ (HTML)  │ │
│ └──────┘     └──────────┘     └──────────┘   └─────────┘ │
└──────────────────────────────────────────────────────────┘
```

- **Zero Server Setup:** No Docker containers, servers, or cloud proxies to maintain.
- **SQLite Recorder Safe:** The ~7,000 active vehicle positions are kept strictly in Python RAM (`IettClient._fleet_by_kapino`) with TTL caching. `sensor.iett_aktif_filo_boyutu` outputs an integer count only (`extra_state_attributes = {}`), preventing Home Assistant database bloat.
- **Resilient Fallbacks:** Real-time stop arrivals prioritize NTCAPI JSON and seamlessly fall back to İETT web HTML parsing if NTCAPI is unavailable.

---

## Features

### 1. 🌆 Automatic 4 Root Sensors
Created automatically under the **İETT İstanbul Geneli** device upon integration setup:
1. `sensor.istanbul_trafik_yogunlugu_genel` — City-wide traffic index (0–100%)
2. `sensor.istanbul_trafik_yogunlugu_avrupa` — European side traffic index (0–100%)
3. `sensor.istanbul_trafik_yogunlugu_anadolu` — Anatolian side traffic index (0–100%)
4. `sensor.iett_aktif_filo_boyutu` — Total active bus count on Istanbul roads (e.g. `4850 araç`)

### 2. 🚏 1a) Stop Tracker
- **Route Filtering:** Track all routes or only specific routes passing through the stop.
- **Approaching Limit:** Track nearest $N$ buses ($1$ to $10$) or all arriving vehicles.
- **Tickbox Granular Entities:**
  - Route number (`sensor.durak_220602_arac_1_hat_no`)
  - License plate (`sensor.durak_220602_arac_1_plaka`)
  - ETA minutes (`sensor.durak_220602_arac_1_eta`)
  - Formatted countdown mm:ss (`sensor.durak_220602_arac_1_eta_dk_sn`)
  - Haversine distance to stop in meters (`sensor.durak_220602_arac_1_duraga_mesafe`)
  - Haversine distance to custom home/work coordinates in meters (`sensor.durak_220602_arac_1_hedefe_mesafe`)
  - Speed in km/h or mph (`sensor.durak_220602_arac_1_hiz`)
  - Amenities (A/C, WiFi, USB, Accessibility) summary
  - Approaching bus GPS tracker (`device_tracker.durak_220602_arac_1`)

### 3. 🚌 1b) Route Tracker
- Active buses operating on route with Gidiş (`G`) and Dönüş (`D`) breakdown.
- Next scheduled departure timer (`next_dep_g_min`, `next_dep_d_min`) with variant/depar filtering (`all`, `base_only`, or `selected`).
- Disruption alerts with automatic binary sensor (`binary_sensor.hat_500t_sefer_uyarisi`).

### 4. 🎯 1c) Single Vehicle Tracker
- Strict Kapı No validation (`X-NNNN` or `XX-NNNN`, e.g. `C-1753`, `A-001`, `M-1042`).
- GPS Device Tracker entity (`device_tracker.arac_c_1753_konum`).
- Real-time plate, speed, route, and duty status.
- Off-duty vehicles gracefully report `online: false` without triggering `unavailable` errors.

---

## 🎛️ On-Demand Lovelace Card (`<iett-card>`)

Included automatically with the integration! The card connects directly to Home Assistant's WebSocket API (`hass.callWS`) and can operate **with or without configured sensor entities**.

### Visibility-Aware Polling
When your browser tab is in the background or your mobile screen is locked (`document.visibilityState === "hidden"`), the card **stops all polling requests**, ensuring zero wasted network and CPU cycles. When brought back into view, it refreshes instantly.

### Themes
- `led` — Retro transit LED display.
- `modern` — Clean card design with progress badges and amenity icons.
- `native` — Blends seamlessly with your current Home Assistant theme.

### Lovelace Configuration Examples

```yaml
# Stop Departure Board (Zero Sensor Dependency)
type: custom:iett-card
mode: stop
stop_code: "220602"
theme: led
refresh_interval: 20
max_items: 6
```

```yaml
# Route Status Card
type: custom:iett-card
mode: route
route_code: "500T"
theme: modern
refresh_interval: 30
```

```yaml
# Single Vehicle Tracking Card
type: custom:iett-card
mode: vehicle
kapino: "C-1753"
theme: modern
refresh_interval: 15
```

---

## Automation Recipes

### Notification when your bus is 5 minutes away
```yaml
alias: "İETT 500T 5 Dakika Kaldı Bildirimi"
trigger:
  - platform: numeric_state
    entity_id: sensor.durak_220602_arac_1_eta
    below: 6
condition:
  - condition: time
    after: "07:30:00"
    before: "09:00:00"
action:
  - service: notify.notify
    data:
      title: "Otobüsün Yaklaşıyor! 🚌"
      message: >
        500T hattındaki {{ states('sensor.durak_220602_arac_1_plaka') }} plakalı araç
        {{ states('sensor.durak_220602_arac_1_eta_dk_sn') }} içinde durakta olacak!
```

---

## Development & Testing

```bash
# Install test dependencies
pip install -r requirements_test.txt

# Run pytest test suite (75 tests)
python -m pytest -v

# Run linter & formatter checks
ruff check .
ruff format --check .
```

---

## License

MIT License. See [LICENSE](LICENSE) for details.
