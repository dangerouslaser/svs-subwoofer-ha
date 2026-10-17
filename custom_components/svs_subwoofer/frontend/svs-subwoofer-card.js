/**
 * SVS Subwoofer dashboard card and tile features.
 *
 * Tile features (they work in any tile card, and in the SVS card):
 * - custom:svs-subwoofer-presets  one button per preset, each in its own color
 * - custom:svs-subwoofer-volume   a volume slider, optionally colored by volume thresholds
 * - custom:svs-subwoofer-standby  the standby mode as a segmented control
 * Each finds its entity on the same device as the card's entity, so a card
 * for a subwoofer group controls the group, and a card for one subwoofer
 * controls that subwoofer.
 *
 * custom:svs-subwoofer-card is Home Assistant's tile card, wrapped: the tile card still
 * draws the name, state, actions and features. The SVS card adds a driver in
 * place of the icon (its size follows the volume, and it shakes when the
 * volume or preset changes), a Bluetooth badge when a subwoofer is not
 * connected, and an optional cabinet finish behind the card.
 *
 * Every corner, color and size comes from the theme's variables.
 */

const VERSION = "1.0.0";
const DOMAIN = "svs_subwoofer";
const CARD_TYPE = "svs-subwoofer-card";
const EDITOR_TYPE = "svs-subwoofer-card-editor";
const TILE_EDITOR_TYPE = "svs-subwoofer-tile-card-editor";

// The entities a feature or the card looks for on a device, by translation key
// (group entities first)
const ROLES = {
  preset: ["group_preset", "preset"],
  volume: ["group_volume", "volume"],
  standby: ["group_standby_mode", "standby_mode"],
  connected: ["connected"],
  reconnect: ["reconnect"],
  disconnect: ["disconnect"],
};
// States that are not presets: never shown as a preset button
const NOT_PRESETS = ["Manual", "Mixed"];

// Home Assistant's named colors (the tile card's color picker)
const HA_COLORS = [
  "primary", "accent", "red", "pink", "purple", "deep-purple", "indigo", "blue", "light-blue", "cyan",
  "teal", "green", "light-green", "lime", "yellow", "amber", "orange", "deep-orange", "brown",
  "light-grey", "grey", "dark-grey", "blue-grey", "black", "white", "disabled",
];
/**
 * Text that reads on a filled button: dark or white, whichever contrasts
 * more with the color (WCAG contrast ratio). The color is the one the button
 * actually shows (a theme variable such as the feature color, resolved by
 * the browser).
 */
let colorProbe;
function textOn(el, cssValue) {
  const resolved = cssValue.startsWith("var(") ? getComputedStyle(el).getPropertyValue(cssValue.slice(4, -1).split(",")[0].trim()).trim() : cssValue;
  // Not known yet (the element is not on the page): the caller tries again
  if (!resolved) return null;
  colorProbe ??= document.createElement("canvas").getContext("2d");
  colorProbe.fillStyle = "#000";
  colorProbe.fillStyle = resolved;
  const [r, g, b] = (colorProbe.fillStyle.match(/[\d.]+/g) ?? [0, 0, 0]).map(Number);
  const hex = colorProbe.fillStyle.startsWith("#") ? colorProbe.fillStyle.slice(1).match(/../g).map((h) => parseInt(h, 16)) : [r, g, b];
  const light = luminance(hex);
  // The dark text is black at 85 %, so on the color it is a little lighter
  const dark = luminance(hex.map((v) => v * 0.15));
  return (light + 0.05) / (dark + 0.05) > 1.05 / (light + 0.05) ? "rgba(0, 0, 0, .85)" : "#fff";
}

/** WCAG relative luminance of an [r, g, b] color (0 to 255). */
function luminance([r, g, b]) {
  const lin = (v) => ((v /= 255) <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4);
  return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b);
}

/**
 * Set --svs-on-color on el from the feature color. Until the browser knows
 * that color (the element is not on the page yet), try again on the next
 * frame. Returns the color, or null while it is not known.
 */
function applyTextOn(el, rerender) {
  const on = textOn(el, "var(--feature-color)");
  if (on) {
    el.style.setProperty("--svs-on-color", on);
  } else if (!el._svsRetry) {
    el._svsRetry = true;
    requestAnimationFrame(() => {
      el._svsRetry = false;
      rerender();
    });
  }
  return on;
}

const cssColor = (color) => (HA_COLORS.includes(color) ? `var(--${color}-color)` : color);

// "Default" is the subwoofer's factory settings (SVS's fourth preset slot):
// not shown unless chosen
const FACTORY_PRESET = "Default";
const defaultShown = (names) => names.filter((n) => n !== FACTORY_PRESET);

// Defaults for the usual preset names; anything else uses the theme's feature color
function presetDefaults(name) {
  const n = name.toLowerCase();
  if (n.includes("low")) return { color: "green", icon: "mdi:volume-low" };
  if (n.includes("med")) return { color: "yellow", icon: "mdi:volume-medium" };
  if (n.includes("high")) return { color: "red", icon: "mdi:volume-high" };
  return {};
}

/** The entity with this role on the same device as entityId, or undefined. */
function sibling(hass, entityId, role) {
  const entities = hass?.entities;
  const device = entities?.[entityId]?.device_id;
  if (!device) return undefined;
  for (const key of ROLES[role]) {
    const found = Object.values(entities).find(
      (e) => e.device_id === device && e.platform === DOMAIN && e.translation_key === key,
    );
    if (found) return found.entity_id;
  }
  return undefined;
}

// The list of subwoofers is sorted by name
const byLabel = (a, b) => a.localeCompare(b, undefined, { sensitivity: "base" });
const sortPairs = (pairs) => [...pairs].sort((a, b) => byLabel(a[1], b[1]));

// The card writes the Auto On standby mode as Auto (the integration's name is unchanged)
const standbyLabel = (mode) => (/^auto on$/i.test(mode ?? "") ? "Auto" : mode);

const isSvs = (hass, entityId) => hass?.entities?.[entityId]?.platform === DOMAIN;

/**
 * The subwoofer's preset, standby mode and volume, for the tile card's state
 * content. They are added as attributes of the card's entity (only for the
 * tile card inside this card), so "State content" can show them next to the
 * entity's own state. The card's own entity is left out.
 */
function subwooferAttributes(hass, entityId) {
  const extra = {};
  for (const [role, attribute] of [["preset", "preset"], ["standby", "standby_mode"], ["volume", "volume"]]) {
    const id = sibling(hass, entityId, role);
    const stateObj = id && id !== entityId ? hass.states[id] : undefined;
    if (!stateObj || unavailable(stateObj) || stateObj.state === "unknown") continue;
    const unit = stateObj.attributes.unit_of_measurement;
    extra[attribute] = unit ? `${stateObj.state} ${unit}` : role === "standby" ? standbyLabel(stateObj.state) : stateObj.state;
  }
  return extra;
}

/** hass with the card's entity carrying the subwoofer attributes (and a picture). */
function withSubwooferAttributes(hass, entityId, picture) {
  const stateObj = hass?.states[entityId];
  if (!stateObj) return hass;
  const attributes = { ...stateObj.attributes, ...subwooferAttributes(hass, entityId) };
  if (picture) attributes.entity_picture = picture;
  return { ...hass, states: { ...hass.states, [entityId]: { ...stateObj, attributes } } };
}
const unavailable = (stateObj) => !stateObj || stateObj.state === "unavailable";

const fire = (el, type, detail) =>
  el.dispatchEvent(new CustomEvent(type, { detail, bubbles: true, composed: true }));

/**
 * Keep taps on a control from reaching the cards around it, such as an
 * expander card whose header opens and closes on a tap.
 */
function keepTaps(el) {
  for (const type of ["click", "touchstart", "touchend", "mousedown", "mouseup"]) {
    el.addEventListener(type, (ev) => ev.stopPropagation());
  }
}

// ---------------------------------------------------------------------------
// Shared feature styles: Home Assistant's feature variables. On the SVS card,
// Flat and Console give each control a solid backing (--svs-feature-backing),
// and Console (the svs-console attribute) makes the buttons keys that press in.
// ---------------------------------------------------------------------------
const KEY_CSS = `
  :host([svs-console]) button {
    background-image: linear-gradient(180deg, rgba(255,255,255,.35), rgba(255,255,255,0) 45%, rgba(0,0,0,.18));
    box-shadow: inset 0 1px 0 rgba(255,255,255,.55), inset 0 -2px 2px rgba(0,0,0,.3), 0 2px 3px rgba(0,0,0,.5);
    transition: transform 120ms ease-in-out, box-shadow 120ms ease-in-out;
  }
  :host([svs-console]) button:active,
  :host([svs-console]) button[aria-pressed="true"] {
    transform: translateY(1px) scale(.96);
    background-image: linear-gradient(180deg, rgba(0,0,0,.22), rgba(0,0,0,0) 55%, rgba(255,255,255,.08));
    box-shadow: inset 0 2px 4px rgba(0,0,0,.55), inset 0 -1px 0 rgba(255,255,255,.2);
  }
`;
// A row of buttons: each tinted in its color, the active one filled
const BUTTON_ROW_CSS = `
  .row { display: flex; gap: var(--feature-button-spacing, 12px); height: var(--feature-height, 42px); }
  button {
    flex: 1 1 0; min-width: 0; height: 100%; padding: 0 4px; border: 0; cursor: pointer;
    position: relative; overflow: hidden; display: grid; place-items: center;
    border-radius: var(--feature-border-radius, 12px);
    background: var(--svs-feature-backing, var(--svs-feature-scrim, transparent));
    color: var(--svs-text, var(--primary-text-color)); font: inherit; font-size: var(--ha-font-size-s, 12px); font-weight: 500;
  }
  button::before { content: ""; position: absolute; inset: 0; background: var(--c, var(--feature-color)); opacity: .2; transition: opacity 180ms ease-in-out; }
  button:hover::before { opacity: .35; }
  button[aria-pressed="true"]::before { opacity: 1; }
  button[aria-pressed="true"] { color: var(--svs-on-color, #fff); }
  button:focus-visible { outline: 2px solid var(--c, var(--feature-color)); outline-offset: 2px; }
  button > * { position: relative; }
  /* Console: a selected key keeps the color of the others and only looks
     pressed in (a filled color would cover its 3D shading) */
  :host([svs-console]) button[aria-pressed="true"]::before { opacity: .2; }
  :host([svs-console]) button[aria-pressed="true"]:hover::before { opacity: .35; }
  :host([svs-console]) button[aria-pressed="true"] { color: var(--svs-text, var(--primary-text-color)); }
  ha-icon { --mdc-icon-size: 22px; }
  span { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  ${KEY_CSS}
`;

const FEATURE_CSS = `
  :host { display: block; }
  .control {
    position: relative; height: var(--feature-height, 42px);
    border-radius: var(--feature-border-radius, 12px); overflow: hidden;
    background: var(--svs-feature-backing, var(--svs-feature-scrim, transparent));
  }
  .tint { position: absolute; inset: 0; background: var(--c, var(--feature-color)); opacity: .2; pointer-events: none; }
  [disabled], .disabled { opacity: .5; pointer-events: none; }
`;

// ---------------------------------------------------------------------------
// Feature: preset buttons
// ---------------------------------------------------------------------------
class SvsPresetButtons extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this.shadowRoot.innerHTML = `
      <style>${FEATURE_CSS}${BUTTON_ROW_CSS}
        .cycle { gap: 6px; grid-auto-flow: column; justify-content: center; align-items: center; }
        /* Console: each key in its color at full strength, as the volume
           slider shows its colors, with text that reads on that color. The
           key's shading lies over the color, so a key still looks raised,
           and pressed in when selected. */
        :host([svs-console]) button::before,
        :host([svs-console]) button:hover::before,
        :host([svs-console]) button[aria-pressed="true"]::before,
        :host([svs-console]) button[aria-pressed="true"]:hover::before { opacity: 1; }
        :host([svs-console]) button,
        :host([svs-console]) button[aria-pressed="true"] { color: var(--svs-on-color, #fff); background-image: none; }
        :host([svs-console]) button::after {
          content: ""; position: absolute; inset: 0; border-radius: inherit; pointer-events: none;
          background: linear-gradient(180deg, rgba(255,255,255,.35), rgba(255,255,255,0) 45%, rgba(0,0,0,.18));
        }
        :host([svs-console]) button:active::after,
        :host([svs-console]) button[aria-pressed="true"]::after {
          background: linear-gradient(180deg, rgba(0,0,0,.22), rgba(0,0,0,0) 55%, rgba(255,255,255,.08));
        }
        :host([svs-console]) button > * { z-index: 1; }
      </style>
      <div class="row" role="group" aria-label="Preset"></div>`;
    this._row = this.shadowRoot.querySelector(".row");
    keepTaps(this);
  }

  static getStubConfig() {
    return { type: "custom:svs-subwoofer-presets" };
  }

  static getConfigElement() {
    return document.createElement("svs-subwoofer-presets-editor");
  }

  setConfig(config) {
    if (!config) throw new Error("Invalid configuration");
    this._config = config;
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    this._render();
  }

  set context(context) {
    this._context = context;
    this._render();
  }

  get _entity() {
    return sibling(this._hass, this._context?.entity_id, "preset");
  }

  _render() {
    if (!this._hass || !this._config || !this._context) return;
    const entity = this._entity;
    const stateObj = entity ? this._hass.states[entity] : undefined;
    // The subwoofer's own preset order (its slots) until the user reorders them
    const names = (stateObj?.attributes.options ?? []).filter((n) => !NOT_PRESETS.includes(n));
    const show = Array.isArray(this._config.presets_shown) ? this._config.presets_shown : null;
    const shown = show ? show.filter((n) => names.includes(n)) : defaultShown(names);
    const cycle = this._config.style === "presets_cycle";
    const on = applyTextOn(this, () => {
      this._key = undefined;
      this._render();
    });
    const key = JSON.stringify([shown, stateObj?.state, this._config.presets, unavailable(stateObj), cycle, on]);
    if (key === this._key) return;
    this._key = key;
    this._row.classList.toggle("disabled", unavailable(stateObj));
    if (cycle) {
      this._row.replaceChildren(this._cycleButton(entity, stateObj, shown));
      return;
    }
    this._row.replaceChildren(...shown.map((name) => {
      const own = this._config.presets?.[name] ?? {};
      const look = { ...presetDefaults(name), ...own };
      const button = document.createElement("button");
      button.type = "button";
      button.title = name;
      button.setAttribute("aria-label", name);
      button.setAttribute("aria-pressed", String(stateObj?.state === name));
      if (look.color) {
        button.style.setProperty("--c", cssColor(look.color));
        const fg = textOn(this, cssColor(look.color));
        if (fg) button.style.setProperty("--svs-on-color", fg);
      }
      if (look.icon) {
        const icon = document.createElement("ha-icon");
        icon.icon = look.icon;
        icon.setAttribute("icon", look.icon);
        button.append(icon);
      } else {
        const label = document.createElement("span");
        label.textContent = name;
        button.append(label);
      }
      button.addEventListener("click", (ev) => {
        ev.stopPropagation();
        // Always sent, even for the preset that is already shown: loading it
        // again puts the subwoofer back to that preset's settings
        this._hass.callService("select", "select_option", { entity_id: entity, option: name });
      });
      return button;
    }));
  }

  /**
   * One button showing the active preset; each tap loads the next one, in the
   * order shown. From Manual (or an unknown preset) it loads the first.
   */
  _cycleButton(entity, stateObj, shown) {
    const current = stateObj?.state;
    const active = shown.includes(current);
    const look = active ? { ...presetDefaults(current), ...(this._config.presets?.[current] ?? {}) } : {};
    const button = document.createElement("button");
    button.type = "button";
    button.className = "cycle";
    const next = shown.length ? shown[(shown.indexOf(current) + 1) % shown.length] : undefined;
    button.title = next ? `Load ${next}` : "";
    button.setAttribute("aria-label", `Preset: ${current ?? "unknown"}${next ? `. Select to load ${next}` : ""}`);
    button.setAttribute("aria-pressed", String(active));
    if (look.color) {
      button.style.setProperty("--c", cssColor(look.color));
      const fg = textOn(this, cssColor(look.color));
      if (fg) button.style.setProperty("--svs-on-color", fg);
    }
    if (look.icon) {
      const icon = document.createElement("ha-icon");
      icon.icon = look.icon;
      icon.setAttribute("icon", look.icon);
      button.append(icon);
    }
    const label = document.createElement("span");
    label.textContent = current && current !== "unknown" ? current : "Preset";
    button.append(label);
    button.addEventListener("click", (ev) => {
      ev.stopPropagation();
      if (next) this._hass.callService("select", "select_option", { entity_id: entity, option: next });
    });
    return button;
  }
}

