/*
 * Tap Electric - Recent Sessions Card
 * A self-contained Lovelace custom card. No build step, no dependencies.
 *
 * Install:
 *   1. Copy this file to  <config>/www/tap-recent-sessions-card.js
 *   2. Settings -> Dashboards -> (top-right menu) Resources -> Add resource
 *        URL: /local/tap-recent-sessions-card.js
 *        Type: JavaScript module
 *   3. Add a card:  type: custom:tap-recent-sessions-card
 *
 * Config:
 *   type:    custom:tap-recent-sessions-card   (required)
 *   entity:  sensor.tap_electric_recent_sessions   (optional, this is the default)
 *   title:   Recent charging sessions            (optional)
 *   limit:   10                                   (optional, max rows to show)
 */

const CARD_VERSION = "0.7.0";

class TapRecentSessionsCard extends HTMLElement {
  static getStubConfig() {
    return { entity: "sensor.tap_electric_recent_sessions", title: "Recent charging sessions" };
  }

  setConfig(config) {
    if (!config) throw new Error("Invalid configuration");
    this._config = {
      entity: config.entity || "sensor.tap_electric_recent_sessions",
      title: config.title !== undefined ? config.title : "Recent charging sessions",
      limit: config.limit || 10,
    };
    this._lastKey = null;
    this._built = false;
  }

  set hass(hass) {
    this._hass = hass;
    this._render();
  }

  getCardSize() {
    const n = this._sessions ? this._sessions.length : 3;
    return 1 + Math.min(n, this._config ? this._config.limit : 10);
  }

  _fmtDate(iso) {
    if (!iso) return "";
    const d = new Date(iso);
    if (isNaN(d)) return iso;
    const lang = (this._hass && this._hass.locale && this._hass.locale.language) || "en";
    try {
      return new Intl.DateTimeFormat(lang, {
        day: "numeric", month: "short", hour: "2-digit", minute: "2-digit",
      }).format(d);
    } catch (e) {
      return d.toLocaleString();
    }
  }

  _eur(v) {
    const n = Number(v) || 0;
    return "€" + n.toFixed(2);
  }

  _render() {
    if (!this._hass || !this._config) return;
    const stateObj = this._hass.states[this._config.entity];

    if (!stateObj) {
      this._shell();
      this._body.innerHTML =
        `<div class="empty">Entity <code>${this._config.entity}</code> not found.</div>`;
      return;
    }

    let sessions = (stateObj.attributes && stateObj.attributes.sessions) || [];
    if (!Array.isArray(sessions)) sessions = [];
    sessions = sessions.slice(0, this._config.limit);
    this._sessions = sessions;

    // Skip DOM churn if nothing changed.
    const key = JSON.stringify(sessions) + "|" + this._config.title;
    if (this._built && key === this._lastKey) return;
    this._lastKey = key;

    this._shell();

    if (!sessions.length) {
      this._body.innerHTML = `<div class="empty">No sessions yet.</div>`;
      return;
    }

    const rows = sessions.map((s) => {
      const loc = s.address || s.city || s.operator || "Unknown location";
      const subParts = [];
      if (s.address && s.city) subParts.push(s.city);
      if (s.operator) subParts.push(s.operator);
      const sub = [this._fmtDate(s.start), subParts.join(" · ")].filter(Boolean).join(" · ");
      const kwh = (Number(s.kwh) || 0).toFixed(1);
      const cost = this._eur(s.cost);
      const price = (Number(s.cost_per_kwh) || 0).toFixed(3);
      const live = s.ongoing
        ? `<span class="live" title="Charging now"></span>`
        : "";
      return `
        <div class="row">
          <div class="icon"><ha-icon icon="mdi:ev-station"></ha-icon></div>
          <div class="main">
            <div class="loc">${live}${this._esc(loc)}</div>
            <div class="sub">${this._esc(sub)}</div>
          </div>
          <div class="nums">
            <div class="energy">${kwh} kWh</div>
            <div class="cost">${cost}</div>
            <div class="price">€${price}/kWh</div>
          </div>
        </div>`;
    });

    this._body.innerHTML = rows.join("");
  }

  _esc(str) {
    return String(str == null ? "" : str).replace(/[&<>"']/g, (c) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
    }[c]));
  }

  _shell() {
    if (this._built) {
      const h = this.querySelector(".card-title");
      if (h) h.textContent = this._config.title || "";
      if (h) h.style.display = this._config.title ? "" : "none";
      return;
    }
    this.innerHTML = `
      <ha-card>
        <style>
          .card-title {
            font-size: 1.25rem;
            font-weight: 500;
            padding: 16px 16px 4px;
            color: var(--primary-text-color);
          }
          .list { padding: 8px 4px 8px; }
          .row {
            display: flex;
            align-items: center;
            gap: 12px;
            padding: 10px 14px;
            border-radius: 12px;
          }
          .row:nth-child(odd) {
            background: var(--table-row-alternative-background-color, rgba(127,127,127,0.06));
          }
          .icon {
            flex: 0 0 auto;
            width: 38px; height: 38px;
            display: flex; align-items: center; justify-content: center;
            border-radius: 50%;
            background: var(--primary-color);
            color: var(--text-primary-color, #fff);
          }
          .icon ha-icon { --mdc-icon-size: 22px; }
          .main { flex: 1 1 auto; min-width: 0; }
          .loc {
            font-weight: 500;
            color: var(--primary-text-color);
            white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
          }
          .sub {
            font-size: 0.82rem;
            color: var(--secondary-text-color);
            white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
          }
          .nums { flex: 0 0 auto; text-align: right; line-height: 1.25; }
          .energy { font-weight: 600; color: var(--primary-text-color); }
          .cost { font-size: 0.9rem; color: var(--primary-text-color); }
          .price { font-size: 0.75rem; color: var(--secondary-text-color); }
          .live {
            display: inline-block;
            width: 8px; height: 8px;
            margin-right: 6px;
            border-radius: 50%;
            background: var(--success-color, #43a047);
            box-shadow: 0 0 0 0 var(--success-color, #43a047);
            animation: tap-pulse 1.8s infinite;
            vertical-align: middle;
          }
          @keyframes tap-pulse {
            0% { box-shadow: 0 0 0 0 rgba(67,160,71,0.6); }
            70% { box-shadow: 0 0 0 7px rgba(67,160,71,0); }
            100% { box-shadow: 0 0 0 0 rgba(67,160,71,0); }
          }
          .empty { padding: 24px 16px; color: var(--secondary-text-color); text-align: center; }
        </style>
        <div class="card-title"></div>
        <div class="list"></div>
      </ha-card>`;
    const title = this.querySelector(".card-title");
    title.textContent = this._config.title || "";
    title.style.display = this._config.title ? "" : "none";
    this._body = this.querySelector(".list");
    this._built = true;
  }
}

customElements.define("tap-recent-sessions-card", TapRecentSessionsCard);

// Make it findable in the "By card" picker.
window.customCards = window.customCards || [];
window.customCards.push({
  type: "tap-recent-sessions-card",
  name: "Tap Electric: Recent Sessions",
  description: "The last charging sessions from your Tap Electric account.",
  preview: false,
});

console.info(
  `%c TAP-ELECTRIC-RECENT-SESSIONS-CARD %c ${CARD_VERSION} `,
  "color:#fff;background:#3b5bdb;font-weight:700;border-radius:3px 0 0 3px;padding:2px 4px;",
  "color:#3b5bdb;background:#eef;border-radius:0 3px 3px 0;padding:2px 4px;"
);
