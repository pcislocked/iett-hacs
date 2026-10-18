# İETT — Istanbul Bus Tracker for Home Assistant (v2.0)

**100% Standalone & Serverless** Home Assistant integration for real-time Istanbul bus telemetry, stop departure boards, route monitoring, and city-wide traffic congestion metrics.

No external middleware or proxy server needed — communicates directly with official İETT SOAP, NTCAPI, and İBB TKM endpoints.

---

## Key Features

- **🌆 4 Automatic Root Sensors:**
  - `sensor.istanbul_trafik_yogunlugu_genel` (%)
  - `sensor.istanbul_trafik_yogunlugu_avrupa` (%)
  - `sensor.istanbul_trafik_yogunlugu_anadolu` (%)
  - `sensor.iett_aktif_filo_boyutu` (Active fleet size; integer-only state, 16 KB SQLite recorder safe)

- **🚏 1a) Stop Tracker:**
  - Route filter: All routes or selected routes passing by the stop
  - Vehicle quantity filter: Nearest N vehicles (1–10) or all approaching vehicles
  - Configurable entity attributes: Route number, license plate, ETA (min), formatted ETA (mm:ss), coordinates, distance to stop (m), distance to custom point (m), vehicle speed (km/h or mph), and equipment (A/C, WiFi, USB, Accessibility)
  - Optional GPS device tracker for approaching buses

- **🚌 1b) Route Tracker:**
  - Active bus count (with Gidiş/Dönüş direction breakdown)
  - Timetable departures with depar filtering (All depars, Base route only, or Selected depar code)
  - Service disruption announcements & binary sensor alert (`binary_sensor.hat_500t_sefer_uyarisi`)

- **🎯 1c) Single Vehicle Tracking:**
  - Strict Kapı No (`X-NNNN`, e.g. `C-1753`)
  - Live GPS device tracker (`device_tracker.arac_c_1753_konum`)
  - Real-time plate, speed, route, and status entities (gracefully transitions to "Bilinmiyor" when vehicle is off-duty)

- **📊 On-Demand Lovelace Card (`<iett-card>`):**
  - Works **with or without sensor entities** via built-in WebSocket API
  - Visibility-aware polling (zero network traffic when tab or screen is off)
  - 3 visual themes: `led` (classic LED matrix), `modern` (clean transit cards), and `native` (Home Assistant theme styling)
  - Visual card editor with live search for stops and routes

---

## Installation via HACS

1. In HACS, go to **Integrations** → **Custom repositories**.
2. Add `https://github.com/pcislocked/iett-hacs` as an **Integration**.
3. Install **İETT Istanbul Bus Tracker**.
4. Restart Home Assistant.
5. Go to **Settings** → **Devices & Services** → **Add Integration** → **İETT**.