class SvsPresetButtonsEditor extends HTMLElement {
  set hass(hass) {
    this._hass = hass;
    this._render();
  }

  set context(context) {
    this._context = context;
    this._render();
  }

  setConfig(config) {
    this._config = config;
    this._render();
  }

  _render() {
    if (!this._hass || !this._config) return;
    if (!this._form) {
      this._form = document.createElement("ha-form");
      this._form.computeLabel = (s) => s.label ?? s.name;
      this._form.addEventListener("value-changed", (ev) => {
        ev.stopPropagation();
        const value = ev.detail.value;
        const presets = {};
        for (const name of value.presets_shown ?? defaultShown(this._names())) {
          const color = value[`color_${name}`], icon = value[`icon_${name}`];
          if (color || icon) presets[name] = { ...(color ? { color } : {}), ...(icon ? { icon } : {}) };
        }
        const config = { type: this._config.type, style: value.style === "presets_cycle" ? "presets_cycle" : "presets_buttons", presets };
        // Kept only when it differs from the default (every preset, in slot order)
        if (Array.isArray(value.presets_shown) && JSON.stringify(value.presets_shown) !== JSON.stringify(defaultShown(this._names()))) {
          config.presets_shown = value.presets_shown;
        }
        this._config = config;
        fire(this, "config-changed", { config });
      });
      this.append(this._form);
    }
    const names = this._names();
    const shownNames = (this._config.presets_shown ?? defaultShown(names)).filter((n) => names.includes(n));
    this._form.hass = this._hass;
    this._form.schema = [
      {
        name: "presets_shown", label: "Presets",
        helper: "Default is the subwoofer's factory settings (SVS's fourth preset); it is shown only if you add it.",
        selector: { select: { multiple: true, reorder: true, mode: "dropdown", options: names } },
      },
      {
        name: "style", label: "Style",
        selector: { select: { mode: "dropdown", options: [
          { value: "presets_buttons", label: "Buttons" },
          { value: "presets_cycle", label: "Cycle button" },
        ] } },
      },
      ...shownNames.map((name) => ({
        type: "grid", name: "", schema: [
          { name: `color_${name}`, label: `${name} color`, selector: { ui_color: {} } },
          { name: `icon_${name}`, label: `${name} icon`, selector: { icon: {} } },
        ],
      })),
    ];
    const data = { style: this._config.style === "presets_cycle" ? "presets_cycle" : "presets_buttons", presets_shown: shownNames };
    for (const name of shownNames) {
      const look = { ...presetDefaults(name), ...(this._config.presets?.[name] ?? {}) };
      data[`color_${name}`] = look.color;
      data[`icon_${name}`] = look.icon;
    }
    this._form.data = data;
  }

  _names() {
    const entity = sibling(this._hass, this._context?.entity_id, "preset");
    const options = entity ? this._hass.states[entity]?.attributes.options ?? [] : [];
    return options.filter((n) => !NOT_PRESETS.includes(n));
  }
}

// ---------------------------------------------------------------------------
// Feature: volume slider, optionally colored by volume thresholds
// ---------------------------------------------------------------------------

/**
 * The slider's range: the entity's own range (-60 to 0 dB), or the part of it
 * chosen in the feature (min and max), so the volumes actually used get the
 * whole width of the slider.
 */
function sliderRange(config, stateObj) {
  const a = stateObj?.attributes ?? {};
  const lo = a.min ?? -60, hi = a.max ?? 0;
  const clamp = (v, d) => (Number.isFinite(v) ? Math.max(lo, Math.min(hi, v)) : d);
  let min = clamp(config?.min, lo), max = clamp(config?.max, hi);
  if (min > max) [min, max] = [max, min];
  if (min === max) [min, max] = [lo, hi];
  return { min, max, step: a.step ?? 1 };
}

/** The volume thresholds, lowest first: [{below, color}, ..., {color}]. */
function colorRanges(config) {
  const ranges = Array.isArray(config?.volume_thresholds) ? config.volume_thresholds : [];
  const bounded = ranges.filter((r) => typeof r?.below === "number").sort((a, b) => a.below - b.below);
  const rest = ranges.find((r) => r && typeof r.below !== "number");
  return rest ? [...bounded, rest] : bounded;
}

function rangeColor(ranges, value) {
  for (const range of ranges) {
    if (typeof range.below !== "number" || value < range.below) return range.color;
  }
  return undefined;
}

class SvsVolume extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this.shadowRoot.innerHTML = `
      <style>${FEATURE_CSS}
        :host { position: relative; }
        .control { cursor: pointer; touch-action: none; outline: none; user-select: none; -webkit-user-select: none; }
        /* The value callout above the slider while it moves, as on Home
           Assistant's own sliders; outside the control, which clips */
        .tooltip {
          pointer-events: none; user-select: none; position: absolute; z-index: 3;
          top: -4px; left: calc(min(max(var(--svs-tip, 0) * 100%, 0%), 100%));
          transform: translate3d(-50%, -100%, 0);
          background-color: var(--svs-tip-background, var(--clear-background-color)); color: var(--svs-text, var(--primary-text-color));
          font-size: var(--control-slider-tooltip-font-size, var(--ha-font-size-m, 14px));
          border-radius: var(--ha-border-radius-lg, 12px); padding: .2em .4em;
          opacity: 0; white-space: nowrap; box-shadow: 0 2px 5px rgba(0, 0, 0, .2);
          transition: opacity 180ms ease-in-out, left 180ms ease-in-out;
        }
        .tooltip.visible { opacity: 1; }
        .control:focus-visible { box-shadow: 0 0 0 2px var(--fill, var(--feature-color)); }
        .zones { position: absolute; inset: 0; display: flex; }
        .zones i { display: block; height: 100%; opacity: .2; }
        .control:not(.ranged) .zones { background: var(--feature-color); opacity: .2; }
        .fill { position: absolute; inset: 0 auto 0 0; background: var(--fill, var(--feature-color)); }
        .tick { position: absolute; top: 25%; bottom: 25%; width: 2px; margin-left: -1px; border-radius: 1px; background: var(--primary-text-color); opacity: .35; }
        .handle { position: absolute; top: 25%; bottom: 25%; width: 4px; margin-left: -10px; border-radius: 2px; background: #fff; box-shadow: 0 0 2px rgba(0, 0, 0, .45); }
        /* Console: no bar, so the whole range stays visible. A round loupe in a
           beveled bezel of the subwoofer's finish (--svs-bezel, set by the
           card) magnifies the color the volume is set at, as on The Lampster
           card's color temperature slider. */
        .loupe { display: none; }
        :host([svs-console]) .fill, :host([svs-console]) .handle { display: none; }
        :host([svs-console]) .zones i { opacity: 1; }
        :host([svs-console]) .loupe {
          --size: calc(var(--feature-height, 42px) - 4px);
          --bezel: var(--svs-bezel, var(--card-background-color, #c3c8cc));
          display: block; position: absolute; top: 50%; width: var(--size); height: var(--size);
          left: clamp(calc(var(--size) / 2 + 2px), var(--at), calc(100% - var(--size) / 2 - 2px));
          transform: translate(-50%, -50%); border-radius: 50%; pointer-events: none;
          background: conic-gradient(from 210deg,
            color-mix(in srgb, var(--bezel), #fff 45%), color-mix(in srgb, var(--bezel), #000 45%) 25%,
            color-mix(in srgb, var(--bezel), #fff 20%) 45%, color-mix(in srgb, var(--bezel), #000 50%) 65%,
            color-mix(in srgb, var(--bezel), #fff 45%) 85%, var(--bezel));
          box-shadow: 0 0 3px rgba(0,0,0,.55), inset 0 1px 0 rgba(255,255,255,.6), inset 0 -1px 0 rgba(0,0,0,.35);
        }
        :host([svs-console]) .loupe::after {
          content: ""; position: absolute; inset: 4px; border-radius: 50%;
          background:
            radial-gradient(70% 55% at 32% 25%, rgba(255,255,255,.75), rgba(255,255,255,0) 60%),
            radial-gradient(circle, rgba(0,0,0,0) 60%, rgba(0,0,0,.18)),
            var(--loupe);
          box-shadow: inset 0 0 3px rgba(0,0,0,.5);
        }
      </style>
      <div class="control" role="slider" tabindex="0" aria-label="Volume">
        <div class="zones"></div><div class="fill"></div><div class="ticks"></div><div class="handle"></div><div class="loupe"></div>
      </div>
      <span class="tooltip" aria-hidden="true"></span>`;
    this._control = this.shadowRoot.querySelector(".control");
    this._tooltip = this.shadowRoot.querySelector(".tooltip");
    this._control.addEventListener("pointerdown", (ev) => this._down(ev));
    this._control.addEventListener("pointermove", (ev) => this._move(ev));
    this._control.addEventListener("pointerup", (ev) => this._up(ev));
    // A cancelled drag reports no position (0), which is the slider's left
    // end: it ends at the last position the drag reached instead
    this._control.addEventListener("pointercancel", () => this._up());
    this._control.addEventListener("lostpointercapture", () => this._up());
    this._control.addEventListener("keydown", (ev) => this._keyDown(ev));
    this._control.addEventListener("keyup", () => this._keyUp());
    keepTaps(this);
  }

  static getStubConfig() {
    return { type: "custom:svs-subwoofer-volume" };
  }

  static getConfigElement() {
    return document.createElement("svs-subwoofer-volume-editor");
  }

  setConfig(config) {
    if (!config) throw new Error("Invalid configuration");
    this._config = config;
    this._ranges = colorRanges(config);
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    this._render();
  }

  set context(context) {
    this._context = context;
    this._render();
  }

  get _entity() {
    return sibling(this._hass, this._context?.entity_id, "volume");
  }

  get _limits() {
    return sliderRange(this._config, this._hass?.states[this._entity]);
  }

  _render() {
    if (!this._hass || !this._config || !this._context) return;
    const stateObj = this._hass.states[this._entity];
    const { min, max } = this._limits;
    const reported = Number(stateObj?.state);
    // A value just sent stays shown until the subwoofer reports it (or for
    // 4 seconds), so the slider does not jump back while the command runs
    if (this._pending !== undefined && (reported === this._pending || Date.now() > this._pendingUntil)) {
      this._pending = undefined;
    }
    const value = this._dragging ?? this._pending ?? reported;
    const known = Number.isFinite(value);
    const at = (v) => ((v - min) / (max - min)) * 100;
    const pct = known ? Math.max(0, Math.min(100, at(value))) : 0;
    const ranged = this._ranges.length > 0;
    const key = JSON.stringify([pct, ranged, this._ranges, unavailable(stateObj)]);
    if (key === this._key) return;
    this._key = key;
    const c = this._control;
    c.classList.toggle("ranged", ranged);
    c.classList.toggle("disabled", unavailable(stateObj));
    c.setAttribute("aria-valuemin", min);
    c.setAttribute("aria-valuemax", max);
    if (known) c.setAttribute("aria-valuenow", value);
    const zones = c.querySelector(".zones"), ticks = c.querySelector(".ticks");
    zones.replaceChildren();
    ticks.replaceChildren();
    if (ranged) {
      let from = min;
      for (const range of this._ranges) {
        const to = typeof range.below === "number" ? Math.max(min, Math.min(max, range.below)) : max;
        const zone = document.createElement("i");
        zone.style.width = `${Math.max(0, at(to) - at(from))}%`;
        zone.style.background = cssColor(range.color ?? "primary");
        zones.append(zone);
        if (to < max && to > min) {
          const tick = document.createElement("div");
          tick.className = "tick";
          tick.style.left = `${at(to)}%`;
          ticks.append(tick);
        }
        from = to;
      }
    }
    const color = ranged && known ? rangeColor(this._ranges, value) : undefined;
    c.style.setProperty("--fill", color ? cssColor(color) : "var(--feature-color)");
    c.querySelector(".fill").style.width = `${pct}%`;
    const handle = c.querySelector(".handle");
    handle.style.left = `${pct}%`;
    handle.style.display = known ? "" : "none";
    // The loupe shows the color it is on, at full strength: the volume's
    // threshold color, or the feature color without thresholds
    c.style.setProperty("--at", `${pct}%`);
    this.style.setProperty("--svs-tip", String(pct / 100));
    if (known) {
      const unit = stateObj?.attributes.unit_of_measurement;
      this._tooltip.textContent = unit ? `${value} ${unit}` : String(value);
    }
    c.style.setProperty("--loupe", color ? cssColor(color) : "var(--feature-color)");
    c.querySelector(".loupe").style.visibility = known ? "" : "hidden";
  }

  _valueAt(ev) {
    const { min, max, step } = this._limits;
    const rect = this._control.getBoundingClientRect();
    const f = Math.max(0, Math.min(1, (ev.clientX - rect.left) / rect.width));
    return Math.round((min + f * (max - min)) / step) * step;
  }

  _down(ev) {
    ev.stopPropagation();
    // No text selection, and no native drag of one, which would cancel this drag
    ev.preventDefault();
    this._control.focus({ preventScroll: true });
    this._control.setPointerCapture(ev.pointerId);
    this._dragging = this._valueAt(ev);
    this._moved(true);
  }

  _move(ev) {
    if (this._dragging === undefined) return;
    this._dragging = this._valueAt(ev);
    this._moved(true);
  }

  _up(ev) {
    if (this._dragging === undefined) return;
    const value = ev ? this._valueAt(ev) : this._dragging;
    this._dragging = undefined;
    this._send(value);
    this._moved(false, value);
  }

  // Shown while the slider moves; after keys, it stays a moment
  _showTooltip(visible, delay = 0) {
    clearTimeout(this._tooltipTimer);
    if (visible || !delay) this._tooltip.classList.toggle("visible", visible);
    else this._tooltipTimer = setTimeout(() => this._tooltip.classList.remove("visible"), delay);
  }

  _keyDown(ev) {
    const { min, max, step } = this._limits;
    const delta = { ArrowRight: step, ArrowUp: step, ArrowLeft: -step, ArrowDown: -step, PageUp: 5 * step, PageDown: -5 * step }[ev.key];
    if (delta === undefined) return;
    ev.preventDefault();
    const current = this._dragging ?? Number(this._hass.states[this._entity]?.state);
    if (!Number.isFinite(current)) return;
    this._dragging = Math.max(min, Math.min(max, current + delta));
    this._moved(true);
    clearTimeout(this._keyTimer);
    this._keyTimer = setTimeout(() => this._keyUp(), 600);
  }

  _keyUp() {
    if (this._dragging === undefined) return;
    const value = this._dragging;
    this._dragging = undefined;
    clearTimeout(this._keyTimer);
    this._send(value);
    this._moved(false, value);
    this._tooltip.classList.add("visible");
    this._showTooltip(false, 500);
  }

  // Tells the SVS card the slider is moving, so its driver can shake
  _moved(active, value = this._dragging) {
    this._key = undefined;
    this._render();
    this._showTooltip(active);
    const { min, max } = this._limits;
    const color = this._ranges.length ? rangeColor(this._ranges, value) : undefined;
    fire(this, "svs-volume-input", { active, level: (value - min) / (max - min), color });
  }

  _send(value) {
    this._pending = value;
    this._pendingUntil = Date.now() + 4000;
    clearTimeout(this._pendingTimer);
    this._pendingTimer = setTimeout(() => {
      this._key = undefined;
      this._render();
    }, 4100);
    this._hass.callService("number", "set_value", { entity_id: this._entity, value });
  }
}

