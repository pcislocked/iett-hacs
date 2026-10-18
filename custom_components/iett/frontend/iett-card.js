/**
 * İETT Istanbul Bus Tracker - Custom Lovelace Card
 * Version: 2.0.0
 * Zero sensor dependency on-demand WebSocket fetching with visibility-aware lifecycle.
 */

function escapeHtml(unsafe) {
  if (unsafe === null || unsafe === undefined) return "";
  return String(unsafe)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

class IettCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._config = null;
    this._hass = null;
    this._data = null;
    this._loading = false;
    this._error = null;
    this._timer = null;
    this._boundVisibilityChange = this._onVisibilityChange.bind(this);
  }

  static async getConfigElement() {
    return document.createElement("iett-card-editor");
  }

  static getStubConfig() {
    return {
      type: "custom:iett-card",
      mode: "stop",
      stop_code: "220602",
      theme: "led",
      refresh_interval: 20,
      max_items: 6,
    };
  }

  setConfig(config) {
    if (!config) throw new Error("Geçersiz kart konfigürasyonu");
    const mode = config.mode || (config.route_code ? "route" : config.kapino ? "vehicle" : "stop");
    if (mode === "stop" && !config.stop_code && !config.entity) {
      throw new Error("Durak modu için stop_code veya entity gereklidir");
    }
    if (mode === "route" && !config.route_code && !config.entity) {
      throw new Error("Hat modu için route_code veya entity gereklidir");
    }
    if (mode === "vehicle" && !config.kapino && !config.entity) {
      throw new Error("Araç modu için kapino veya entity gereklidir");
    }
    this._config = {
      mode,
      theme: "led",
      refresh_interval: 20,
      max_items: 8,
      ...config,
    };
    this._render();
    if (this.isConnected) {
      this._startTimer();
      if (this._hass) {
        this._fetchData();
      }
    }
  }

  set hass(hass) {
    const firstHass = !this._hass;
    this._hass = hass;
    if (firstHass && this.isConnected) {
      this._fetchData();
    } else if (this._config && this._config.entity) {
      // If bound to entity, sync from entity state and re-render
      this._syncFromEntity();
      this._render();
    }
  }

  connectedCallback() {
    document.addEventListener("visibilitychange", this._boundVisibilityChange);
    this._startTimer();
    if (this._hass) {
      this._fetchData();
    }
  }

  disconnectedCallback() {
    document.removeEventListener("visibilitychange", this._boundVisibilityChange);
    this._stopTimer();
  }

  _onVisibilityChange() {
    if (document.visibilityState === "visible" && this.isConnected && this._hass) {
      this._fetchData();
    }
  }

  _startTimer() {
    this._stopTimer();
    const intervalMs = Math.max(10, Number(this._config?.refresh_interval || 20)) * 1000;
    this._timer = window.setInterval(() => {
      if (document.visibilityState === "visible" && this.isConnected && this._hass) {
        this._fetchData();
      }
    }, intervalMs);
  }

  _stopTimer() {
    if (this._timer !== null) {
      window.clearInterval(this._timer);
      this._timer = null;
    }
  }

  _syncFromEntity() {
    if (!this._hass || !this._config?.entity) return false;
    const stateObj = this._hass.states?.[this._config.entity];
    if (!stateObj) return false;
    const attrs = stateObj.attributes || {};
    const mode = this._config.mode;
    if (mode === "stop") {
      const vehicles = attrs.vehicles || [];
      this._data = {
        stop_code: attrs.stop_code || this._config.stop_code || "",
        stop_name: attrs.stop_name || attrs.friendly_name || this._config.entity,
        direction: attrs.direction || "",
        arrivals: vehicles.map((v) => ({
          route_code: v.hatno || v.route_code || "",
          destination: v.destination || "",
          eta_minutes: v.eta ?? v.eta_minutes ?? null,
          eta_mmss: v.eta_mmss || null,
          eta_raw: v.eta_raw || "",
          kapino: v.kapino || null,
          plate: v.plaka || v.plate || null,
          distance_to_stop_m: v.dist_stop ?? v.distance_to_stop_m ?? null,
          amenities: v.amenities || {},
        })),
      };
      return true;
    }
    if (mode === "route") {
      this._data = {
        route_code: attrs.route_code || this._config.route_code || "",
        active_buses: attrs.buses ? attrs.buses.length : stateObj.state,
        announcements: attrs.announcements || [],
        schedule: attrs.upcoming_departures || [],
      };
      return true;
    }
    if (mode === "vehicle") {
      this._data = {
        kapino: attrs.kapino || this._config.kapino || "",
        online: stateObj.state !== "unavailable" && stateObj.state !== "unknown" && stateObj.state !== "off",
        vehicle: {
          plate: attrs.plate || stateObj.state,
          route_code: attrs.route_code || null,
          speed: attrs.speed ?? null,
          operator: attrs.operator || null,
        },
      };
      return true;
    }
    return false;
  }

  async _fetchData() {
    if (!this._hass || !this._config) return;
    this._loading = true;
    this._error = null;

    try {
      const mode = this._config.mode;
      if (mode === "stop" && this._config.stop_code) {
        const res = await this._hass.callWS({
          type: "iett/get_stop_board",
          stop_code: String(this._config.stop_code).trim(),
          route_filter: this._config.route_filter || [],
          max_items: this._config.max_items || 10,
        });
        this._data = res;
      } else if (mode === "route" && this._config.route_code) {
        const res = await this._hass.callWS({
          type: "iett/get_route_board",
          route_code: String(this._config.route_code).trim().toUpperCase(),
        });
        this._data = res;
      } else if (mode === "vehicle" && this._config.kapino) {
        const res = await this._hass.callWS({
          type: "iett/get_vehicle_card",
          kapino: String(this._config.kapino).trim().toUpperCase(),
        });
        this._data = res;
      } else if (this._config.entity) {
        this._syncFromEntity();
      }
    } catch (err) {
      if (!this._syncFromEntity()) {
        this._error = err.message || "Veri alınamadı";
      }
    } finally {
      this._loading = false;
      this._render();
    }
  }

  _render() {
    if (!this.shadowRoot) return;
    const theme = this._config?.theme || "led";
    const mode = this._config?.mode || "stop";

    const styles = `
      <style>
        :host {
          display: block;
          font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
        }
        ha-card {
          overflow: hidden;
          padding: 16px;
          border-radius: var(--ha-card-border-radius, 12px);
          background: var(--ha-card-background, #1e1e24);
          color: var(--primary-text-color, #ffffff);
          box-shadow: var(--ha-card-box-shadow, 0 4px 12px rgba(0,0,0,0.15));
        }
        /* Theme: LED Smart Stop */
        ha-card.theme-led {
          background: #0f1016;
          border: 1px solid #282a36;
          color: #ffb86c;
        }
        ha-card.theme-led .header-title {
          color: #f1fa8c;
          font-family: "Courier New", Courier, monospace;
          letter-spacing: 1px;
        }
        ha-card.theme-led .badge-route {
          background: #ff5555;
          color: #fff;
          font-weight: bold;
        }
        ha-card.theme-led .eta-pill {
          background: #44475a;
          color: #50fa7b;
          font-family: monospace;
          font-weight: bold;
        }
        ha-card.theme-led .eta-pulsing {
          color: #50fa7b;
          animation: pulse 1.2s infinite;
        }
        /* Theme: Modern Transit */
        ha-card.theme-modern {
          background: var(--ha-card-background, #ffffff);
          color: var(--primary-text-color, #1a202c);
          border: 1px solid rgba(0,0,0,0.08);
        }
        ha-card.theme-modern .badge-route {
          background: #2563eb;
          color: #ffffff;
          border-radius: 6px;
        }
        ha-card.theme-modern .eta-pill {
          background: #eff6ff;
          color: #1d4ed8;
          border-radius: 6px;
        }
        ha-card.theme-modern .eta-pulsing {
          background: #dcfce7;
          color: #15803d;
        }
        /* Common Layout */
        .card-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-bottom: 14px;
          border-bottom: 1px solid rgba(255,255,255,0.08);
          padding-bottom: 8px;
        }
        .header-title {
          font-size: 1.15rem;
          font-weight: 600;
          display: flex;
          align-items: center;
          gap: 8px;
        }
        .header-badge {
          font-size: 0.75rem;
          padding: 2px 6px;
          border-radius: 4px;
          background: rgba(255,255,255,0.12);
        }
        .arrival-row {
          display: flex;
          align-items: center;
          justify-content: space-between;
          padding: 8px 0;
          border-bottom: 1px solid rgba(255,255,255,0.05);
        }
        .arrival-left {
          display: flex;
          align-items: center;
          gap: 10px;
          flex: 1;
          min-width: 0;
        }
        .badge-route {
          padding: 4px 8px;
          border-radius: 4px;
          font-size: 0.9rem;
          font-weight: 700;
          min-width: 44px;
          text-align: center;
        }
        .arrival-info {
          display: flex;
          flex-direction: column;
          overflow: hidden;
        }
        .arrival-dest {
          font-size: 0.95rem;
          font-weight: 500;
          white-space: nowrap;
          overflow: hidden;
          text-overflow: ellipsis;
        }
        .arrival-meta {
          font-size: 0.78rem;
          opacity: 0.75;
          display: flex;
          gap: 8px;
          margin-top: 2px;
        }
        .arrival-right {
          margin-left: 10px;
          text-align: right;
        }
        .eta-pill {
          padding: 4px 10px;
          border-radius: 6px;
          font-size: 0.95rem;
          font-weight: 700;
          display: inline-block;
        }
        .amenity-chip {
          display: inline-flex;
          gap: 4px;
          opacity: 0.85;
          font-size: 0.8rem;
        }
        .alert-box {
          background: rgba(234, 179, 8, 0.15);
          border: 1px solid rgba(234, 179, 8, 0.4);
          color: #eab308;
          padding: 10px;
          border-radius: 6px;
          font-size: 0.85rem;
          margin-top: 10px;
        }
        .error-box {
          color: #ef4444;
          font-size: 0.88rem;
          padding: 8px 0;
        }
        .empty-state {
          padding: 16px 0;
          text-align: center;
          opacity: 0.65;
          font-size: 0.9rem;
        }
        @keyframes pulse {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.4; }
        }
      </style>
    `;

    let content = "";
    if (this._error) {
      content = `<div class="error-box">⚠️ ${escapeHtml(this._error)}</div>`;
    } else if (mode === "stop") {
      content = this._renderStopContent();
    } else if (mode === "route") {
      content = this._renderRouteContent();
    } else if (mode === "vehicle") {
      content = this._renderVehicleContent();
    }

    this.shadowRoot.innerHTML = `
      ${styles}
      <ha-card class="theme-${escapeHtml(theme)}">
        ${content}
      </ha-card>
    `;
  }

  _renderStopContent() {
    const data = this._data;
    const stopName = data?.stop_name || this._config.title || `Durak ${this._config.stop_code || ""}`;
    const stopCode = data?.stop_code || this._config.stop_code || "";
    const arrivals = data?.arrivals || [];

    let rowsHtml = "";
    if (arrivals.length === 0) {
      rowsHtml = `<div class="empty-state">Yaklaşan araç bulunmuyor</div>`;
    } else {
      rowsHtml = arrivals
        .map((arr) => {
          const isPulse = arr.eta_minutes !== null && arr.eta_minutes <= 3;
          const etaText = arr.eta_mmss || (arr.eta_minutes !== null ? `${arr.eta_minutes} dk` : arr.eta_raw || "--");
          const distText = arr.distance_to_stop_m ? `${arr.distance_to_stop_m}m` : "";
          const kapiPlate = [arr.kapino, arr.plate].filter(Boolean).join(" • ");

          const am = arr.amenities || {};
          const amIcons = [];
          if (am.ac) amIcons.push("❄️");
          if (am.wifi) amIcons.push("📶");
          if (am.usb) amIcons.push("🔌");
          if (am.accessible) amIcons.push("♿");

          return `
            <div class="arrival-row">
              <div class="arrival-left">
                <span class="badge-route">${escapeHtml(arr.route_code)}</span>
                <div class="arrival-info">
                  <span class="arrival-dest">${escapeHtml(arr.destination)}</span>
                  <div class="arrival-meta">
                    ${kapiPlate ? `<span>${escapeHtml(kapiPlate)}</span>` : ""}
                    ${distText ? `<span>${escapeHtml(distText)}</span>` : ""}
                    ${amIcons.length ? `<span class="amenity-chip">${escapeHtml(amIcons.join(""))}</span>` : ""}
                  </div>
                </div>
              </div>
              <div class="arrival-right">
                <span class="eta-pill ${isPulse ? "eta-pulsing" : ""}">${escapeHtml(etaText)}</span>
              </div>
            </div>
          `;
        })
        .join("");
    }

    return `
      <div class="card-header">
        <div class="header-title">
          <span>🚏 ${escapeHtml(stopName)}</span>
          ${stopCode ? `<span class="header-badge">${escapeHtml(stopCode)}</span>` : ""}
        </div>
        ${data?.direction ? `<span class="header-badge">${escapeHtml(data.direction)}</span>` : ""}
      </div>
      <div class="card-content">
        ${rowsHtml}
      </div>
    `;
  }

  _renderRouteContent() {
    const data = this._data;
    const routeCode = data?.route_code || this._config.route_code || "";
    const activeCount = data?.active_buses ?? "--";
    const announcements = data?.announcements || [];
    const schedule = data?.schedule || [];

    let annHtml = "";
    if (announcements.length > 0) {
      annHtml = `
        <div class="alert-box">
          ⚠️ <strong>Duyuru:</strong> ${escapeHtml(announcements[0].message)}
        </div>
      `;
    }

    let depHtml = "";
    if (schedule.length > 0) {
      const nextFew = schedule.slice(0, 3).map((s) => `${s.departure_time} (${s.direction})`).join(" • ");
      depHtml = `<div class="arrival-meta" style="margin-top: 8px;">Kalkışlar: ${escapeHtml(nextFew)}</div>`;
    }

    return `
      <div class="card-header">
        <div class="header-title">
          <span class="badge-route">${escapeHtml(routeCode)}</span>
          <span>Hattı Canlı Durumu</span>
        </div>
        <span class="header-badge">${escapeHtml(String(activeCount))} Araç Sahada</span>
      </div>
      <div class="card-content">
        ${depHtml}
        ${annHtml}
      </div>
    `;
  }

  _renderVehicleContent() {
    const data = this._data;
    const veh = data?.vehicle;
    const kapino = data?.kapino || this._config.kapino || "";
    const online = data?.online;

    return `
      <div class="card-header">
        <div class="header-title">
          <span>🚌 ${escapeHtml(kapino)}</span>
          <span class="header-badge">${online ? "Seferde" : "Garajda / Çevrimdışı"}</span>
        </div>
        ${veh?.plate ? `<span class="header-badge" style="font-weight: bold; border: 1px solid rgba(255,255,255,0.2);">TR ${escapeHtml(veh.plate)}</span>` : ""}
      </div>
      <div class="card-content">
        ${online && veh ? `
          <div class="arrival-row">
            <div>Aktif Hat: <strong>${escapeHtml(veh.route_code || "Boşta")}</strong></div>
            <div>Hız: <strong>${escapeHtml(String(veh.speed ?? 0))} km/h</strong></div>
          </div>
          ${veh.operator ? `<div class="arrival-meta">Operatör: ${escapeHtml(veh.operator)}</div>` : ""}
        ` : `
          <div class="empty-state">Araç aktif sinyal vermiyor</div>
        `}
      </div>
    `;
  }
}

