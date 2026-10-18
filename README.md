# İETT — Istanbul Bus Tracker for Home Assistant (v2.1)

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)
[![Tests](https://img.shields.io/badge/tests-86%20passed-brightgreen)](#development--testing)
[![HA](https://img.shields.io/badge/Home%20Assistant-2024.1%2B-41BDF5?logo=home-assistant)](https://www.home-assistant.io/)
[![Version](https://img.shields.io/badge/version-2.1.2-blue)](https://github.com/pcislocked/iett-hacs/releases)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

A **100% Standalone & Serverless** Home Assistant custom integration for real-time Istanbul public transport tracking. Communicates directly with official İETT SOAP, NTCAPI, and İBB TKM endpoints without requiring any external proxy or middleware.

---

## Architecture (v2.1 Standalone)

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

- **Zero Middleware Required:** Connects straight to municipal transit endpoints from inside Home Assistant.
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
- **Smart Stop Search:** Search by 6-digit stop code (e.g. `301341`) or by stop name (e.g. `Beşiktaş Meydan`). Results are enriched with direction (`➔ Kadıköy`) and district (`Beşiktaş`) badges so you never pick the wrong side of the street.
- **Route Filtering:** Track all routes or only specific routes passing through the stop.
- **Approaching Limit:** Track nearest $N$ buses ($1$ to $10$) or all arriving vehicles.
- **Relative vs Absolute Time Display:**
  - **Relative (Default):** Natural countdown like `5 dk`, `3 dk`, `1 dk`, `Yaklaşıyor` (matching official displays and PWA).
  - **Absolute:** Exact 24-hour arrival clock time (e.g. `14:35`) in Istanbul time (UTC+3).
- **Home Zone Proximity:** Distance-to-target dynamically defaults to your Home Assistant Home Zone coordinates (`Settings` → `System` → `General` → `Home Location`), or can be set to custom coordinates.
- **Tickbox Granular Entities:**
  - Route number (`sensor.durak_301341_arac_1_hat_no`)
  - License plate (`sensor.durak_301341_arac_1_plaka`)
  - ETA minutes (`sensor.durak_301341_arac_1_eta`)
  - Arrival clock time (`sensor.durak_301341_arac_1_varis_saati`)
  - Haversine distance to stop in meters (`sensor.durak_301341_arac_1_duraga_mesafe`)
  - Haversine distance to home/work in meters (`sensor.durak_301341_arac_1_hedefe_mesafe`)
  - Speed in km/h or mph (`sensor.durak_301341_arac_1_hiz`)
  - Amenities (A/C, WiFi, USB, Accessibility) summary
  - Approaching bus GPS tracker (`device_tracker.durak_301341_arac_1`)

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

### Features:
- **Visibility-Aware Polling:** Zero network traffic when the browser tab is hidden or screen is locked (`document.visibilityState === "hidden"`).
- **Time Display Modes:**
  - `relative` *(Default)*: Remaining minutes countdown (e.g. `5 dk`, `Yaklaşıyor`).
  - `absolute`: Scheduled arrival clock time (e.g. `14:35`).
  - `both`: Shows relative time with clock time (e.g. `5 dk • 14:35`).
- **Visual Card Editor:** Full UI configuration with live preview, mode selection, and stop/route inputs.
- **3 Visual Themes:**
  - `led` — Retro transit LED display.
  - `modern` — Clean card design with progress badges and amenity icons.
  - `native` — Blends seamlessly with your current Home Assistant theme.

### Lovelace Configuration Examples

```yaml
# Stop Departure Board (Zero Sensor Dependency)
type: custom:iett-card
mode: stop
stop_code: "301341"
time_format: relative
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

### 📱 Mobile (Home Assistant Companion App) & Troubleshooting

The card resource is registered dynamically into Home Assistant's Lovelace Resources with content-hashed cache busting. If your mobile device shows:
```
Configuration error: Custom element doesn't exist: iett-card.
```
1. Ensure the İETT integration is added and loaded in Home Assistant.
2. In the Companion App, open **Settings** → **Companion App** → **Debugging** (or **Troubleshooting**) → tap **Reset frontend cache**.
3. Force-close and reopen the app.

---

## Automation Recipes

### Notification when your bus is 5 minutes away
```yaml
alias: "İETT 500T 5 Dakika Kaldı Bildirimi"
trigger:
  - platform: numeric_state
    entity_id: sensor.durak_301341_arac_1_eta
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
        500T hattındaki {{ states('sensor.durak_301341_arac_1_plaka') }} plakalı araç
        {{ states('sensor.durak_301341_arac_1_eta') }} dakika içinde durakta olacak!
```

---

## Development & Testing

```bash
# Install test dependencies
pip install -r requirements_test.txt

# Run pytest test suite (86 tests)
python -m pytest -v

# Run linter & formatter checks
ruff check .
ruff format --check .
```

---

## License

MIT License. See [LICENSE](LICENSE) for details.