/**
 * The panel's volume feature whose settings are being opened: a row's, which
 * can copy the main subwoofer's (volume), or the main subwoofer's, which can
 * be copied to every row (copyTo). Home Assistant's editor dialog opens a
 * feature's settings itself (not inside the panel's editor), so the panel
 * editor notes here which feature it is, and the volume settings editor
 * opened for that feature offers the copy.
 */
let panelVolume = null;

class SvsVolumeEditor extends HTMLElement {
  set hass(hass) {
    this._hass = hass;
    if (this._form) this._form.hass = hass;
  }

  setConfig(config) {
    // The configuration this editor just sent comes back here: the fields
    // already show it (an emptied field included), so they are left alone
    const echo = this._config && JSON.stringify(config) === JSON.stringify(this._config);
    // Opened for a panel row's volume feature: it can copy the main subwoofer's
    if (this._panel === undefined) this._panel = panelVolume?.key === JSON.stringify(config) ? panelVolume : null;
    this._config = config;
    if (!echo || !this._form) this._render();
  }

  _render() {
    if (!this._form) {
      this.innerHTML = `<style>.note { color: var(--secondary-text-color); font-size: var(--ha-font-size-s, 12px); margin-top: 8px; min-height: 1em; }</style>`;
      this._form = document.createElement("ha-form");
      this._form.computeLabel = (s) => s.label ?? s.name;
      this._form.computeHelper = (s) => s.helper;
      this._form.addEventListener("value-changed", (ev) => this._changed(ev));
      this._note = document.createElement("div");
      this._note.className = "note";
      this._note.setAttribute("role", "status");
      this._copy = document.createElement("ha-button");
      this._copy.addEventListener("click", () => this._copyClicked());
      this.append(this._copy, this._form, this._note);
    }
    this._renderCopy();
    if (this._hass) this._form.hass = this._hass;
    const ranges = colorRanges(this._config);
    const on = ranges.length > 0;
    const db = { number: { mode: "box", step: 1, min: -60, max: 0, unit_of_measurement: "dB" } };
    this._form.schema = [
      {
        type: "grid", name: "", schema: [
          { name: "min", label: "Slider from", selector: db },
          { name: "max", label: "Slider to", selector: db },
        ],
      },
      {
        name: "colored", label: "Volume thresholds",
        helper: "Split the slider into three volume ranges, each with its own color.",
        selector: { boolean: {} },
      },
      ...(on ? [
        { type: "grid", name: "", schema: [
          { name: "color_1", label: "Quietest color", selector: { ui_color: {} } },
          { name: "split_1", label: "Up to (dB)", selector: { number: { mode: "box", step: 1, min: -60, max: 0 } } },
        ] },
        { type: "grid", name: "", schema: [
          { name: "color_2", label: "Middle color", selector: { ui_color: {} } },
          { name: "split_2", label: "Up to (dB)", selector: { number: { mode: "box", step: 1, min: -60, max: 0 } } },
        ] },
        { name: "color_3", label: "Loudest color", selector: { ui_color: {} } },
      ] : []),
    ];
    const range = { min: this._config.min ?? -60, max: this._config.max ?? 0 };
    this._form.data = on
      ? {
        ...range,
        colored: true,
        color_1: ranges[0]?.color, split_1: ranges[0]?.below,
        color_2: ranges[1]?.color, split_2: ranges[1]?.below,
        color_3: ranges[2]?.color,
      }
      : { ...range, colored: false };
  }

  // Copy from main: on a panel row's volume, when the main subwoofer has one.
  // Copy to members: on the main subwoofer's volume, when the panel has rows.
  _renderCopy() {
    const toMembers = !!this._panel?.copyTo && this._panel.members() > 0;
    const fromMain = !!this._panel?.volume?.();
    this._copy.textContent = toMembers ? "Copy to members" : "Copy from main";
    this._copy.style.display = toMembers || fromMain ? "" : "none";
  }

  _copyClicked() {
    // The main subwoofer's range and thresholds go to every row
    if (this._panel?.copyTo) {
      this._panel.copyTo(JSON.parse(JSON.stringify(this._config)));
      this._note.textContent = "Copied to every subwoofer in the collapsible section.";
      return;
    }
    // The main subwoofer's range and thresholds replace this row's
    const volume = this._panel?.volume?.();
    if (!volume) return;
    this._config = { ...JSON.parse(JSON.stringify(volume)), type: this._config.type };
    this._note.textContent = "";
    this._render();
    fire(this, "config-changed", { config: this._config });
  }

  _changed(ev) {
    ev.stopPropagation();
    const v = ev.detail.value;
    this._note.textContent = "";
    // An emptied field stays empty while the user types; the saved
    // configuration keeps the previous value (or the default) until then
    const previousRanges = colorRanges(this._config);
    const keep = (value, fallback) => (Number.isFinite(value) ? value : fallback);
    let config = { type: this._config.type };
    // The range is kept only when it differs from the full -60 to 0 dB; ends
    // entered the other way round are swapped
    let min = keep(v.min, this._config.min ?? -60), max = keep(v.max, this._config.max ?? 0);
    if (min > max) {
      [min, max] = [max, min];
      this._note.textContent = "Slider from and Slider to were the other way round, so they were swapped.";
    }
    if (min === max) {
      this._note.textContent = "Slider from and Slider to are the same, so the slider uses the full range.";
    } else {
      if (min !== -60) config.min = min;
      if (max !== 0) config.max = max;
    }
    if (v.colored) {
      let a = keep(v.split_1, previousRanges[0]?.below ?? -30);
      let b = keep(v.split_2, previousRanges[1]?.below ?? -15);
      let c1 = v.color_1 ?? "green", c3 = v.color_3 ?? "red";
      // Splits entered the other way round are put back in order, and the
      // outer colors move with them, so each color stays on the volumes meant
      if (a > b) {
        [a, b] = [b, a];
        [c1, c3] = [c3, c1];
        this._note.textContent = "The two threshold volumes were the other way round, so they were swapped, and the quietest and loudest colors moved with them.";
      } else if (a === b) {
        this._note.textContent = "Both threshold volumes are the same, so the middle color is not used.";
      }
      config.volume_thresholds = [
        { below: a, color: c1 },
        { below: b, color: v.color_2 ?? "yellow" },
        { color: c3 },
      ];
    }
    const toggled = !!v.colored !== previousRanges.length > 0;
    this._config = config;
    if (toggled) {
      this._render();
    } else {
      // Keep what is in the fields (an emptied field included)
      this._form.data = v;
    }
    fire(this, "config-changed", { config });
  }
}

// ---------------------------------------------------------------------------
// Feature: standby mode
// ---------------------------------------------------------------------------
class SvsStandby extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    // The same buttons as the presets, in the feature color; the selected
    // mode's text is dark or white to read on that color
    this.shadowRoot.innerHTML = `
      <style>${FEATURE_CSS}${BUTTON_ROW_CSS}</style>
      <div class="row" role="group" aria-label="Standby mode"></div>`;
    this._row = this.shadowRoot.querySelector(".row");
    keepTaps(this);
  }

  static getStubConfig() {
    return { type: "custom:svs-subwoofer-standby" };
  }

  setConfig(config) {
    if (!config) throw new Error("Invalid configuration");
    this._config = config;
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    this._render();
  }

  set context(context) {
    this._context = context;
    this._render();
  }

  _render() {
    if (!this._hass || !this._config || !this._context) return;
    const entity = sibling(this._hass, this._context.entity_id, "standby");
    const stateObj = entity ? this._hass.states[entity] : undefined;
    const options = (stateObj?.attributes.options ?? []).filter((o) => !NOT_PRESETS.includes(o));
    const on = applyTextOn(this, () => {
      this._key = undefined;
      this._render();
    });
    const key = JSON.stringify([options, stateObj?.state, unavailable(stateObj), on]);
    if (key === this._key) return;
    this._key = key;
    this._row.classList.toggle("disabled", unavailable(stateObj));
    this._row.replaceChildren(...options.map((option) => {
      const button = document.createElement("button");
      button.type = "button";
      const label = document.createElement("span");
      label.textContent = standbyLabel(option);
      button.append(label);
      button.setAttribute("aria-pressed", String(stateObj.state === option));
      button.addEventListener("click", (ev) => {
        ev.stopPropagation();
        this._hass.callService("select", "select_option", { entity_id: entity, option });
      });
      return button;
    }));
  }
}

// ---------------------------------------------------------------------------
// Finishes, drawn on a canvas behind the card
// ---------------------------------------------------------------------------
const FINISHES = [
  ["none", "None (theme)"],
  ["black_ash", "Premium Black Ash"],
  ["black_oak", "Black Oak Real Wood Veneer"],
  ["gloss_black", "Piano Gloss Black"],
  ["gloss_white", "Piano Gloss White"],
  ["fabric", "Fabric"],
  ["grille", "Grille"],
];
const WOOD = ["black_ash", "black_oak"];
const finishTone = (finish) => (finish === "gloss_white" ? "light" : finish === "none" ? null : "dark");
// The solid backing behind each feature control on a finish
const BACKING = { dark: "#1e1f22", light: "#eceef1" };
const DEFAULT_PATTERN = 4242;
// Each finish's color for the volume loupe's bezel
const BEZEL = {
  black_ash: "#24211f", black_oak: "#1f1b17", gloss_black: "#101113",
  gloss_white: "#f3f4f6", fabric: "#1b1c1e", grille: "#2c2e33",
};

function rng(seed) {
  let s = seed >>> 0;
  return () => (s = (s * 1664525 + 1013904223) >>> 0) / 4294967296;
}

function valueNoise(seed) {
  const R = rng(seed), perm = new Uint8Array(512), vals = new Float32Array(256);
  for (let i = 0; i < 256; i++) { perm[i] = i; vals[i] = R(); }
  for (let i = 255; i > 0; i--) { const j = Math.floor(R() * (i + 1)); [perm[i], perm[j]] = [perm[j], perm[i]]; }
  for (let i = 0; i < 256; i++) perm[i + 256] = perm[i];
  const sm = (t) => t * t * (3 - 2 * t);
  const n2 = (x, y) => {
    let xi = Math.floor(x), yi = Math.floor(y);
    const xf = x - xi, yf = y - yi;
    xi &= 255; yi &= 255;
    const a = vals[perm[perm[xi] + yi]], b = vals[perm[perm[xi + 1] + yi]];
    const c = vals[perm[perm[xi] + yi + 1]], d = vals[perm[perm[xi + 1] + yi + 1]];
    const u = sm(xf), v = sm(yf);
    return a + (b - a) * u + (c - a) * v + (a - b - c + d) * u * v;
  };
  return (x, y, octaves) => {
    let sum = 0, amp = .5, f = 1, norm = 0;
    for (let k = 0; k < octaves; k++) { sum += n2(x * f, y * f) * amp; norm += amp; amp *= .5; f *= 2.03; }
    return sum / norm;
  };
}

/**
 * Draw a finish. Wood runs vertically or horizontally (a couple of degrees of
 * tilt at most) at a zoom from the pattern; gloss reflections fall at any angle.
 */
