/**
 * DigitalHouses Climate System Tree: presentation-only Lovelace card.
 * Push updates via HA's hass setter. No polling and no equipment control.
 */
class DhClimateTreeCard extends HTMLElement {
  setConfig(config) {
    if (config.entity !== undefined &&
        (typeof config.entity !== "string" || !config.entity.startsWith("sensor."))) {
      throw new Error("entity must be a sensor entity_id");
    }
    this._entity = config.entity || "sensor.dh_climate_app_topology";
    this._lastAttributes = null;
    if (!this.shadowRoot) {
      this.attachShadow({ mode: "open" });
      const style = document.createElement("style");
      style.textContent = `
        ha-card { padding: 16px; }
        .tree { overflow-x: auto; font: 13px/1.75 var(--code-font-family, monospace); }
        .line { display: flex; align-items: baseline; white-space: pre; min-width: max-content; }
        .prefix { white-space: pre; color: var(--secondary-text-color); }
        .field { white-space: pre; }
        button.field { font: inherit; padding: 0; border: 0; margin: 0; background: transparent;
          color: var(--primary-text-color); cursor: pointer; text-align: left; }
        button.field:hover { text-decoration: underline; color: var(--primary-color); }
        button.field:focus-visible { outline: 2px solid var(--primary-color); border-radius: 2px; }
        .message { color: var(--secondary-text-color); }
      `;
      const card = document.createElement("ha-card");
      const tree = document.createElement("div");
      tree.className = "tree";
      card.appendChild(tree);
      this.shadowRoot.append(style, card);
      this._tree = tree;
    }
  }

  set hass(hass) {
    const entity = hass.states[this._entity];
    const attributes = entity?.attributes;
    if (this._lastAttributes === attributes) return;
    this._lastAttributes = attributes;
    if (!this._tree) return;
    this._tree.replaceChildren();
    if (!entity || entity.state !== "ready" ||
        attributes?.schema_version !== 1 || !Array.isArray(attributes.lines)) {
      const message = document.createElement("div");
      message.className = "message";
      message.textContent = entity?.state === "too_large"
        ? "System Tree: размер топологии превышает предел. См. диагностику приложения."
        : "System Tree: данные недоступны.";
      this._tree.appendChild(message);
      return;
    }
    for (const line of attributes.lines) {
      if (typeof line.prefix !== "string" || !Array.isArray(line.parts)) continue;
      const row = document.createElement("div");
      row.className = "line";
      const prefix = document.createElement("span");
      prefix.className = "prefix";
      prefix.textContent = line.prefix;
      row.appendChild(prefix);
      for (const part of line.parts) {
        if (typeof part.text !== "string") continue;
        const clickable = typeof part.entity_id === "string" &&
          /^[a-z_]+\.[a-zA-Z0-9_]+$/.test(part.entity_id);
        const element = document.createElement(clickable ? "button" : "span");
        element.className = "field";
        element.textContent = part.text;
        if (clickable) {
          element.type = "button";
          element.title = part.entity_id;
          element.addEventListener("click", () => {
            this.dispatchEvent(new CustomEvent("hass-more-info", {
              detail: { entityId: part.entity_id },
              bubbles: true, composed: true,
            }));
          });
        }
        row.appendChild(element);
      }
      this._tree.appendChild(row);
    }
  }

  getCardSize() { return 10; }
  static getStubConfig() { return { entity: "sensor.dh_climate_app_topology" }; }
}

if (!customElements.get("dh-climate-tree-card")) {
  customElements.define("dh-climate-tree-card", DhClimateTreeCard);
}
window.customCards = window.customCards || [];
if (!window.customCards.some(card => card.type === "dh-climate-tree-card")) {
  window.customCards.push({
    type: "dh-climate-tree-card",
    name: "DH Climate System Tree",
    description: "Read-only topology from DigitalHouses Climate App",
  });
}