class IettCardEditor extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._config = null;
    this._hass = null;
  }

  setConfig(config) {
    this._config = config;
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
  }

  _render() {
    if (!this.shadowRoot || !this._config) return;

    this.shadowRoot.innerHTML = `
      <style>
        .form-row {
          display: flex;
          flex-direction: column;
          margin-bottom: 12px;
        }
        label {
          font-size: 0.85rem;
          font-weight: 500;
          margin-bottom: 4px;
        }
        input, select {
          padding: 8px;
          border-radius: 4px;
          border: 1px solid #ccc;
          font-size: 0.95rem;
        }
      </style>
      <div class="form-row">
        <label>Mod</label>
        <select id="mode">
          <option value="stop" ${this._config.mode === "stop" ? "selected" : ""}>Durak Tabelası</option>
          <option value="route" ${this._config.mode === "route" ? "selected" : ""}>Hat Durumu</option>
          <option value="vehicle" ${this._config.mode === "vehicle" ? "selected" : ""}>Tekil Araç</option>
        </select>
      </div>
      <div class="form-row">
        <label>Durak Kodu (stop_code)</label>
        <input type="text" id="stop_code" value="${escapeHtml(this._config.stop_code || "")}" placeholder="Örn: 220602" />
      </div>
      <div class="form-row">
        <label>Hat Kodu (route_code)</label>
        <input type="text" id="route_code" value="${escapeHtml(this._config.route_code || "")}" placeholder="Örn: 500T" />
      </div>
      <div class="form-row">
        <label>Kapı No (kapino)</label>
        <input type="text" id="kapino" value="${escapeHtml(this._config.kapino || "")}" placeholder="Örn: C-1753" />
      </div>
      <div class="form-row">
        <label>Tema</label>
        <select id="theme">
          <option value="led" ${this._config.theme === "led" ? "selected" : ""}>Akıllı Durak (LED)</option>
          <option value="modern" ${this._config.theme === "modern" ? "selected" : ""}>Modern</option>
          <option value="native" ${this._config.theme === "native" ? "selected" : ""}>Home Assistant</option>
        </select>
      </div>
      <div class="form-row">
        <label>Yenileme Süresi (Saniye)</label>
        <input type="number" id="refresh_interval" value="${escapeHtml(this._config.refresh_interval || 20)}" min="10" max="120" />
      </div>
    `;

    const inputs = this.shadowRoot.querySelectorAll("input, select");
    inputs.forEach((input) => {
      input.addEventListener("change", () => {
        const newConfig = { ...this._config };
        inputs.forEach((i) => {
          if (i.value) {
            newConfig[i.id] = i.type === "number" ? Number(i.value) : i.value;
          } else {
            delete newConfig[i.id];
          }
        });
        const event = new CustomEvent("config-changed", {
          detail: { config: newConfig },
          bubbles: true,
          composed: true,
        });
        this.dispatchEvent(event);
      });
    });
  }
}

if (!customElements.get("iett-card")) {
  customElements.define("iett-card", IettCard);
}
if (!customElements.get("iett-card-editor")) {
  customElements.define("iett-card-editor", IettCardEditor);
}

window.customCards = window.customCards || [];
window.customCards.push({
  type: "iett-card",
  name: "İETT Canlı Kartı",
  description: "Sensörsüz on-demand çalışan İETT Akıllı Durak ve Hat kartı",
  preview: true,
});