function drawFinish(ctx, finish, pattern, w, h) {
  const r = rng(pattern * 31 + 7);
  const wood = WOOD.includes(finish);
  const angle = wood ? (r() < .5 ? 0 : Math.PI / 2) + (r() - .5) * .07 : r() * Math.PI;
  const zoom = wood ? .6 + r() * 1.1 : 1;
  const D = Math.ceil(Math.sqrt(w * w + h * h) / Math.min(zoom, 1)) + 20;
  const half = D / 2;
  if (finish === "fabric" || finish === "grille") {
    const img = ctx.createImageData(w, h);
    (finish === "fabric" ? drawFabric : drawGrille)(img.data, w, h, pattern);
    ctx.putImageData(img, 0, 0);
    return;
  }
  if (finish === "black_ash") {
    // Wide, wavy grey bands with a rough, porous texture on black, pinching
    // together and swirling into long ovals: the contour rings of a warped
    // noise field, stretched along the grain
    const img = ctx.createImageData(w, h), px = img.data;
    const noise = valueNoise(pattern * 7 + 1);
    const ca = Math.cos(angle), sa = Math.sin(angle);
    const period = 21 + r() * 6, warp = 3 + r() * 1.2, share = .46 + r() * .08;
    for (let y = 0; y < h; y++) {
      for (let x = 0; x < w; x++) {
        const dx = x - w / 2, dy = y - h / 2;
        const u = (dx * ca + dy * sa) / zoom, v = (-dx * sa + dy * ca) / zoom;
        const t = u / period + noise(u * .008, v * .0045, 3) * warp;
        const ring = t - Math.floor(t);
        const width = share + (noise(u * .02 + 40, v * .007, 2) - .5) * .6;
        const pore = noise(u * .7 + 90, v * .05, 2);
        let tone;
        if (ring - width + (pore - .5) * .45 < 0) {
          tone = 74 + (pore - .5) * 60 + (noise(u * .9 + 7, v * .25, 1) - .5) * 30;
          if (pore < .3) tone -= 32;
        } else {
          tone = 20 + (pore - .5) * 10;
        }
        tone = Math.max(10, Math.min(120, tone));
        const o = (y * w + x) * 4;
        px[o] = tone; px[o + 1] = tone; px[o + 2] = tone + 3; px[o + 3] = 255;
      }
    }
    ctx.putImageData(img, 0, 0);
    const lx = r() * w, g = ctx.createRadialGradient(lx, 0, 0, lx, 0, Math.max(w, h) * 1.1);
    g.addColorStop(0, "rgba(255,255,255,.07)");
    g.addColorStop(1, "rgba(0,0,0,.22)");
    ctx.fillStyle = g;
    ctx.fillRect(0, 0, w, h);
  } else if (finish === "black_oak") {
    // Matte near-black with fine, low-contrast straight grain and open pores
    ctx.fillStyle = "#151516";
    ctx.fillRect(0, 0, w, h);
    ctx.save();
    ctx.translate(w / 2, h / 2);
    ctx.rotate(angle);
    ctx.scale(zoom, zoom);
    const drift = (r() - .5) * .04;
    for (let j = 0; j < D / 1.4; j++) {
      const gx = -half + r() * D;
      ctx.beginPath();
      ctx.moveTo(gx, -half);
      ctx.quadraticCurveTo(gx + (r() - .5) * 3 + drift * D, 0, gx + drift * D * 2, half);
      ctx.strokeStyle = `rgba(92,92,96,${(.05 + r() * .12).toFixed(3)})`;
      ctx.lineWidth = .3 + r() * .9;
      ctx.stroke();
    }
    if (r() < .7) {
      const cx = (r() - .5) * D * .5, top = -half * (.1 + r() * .6);
      for (let k = 0; k < 14; k++) {
        const sp = 8 + k * (6 + r() * 3);
        ctx.beginPath();
        ctx.moveTo(cx - sp, half);
        ctx.quadraticCurveTo(cx - sp * .55, top + k * 9, cx, top + k * 9 - 6);
        ctx.quadraticCurveTo(cx + sp * .55, top + k * 9, cx + sp, half);
        ctx.strokeStyle = `rgba(96,94,92,${(.04 + r() * .05).toFixed(3)})`;
        ctx.lineWidth = .6 + r() * .8;
        ctx.stroke();
      }
    }
    for (let p = 0; p < D * 2.5; p++) {
      ctx.fillStyle = r() < .5 ? "rgba(0,0,0,.5)" : "rgba(110,110,114,.12)";
      ctx.fillRect(-half + r() * D, -half + r() * D, .6, 1.5 + r() * 4);
    }
    ctx.restore();
    const g = ctx.createLinearGradient(0, 0, 0, h);
    g.addColorStop(0, "rgba(255,255,255,.03)");
    g.addColorStop(1, "rgba(0,0,0,.18)");
    ctx.fillStyle = g;
    ctx.fillRect(0, 0, w, h);
  } else {
    const dark = finish === "gloss_black";
    const g = ctx.createLinearGradient(0, 0, w, h);
    g.addColorStop(0, dark ? "#22252b" : "#fbfbfc");
    g.addColorStop(1, dark ? "#060708" : "#d8dbe0");
    ctx.fillStyle = g;
    ctx.fillRect(0, 0, w, h);
    ctx.save();
    ctx.translate(w / 2, h / 2);
    ctx.rotate(angle);
    const n = 2 + Math.floor(r() * 3);
    for (let s = 0; s < n; s++) {
      const x = -half + r() * D, wd = 18 + r() * 110, peak = dark ? .05 + r() * .1 : .5 + r() * .4;
      const sg = ctx.createLinearGradient(x, 0, x + wd, 0);
      sg.addColorStop(0, "rgba(255,255,255,0)");
      sg.addColorStop(.5, `rgba(255,255,255,${peak.toFixed(3)})`);
      sg.addColorStop(1, "rgba(255,255,255,0)");
      ctx.fillStyle = sg;
      ctx.fillRect(x, -half, wd, D);
    }
    ctx.restore();
  }
}

/**
 * Speaker fabric: a near-black fine knit (two crossing fine weaves and a
 * speckle), with a very subdued sheen whose angle and place come from the
 * pattern.
 */
function drawFabric(px, w, h, pattern) {
  const r = rng(pattern * 31 + 7), noise = valueNoise(pattern * 7 + 3);
  const angle = r() * Math.PI, ca = Math.cos(angle), sa = Math.sin(angle);
  const cx = r() * w, cy = r() * h, reach = Math.max(w, h) * (.7 + r() * .6);
  for (let y = 0; y < h; y++) {
    for (let x = 0; x < w; x++) {
      const k1 = Math.sin((x + y) * 1.9 + noise(x * .35, y * .35, 1) * 3) * .5 + .5;
      const k2 = Math.sin((x - y) * 1.7 + noise(x * .3 + 50, y * .3, 1) * 3) * .5 + .5;
      const speck = noise(x * .7 + 20, y * .7, 2);
      const d = ((x - cx) * ca + (y - cy) * sa) / reach;
      const t = 33 + (k1 * k2 - .25) * 10 + (speck - .5) * 17 + (noise(x * .02, y * .02, 2) - .5) * 5 + Math.max(0, 1 - d * d) * 4;
      const o = (y * w + x) * 4;
      px[o] = t; px[o + 1] = t; px[o + 2] = t + 2; px[o + 3] = 255;
    }
  }
}

/**
 * A perforated metal speaker grille: hexagonal holes with a vertex straight
 * up and down, dark behind them, in a brushed metal web. The web carries a
 * strong reflection band and each hole's rim catches the light on one side,
 * so the grille stands out; the reflection's angle and place come from the
 * pattern.
 */
function drawGrille(px, w, h, pattern) {
  const r = rng(pattern * 31 + 7), noise = valueNoise(pattern * 7 + 5);
  const R = 6, across = Math.sqrt(3) * R, down = 1.5 * R, hole = R * .8;
  const angle = r() * Math.PI, ca = Math.cos(angle), sa = Math.sin(angle);
  const cx = r() * w, cy = r() * h, reach = Math.max(w, h) * (.45 + r() * .4);
  for (let y = 0; y < h; y++) {
    for (let x = 0; x < w; x++) {
      // The nearest hole center (rows offset by half a hole)
      const row = Math.round(y / down), col = Math.round((x - ((row & 1) ? across / 2 : 0)) / across);
      let best = Infinity, bx = 0, by = 0;
      for (let rr = row - 1; rr <= row + 1; rr++) {
        const shift = (rr & 1) ? across / 2 : 0;
        for (let cc = col - 1; cc <= col + 1; cc++) {
          const X = cc * across + shift, Y = rr * down, dd = (x - X) ** 2 + (y - Y) ** 2;
          if (dd < best) { best = dd; bx = X; by = Y; }
        }
      }
      // Within a hexagon whose flat sides are left and right (vertices up and down)
      const ax = Math.abs(x - bx), ay = Math.abs(y - by);
      const dist = Math.max(ax, ax * .5 + ay * .8660254) / (hole * .8660254);
      const d = ((x - cx) * ca + (y - cy) * sa) / reach, sheen = Math.max(0, 1 - d * d);
      let t;
      if (dist < 1) {
        const edge = Math.min(1, (1 - dist) * 4);
        t = 18 + (46 + (noise(bx * .05, by * .05, 2) - .5) * 10 + sheen * 14 - 18) * edge;
        if (dist > .82) t += ((x - bx) + (y - by)) / hole > 0 ? 16 * sheen + 6 : -6;
      } else {
        t = 34 + sheen * 70 + (noise(x * .5, y * .5, 1) - .5) * 8 + (noise(x * .05 + 9, y * .05, 2) - .5) * 10;
      }
      const o = (y * w + x) * 4;
      px[o] = t; px[o + 1] = t; px[o + 2] = t + 3; px[o + 3] = 255;
    }
  }
}

// ---------------------------------------------------------------------------
// The driver picture shown in place of the tile icon
// ---------------------------------------------------------------------------
function driverPicture(ring) {
  const svg =
    `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 40 40">` +
    `<circle cx="20" cy="20" r="15.5" fill="#15171a" stroke="${ring ?? "#2a2d32"}" stroke-width="${ring ? 2.4 : 1.2}"/>` +
    `<circle cx="20" cy="20" r="12.6" fill="#24272c" stroke="#3a3e45" stroke-width="1.6"/>` +
    `<circle cx="20" cy="20" r="9.6" fill="#1a1c20"/>` +
    `<circle cx="20" cy="20" r="5.4" fill="#3d424a"/>` +
    `<circle cx="18.6" cy="18.4" r="2" fill="#5b616b" opacity=".7"/>` +
    `</svg>`;
  return `data:image/svg+xml,${encodeURIComponent(svg)}`;
}

const BT_ON = "M14.88,16.29L13,18.17V14.41M13,5.83L14.88,7.71L13,9.58M17.71,7.71L12,2H11V9.58L6.41,5L5,6.41L10.59,12L5,17.58L6.41,19L11,14.41V22H12L17.71,16.29L13.41,12L17.71,7.71Z";
const BT_OFF = "M13 5.83l1.88 1.88-1.6 1.6 1.41 1.41 3.02-3.02L12 2h-1v5.03l2 2zM5.41 4L4 5.41 10.59 12 5 17.59 6.41 19 11 14.41V22h1l4.29-4.29 2.3 2.29L20 18.59 5.41 4zM13 18.17v-3.76l1.88 1.88L13 18.17z";

// Options this card adds to the tile card's
// The prototype panel card's own options, kept out of the tile card too
const PANEL_KEYS = ["members", "members_open", "members_toggle"];
const OWN_KEYS = ["finish", "pattern", "vibration", "bluetooth", "standby_badge", "driver_ring", "finish_extent", "features_style", "_embedded", "_member_entities", ...PANEL_KEYS];
// The same keys and values as The Lampster card
const FEATURES_STYLES = [["match", "Match style"], ["flat", "Flat"], ["console", "Console"]];
// The finish's base color, without grain or reflections, for Flat
const FLAT = { black_ash: "#1a1a1d", black_oak: "#161617", gloss_black: "#101113", gloss_white: "#e7e9ed", fabric: "#1f1f21", grille: "#1d1e20" };
const BLUETOOTH = [
  ["show", "Show"],
  ["disconnected", "Show only when not connected"],
  ["off", "Hide"],
];
const FINISH_EXTENTS = [
  ["card", "Card"],
  ["container", "Container"],
];

function tileConfig(config) {
  const tile = { ...config, type: "tile", show_entity_picture: true };
  for (const key of OWN_KEYS) delete tile[key];
  return tile;
}

/**
 * Console styling for Home Assistant's own toggle feature: a slide with a
 * beveled tab. This styles parts inside Home Assistant's controls; if an
 * update renames them, they keep their usual look.
 */
const HA_CONTROL_SHEET = `
  :host([svs-slide]) .switch .background,
  :host([svs-slide]) .switch:hover .background,
  :host([svs-slide]) .switch:focus-visible .background { opacity: 0 !important; }
  :host([svs-slide]) { --control-switch-padding: 0px !important; }
  :host([svs-slide]) .switch { padding: 0 !important; }
  :host([svs-slide]) .switch .button {
    position: relative;
    background-color: var(--control-switch-on-color);
    background-image: linear-gradient(180deg, rgba(255,255,255,.4), rgba(255,255,255,.05) 40%, rgba(0,0,0,.05) 60%, rgba(0,0,0,.3));
    box-shadow:
      inset 0 1px 0 rgba(255,255,255,.6), inset 0 -1px 0 rgba(0,0,0,.35),
      inset 1px 0 0 rgba(255,255,255,.25), inset -1px 0 0 rgba(0,0,0,.25),
      0 1px 2px rgba(0,0,0,.55);
  }
  :host([svs-slide]) .switch .button ha-svg-icon,
  :host([svs-slide]) .switch .button slot { display: none; }
`;
let haControlSheet;
function styleHaControl(control, attribute, on) {
  const root = control.shadowRoot;
  if (!root) return;
  if (!haControlSheet) {
    haControlSheet = new CSSStyleSheet();
    haControlSheet.replaceSync(HA_CONTROL_SHEET);
  }
  if (!root.adoptedStyleSheets.includes(haControlSheet)) root.adoptedStyleSheets = [...root.adoptedStyleSheets, haControlSheet];
  control.toggleAttribute(attribute, on);
}

/** All elements matching selector inside root's shadow roots, a few deep. */
function findAllDeep(root, selector, depth = 5, out = []) {
  if (!root || depth < 0) return out;
  out.push(...(root.querySelectorAll?.(selector) ?? []));
  for (const el of root.querySelectorAll?.("*") ?? []) {
    if (el.shadowRoot) findAllDeep(el.shadowRoot, selector, depth - 1, out);
  }
  return out;
}

/** Elements matching selector in el's shadow root, a few shadow roots deep. */
function findDeep(root, selector, depth = 5) {
  if (!root || depth < 0) return null;
  const found = root.querySelector?.(selector);
  if (found) return found;
  for (const el of root.querySelectorAll?.("*") ?? []) {
    const hit = el.shadowRoot && findDeep(el.shadowRoot, selector, depth - 1);
    if (hit) return hit;
  }
  return null;
}

// Option names in this card's own namespace: one that is not a current option
// is a mistake (a typo, or an option that was renamed), so the card says so
const OWN_PREFIXES = ["member", "finish", "bluetooth", "standby", "vibration", "pattern", "features_style", "_"];
function checkOptions(config, known) {
  const unknown = Object.keys(config).filter((k) => OWN_PREFIXES.some((p) => k.startsWith(p)) && !known.includes(k));
  if (unknown.length) throw new Error(`Unknown option${unknown.length > 1 ? "s" : ""}: ${unknown.join(", ")}`);
}

const reducedMotion = () => window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

// ---------------------------------------------------------------------------
// The card
// ---------------------------------------------------------------------------
class SvsCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this.shadowRoot.innerHTML = `
      <style>
        :host { display: block; height: 100%; }
        .frame {
          position: relative; height: 100%; box-sizing: border-box; isolation: isolate;
          /* Exactly the tile card's own corners (ha-card), from the theme */
          border-radius: var(--ha-card-border-radius, var(--ha-border-radius-lg));
        }
        /* Only the finish layers are clipped to the rounded outline; the tile
           card is not, so its callouts (such as a slider's value tooltip) can
           extend past the card's edge, as on a plain tile card */
        .clip { position: absolute; inset: 0; border-radius: inherit; overflow: hidden; pointer-events: none; }
        canvas { position: absolute; inset: 0; width: 100%; height: 100%; display: none; pointer-events: none; }
        .finished canvas { display: block; }
        .finished::after {
          content: ""; position: absolute; inset: 0; border-radius: inherit; pointer-events: none; z-index: 2;
          box-shadow: inset 0 1px 0 rgba(255, 255, 255, .16), inset 0 -1px 0 rgba(0, 0, 0, .4);
        }
        .tile { position: relative; display: block; height: 100%; }
        .finished .tile {
          --ha-card-background: transparent; --card-background-color: transparent;
          --ha-card-box-shadow: none; --ha-card-border-color: transparent;
          --ha-card-backdrop-filter: none;
        }
        /* On a finish, its own text colors (--svs-text for the controls, which
           a theme does not set), and the value callout in the finish's tone */
        .tile.dark {
          --primary-text-color: rgba(255, 255, 255, .95); --secondary-text-color: rgba(235, 235, 240, .7);
          --svs-text: rgba(255, 255, 255, .95); --svs-tip-background: #2b2c30; text-shadow: 0 1px 2px rgba(0, 0, 0, .8);
          /* Match: the finish shows through the controls, dimmed enough for their text */
          --svs-feature-scrim: rgba(0, 0, 0, .45);
        }
        .tile.light {
          --primary-text-color: rgba(0, 0, 0, .85); --secondary-text-color: rgba(40, 40, 48, .62);
          --svs-text: rgba(0, 0, 0, .85); --svs-tip-background: #f6f7f9;
          --svs-feature-scrim: rgba(255, 255, 255, .45);
        }
        /* Flat and Console: no finish shows through a control */
        .tile.dark.solid { --svs-feature-backing: ${BACKING.dark}; }
        .tile.light.solid { --svs-feature-backing: ${BACKING.light}; }
        /* With the finish on the expander card, this card is see-through */
        .through .tile {
          --ha-card-background: transparent; --card-background-color: transparent;
          --ha-card-box-shadow: none; --ha-card-border-color: transparent;
          --ha-card-backdrop-filter: none;
        }
        .through canvas, .through::after { display: none; }
        /* Features style: a flat patch of the finish's base color, or a channel
           pressed into the panel, behind each feature control */
        #areas { position: absolute; inset: 0; pointer-events: none; }
        .area { position: absolute; box-sizing: border-box; }
        .area.flat { background: var(--flat); box-shadow: 0 0 3px 1px var(--flat); }
        .area.console {
          background: linear-gradient(180deg, rgba(0, 0, 0, .22), rgba(0, 0, 0, .08));
          box-shadow:
            inset 0 2px 3px rgba(0, 0, 0, .55), inset 0 1px 1px rgba(0, 0, 0, .4),
            inset 0 -1px 0 rgba(255, 255, 255, .14), 0 1px 0 rgba(255, 255, 255, .18);
        }
        /* No backing: a soft shadow keeps the symbol readable on any finish */
        .badge {
          position: absolute; z-index: 3; width: 18px; height: 18px; margin: -9px 0 0 -9px; padding: 0; border: 0;
          display: none; place-items: center; background: none;
          border-radius: var(--ha-border-radius-pill, 9999px);
          color: var(--secondary-text-color); pointer-events: none; cursor: default;
          filter: drop-shadow(0 0 1px rgba(0, 0, 0, .9)) drop-shadow(0 0 2px rgba(0, 0, 0, .6));
        }
        .badge.on { display: grid; }
        .badge.connected { color: var(--blue-color, #2196f3); }
        .badge.some { color: var(--warning-color, #ffa600); }
        .badge svg { width: 16px; height: 16px; }
        .standby-badge {
          position: absolute; z-index: 3; width: 14px; height: 14px; margin: -7px 0 0 -7px; display: none;
          place-items: center; pointer-events: none;
          font: 700 11px/1 var(--ha-font-family-body, inherit); color: var(--primary-text-color);
          filter: drop-shadow(0 0 1px rgba(0, 0, 0, .9)) drop-shadow(0 0 2px rgba(0, 0, 0, .6));
        }
        .standby-badge.on { display: grid; }
        /* Without a finish, the badges get a halo in the card's own color */
        .frame:not(.finished) .badge, .frame:not(.finished) .standby-badge {
          filter: drop-shadow(0 0 1px var(--ha-card-background, var(--card-background-color, #fff)))
            drop-shadow(0 0 2px var(--ha-card-background, var(--card-background-color, #fff)));
        }
        /* On a light finish, the badges get a light halo */
        .light-finish .badge, .light-finish .standby-badge {
          filter: drop-shadow(0 0 1px rgba(255, 255, 255, .95)) drop-shadow(0 0 2px rgba(255, 255, 255, .7));
        }
        .light-finish .standby-badge { color: rgba(0, 0, 0, .85); }
      </style>
      <div class="frame">
        <div class="clip">
          <canvas></canvas>
          <div id="areas"></div>
        </div>
        <span class="standby-badge" aria-hidden="true"></span>
        <span class="badge" role="img"><svg viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="${BT_OFF}"/></svg></span>
      </div>`;
    this._frame = this.shadowRoot.querySelector(".frame");
    this._canvas = this.shadowRoot.querySelector("canvas");
    this._badge = this.shadowRoot.querySelector(".badge");
    this._standbyBadge = this.shadowRoot.querySelector(".standby-badge");
    this._areas = this.shadowRoot.getElementById("areas");
    this._resize = new ResizeObserver(() => this._layout());
    this._resize.observe(this._frame);
    // The volume feature reports while its slider moves
    this._frame.addEventListener("svs-volume-input", (ev) => this._sliderMoved(ev.detail));
  }

  static getConfigElement() {
    return document.createElement(EDITOR_TYPE);
  }

  static getStubConfig(hass) {
    const all = Object.values(hass.entities ?? {});
    const pick = (key) => all.find((e) => e.platform === DOMAIN && e.translation_key === key)?.entity_id;
    const entity = pick("group_volume") ?? pick("volume") ?? "";
    return {
      entity,
      finish: "none",
      vibration: true,
      features: [{ type: "custom:svs-subwoofer-presets" }, { type: "custom:svs-subwoofer-volume" }],
      features_position: "bottom",
    };
  }

  setConfig(config) {
    if (!config?.entity) throw new Error("Choose an SVS Subwoofer entity");
    checkOptions(config, OWN_KEYS.filter((k) => !PANEL_KEYS.includes(k)));
    const finish = config.finish ?? "none";
    if (!FINISHES.some(([id]) => id === finish)) throw new Error(`Unknown finish: ${finish}`);
    this._config = { ...config, finish };
    const tile = tileConfig(this._config);
    if (this._tile) {
      this._tile.setConfig(tile);
    } else if (customElements.get("hui-tile-card")) {
      this._createTile(tile);
    } else {
      // The tile card is loaded on demand; the card helpers load it
      window.loadCardHelpers?.().then(async (helpers) => {
        helpers.createCardElement({ type: "tile", entity: tile.entity });
        await customElements.whenDefined("hui-tile-card");
        if (!this._tile) this._createTile(tileConfig(this._config));
      });
    }
    this._drawn = undefined;
    this._expanderDrawn = undefined;
    this._layout();
    if (this._hass) this._updateBadge();
  }

  _createTile(tile) {
    this._tile = document.createElement("hui-tile-card");
    this._tile.classList.add("tile");
    this._tile.setConfig(tile);
    if (this._hass) this._tile.hass = this._innerHass(this._hass);
    if (this._preview !== undefined) this._tile.preview = this._preview;
    if (this._layoutValue !== undefined) this._tile.layout = this._layoutValue;
    this._frame.insertBefore(this._tile, this._badge);
    this._layout();
  }

  set hass(hass) {
    const before = this._hass;
    this._hass = hass;
    if (this._tile) this._tile.hass = this._innerHass(hass);
    this._watchChanges(before, hass);
    this._updateBadge();
    this._sizeDriver();
  }

  get hass() {
    return this._hass;
  }

  // Dashboard properties the tile card uses
  set preview(value) {
    this._preview = value;
    if (this._tile) this._tile.preview = value;
  }

  set layout(value) {
    this._layoutValue = value;
    if (this._tile) this._tile.layout = value;
  }

  getCardSize() {
    if (this._tile?.getCardSize) return this._tile.getCardSize();
    return 1 + (this._config?.features?.length ?? 0);
  }

  getGridOptions() {
    if (this._tile?.getGridOptions) return this._tile.getGridOptions();
    return { columns: 6, rows: 1 + (this._config?.features?.length ?? 0), min_columns: 6, min_rows: 1 };
  }

  get _entities() {
    const id = this._config?.entity;
    return {
      standby: sibling(this._hass, id, "standby"),
      preset: sibling(this._hass, id, "preset"),
      volume: this._hass?.entities?.[id]?.translation_key?.endsWith("volume") ? id : sibling(this._hass, id, "volume"),
      connected: sibling(this._hass, id, "connected"),
    };
  }

  /** The volume as a fraction of its range (0 at the quietest, 1 at the loudest). */
  _level(value) {
    const id = this._entities.volume;
    const stateObj = id ? this._hass?.states[id] : undefined;
    const v = value ?? Number(stateObj?.state);
    if (!Number.isFinite(v)) return 0;
    // The same range as the card's volume slider, if it has one
    const slider = (this._config?.features ?? []).find((f) => f.type === "custom:svs-subwoofer-volume");
    const { min, max } = sliderRange(slider, stateObj);
    return Math.max(0, Math.min(1, (v - min) / (max - min)));
  }

  /**
   * The driver's ring: while the volume slider moves, the color of the volume
   * threshold it is in; otherwise the active preset's color; with no preset
   * (Manual), the threshold color of the volume; and a neutral ring if none apply.
   */
  _ringColor() {
    if (this._dragColor) return this._resolve(this._dragColor);
    const features = this._config?.features ?? [];
    const preset = this._entities.preset;
    const name = preset ? this._hass?.states[preset]?.state : undefined;
    const isPreset = name && !NOT_PRESETS.includes(name) && name !== "unavailable" && name !== "unknown";
    if (isPreset) {
      const presetFeature = features.find((f) => f.type === "custom:svs-subwoofer-presets");
      const color = presetFeature?.presets?.[name]?.color ?? presetDefaults(name).color;
      if (color) return this._resolve(color);
    }
    const thresholds = colorRanges(features.find((f) => f.type === "custom:svs-subwoofer-volume"));
    const volume = this._entities.volume;
    const value = volume ? Number(this._hass?.states[volume]?.state) : NaN;
    if (thresholds.length && Number.isFinite(value)) {
      const color = rangeColor(thresholds, value);
      if (color) return this._resolve(color);
    }
    return isPreset ? "#9aa0a8" : "#6b7079";
  }

  // A theme color as a value the picture can use
  _resolve(color) {
    const value = HA_COLORS.includes(color) ? getComputedStyle(this).getPropertyValue(`--${color}-color`).trim() : color;
    return value || "#9aa0a8";
  }

  /**
   * The Home Assistant object the tile card sees: the same, except that the
   * card's entity has the driver as its picture. The changed state object is
   * reused until the real one or the picture changes.
   */
  _innerHass(hass) {
    const entity = this._config?.entity;
    const stateObj = hass.states[entity];
    if (!stateObj) return hass;
    const picture = driverPicture(this._config.driver_ring === false ? null : this._ringColor());
    const extra = subwooferAttributes(hass, entity);
    const extraKey = JSON.stringify(extra);
    if (this._sourceState !== stateObj || this._lastPicture !== picture || this._lastExtra !== extraKey) {
      this._sourceState = stateObj;
      this._lastPicture = picture;
      this._lastExtra = extraKey;
      this._innerState = { ...stateObj, attributes: { ...stateObj.attributes, ...extra, entity_picture: picture } };
    }
    return { ...hass, states: { ...hass.states, [entity]: this._innerState } };
  }

  // The driver picture inside the tile card's icon; undefined if the tile
  // card ever changes how it shows a picture (the card then just does not move it)
  get _driver() {
    const icon = this._tile?.shadowRoot?.querySelector("ha-tile-icon");
    return icon?.shadowRoot?.querySelector("img") ?? icon?.querySelector?.("img") ?? undefined;
  }

  // The driver's size follows the volume: small when quiet, filling the icon when loud
  _sizeDriver(level = this._level()) {
    const driver = this._driver;
    if (!driver) {
      // The tile card renders after this card; try again once it has
      if (this._tile && !this._sizeRetry) {
        this._sizeRetry = true;
        this._tile.updateComplete?.then(() => {
          this._sizeRetry = false;
          if (this._driver) this._sizeDriver();
        });
      }
      return;
    }
    driver.style.transition = reducedMotion() ? "none" : "scale 350ms cubic-bezier(.3, 1.5, .5, 1)";
    driver.style.scale = String(.7 + level * .5);
    if (reducedMotion()) this._placeBadge();
  }

  // A preset or volume change from anywhere shakes the driver briefly, harder
  // at a higher volume
  _watchChanges(before, hass) {
    if (!before || !this._config) return;
    const { preset, volume } = this._entities;
    const changed = (id) => id && before.states[id]?.state !== hass.states[id]?.state &&
      before.states[id] !== undefined && hass.states[id]?.state !== "unavailable";
    // The slider shakes the driver itself; its own volume change arriving
    // afterwards does not shake it again
    const fromSlider = this._sliding || Date.now() - (this._slideEnded ?? 0) < 2500;
    if (changed(preset) || (changed(volume) && !fromSlider)) this._shake(this._level(), 650);
  }

  _sliderMoved({ active, level, color }) {
    this._sliding = active;
    // The ring shows the threshold color while the slider moves
    const dragColor = active ? color : undefined;
    if (dragColor !== this._dragColor) {
      this._dragColor = dragColor;
      if (this._tile && this._hass) this._tile.hass = this._innerHass(this._hass);
    }
    if (!active) this._slideEnded = Date.now();
    this._sizeDriver(level);
    if (active) this._shake(level);
    else this._shake(level, 450);
  }

  /** Shake the driver; with no duration, until the slider stops. */
  _shake(level, duration) {
    if (this._config?.vibration === false || reducedMotion()) return;
    const driver = this._driver;
    if (!driver?.animate) return;
    const a = (.3 + level * 1.4).toFixed(2), s = (1 + level * .06).toFixed(3);
    const frames = [
      { transform: "translate(0, 0) scale(1)" },
      { transform: `translate(${a}px, ${-a / 2}px) scale(${s})` },
      { transform: "translate(0, 0) scale(1)" },
      { transform: `translate(${-a}px, ${a / 2}px) scale(${s})` },
      { transform: "translate(0, 0) scale(1)" },
    ];
    this._shaking?.cancel();
    this._shaking = driver.animate(frames, { duration: 90, iterations: duration ? Math.max(1, Math.round(duration / 90)) : Infinity });
  }

  /**
   * The Bluetooth badge on the driver: the connection status, and (by
   * default) a tap connects or disconnects. A group has no connection of its
   * own, so it has no badge.
   */
  /**
   * The connection sensors the badge shows: the subwoofer's own, or for a
   * group in the panel card, those of the subwoofers in its rows.
   */
  get _connectionSensors() {
    const own = this._entities.connected;
    if (own) return [own];
    return (this._config?._member_entities ?? []).map((id) => sibling(this._hass, id, "connected")).filter(Boolean);
  }

  _updateBadge() {
    const mode = this._config?.bluetooth ?? "show";
    const sensors = this._connectionSensors;
    const on = sensors.filter((id) => this._hass?.states[id]?.state === "on").length;
    const connected = sensors.length > 0 && on === sensors.length;
    const some = on > 0 && !connected;
    const show = sensors.length > 0 && (mode === "show" || (mode === "disconnected" && !connected));
    this._badge.classList.toggle("on", show);
    this._badge.classList.toggle("connected", connected);
    this._badge.classList.toggle("some", some);
    this._badge.querySelector("path").setAttribute("d", connected || some ? BT_ON : BT_OFF);
    const group = sensors.length > 1;
    const status = connected
      ? (group ? "All connected" : "Connected")
      : some ? `${on} of ${sensors.length} connected` : (group ? "None connected" : "Not connected");
    const label = status;
    this._badge.title = label;
    this._badge.setAttribute("aria-label", label);
    // The standby mode's first letter: A (Auto On), O (On), T (Trigger)
    const standby = this._entities.standby;
    const value = standby ? this._hass?.states[standby]?.state : undefined;
    const letter = this._config?.standby_badge && value && !NOT_PRESETS.includes(value) && value !== "unavailable" && value !== "unknown"
      ? value.trim()[0].toUpperCase() : "";
    this._standbyBadge.textContent = letter;
    this._standbyBadge.title = letter ? `Standby mode: ${value}` : "";
    this._standbyBadge.classList.toggle("on", !!letter);
    if (show || letter) this._placeBadge();
  }



  /**
   * The badges sit on the driver's own edge (the driver grows and shrinks
   * with the volume): Bluetooth up and to the right, the standby mode down
   * and to the right, each about half over the driver.
   */
  _placeBadge() {
    const driver = this._driver;
    const icon = this._tile?.shadowRoot?.querySelector("ha-tile-icon");
    const target = driver ?? icon;
    if (!target) return;
    if (driver && !this._badgeFollows) {
      this._badgeFollows = true;
      driver.addEventListener("transitionend", () => this._placeBadge());
    }
    const frame = this._frame.getBoundingClientRect(), box = target.getBoundingClientRect();
    const scale = frame.width / this._frame.offsetWidth || 1;
    // The driver's outer ring is 16.7 of the picture's 20 radius
    const r = (box.width / 2 / scale) * (driver ? 16.7 / 20 : 1);
    const cx = (box.left - frame.left) / scale + box.width / 2 / scale;
    const cy = (box.top - frame.top) / scale + box.height / 2 / scale;
    this._badge.style.left = `${cx + r * .7071}px`;
    this._badge.style.top = `${cy - r * .7071}px`;
    this._standbyBadge.style.left = `${cx + r * .7071}px`;
    this._standbyBadge.style.top = `${cy + r * .7071}px`;
  }

  connectedCallback() {
    this._layout();
  }

  disconnectedCallback() {
    this._expanderResize?.disconnect();
    this._expanderResize = undefined;
  }

  _layout() {
    if (!this._config) return;
    const finish = this._config.finish;
    const tone = finishTone(finish);
    // Embedded (in the prototype panel card), the panel draws the finish
    const embedded = !!this._config._embedded;
    const onExpander = !!tone && this._config.finish_extent === "container" && !embedded;
    const through = embedded || onExpander;
    this._frame.classList.toggle("finished", !!tone);
    this._frame.classList.toggle("through", through);
    this._frame.classList.toggle("light-finish", tone === "light");
    // The volume loupe's bezel is of the finish (the theme's card color without one)
    if (BEZEL[finish]) this.style.setProperty("--svs-bezel", BEZEL[finish]);
    else this.style.removeProperty("--svs-bezel");
    if (this._tile) {
      this._tile.classList.toggle("dark", tone === "dark");
      this._tile.classList.toggle("light", tone === "light");
      this._tile.classList.toggle("solid", !!tone && (this._config.features_style ?? "match") !== "match");
    }
    if (this._badge.classList.contains("on")) this._placeBadge();
    if (!embedded) this._paintExpander(onExpander);
    this._drawAreas();
    if (!tone || through) return;
    const w = this._frame.clientWidth, h = this._frame.clientHeight;
    if (!w || !h) return;
    const pattern = Number.isFinite(this._config.pattern) ? this._config.pattern : DEFAULT_PATTERN;
    const key = `${finish}|${pattern}|${w}x${h}`;
    if (key === this._drawn) return;
    this._drawn = key;
    this._canvas.width = w;
    this._canvas.height = h;
    drawFinish(this._canvas.getContext("2d"), finish, pattern, w, h);
  }

  /**
   * The areas the feature controls take, in the card's own pixels: each
   * control, except that each preset button counts on its own (so the finish
   * shows between them). Read from the tile card's rendered layout; if it
   * ever changes, the areas are simply not drawn.
   */
  _featureAreas() {
    const root = this._tile?.shadowRoot;
    if (!root) return [];
    const origin = this._frame.getBoundingClientRect();
    const scale = origin.width / this._frame.offsetWidth || 1;
    const box = (el) => {
      const r = el.getBoundingClientRect();
      if (!r.width || !r.height) return null;
      const radius = parseFloat(getComputedStyle(el).borderTopLeftRadius) || 0;
      return { x: (r.left - origin.left) / scale, y: (r.top - origin.top) / scale, w: r.width / scale, h: r.height / scale, radius };
    };
    const areas = [];
    this._watchedGroups ??= new WeakSet();
    for (const group of root.querySelectorAll("hui-card-features")) {
      if (!this._watchedGroups.has(group)) {
        this._watchedGroups.add(group);
        this._resize.observe(group);
        this._watchAdded(group.shadowRoot);
      }
      for (const wrap of group.shadowRoot?.querySelectorAll("hui-card-feature") ?? []) {
        const inner = wrap.shadowRoot ?? wrap;
        const row = findDeep(inner, "svs-subwoofer-presets, svs-subwoofer-standby");
        const buttons = row ? [...(row.shadowRoot?.querySelectorAll("button") ?? [])] : [];
        const own = findDeep(inner, "svs-subwoofer-volume");
        const control = own?.shadowRoot?.querySelector(".control");
        const element = [...inner.children].find((c) => c.tagName !== "STYLE");
        for (const el of buttons.length ? buttons : [control ?? element]) {
          const b = el && box(el);
          if (b) areas.push(b);
        }
      }
    }
    this._watchAdded(root);
    return areas;
  }

  // Console: the preset and standby buttons become keys, and Home Assistant's
  // toggle a slide
  _styleControls(keys) {
    const root = this._tile?.shadowRoot;
    if (!root) return;
    try {
      for (const el of findAllDeep(root, "svs-subwoofer-presets, svs-subwoofer-volume, svs-subwoofer-standby")) {
        el.toggleAttribute("svs-console", keys);
      }
      for (const el of findAllDeep(root, "ha-control-switch")) styleHaControl(el, "svs-slide", keys);
    } catch (err) {
      console.warn("SVS Subwoofer card: could not style the controls", err);
    }
  }

  // Redraw when elements are added in the tile card (features render late)
  _watchAdded(root) {
    if (!root) return;
    this._observed ??= new WeakSet();
    if (this._observed.has(root)) return;
    this._observed.add(root);
    this._mutations ??= new MutationObserver(() => {
      clearTimeout(this._areasTimer);
      this._areasTimer = setTimeout(() => this._drawAreas(), 0);
    });
    this._mutations.observe(root, { childList: true, subtree: true });
  }

  _drawAreas() {
    const style = finishTone(this._config?.finish) ? this._config.features_style ?? "match" : "match";
    this._styleControls(style === "console");
    if (style === "match") {
      this._areas.replaceChildren();
      this._areasKey = undefined;
      return;
    }
    const pad = style === "console" ? 3 : 2;
    const areas = this._featureAreas().map((b) => ({
      x: b.x - pad, y: b.y - pad, w: b.w + 2 * pad, h: b.h + 2 * pad,
      radius: Math.min(b.radius + pad, (b.h + 2 * pad) / 2),
    }));
    const key = style + JSON.stringify(areas.map((a) => [a.x, a.y, a.w, a.h, a.radius].map(Math.round)));
    if (key !== this._areasKey) {
      this._areasKey = key;
      this._areas.style.setProperty("--flat", FLAT[this._config.finish] ?? "transparent");
      this._areas.replaceChildren(...areas.map((a) => {
        const el = document.createElement("div");
        el.className = `area ${style}`;
        Object.assign(el.style, { left: `${a.x}px`, top: `${a.y}px`, width: `${a.w}px`, height: `${a.h}px`, borderRadius: `${a.radius}px` });
        return el;
      }));
    }
    // The tile card can move its features without changing size (fonts
    // loading, the editor preview opening): check again for about a second
    if (this._settling) return;
    this._settleUntil = performance.now() + 1200;
    this._settling = true;
    const check = () => {
      if (performance.now() > this._settleUntil || !this.isConnected) {
        this._settling = false;
        return;
      }
      this._drawAreas();
      setTimeout(check, 100);
    };
    setTimeout(check, 100);
  }

  /**
   * The expander card (custom:expander-card) this card sits in, and whether
   * this card is its header (title card).
   */
  _findExpander() {
    let node = this, header = false;
    while (node) {
      if (node.classList?.contains("title-card-container")) header = true;
      if (node.tagName === "EXPANDER-CARD") return { expander: node, header };
      node = node.parentNode ?? node.host;
    }
    return undefined;
  }

  /**
   * With "The expander card around it", the finish covers the whole expander
   * card, so the header and the cards inside it read as one card. The header
   * card draws it; the cards inside are see-through. This styles the
   * expander card from outside; if a change to that card breaks it, the
   * expander keeps its usual background.
   */
  _paintExpander(on) {
    const found = this._findExpander();
    const root = found?.expander.shadowRoot;
    if (!root) return;
    let style = root.getElementById("svs-subwoofer-finish");
    if (!on || !found.header) {
      if (!on && found.header) style?.remove();
      return;
    }
    const surface = root.querySelector("ha-card");
    if (!surface) return;
    if (!this._expanderResize) {
      this._expanderResize = new ResizeObserver(() => {
        clearTimeout(this._expanderTimer);
        this._expanderTimer = setTimeout(() => this._paintExpander(this._config?.finish_extent === "container" && !!finishTone(this._config?.finish)), 150);
      });
      this._expanderResize.observe(surface);
    }
    const w = surface.clientWidth, h = surface.clientHeight;
    if (!w || !h) return;
    const pattern = Number.isFinite(this._config.pattern) ? this._config.pattern : DEFAULT_PATTERN;
    const key = `${this._config.finish}|${pattern}|${w}x${h}`;
    if (key === this._expanderDrawn && style) return;
    this._expanderDrawn = key;
    const canvas = document.createElement("canvas");
    canvas.width = w;
    canvas.height = h;
    drawFinish(canvas.getContext("2d"), this._config.finish, pattern, w, h);
    if (!style) {
      style = document.createElement("style");
      style.id = "svs-subwoofer-finish";
      root.append(style);
    }
    style.textContent = `ha-card { background: url("${canvas.toDataURL()}") center / 100% 100% no-repeat !important; ` +
      "box-shadow: inset 0 1px 0 rgba(255, 255, 255, .16), inset 0 -1px 0 rgba(0, 0, 0, .4) !important; }";
  }
}

// ---------------------------------------------------------------------------
// PROTOTYPE: the panel card. The SVS Subwoofer card for a subwoofer or group,
// with rows for chosen subwoofers below it, on one surface: the finish covers
// the whole panel, and a handle opens and closes the rows. It stands in for
// an expander card holding an SVS Subwoofer card and one card per subwoofer.
// ---------------------------------------------------------------------------
const PANEL_TYPE = "svs-subwoofer-panel-card";
const PANEL_EDITOR_TYPE = "svs-subwoofer-panel-card-editor";
/** Every single subwoofer's volume entity (not groups), as [entity_id, name]. */
function subwoofers(hass) {
  return Object.values(hass?.entities ?? {})
    .filter((e) => e.platform === DOMAIN && e.translation_key === "volume")
    .map((e) => {
      const device = hass.devices?.[e.device_id];
      return [e.entity_id, device?.name_by_user || device?.name || e.entity_id];
    });
}

/** A new member row: the subwoofer's volume, with its state and a slider. */
function newMember(entity) {
  return {
    entity,
    state_content: ["state", "preset", "standby_mode"],
    features: [{ type: "custom:svs-subwoofer-volume" }],
    features_position: "inline",
  };
}

/** The names the rows show by default, by entity. */
function defaultMemberNames(hass, ids) {
  const all = Object.fromEntries(subwoofers(hass));
  const names = shortNames(ids.map((id) => all[id] ?? id));
  return Object.fromEntries(ids.map((id, i) => [id, names[i]]));
}

// Names without the part they all share ("Subwoofer Left", "Subwoofer Right"
// become "Left" and "Right")
function shortNames(names) {
  if (names.length < 2) return names;
  const words = names.map((n) => n.split(" "));
  let common = 0;
  while (words.every((w) => w.length > common + 1 && w[common] === words[0][common])) common++;
  return words.map((w) => w.slice(common).join(" "));
}

class SvsPanelCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this.shadowRoot.innerHTML = `
      <style>
        :host { display: block; }
        .panel {
          position: relative; isolation: isolate; box-sizing: border-box;
          border-radius: var(--ha-card-border-radius, var(--ha-border-radius-lg));
          background: var(--ha-card-background, var(--card-background-color, #fff));
          -webkit-backdrop-filter: var(--ha-card-backdrop-filter, none); backdrop-filter: var(--ha-card-backdrop-filter, none);
          border: var(--ha-card-border-width, 1px) solid var(--ha-card-border-color, var(--divider-color, #e0e0e0));
          box-shadow: var(--ha-card-box-shadow, none);
          color: var(--primary-text-color);
        }
        canvas { position: absolute; inset: 0; width: 100%; height: 100%; display: none; pointer-events: none; }
        /* Only the finish is clipped to the outline, so the rows' callouts can
           extend past the panel's edge */
        .clip { position: absolute; inset: 0; border-radius: inherit; overflow: hidden; pointer-events: none; z-index: -1; }
        .finished { -webkit-backdrop-filter: none; backdrop-filter: none; border-color: transparent; }
        .finished canvas { display: block; }
        .finished::after {
          content: ""; position: absolute; inset: 0; border-radius: inherit; pointer-events: none;
          box-shadow: inset 0 1px 0 rgba(255, 255, 255, .16), inset 0 -1px 0 rgba(0, 0, 0, .4);
        }
        .dark { --primary-text-color: rgba(255, 255, 255, .95); --divider-color: rgba(255, 255, 255, .14); }
        .light { --primary-text-color: rgba(0, 0, 0, .85); --divider-color: rgba(0, 0, 0, .12); }
        .members { display: grid; }
        .panel:not(.open) .members { display: none; }
      </style>
      <div class="panel">
        <div class="clip"><canvas></canvas></div>
        <div class="header"></div>
        <div class="members"></div>
      </div>`;
    this._panel = this.shadowRoot.querySelector(".panel");
    this._canvas = this.shadowRoot.querySelector("canvas");
    this._headerSlot = this.shadowRoot.querySelector(".header");
    this._membersSlot = this.shadowRoot.querySelector(".members");
    // The header card's tap action shows or hides the rows (see setConfig)
    this._panel.addEventListener("ll-custom", (ev) => {
      if (ev.detail?.svs_subwoofer_panel !== "toggle") return;
      ev.stopPropagation();
      this._setOpen(!this._open);
    });
    new ResizeObserver(() => this._paint()).observe(this._panel);
  }

  static getConfigElement() {
    return document.createElement(PANEL_EDITOR_TYPE);
  }

  static getStubConfig(hass) {
    const ids = sortPairs(subwoofers(hass)).map(([id]) => id);
    return { ...SvsCard.getStubConfig(hass), members: ids.map((entity) => newMember(entity)) };
  }

  setConfig(config) {
    if (!config?.entity) throw new Error("Choose an SVS Subwoofer entity");
    checkOptions(config, OWN_KEYS.filter((k) => !k.startsWith("_")));
    if (config.members !== undefined && (!Array.isArray(config.members) || config.members.some((m) => !m || typeof m !== "object" || !m.entity))) {
      throw new Error("members must be a list of card settings, each with an entity");
    }
    this._config = config;
    // The header: the SVS Subwoofer card, without the panel's own options
    const header = { ...config, type: "custom:svs-subwoofer-card", _embedded: true };
    for (const key of PANEL_KEYS) delete header[key];
    // The header shows its rows' Bluetooth connections together
    const rows = (config.members ?? []).map((m) => m?.entity).filter(Boolean);
    if (rows.length) header._member_entities = rows;
    // A tap on the card shows or hides the rows (instead of its own tap action)
    if (config.members_toggle !== false && (config.members ?? []).some((m) => m?.entity)) {
      header.tap_action = { action: "fire-dom-event", svs_subwoofer_panel: "toggle" };
    }
    if (!this._header) {
      this._header = document.createElement("svs-subwoofer-card");
      this._headerSlot.append(this._header);
    }
    this._header.setConfig(header);
    this._members = undefined;
    this._open = config.members_toggle === false ? true : this._storedOpen() ?? config.members_open !== false;
    this._buildMembers();
    this._apply();
  }

  set hass(hass) {
    this._hass = hass;
    if (this._header) this._header.hass = hass;
    if (!this._members) this._buildMembers();
    for (const card of this._memberCards ?? []) card.hass = hass;
  }

  get hass() {
    return this._hass;
  }

  getCardSize() {
    return 1 + (this._config?.features?.length ?? 0) + (this._open ? this._memberConfigs().length : 0);
  }

  getGridOptions() {
    return { columns: 12, min_columns: 6 };
  }

  _memberConfigs() {
    return (this._config?.members ?? []).filter((m) => m && typeof m === "object" && m.entity);
  }

  // Each member is an SVS Subwoofer card, configured on its own tab in the
  // editor; the panel's finish and features style apply to all of them
  _buildMembers() {
    if (!this._config || !this._hass) return;
    const members = this._memberConfigs();
    const defaults = defaultMemberNames(this._hass, members.map((m) => m.entity));
    this._members = members;
    this._memberCards = members.map((member) => {
      const card = document.createElement("svs-subwoofer-card");
      const own = { ...member };
      delete own.type;
      card.setConfig({
        bluetooth: this._config.bluetooth ?? "show",
        vibration: this._config.vibration !== false,
        standby_badge: !!this._config.standby_badge,
        driver_ring: this._config.driver_ring !== false,
        ...own,
        type: "custom:svs-subwoofer-card",
        name: member.name || defaults[member.entity],
        finish: this._config.finish ?? "none",
        ...(this._config.pattern !== undefined ? { pattern: this._config.pattern } : {}),
        features_style: this._config.features_style ?? "match",
        _embedded: true,
      });
      card.hass = this._hass;
      return card;
    });
    this._membersSlot.replaceChildren(...this._memberCards);
  }

  // The open state is remembered in this browser, per panel
  get _storageKey() {
    return `svs-subwoofer-panel:${this._config?.entity}`;
  }

  _storedOpen() {
    try {
      const v = window.localStorage.getItem(this._storageKey);
      return v === null ? undefined : v === "1";
    } catch (err) {
      return undefined;
    }
  }

  _setOpen(open) {
    this._open = open;
    try {
      window.localStorage.setItem(this._storageKey, open ? "1" : "0");
    } catch (err) {
      // Storage can be unavailable (private windows); the panel still works
    }
    this._apply();
  }

  _apply() {
    const tone = finishTone(this._config?.finish ?? "none");
    this._panel.classList.toggle("open", this._open);
    this._panel.classList.toggle("finished", !!tone);
    this._panel.classList.toggle("dark", tone === "dark");
    this._panel.classList.toggle("light", tone === "light");
    this._paint();
  }

  _paint() {
    const finish = this._config?.finish ?? "none";
    if (!finishTone(finish)) return;
    const w = this._panel.clientWidth, h = this._panel.clientHeight;
    if (!w || !h) return;
    const pattern = Number.isFinite(this._config.pattern) ? this._config.pattern : DEFAULT_PATTERN;
    const key = `${finish}|${pattern}|${w}x${h}`;
    if (key === this._drawn) return;
    this._drawn = key;
    this._canvas.width = w;
    this._canvas.height = h;
    drawFinish(this._canvas.getContext("2d"), finish, pattern, w, h);
  }
}

// ---------------------------------------------------------------------------
// The editor: the tile card's own editor, plus a panel for the SVS look
// ---------------------------------------------------------------------------

// Tile card options this card sets itself, so they are left out of its editor
const HIDDEN_TILE_OPTIONS = ["icon", "show_entity_picture"];

function hideOptions(schema, entities) {
  return schema
    .filter((item) => !HIDDEN_TILE_OPTIONS.includes(item.name))
    .map((item) => {
      if (Array.isArray(item.schema)) return { ...item, schema: hideOptions(item.schema, entities) };
      // The entity picker offers only the volumes this card works with
      if (item.name === "entity" && entities) return { ...item, selector: { entity: { include_entities: entities } } };
      return item;
    });
}

/** The SVS volume entities: every subwoofer's, and with groups, every group's. */
function svsVolumes(hass, groups = true) {
  return Object.values(hass?.entities ?? {})
    .filter((e) => e.platform === DOMAIN && (e.translation_key === "volume" || (groups && e.translation_key === "group_volume")))
    .map((e) => e.entity_id)
    .sort();
}

/**
 * The tile card's editor, with the options above left out. It is the tile
 * card's own editor class, so it keeps every future change to it. If a Home
 * Assistant update renames its form layout, the editor still works and simply
 * shows those options again.
 */
function tileEditorType() {
  if (customElements.get(TILE_EDITOR_TYPE)) return TILE_EDITOR_TYPE;
  const Base = customElements.get("hui-tile-card-editor");
  if (!Base) return null;
  customElements.define(TILE_EDITOR_TYPE, class extends Base {
    constructor() {
      super();
      const original = this._schema;
      if (typeof original !== "function") return;
      let lastIn, lastKey, lastOut;
      this._schema = (...args) => {
        const schema = original.apply(this, args);
        const key = (this.svsEntities ?? []).join(",");
        if (schema !== lastIn || key !== lastKey) {
          lastIn = schema;
          lastKey = key;
          lastOut = Array.isArray(schema) ? hideOptions(schema, this.svsEntities) : schema;
        }
        return lastOut;
      };
    }
  });
  return TILE_EDITOR_TYPE;
}

const RANDOMIZE_LABEL = {
  black_ash: "Randomize grain",
  black_oak: "Randomize grain",
  gloss_black: "Randomize reflections",
  gloss_white: "Randomize reflections",
  fabric: "Randomize reflections",
  grille: "Randomize reflections",
};

class SvsCardEditor extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this.shadowRoot.innerHTML = `
      <style>
        #tile { display: block; }
        ha-expansion-panel {
          display: block; margin-top: 24px;
          --expansion-panel-content-padding: 0;
          border-radius: var(--ha-border-radius-md, 8px);
          --ha-card-border-radius: var(--ha-border-radius-md, 8px);
        }
        ha-expansion-panel > [slot="header"] { margin: 0; font-size: inherit; font-weight: inherit; }
        .content { padding: 12px; display: grid; gap: 16px; }
        .row { display: flex; align-items: center; gap: 12px; }
      </style>
      <div id="tile"></div>
      <ha-expansion-panel outlined expanded>
        <div slot="header" role="heading" aria-level="3">SVS style</div>
        <div class="content">
          <ha-form id="finish"></ha-form>
          <div class="row" id="row"><ha-button id="randomize"></ha-button></div>
          <ha-form id="form"></ha-form>
        </div>
      </ha-expansion-panel>`;
    this._finishForm = this.shadowRoot.getElementById("finish");
    this._form = this.shadowRoot.getElementById("form");
    for (const form of [this._finishForm, this._form]) {
      form.computeLabel = (s) => s.label ?? s.name;
      form.computeHelper = (s) => s.helper;
      form.addEventListener("value-changed", (ev) => this._changed(ev));
    }
    this.shadowRoot.getElementById("randomize").addEventListener("click", () => {
      this._update({ pattern: 1 + Math.floor(Math.random() * 99999) });
    });
  }

  // Either form changed: both forms' values make the card's options
  _changed(ev) {
    ev.stopPropagation();
    const v = { ...this._finishForm.data, ...this._form.data, ...ev.detail.value };
    this._update({
      finish: v.finish ?? "none", finish_extent: v.finish_extent ?? "card", features_style: v.features_style ?? "match",
      vibration: v.vibration !== false, bluetooth: v.bluetooth ?? "show", standby_badge: !!v.standby_badge,
      driver_ring: v.driver_ring !== false,
    });
  }

  /**
   * In the panel editor the card's editor is split in two sections: "style"
   * shows only the SVS style options (without their own heading), "tile"
   * only the tile card's options. Unset, both show.
   */
  set part(part) {
    this._part = part;
    const panel = this.shadowRoot.querySelector("ha-expansion-panel");
    if (part === "style" && panel) panel.replaceWith(panel.querySelector(".content"));
    if (part === "tile" && panel) panel.style.display = "none";
  }

  set hass(hass) {
    this._hass = hass;
    this._finishForm.hass = hass;
    this._form.hass = hass;
    if (this._tileEditor) this._tileEditor.hass = withSubwooferAttributes(hass, this._config?.entity);
  }

  set lovelace(lovelace) {
    this._lovelace = lovelace;
    if (this._tileEditor) this._tileEditor.lovelace = lovelace;
  }

  setConfig(config) {
    this._config = explicit(config);
    this._render();
    this._setTileEditorConfig();
    if (JSON.stringify(this._config) !== JSON.stringify(config)) this._fire();
  }

  async _setTileEditorConfig() {
    if (this._part === "style") return;
    if (!this._tileEditor) {
      this._loading ??= (async () => {
        const helpers = await window.loadCardHelpers();
        helpers.createCardElement({ type: "tile", entity: this._config.entity });
        await customElements.whenDefined("hui-tile-card");
        const original = await customElements.get("hui-tile-card").getConfigElement();
        const type = tileEditorType();
        const editor = type ? document.createElement(type) : original;
        editor.addEventListener("config-changed", (ev) => {
          // The tile card's options changed: keep ours and pass the whole card on
          ev.stopPropagation();
          const own = Object.fromEntries(OWN_KEYS.filter((k) => k in this._config).map((k) => [k, this._config[k]]));
          const next = { ...ev.detail.config, ...own, type: this._config.type };
          delete next.show_entity_picture;  // always on: the driver is shown there
          this._config = next;
          this._fire();
        });
        editor.svsEntities = svsVolumes(this._hass);
        editor.hass = withSubwooferAttributes(this._hass, this._config.entity);
        if (this._lovelace) editor.lovelace = this._lovelace;
        this.shadowRoot.getElementById("tile").replaceWith(editor);
        this._tileEditor = editor;
      })();
      await this._loading;
    }
    this._tileEditor.setConfig(tileConfig(this._config));
  }

  _render() {
    const c = this._config;
    this._finishForm.schema = [
      { name: "finish", label: "Finish", selector: { select: { mode: "dropdown", options: FINISHES.map(([value, label]) => ({ value, label })) } } },
    ];
    this._finishForm.data = { finish: c.finish };
    this._form.schema = [
      ...(c.finish === "none" ? [] : [{
        name: "finish_extent", label: "Finish extent",
        helper: "Normally set to Card. Set to Container when the SVS Subwoofer card is contained in another card (e.g. Expander card) to extend the selected Finish to that card.",
        selector: { select: { mode: "dropdown", options: FINISH_EXTENTS.map(([value, label]) => ({ value, label })) } },
      }, {
        name: "features_style", label: "Features style",
        helper: "Match style: the finish shows through the feature controls. Flat: similar to match but without grain or reflections. Console: 3D machine appearance.",
        selector: { select: { mode: "dropdown", options: FEATURES_STYLES.map(([value, label]) => ({ value, label })) } },
      }]),
      {
        name: "bluetooth", label: "Bluetooth badge",
        helper: "To connect and disconnect with a tap, set Icon tap behavior (under Interactions) to Perform action, Switch: Toggle, with the subwoofer's Connection switch as the target. On a group subwoofer, the badge shows its subwoofers together.",
        selector: { select: { mode: "dropdown", options: BLUETOOTH.map(([value, label]) => ({ value, label })) } },
      },
      {
        name: "driver_ring", label: "Driver ring",
        helper: "In the active preset's color, or the volume threshold's color.",
        selector: { boolean: {} },
      },
      {
        name: "standby_badge", label: "Standby mode badge",
        helper: "A letter on the driver for the standby mode: A (Auto), O (On) or T (Trigger).",
        selector: { boolean: {} },
      },
      {
        name: "vibration", label: "Shake when the volume or preset changes",
        helper: "The driver shakes harder at a higher volume. It stays still for anyone who has reduced motion turned on.",
        selector: { boolean: {} },
      },
    ];
    this._form.data = { finish_extent: c.finish_extent ?? "card", features_style: c.features_style ?? "match", vibration: c.vibration !== false, bluetooth: c.bluetooth ?? "show", standby_badge: !!c.standby_badge, driver_ring: c.driver_ring !== false };
    const label = RANDOMIZE_LABEL[c.finish];
    this.shadowRoot.getElementById("row").style.display = label ? "" : "none";
    this.shadowRoot.getElementById("randomize").textContent = label ?? "";
  }

  _update(changes) {
    this._config = explicit({ ...this._config, ...changes });
    this._render();
    this._fire();
  }

  _fire() {
    fire(this, "config-changed", { config: this._config });
  }
}

// Material Design Icons used by the panel editor
const MDI = {
  plus: "M19,13H13V19H11V13H5V11H11V5H13V11H19V13Z",
  left: "M20,11V13H8L13.5,18.5L12.08,19.92L4.16,12L12.08,4.08L13.5,5.5L8,11H20Z",
  right: "M4,11V13H16L10.5,18.5L11.92,19.92L19.84,12L11.92,4.08L10.5,5.5L16,11H4Z",
  delete: "M19,4H15.5L14.5,3H9.5L8.5,4H5V6H19M6,19A2,2 0 0,0 8,21H16A2,2 0 0,0 18,19V7H6V19Z",
  copy: "M19,21H8V7H19M19,5H8A2,2 0 0,0 6,7V21A2,2 0 0,0 8,23H19A2,2 0 0,0 21,21V7A2,2 0 0,0 19,5M16,1H4A2,2 0 0,0 2,3V17H4V3H16V1Z",
};

/** The tile card's editor (without the options the SVS card sets), once loaded. */
async function createTileEditor(entity) {
  const helpers = await window.loadCardHelpers();
  helpers.createCardElement({ type: "tile", entity });
  await customElements.whenDefined("hui-tile-card");
  const original = await customElements.get("hui-tile-card").getConfigElement();
  const type = tileEditorType();
  return type ? document.createElement(type) : original;
}

/**
 * The panel card's editor, laid out like Home Assistant's stack card editor:
 * a tab for the card itself (the SVS Subwoofer card's editor, plus how the
 * rows open), and a tab for each subwoofer row, which is edited like any
 * tile card (name, state content, features). The plus button adds a
 * subwoofer; a subwoofer's tab can move it or remove it.
 */
class SvsPanelCardEditor extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this.shadowRoot.innerHTML = `
      <style>
        h3 { margin: 24px 0 4px; font-size: var(--ha-font-size-l, 16px); font-weight: 500; }
        .hint { margin: 0 0 8px; color: var(--secondary-text-color); font-size: var(--ha-font-size-s, 12px); }
        ha-expansion-panel .hint { margin: 8px 0 0; }
        ha-expansion-panel + ha-expansion-panel { margin-top: 8px; }
        .toolbar { display: flex; align-items: center; gap: 4px; border-bottom: 1px solid var(--divider-color); margin-bottom: 16px; }
        .tabs { display: flex; flex: 1; gap: 4px; overflow-x: auto; }
        .tab {
          border: 0; background: none; padding: 12px 16px; cursor: pointer; white-space: nowrap;
          color: var(--secondary-text-color); font: inherit; font-weight: 500; border-bottom: 2px solid transparent;
        }
        .tab[aria-selected="true"] { color: var(--primary-color); border-bottom-color: var(--primary-color); }
        .tab:focus-visible { outline: 2px solid var(--primary-color); outline-offset: -2px; }
        .row-options { display: flex; align-items: center; justify-content: flex-end; gap: 4px; margin-bottom: 8px; }
        .row-options .buttons { display: flex; gap: 4px; }
        ha-form { display: block; margin-top: 24px; }
      </style>
      <ha-expansion-panel outlined header="Card">
        <div id="style"></div>
      </ha-expansion-panel>
      <ha-expansion-panel outlined header="Main subwoofer">
        <p class="hint">Recommended: a subwoofer group, so the card controls all of its subwoofers together.</p>
        <div id="card"></div>
      </ha-expansion-panel>
      <h3>Subwoofers in the collapsible section</h3>
      <p class="hint">Recommended: the group's member subwoofers, so each one can also be adjusted on its own. Each numbered tab is one subwoofer; the plus button adds one.</p>
      <div id="rows"></div>
      <div class="toolbar">
        <div class="tabs" role="tablist" aria-label="Subwoofers in the collapsible section"></div>
        <ha-icon-button id="add"></ha-icon-button>
      </div>
      <div id="body"></div>`;
    this._cardSlot = this.shadowRoot.getElementById("card");
    this._styleSlot = this.shadowRoot.getElementById("style");
    this._rowsSlot = this.shadowRoot.getElementById("rows");
    this._tabs = this.shadowRoot.querySelector(".tabs");
    this._body = this.shadowRoot.getElementById("body");
    const add = this.shadowRoot.getElementById("add");
    add.path = MDI.plus;
    add.label = "Add a subwoofer";
    add.addEventListener("click", () => this._select("add"));
    this._selected = 0;
  }

  set hass(hass) {
    this._hass = hass;
    if (this._cardEditor) this._cardEditor.hass = hass;
    if (this._styleEditor) this._styleEditor.hass = hass;
    if (this._rowsForm) this._rowsForm.hass = hass;
    if (this._addForm) this._addForm.hass = hass;
    if (this._memberEditor) this._memberEditor.hass = withSubwooferAttributes(hass, this._member?.entity);
    if (!this._built) this._show();
  }

  set lovelace(lovelace) {
    this._lovelace = lovelace;
    if (this._cardEditor) this._cardEditor.lovelace = lovelace;
    if (this._memberEditor) this._memberEditor.lovelace = lovelace;
  }

  setConfig(config) {
    // The configuration this editor just sent comes back here: nothing to redraw
    if (this._config && JSON.stringify(config) === JSON.stringify(this._config)) return;
    this._config = config;
    this._show();
  }

  get _members() {
    return (this._config?.members ?? []).filter((m) => m && typeof m === "object" && m.entity);
  }

  _renderTabs() {
    // Numbered, like the vertical stack card's tabs
    this._tabs.replaceChildren(...this._members.map((m, i) => {
      const tab = document.createElement("button");
      tab.type = "button";
      tab.className = "tab";
      tab.setAttribute("role", "tab");
      tab.setAttribute("aria-selected", String(this._selected === i));
      tab.textContent = String(i + 1);
      tab.title = m.name || defaultMemberNames(this._hass, [m.entity])[m.entity] || m.entity;
      tab.addEventListener("click", () => this._select(i));
      return tab;
    }));
  }

  _select(key) {
    this._selected = key;
    this._showBody();
  }

  _show() {
    if (!this._config || !this._hass) return;
    this._built = true;
    this._showCard();
    this._showBody();
  }

  _showBody() {
    if (typeof this._selected === "number" && !this._members[this._selected]) {
      this._selected = this._members.length ? 0 : "add";
    }
    this._renderTabs();
    this._memberEditor = undefined;
    if (this._selected === "add") this._showAdd();
    else this._showMember(this._selected);
  }

  // Above the tabs, two collapsed sections with the SVS Subwoofer card's
  // editor split in two: the Card (its SVS style options) and the Main
  // subwoofer (the tile card's options). Below them, how the collapsible
  // section opens.
  _showCard() {
    if (!this._cardEditor) {
      this._styleEditor = document.createElement(EDITOR_TYPE);
      this._styleEditor.part = "style";
      this._cardEditor = document.createElement(EDITOR_TYPE);
      this._cardEditor.part = "tile";
      // The main subwoofer's volume settings can be copied to every row
      this._cardEditor.addEventListener("edit-sub-element", (ev) => {
        const feature = ev.detail?.config;
        panelVolume = feature?.type === "custom:svs-subwoofer-volume" ? {
          key: JSON.stringify(feature),
          members: () => this._members.length,
          copyTo: (volume) => this._copyVolumeToMembers(volume),
        } : null;
      });
      for (const editor of [this._styleEditor, this._cardEditor]) {
        editor.addEventListener("config-changed", (ev) => {
          ev.stopPropagation();
          const keep = Object.fromEntries(PANEL_KEYS.filter((k) => k in this._config).map((k) => [k, this._config[k]]));
          this._fire({ ...ev.detail.config, ...keep, type: this._config.type });
          // Editors update their fields only when handed their configuration
          // back (Home Assistant does this for a card's own editor); both
          // halves show the same card
          this._styleEditor.setConfig(ev.detail.config);
          this._cardEditor.setConfig(ev.detail.config);
        });
      }
      this._rowsForm = document.createElement("ha-form");
      this._rowsForm.computeLabel = (s) => s.label;
      this._rowsForm.computeHelper = (s) => s.helper;
      this._rowsForm.addEventListener("value-changed", (ev) => {
        ev.stopPropagation();
        const v = ev.detail.value;
        this._fire({ ...this._config, members_toggle: v.members_toggle !== false, members_open: v.members_open !== false });
        this._renderRowsForm();
      });
      this._styleSlot.replaceChildren(this._styleEditor);
      this._cardSlot.replaceChildren(this._cardEditor);
      this._rowsSlot.replaceChildren(this._rowsForm);
    }
    const card = { ...this._config };
    for (const key of PANEL_KEYS) delete card[key];
    for (const editor of [this._styleEditor, this._cardEditor]) {
      editor.hass = this._hass;
      if (this._lovelace) editor.lovelace = this._lovelace;
      editor.setConfig(card);
    }
    this._renderRowsForm();
  }

  // The main subwoofer's volume settings on every row: each row's volume
  // feature is replaced (or added)
  _copyVolumeToMembers(volume) {
    const members = this._members.map((member) => {
      const features = [...(member.features ?? [])];
      const at = features.findIndex((f) => f.type === "custom:svs-subwoofer-volume");
      if (at >= 0) features[at] = JSON.parse(JSON.stringify(volume));
      else features.push(JSON.parse(JSON.stringify(volume)));
      return { ...member, features };
    });
    this._fire({ ...this._config, members });
    this._showBody();
  }

  _renderRowsForm() {
    this._rowsForm.hass = this._hass;
    this._rowsForm.schema = [
      {
        name: "members_toggle", label: "Tap the card to toggle the collapsible section",
        helper: "While this is on, a tap on the card does this instead of its Tap behavior (under Interactions). Icon tap behavior still works.",
        selector: { boolean: {} },
      },
      ...(this._config.members_toggle === false ? [] : [
        { name: "members_open", label: "Show the collapsible section at load", selector: { boolean: {} } },
      ]),
    ];
    this._rowsForm.data = { members_toggle: this._config.members_toggle !== false, members_open: this._config.members_open !== false };
  }

  // Adding a subwoofer: the subwoofers not yet in the panel, by name
  _showAdd() {
    if (!this._addForm) {
      this._addForm = document.createElement("ha-form");
      this._addForm.computeLabel = (s) => s.label;
      this._addForm.addEventListener("value-changed", (ev) => {
        ev.stopPropagation();
        const entity = ev.detail.value.entity;
        if (!entity) return;
        const members = [...this._members, newMember(entity)];
        this._selected = members.length - 1;
        this._fire({ ...this._config, members });
        this._showBody();
      });
    }
    const taken = new Set(this._members.map((m) => m.entity));
    const options = sortPairs(subwoofers(this._hass)).filter(([id]) => !taken.has(id)).map(([value, label]) => ({ value, label }));
    this._addForm.hass = this._hass;
    this._addForm.schema = [{ name: "entity", label: "Subwoofer to add", selector: { select: { mode: "dropdown", options } } }];
    this._addForm.data = {};
    this._body.replaceChildren(this._addForm);
  }

  // A subwoofer's row: edited like a tile card, with buttons to copy the
  // card's volume settings, duplicate, move or remove it
  async _showMember(index) {
    const member = this._members[index];
    this._member = member;
    const options = document.createElement("div");
    options.className = "row-options";
    const buttons = document.createElement("div");
    buttons.className = "buttons";
    const button = (path, label, disabled, onClick) => {
      const b = document.createElement("ha-icon-button");
      b.path = path;
      b.label = label;
      b.disabled = disabled;
      b.addEventListener("click", onClick);
      return b;
    };
    const update = (members, selected) => {
      this._selected = selected;
      this._fire({ ...this._config, members });
      this._showBody();
    };
    const move = (step) => {
      const members = [...this._members];
      const [item] = members.splice(index, 1);
      members.splice(index + step, 0, item);
      update(members, index + step);
    };
    // Duplicate: the row as it is now, for the next subwoofer not yet in the
    // panel (by name), so only the entity needs changing, if anything
    const duplicate = () => {
      const taken = new Set(this._members.map((m) => m.entity));
      const next = sortPairs(subwoofers(this._hass)).map(([id]) => id).find((id) => !taken.has(id));
      const copy = JSON.parse(JSON.stringify(this._members[index]));
      delete copy.name;
      if (next) copy.entity = next;
      const members = [...this._members];
      members.splice(index + 1, 0, copy);
      update(members, index + 1);
    };
    buttons.append(
      button(MDI.copy, "Duplicate", false, duplicate),
      button(MDI.left, "Move before", index === 0, () => move(-1)),
      button(MDI.right, "Move after", index === this._members.length - 1, () => move(1)),
      button(MDI.delete, "Remove this subwoofer", false, () => {
        const members = this._members.filter((_, i) => i !== index);
        update(members, Math.max(0, index - 1));
      }),
    );
    options.append(buttons);
    this._body.replaceChildren(options);
    const editor = await createTileEditor(member.entity);
    if (this._selected !== index) return;  // another tab was chosen meanwhile
    // Only single subwoofers' volumes in the entity picker
    editor.svsEntities = svsVolumes(this._hass, false);
    // This row's volume settings, when opened, offer the main subwoofer's
    editor.addEventListener("edit-sub-element", (ev) => {
      const feature = ev.detail?.config;
      panelVolume = feature?.type === "custom:svs-subwoofer-volume" ? {
        key: JSON.stringify(feature),
        volume: () => (this._config.features ?? []).find((f) => f.type === "custom:svs-subwoofer-volume"),
      } : null;
    });
    editor.addEventListener("config-changed", (ev) => {
      ev.stopPropagation();
      const next = { ...ev.detail.config };
      delete next.type;
      delete next.show_entity_picture;
      const members = [...this._members];
      members[index] = next;
      this._member = next;
      this._fire({ ...this._config, members });
      // The tile editor shows a change (a removed state content, an added
      // feature) only once its configuration is handed back
      editor.setConfig(ev.detail.config);
      if (ev.detail.config.entity !== member.entity) editor.hass = withSubwooferAttributes(this._hass, ev.detail.config.entity);
    });
    editor.hass = withSubwooferAttributes(this._hass, member.entity);
    if (this._lovelace) editor.lovelace = this._lovelace;
    editor.setConfig(tileConfig({ ...member, type: "tile" }));
    this._memberEditor = editor;
    this._body.append(editor);
  }

  _fire(config) {
    this._config = config;
    fire(this, "config-changed", { config });
  }
}

/**
 * The configuration as the editor saves it: finish and vibration written
 * out, and the pattern only for a finish that has one.
 */
function explicit(config) {
  const c = { ...config };
  c.finish = FINISHES.some(([id]) => id === c.finish) ? c.finish : "none";
  c.vibration = c.vibration !== false;
  c.bluetooth = BLUETOOTH.some(([id]) => id === c.bluetooth) ? c.bluetooth : "show";
  c.standby_badge = !!c.standby_badge;
  c.driver_ring = c.driver_ring !== false;
  if (c.finish === "none") {
    delete c.pattern;
    delete c.finish_extent;
    delete c.features_style;
  } else {
    c.pattern = Number.isFinite(c.pattern) ? c.pattern : DEFAULT_PATTERN;
    c.finish_extent = FINISH_EXTENTS.some(([id]) => id === c.finish_extent) ? c.finish_extent : "card";
    c.features_style = FEATURES_STYLES.some(([id]) => id === c.features_style) ? c.features_style : "match";
  }
  return c;
}

// ---------------------------------------------------------------------------
// Registration
// ---------------------------------------------------------------------------
const define = (name, cls) => {
  if (!customElements.get(name)) customElements.define(name, cls);
};

if (!customElements.get(CARD_TYPE)) {
  define("svs-subwoofer-presets", SvsPresetButtons);
  define("svs-subwoofer-presets-editor", SvsPresetButtonsEditor);
  define("svs-subwoofer-volume", SvsVolume);
  define("svs-subwoofer-volume-editor", SvsVolumeEditor);
  define("svs-subwoofer-standby", SvsStandby);
  define(CARD_TYPE, SvsCard);
  define(EDITOR_TYPE, SvsCardEditor);
  define(PANEL_TYPE, SvsPanelCard);
  define(PANEL_EDITOR_TYPE, SvsPanelCardEditor);

  const supports = (role) => (hass, context) => isSvs(hass, context?.entity_id) && !!sibling(hass, context.entity_id, role);
  window.customCardFeatures = window.customCardFeatures || [];
  window.customCardFeatures.push(
    { type: "svs-subwoofer-presets", name: "SVS Subwoofer presets", isSupported: supports("preset"), configurable: true },
    { type: "svs-subwoofer-volume", name: "SVS Subwoofer volume", isSupported: supports("volume"), configurable: true },
    { type: "svs-subwoofer-standby", name: "SVS Subwoofer standby mode", isSupported: supports("standby") },
  );

  window.customCards = window.customCards || [];
  window.customCards.push({
    type: CARD_TYPE,
    name: "SVS Subwoofer",
    description: "A tile card for an SVS subwoofer or subwoofer group, with an optional SVS cabinet finish.",
    preview: true,
    documentationURL: "https://github.com/dangerouslaser/svs-subwoofer-ha#dashboard-card",
  }, {
    type: PANEL_TYPE,
    name: "SVS Subwoofer panel (prototype)",
    description: "The SVS Subwoofer card with rows for chosen subwoofers below it, on one surface.",
    preview: true,
  });
  console.info(`%c SVS SUBWOOFER CARD %c ${VERSION} `, "color: #fff; background: #555; font-weight: bold", "color: #fff; background: #c8102e");
}
