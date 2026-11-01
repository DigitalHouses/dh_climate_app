"use strict";
// DH Climate Explorer: one object tree; configuration writes are isolated in editor.js.
const $ = (id) => document.getElementById(id);
let snapshot = null;
let locale = (navigator.language || "en").toLowerCase().startsWith("ru") ? "ru" : "en";
let dictionary = {};
let selection = {kind:"system"};
let nodes = [];
let expanded = new Set(["system|||", "home|||", "rooms|||"]);
let inspectorOpen = false;
let explorerOpen = true;
let streamConnected = false;
let weatherCatalog = null;
let weatherCatalogAt = 0;
let weatherCatalogLoading = null;

async function loadWeatherCatalog() {
  if (weatherCatalogLoading) return weatherCatalogLoading;
  if (weatherCatalog && Date.now() - weatherCatalogAt < 30000)
    return weatherCatalog;
  weatherCatalogLoading = (async () => {
    try {
      const response = await fetch("api/entities", {cache:"no-store",
        credentials:"same-origin"});
      if (!response.ok) return null;
      const catalog = await response.json();
      if (!Array.isArray(catalog.entities)) return null;
      weatherCatalog = catalog;
      weatherCatalogAt = Date.now();
      if (["weather_priorities","weather_sources","season"].includes(selection.kind))
        render();
      return catalog;
    } catch (_) { return null; }
    finally { weatherCatalogLoading = null; }
  })();
  return weatherCatalogLoading;
}
let explorerWidth = 275;
let menuReturnFocus = null;

const t = (key) => dictionary[key] || key;
const unknown = () => t("unknown");
const display = (v) => v === null || v === undefined || v === "" ? "—" : String(v);
const statusText = (v) => v === null || v === undefined ? unknown() : t(String(v));
const technical = (v) => v === null || v === undefined ? "—" : String(v).toUpperCase();
const severity = (v) => v === "healthy" ? "good" : v === "critical" ? "bad" : v === "degraded" ? "warn" : "muted";
const number = (v, unit = "") => v === null || v === undefined || !Number.isFinite(Number(v))
  ? "—" : new Intl.NumberFormat(locale, {minimumFractionDigits:1, maximumFractionDigits:1}).format(Number(v)) + unit;
const keyOf = (item) => [item.kind, item.room || "", item.resource || "", item.id || ""].join("|");
const selectedKey = () => keyOf(selection);
const roomById = (id) => (snapshot?.rooms || []).find(r => r.id === id) ||
  window.DHClimateEditor?.previewRoom(id);
const resourceById = (id) => (snapshot?.home.resources || []).find(r => r.id === id);
const deviceById = (roomId, id) => roomById(roomId)?.devices.find(d => d.entity_id === id);
const observedText = (entity) => (!snapshot?.app.ha_connected || !entity?.available) ? unknown() : display(entity.state);
const demandValue = (item) => item?.active === true ? t("on") : item?.active === false ? t("off") : unknown();
const withOverride = (kind, id, fallback) =>
  window.DHClimateEditor?.displayName(kind,id,locale,fallback) || fallback;
const namedRoom = room => withOverride("room",room?.id,
  room?.friendly_name || room?.name || room?.id || "—");
const namedEntity = (entity, fallback = null) => {
  const id = entity?.entity_id || fallback;
  return withOverride("entity",id,entity?.friendly_name || id || "—");
};
const namedResource = resource => withOverride("resource",resource?.id,
  t(resource?.id || "") === (resource?.id || "")
    ? technical(resource?.id) : t(resource.id));
const namedPart = (resource,type,part) =>
  withOverride("part",resource+":"+type+":"+part.id,part.name);
const namedProvider = provider => withOverride("provider",provider.id,
  provider.friendly_name || provider.entity_id || provider.id);
const namedWeatherSensor = (provider,quantity) =>
  withOverride("weather_sensor",provider.id+"."+quantity,
    t(quantity)+" · "+namedProvider(provider));
const namedOutdoorSensor = sensor => withOverride("outdoor_sensor",sensor.id,
  sensor.friendly_name || sensor.entity_id || sensor.id);

function dom(tag, cls, text) {
  const el = document.createElement(tag);
  if (cls) el.className = cls;
  if (text !== undefined && text !== null) el.textContent = String(text);
  return el;
}
function add(parent, ...items) { items.forEach(x => { if (x) parent.append(x); }); return parent; }
function paragraph(value, cls = "") { return dom("p", cls, value); }
function title(value) { return dom("h2", "page-title", value); }
function heading(value) { return dom("h3", "section-heading", value); }
function row(label, value) { return add(dom("div", "kv"), dom("span", "label", label), dom("span", "kv-value", value)); }
function stat(label, value, tone = "") {
  return add(dom("div", "stat"), dom("div", "stat-label", label), dom("div", "stat-value " + tone, value));
}
function stats(...items) { return add(dom("div", "stats"), ...items); }
function card(label, ...items) {
  const box = dom("section", "card");
  if (label) box.append(heading(label));
  return add(box, ...items);
}
function clickable(label, meta, onClick) {
  const b = add(dom("button", "click-row"), dom("span", "row-main", label), dom("span", "row-meta", meta || ""));
  b.type = "button"; b.onclick = onClick; return b;
}
function listOrEmpty(children, emptyKey = "not_configured") {
  const box = add(dom("div", "list"), ...children);
  if (!children.length) box.append(paragraph(t(emptyKey), "subtle"));
  return box;
}

function node(kind, label, icon, children = [], fields = {}) {
  return {kind, label, icon, children, ...fields};
}
function buildTree(data) {
  const rooms = window.DHClimateEditor?.previewRooms(data?.rooms || []) || data?.rooms || [];
  const resources = [...(data?.home.resources || [])];
  // Heating source / VRF are configured resources even without telemetry.
  if (data?.home.heating_source && !resources.some(r => r.id === data.home.heating_source))
    resources.push({id:data.home.heating_source, signals:[], pumps:[], circuits:[]});
  if (data?.home.vrf_enabled === true && !resources.some(r => r.id === "vrf"))
    resources.push({id:"vrf", signals:[], pumps:[], circuits:[]});
  const roomNodes = rooms.map(room => {
    const sensors = ["temperature", "humidity", "window"].flatMap(role =>
      (room.sensors?.[role] || []).map(sensor =>
        node("sensor", namedEntity(sensor), "◉", [], {room:room.id, id:sensor.entity_id,
          role, haName:sensor.friendly_name, technicalId:sensor.entity_id})
      )
    );
    const devices = (room.devices || []).map(device =>
      node("device", namedEntity(device.observed, device.entity_id), "⚙", [],
        {room:room.id, id:device.entity_id,haName:device.observed?.friendly_name,
          technicalId:device.entity_id})
    );
    const children = [
      node("thermostat", t("room_thermostat"), "◉", [], {room:room.id, id:room.id}),
    ];
    if (sensors.length) children.push(node("sensors", t("sensors"), "▤", sensors, {room:room.id, id:room.id}));
    if (devices.length) children.push(node("devices", t("devices"), "▤", devices, {room:room.id, id:room.id}));
    return node("room", namedRoom(room), "▱", children,
      {id:room.id, health:room.health,haName:room.friendly_name,
        sourceName:room.name,technicalId:room.id});
  });
  const resourceNodes = resources.map(resource => {
    const pumps = (resource.pumps || []).map(part =>
      node("part", namedPart(resource.id,"pumps",part), "◉", [],
        {resource:resource.id, partType:"pumps",id:part.id,sourceName:part.name,technicalId:part.id})
    );
    const circuits = (resource.circuits || []).map(part =>
      node("part", namedPart(resource.id,"circuits",part), "◉", [],
        {resource:resource.id, partType:"circuits",id:part.id,sourceName:part.name,technicalId:part.id})
    );
    const children = [];
    if (pumps.length) children.push(node("parts", t("pumps"), "▤", pumps, {resource:resource.id, partType:"pumps", id:resource.id}));
    if (circuits.length) children.push(node("parts", t("circuits"), "▤", circuits, {resource:resource.id, partType:"circuits", id:resource.id}));
    return node("resource", namedResource(resource), "▱", children,
      {id:resource.id,technicalId:resource.id});
  });
  const weather = data?.weather || {};
  const providerNodes = (weather.providers || []).map(p =>
    node("provider", namedProvider(p), "☁", [
      ...["temperature","humidity"].map(quantity=>
        node("weather_sensor",namedWeatherSensor(p,quantity),
          quantity==="temperature"?"🌡":"💧",[],
          {id:p.id+"."+quantity,provider:p.id,quantity,technicalId:p.id+"."+quantity,
            sourceName:p.entity_id}))
    ],{id:p.id,technicalId:p.id,sourceName:p.entity_id,haName:p.friendly_name})
  );
  const physicalNodes = (weather.physical_sensors || []).map(s =>
    node("outdoor_sensor",namedOutdoorSensor(s),s.quantity==="temperature"?"🌡":"💧",
      [],{id:s.id,technicalId:s.id,sourceName:s.entity_id,haName:s.friendly_name})
  );
  const weatherChildren = [
    node("weather_sources",t("weather_sources_and_sensors"),"▤",
      weather.source_model==="sensors"?
        [...providerNodes,...physicalNodes]:[]),
    node("weather_priorities",t("weather_sensor_priorities"),"≡"),
    node("season", t("season"), "◷"),
  ];
  return [node("system", t("system"), "◈", [
    node("weather", t("weather"), "☁",weatherChildren),
    node("home", t("home"), "⌂", [
      node("resources", t("resources"), "▤", resourceNodes),
      node("rooms", t("rooms"), "▤", roomNodes),
    ]),
  ])];
}
function findPath(target, collection = nodes, ancestors = []) {
  for (const n of collection) {
    const path = [...ancestors, n];
    if (keyOf(n) === keyOf(target)) return path;
    const nested = findPath(target, n.children || [], path);
    if (nested) return nested;
  }
  return null;
}
function navigate(item) {
  closeContextMenu();
  if (window.DHClimateEditor && !window.DHClimateEditor.onNavigate()) return;
  selection = {kind:item.kind, id:item.id || null, room:item.room || null,
    resource:item.resource || null, partType:item.partType || null};
  if (["weather_sources","weather_priorities","season"].includes(item.kind)) {
    if (item.kind !== "season")
      window.DHClimateEditor?.enterWeatherSection?.(item.kind);
    void loadWeatherCatalog();
  }
  const path = findPath(selection);
  if (path) path.slice(0, -1).forEach(n => expanded.add(keyOf(n)));
  render();
  if (window.matchMedia("(max-width: 560px)").matches) {
    explorerOpen = false; renderPanels();
  }
}
function renderTree() {
  nodes = buildTree(snapshot);
  const tree = $("tree"); tree.replaceChildren();
  function draw(item, container, depth = 0) {
    const k = keyOf(item);
    const expandable = item.children.length > 0;
    const open = expanded.has(k);
    const wrap = dom("div", "tree-group");
    const line = dom("div", "tree-item" + (k === selectedKey() ? " selected" : ""));
    const toggle = dom("button", "tree-disclosure", expandable ? (open ? "⌄" : "›") : "");
    toggle.type = "button";
    toggle.disabled = !expandable;
    toggle.setAttribute("aria-label", (open ? t("collapse") : t("expand")) + " " + item.label);
    if (expandable) toggle.setAttribute("aria-expanded", String(open));
    toggle.onclick = () => {
      if (expanded.has(k)) expanded.delete(k); else expanded.add(k);
      renderTree();
    };
    const select = dom("button", "tree-label");
    select.type = "button";
    select.title = item.id && item.id !== item.label
      ? item.label + "\n" + item.id : item.label;
    if (k === selectedKey()) select.setAttribute("aria-current", "page");
    add(select, dom("span", "tree-icon", item.icon), dom("span", "tree-text", item.label));
    select.onclick = () => navigate(item);
    if (["device","sensor"].includes(item.kind) ||
        window.DHClimateEditor?.menuActions(item)?.length)
      select.setAttribute("aria-haspopup", "menu");
    line.append(toggle, select);
    line.oncontextmenu = event => {
      event.preventDefault();
      openContextMenu(item, event.clientX, event.clientY, select);
    };
    select.onkeydown = event => {
      if (event.key === "ContextMenu" || (event.shiftKey && event.key === "F10")) {
        event.preventDefault();
        const bounds = select.getBoundingClientRect();
        openContextMenu(item, bounds.left + 18, bounds.bottom, select);
      }
    };
    if (item.health && item.health !== "healthy") line.append(dom("span", "tree-node-health " + severity(item.health), "●"));
    wrap.append(line);
    if (expandable && open) {
      const branch = dom("div", "tree-branch");
      item.children.forEach(child => draw(child, branch, depth + 1));
      wrap.append(branch);
    }
    container.append(wrap);
  }
  nodes.forEach(n => draw(n, tree));
}
function renderBreadcrumbs() {
  const bc = $("breadcrumbs"); bc.replaceChildren();
  const path = findPath(selection) || nodes.slice(0, 1);
  path.forEach((item, index) => {
    if (index) bc.append(dom("span", "breadcrumb-divider", "›"));
    const b = dom("button", "breadcrumb-link", item.label);
    b.type = "button"; b.onclick = () => navigate(item);
    bc.append(b);
  });
}
function renderPanels() {
  $("explorer").hidden = !explorerOpen;
  $("explorer-resizer").hidden = !explorerOpen;
  $("inspector").hidden = !inspectorOpen;
  if (!explorerOpen) closeContextMenu();
  $("toggle-explorer").setAttribute("aria-pressed", String(explorerOpen));
  $("toggle-inspector").setAttribute("aria-pressed", String(inspectorOpen));
}
function closeContextMenu(restoreFocus = false) {
  const menu = $("context-menu");
  if (!menu) return;
  const previous = menuReturnFocus;
  menuReturnFocus = null;
  menu.hidden = true;
  menu.replaceChildren();
  if (restoreFocus && previous?.isConnected) previous.focus();
}
function openContextMenu(item, x, y, source) {
  closeContextMenu();
  const menu = $("context-menu");
  // Navigation and expand/collapse are already direct tree interactions.
  // A context menu exists only when the object has an actual action.
  const actions = [];
  const entity = ["device","sensor"].includes(item.kind) ? item.id : null;
  if (entity) actions.push({label:t("copy_entity"), run:async()=> {
    try { await navigator.clipboard.writeText(entity); } catch (_) { /* clipboard not available */ }
  }});
  const editorActions=window.DHClimateEditor?.menuActions(item) || [];
  if (editorActions.length) {
    if (actions.length) actions.push({separator:true});
    actions.push(...editorActions);
  }
  if (!actions.length) return;
  actions.forEach(action => {
    if (action.separator) { menu.append(dom("div", "context-menu-separator")); return; }
    const button = dom("button", "context-menu-action"+(action.destructive ? " destructive" : ""), action.label);
    button.type="button";
    button.setAttribute("role","menuitem");
    button.onclick=()=>{
      closeContextMenu();
      action.run();
    };
    menu.append(button);
  });
  menuReturnFocus=source;
  menu.hidden=false;
  const box=menu.getBoundingClientRect();
  const maxX=Math.max(4,window.innerWidth-box.width-8);
  const maxY=Math.max(4,window.innerHeight-box.height-8);
  menu.style.left=Math.max(4,Math.min(x,maxX))+"px";
  menu.style.top=Math.max(4,Math.min(y,maxY))+"px";
  menu.querySelector('[role="menuitem"]')?.focus();
}
function initExplorerWidth() {
  const min=190, max=1100;
  const pane=$("explorer"), divider=$("explorer-resizer");
  const limit=()=>Math.max(min,Math.min(max,window.innerWidth-320));
  const apply=width=>{
    explorerWidth=Math.max(min,Math.min(limit(),Math.round(width)));
    pane.style.setProperty("--explorer-width",explorerWidth+"px");
    divider.setAttribute("aria-valuenow",String(explorerWidth));
    divider.setAttribute("aria-valuemax",String(limit()));
  };
  try {
    const stored=Number(localStorage.getItem("dh-climate-explorer-width"));
    if (Number.isFinite(stored) && stored>=min) explorerWidth=stored;
  } catch (_) { /* private browsing */ }
  apply(explorerWidth);
  const save=()=>{
    try {localStorage.setItem("dh-climate-explorer-width",String(explorerWidth));} catch (_) {}
  };
  let dragging=false;
  const move=event=>{
    if (!dragging) return;
    apply(event.clientX-pane.getBoundingClientRect().left);
    event.preventDefault();
  };
  const stop=()=>{
    if (!dragging) return;
    dragging=false;
    document.body.classList.remove("resizing-explorer");
    window.removeEventListener("pointermove",move);
    window.removeEventListener("pointerup",stop);
    window.removeEventListener("pointercancel",stop);
    save();
  };
  divider.addEventListener("pointerdown",event=>{
    if (event.button !== 0) return;
    event.preventDefault();
    dragging=true;
    document.body.classList.add("resizing-explorer");
    window.addEventListener("pointermove",move);
    window.addEventListener("pointerup",stop);
    window.addEventListener("pointercancel",stop);
  });
  divider.onkeydown=event=>{
    const delta=event.key==="ArrowRight" ? (event.shiftKey?50:20)
      : event.key==="ArrowLeft" ? -(event.shiftKey?50:20) : 0;
    if (delta) {event.preventDefault(); apply(explorerWidth+delta); save();}
    if (event.key==="Home") {event.preventDefault();apply(min);save();}
  };
  divider.ondblclick=()=>{apply(275);save();};
  window.addEventListener("resize",()=>apply(explorerWidth));
}
document.addEventListener("pointerdown",event=>{
  const menu=$("context-menu");
  if (!menu.hidden && !menu.contains(event.target)) closeContextMenu();
});
document.addEventListener("keydown",event=>{
  const menu=$("context-menu");
  if (menu.hidden) return;
  if (event.key==="Escape") {
    event.preventDefault();closeContextMenu(true);return;
  }
  if (event.key==="ArrowDown" || event.key==="ArrowUp") {
    event.preventDefault();
    const items=[...menu.querySelectorAll('[role="menuitem"]')];
    const index=items.indexOf(document.activeElement);
    items[(index+(event.key==="ArrowDown"?1:-1)+items.length)%items.length]?.focus();
  }
});
window.addEventListener("blur",()=>closeContextMenu());

function problemsForRoom(id) {
  return (snapshot?.app.problems || []).filter(p => p.room_id === id);
}
function displayProblems(problems) {
  const out = dom("div", "list");
  if (!problems.length) { out.append(paragraph(t("no_problems"), "subtle")); return out; }
  problems.forEach(p => {
    const label = t("problem." + p.code);
    const item = dom("div", "problem");
    item.append(dom("strong", p.severity === "critical" ? "bad" : "warn",
      label.startsWith("problem.") ? p.code : label));
    if (p.entity_id) item.append(paragraph(p.entity_id, "mono subtle"));
    if (p.details) item.append(paragraph(p.details, "small subtle"));
    out.append(item);
  });
  return out;
}
function signalRows(signals) {
  return listOrEmpty((signals || []).map(signal => {
    const line = dom("div", "signal");
    const extra = [];
    if (signal.attributes?.temperature !== null && signal.attributes?.temperature !== undefined)
      extra.push(number(signal.attributes.temperature, " °C"));
    if (signal.attributes?.humidity !== null && signal.attributes?.humidity !== undefined)
      extra.push(number(signal.attributes.humidity, " %"));
    line.append(row(t(signal.role), observedText(signal) + (extra.length ? " · " + extra.join(" · ") : "")));
    const label = snapshot?.weather?.source_model==="sensors"
      ? (signal.original_entity_id?.startsWith("weather.")
          ? withOverride("weather_sensor",signal.entity_id,
              t(signal.role)+" · "+(signal.friendly_name || signal.entity_id))
          : withOverride("outdoor_sensor",signal.entity_id,
              signal.friendly_name || signal.entity_id))
      : signal.friendly_name;
    if (label) line.append(paragraph(label, "small"));
    line.append(paragraph(signal.entity_id, "mono subtle small"));
    return line;
  }));
}
function deviceLinks(room) {
  return listOrEmpty((room.devices || []).map(dev =>
    clickable(namedEntity(dev.observed),
      technical(dev.role) + " · " + technical(dev.device_type) + " · " + observedText(dev.observed),
      () => navigate({kind:"device", id:dev.entity_id, room:room.id}))), "no_devices");
}
function roomLinks() {
  return listOrEmpty((snapshot?.rooms || []).map(room =>
    clickable(namedRoom(room), number(room.temperature, " °C") + " · " + statusText(room.hvac_action),
      () => navigate({kind:"room", id:room.id}))), "no_rooms");
}
function resourceLinks() {
  const configured = [...(snapshot?.home.resources || [])];
  const source = snapshot?.home.heating_source;
  if (source && !configured.some(r => r.id === source)) configured.push({id:source});
  if (snapshot?.home.vrf_enabled === true && !configured.some(r => r.id === "vrf")) configured.push({id:"vrf"});
  return listOrEmpty(configured.map(resource =>
    clickable(namedResource(resource), t("resource"), () => navigate({kind:"resource", id:resource.id}))),
    "no_resource_signals");
}
function demandRows(items) {
  return listOrEmpty((items || []).map(d => row(technical(d.layer) + " · " + technical(d.direction),
    demandValue(d))), "not_configured");
}
function showSystem(main) {
  const app = snapshot.app;
  add(main, title(t("system")),
    stats(stat(t("health"), statusText(app.health), severity(app.health)),
      stat(t("ha_connection"), app.ha_connected ? t("online") : t("offline"), app.ha_connected ? "good" : "bad"),
      stat(t("rooms"), snapshot.rooms.length), stat(t("problems"), app.problems.length)),
    card(t("about"), row(t("version"), app.version), paragraph(t("read_only_info"), "subtle")),
    card(t("problems"), displayProblems(app.problems)));
}
function showWeather(main) {
  const w = snapshot.weather;
  add(main, title(t("weather")),
    stats(stat(t("temperature"), number(w.temperature, " °C")),
      stat(t("raw_temperature"), number(w.raw_temperature, " °C")),
      stat(t("avg24"), number(w.avg24, " °C")), stat(t("humidity"), number(w.humidity, " %"))),
    card(t("source"), row(t("temperature"), display(w.source)),
      row(t("humidity"), display(w.humidity_source)),
      row(t("weather_forecast_source"), display(w.condition_source)),
      row(t("condition"), statusText(w.condition)),
      row(t("precipitation"), number(w.precipitation_mm, " mm")),
      row(t("data_quality"), w.stale === null ? unknown() : w.stale ? t("stale") : t("current"))),
    card(t("temperature_sources"), signalRows((w.temperature_sources || []).map(e => ({...e, role:"temperature"})))),
    card(t("humidity_sources"), signalRows((w.humidity_sources || []).map(e => ({...e, role:"humidity"})))));
  main.append(paragraph(t("weather_priority_note"),"subtle small"));
}
function showProviders(main) {
  const w=snapshot.weather;
  const providers=(w.providers||[]).map(p=>
    clickable(namedProvider(p),p.entity_id,
      ()=>navigate({kind:"provider",id:p.id})));
  const physical=(w.physical_sensors||[]).map(p=>
    clickable(namedOutdoorSensor(p),p.entity_id,
      ()=>navigate({kind:"outdoor_sensor",id:p.id})));
  add(main,title(t("weather_sources_and_sensors")),
    card(t("weather_providers"),listOrEmpty(providers)),
    card(t("weather_physical"),listOrEmpty(physical)));
}
function showProvider(main) {
  const provider=(snapshot.weather.providers||[]).find(p=>p.id===selection.id);
  if(!provider)return showProviders(main);
  const sensorLinks=["temperature","humidity"].map(quantity=>
    clickable(namedWeatherSensor(provider,quantity),
      number(provider[quantity],quantity==="temperature"?" °C":" %"),
      ()=>navigate({kind:"weather_sensor",id:provider.id+"."+quantity})));
  add(main,
    title(namedProvider(provider)),
    paragraph(provider.entity_id,"mono subtle"),
    card(t("identification"),row(t("source"),provider.entity_id)),
    stats(stat(t("temperature"),number(provider.temperature," °C")),
      stat(t("humidity"),number(provider.humidity," %"))),
    card(t("sensors"),listOrEmpty(sensorLinks)));
}
function showWeatherSensor(main) {
  const [providerId,quantity]=String(selection.id||"").split(".");
  const provider=(snapshot.weather.providers||[]).find(p=>p.id===providerId);
  if(!provider)return showProviders(main);
  // Suggested ID applies when HA creates a new MQTT entity.
  // Existing entities retain their registry entity_id, not renamed on update.
  const suggested="sensor.dh_climate_app_weather_"+providerId+"_"+quantity;
  add(main,
    title(namedWeatherSensor(provider,quantity)),
    paragraph(selection.id,"mono subtle"),
    card(t("identification"),row(t("source"),provider.entity_id),
      row(t("suggested_entity_id"),suggested),
      paragraph(t("weather_existing_entity_id"),"subtle small")),
    stats(stat(t(quantity),number(provider[quantity],
      quantity==="temperature"?" °C":" %"))));
}
function showOutdoorPhysical(main) {
  const links=(snapshot.weather.physical_sensors||[]).map(s=>
    clickable(namedOutdoorSensor(s),s.entity_id,
      ()=>navigate({kind:"outdoor_sensor",id:s.id})));
  add(main,title(t("weather_physical")),
    card(t("weather_physical"),listOrEmpty(links)));
}
function showOutdoorSensor(main) {
  const sensor=(snapshot.weather.physical_sensors||[]).find(s=>s.id===selection.id);
  if(!sensor)return showOutdoorPhysical(main);
  add(main,title(namedOutdoorSensor(sensor)),
    paragraph(sensor.entity_id,"mono subtle"),
    card(t("identification"),row(t("source"),sensor.entity_id),
      row(t("role"),t(sensor.quantity))),
    stats(stat(t(sensor.quantity),
      number(sensor.value,sensor.quantity==="temperature"?" °C":" %"))));
}
function weatherSourceMetadata(id,quantity) {
  const w=snapshot?.weather || {};
  const physical=(w.physical_sensors||[]).find(s=>s.id===id);
  const provider=(w.providers||[]).find(p=>
    id===p.id+"."+quantity);
  const source=(w[quantity+"_sources"]||[]).find(s=>s.entity_id===id);
  const matching=(weatherCatalog?.entities||[]).find(s=>
    s.climate_source_id===id ||
    (physical && s.entity_id===physical.entity_id));
  const suggested=physical?.entity_id ||
    "sensor.dh_climate_app_weather_"+id.replace(".","_");
  const name=matching?.name || (
    physical?namedOutdoorSensor(physical):
    provider?namedWeatherSensor(provider,quantity):id
  );
  const value=source ? source.state : matching?.state;
  const valid=value!==null && value!==undefined &&
    value!=="" && value!=="unknown" && value!=="unavailable" &&
    Number.isFinite(Number(value));
  return {
    name, entityId:matching?.entity_id || suggested,
    value:valid?number(value,quantity==="temperature"?" °C":" %"):
      t("weather_unavailable"),
    valid,
  };
}
function showWeatherPriorities(main) {
  const w=snapshot.weather;
  const makeRows=quantity=>{
    const refs=w[quantity+"_sources"]||[];
    const lines=refs.map((s,i)=>{
      const item=weatherSourceMetadata(s.entity_id,quantity);
      const line=dom("div","weather-priority-readonly");
      add(line,dom("strong","",String(i+1)+"."),
        dom("div","weather-priority-readonly-name",item.name),
        dom("span",item.valid?"":"warn",item.value),
        paragraph(item.entityId,"mono subtle"));
      return line;
    });
    return listOrEmpty(lines);
  };
  add(main,title(t("weather_sensor_priorities")),
    paragraph(t("weather_priority_help"),"subtle small"),
    card(t("temperature_sources"),makeRows("temperature")),
    card(t("humidity_sources"),makeRows("humidity")));
  if (!window.DHClimateEditor?.canChange?.())
    main.append(paragraph(t("weather_readonly_priority"),"subtle small"));
}
// Temperature source provenance is presentation-only; never modifies the
// Engine's priority order, thresholds, or the authoritative manifest.
function seasonSourceNode(id) {
  const w = snapshot?.weather || {};
  const source = (w.temperature_sources || []).find(s => s.entity_id === id);
  const physical = (w.physical_sensors || []).find(s => s.id === id);
  const provider = (w.providers || []).find(p => id === p.id + ".temperature");
  const original = source?.original_entity_id ||
    ((id.startsWith("sensor.") || id.startsWith("weather.")) ? id : null);
  const registered = (weatherCatalog?.entities || []).find(e =>
    e.climate_source_id === id ||
    (id.startsWith("sensor.") && e.entity_id === id));
  const name = registered?.name ||
    (physical ? namedOutdoorSensor(physical) :
      provider ? namedWeatherSensor(provider,"temperature") :
      source?.friendly_name || id);
  const box = dom("div","season-source-item");
  box.append(paragraph(name,"season-source-name"));
  // Never pretend that a suggested MQTT entity_id is the one used in HA.
  const actualId = registered?.entity_id ||
    (id.startsWith("sensor.") ? id : null);
  if (actualId) box.append(paragraph(actualId,"mono subtle"));
  else if (id !== original) box.append(paragraph(id,"mono subtle"));
  if (original?.startsWith("weather."))
    box.append(paragraph(original+" → temperature","mono subtle"));
  else if (original && original !== actualId)
    box.append(paragraph(original,"mono subtle"));
  return box;
}
function showSeason(main) {
  const w = snapshot.weather;
  const avgSensor = (weatherCatalog?.entities || []).find(
    e => e.climate_avg24_sensor === true);
  const avgInfo = [
    paragraph(avgSensor?.name || t("season_avg_internal"),"season-source-name"),
    paragraph(t("season_avg_method"),"subtle small"),
  ];
  if (avgSensor?.entity_id)
    avgInfo.splice(1,0,paragraph(avgSensor.entity_id,"mono subtle"));
  const history = (w.avg24_input_sources || [])
    .filter(id => typeof id === "string" && id.length)
    .map(seasonSourceNode);
  const active = w.source
    ? seasonSourceNode(w.source)
    : paragraph(t("unknown"),"subtle");
  add(main, title(t("season")),
    stats(stat(t("season"),statusText(w.season)),
      stat(t("avg24"),number(w.avg24," °C"))),
    card(t("season_avg_sensor"),...avgInfo),
    card(t("season_current_source"),active,
      row(t("data_quality"),w.stale === null || w.stale === undefined
        ? unknown() : w.stale ? t("stale") : t("current"))),
    card(t("season_history_sources"),
      listOrEmpty(history,"season_history_empty"),
      paragraph(t("season_history_note"),"subtle small")),
    card(t("season_thresholds"),
      row(t("season_heat_threshold"),number(w.heat_threshold," °C")),
      row(t("season_cool_threshold"),number(w.cool_threshold," °C")),
      row(t("season_hysteresis"),number(w.season_hysteresis," °C"))),
    paragraph(t("season_info"),"subtle small"));
}
function showHome(main) {
  add(main, title(t("home")),
    card(t("home"), row(t("heating_source"), statusText(snapshot.home.heating_source)),
      row(t("vrf_enabled"), snapshot.home.vrf_enabled == null ? unknown() : snapshot.home.vrf_enabled ? t("yes") : t("no")),
      row(t("presence"), observedText(snapshot.home.presence)),
      row(t("night"), observedText(snapshot.home.night))),
    card(t("resources"), resourceLinks()), card(t("rooms"), roomLinks()));
}
function showResources(main) {
  add(main, title(t("resources")), card(t("resources"), resourceLinks()));
  const requests = (snapshot.demands || []).filter(d => ["boiler","central_heating","vrf"].includes(d.layer));
  if (requests.length) main.append(card(t("resource_requests"), demandRows(requests)));
}
function showResource(main) {
  const resource = resourceById(selection.id);
  if (!resource) {
    const configured = selection.id === snapshot.home.heating_source ||
      (selection.id === "vrf" && snapshot.home.vrf_enabled === true);
    if (!configured) return showResources(main);
    add(main, title(namedResource({id:selection.id})),
      paragraph(technical(selection.id), "mono subtle"),
      card(t("resource"), paragraph(t("no_resource_signals"), "subtle")));
    const matches = (snapshot.demands || []).filter(d => d.layer === selection.id);
    if (matches.length) main.append(card(t("resource_requests"), demandRows(matches)));
    return;
  }
  add(main, title(namedResource(resource)),
    paragraph(technical(resource.id), "mono subtle"),
    card(t("resource"), signalRows(resource.signals)));
  if (resource.pumps.length) main.append(card(t("pumps"), listOrEmpty(resource.pumps.map(p =>
    clickable(p.name, t("pump"), () => navigate({kind:"part",resource:resource.id,partType:"pumps",id:p.id}))))));
  if (resource.circuits.length) main.append(card(t("circuits"), listOrEmpty(resource.circuits.map(p =>
    clickable(p.name, t("circuit"), () => navigate({kind:"part",resource:resource.id,partType:"circuits",id:p.id}))))));
}
function showPart(main) {
  const resource = resourceById(selection.resource);
  const part = resource?.[selection.partType]?.find(p => p.id === selection.id);
  if (!part) return showResources(main);
  add(main, title(part.name), card(t(selection.partType === "pumps" ? "pump" : "circuit"),
    row(t("resource"), technical(selection.resource)), signalRows(part.signals)));
}
function showParts(main) {
  const parts = resourceById(selection.resource)?.[selection.partType] || [];
  add(main, title(t(selection.partType)), card(t("resources"),
    listOrEmpty(parts.map(p => clickable(p.name, t("resource"),
      () => navigate({kind:"part",resource:selection.resource,partType:selection.partType,id:p.id}))))));
}
function showRooms(main) { add(main, title(t("rooms")), card(t("rooms"), roomLinks())); }
function roomSensors(room) {
  const items = ["temperature","humidity","window"].flatMap(role =>
    (room.sensors?.[role] || []).map(entity => ({...entity, role})));
  return signalRows(items);
}
function showRoom(main) {
  const room = roomById(selection.id);
  if (!room) return showRooms(main);
  add(main, title(namedRoom(room)), paragraph(room.id, "mono subtle"),
    card(t("identification"),
      row(t("configuration_name"),room.name || "—"),
      row(t("ha_friendly_name"),room.friendly_name || "—"),
      row(t("ha_area"),window.DHClimateEditor?.roomAreaLabel(room.id) || "—")),
    stats(stat(t("temperature"), number(room.temperature, " °C")),
      stat(t("target"), number(room.target, " °C")),
      stat(t("humidity"), number(room.humidity, " %")),
      stat(t("health"), statusText(room.health), severity(room.health))),
    card(t("room_climate"),
      row(t("profile"), statusText(room.profile)), row(t("hvac_mode"), statusText(room.hvac_mode)),
      row(t("hvac_action"), statusText(room.hvac_action)), row(t("window"), statusText(room.window_state))),
    card(t("sensors"), roomSensors(room)),
    card(t("devices"), deviceLinks(room)),
    card(t("problems"), displayProblems(problemsForRoom(room.id))));
}
function showThermostat(main) {
  const room = roomById(selection.room);
  if (!room) return showRooms(main);
  add(main, title(t("room_thermostat")),
    paragraph(room.climate_entity, "mono subtle"),
    stats(stat(t("temperature"), number(room.temperature, " °C")),
      stat(t("target"), number(room.target, " °C"))),
    card(t("room_climate"), row(t("profile"), statusText(room.profile)),
      row(t("hvac_mode"), statusText(room.hvac_mode)), row(t("hvac_action"), statusText(room.hvac_action))));
}
function showDevices(main) {
  const room = roomById(selection.room);
  if (!room) return showRooms(main);
  add(main, title(t("devices")), card(namedRoom(room), deviceLinks(room)));
}
function showSensors(main) {
  const room = roomById(selection.room);
  if (!room) return showRooms(main);
  add(main, title(t("sensors")), card(namedRoom(room), roomSensors(room)));
}
function findSensor(room, id) {
  for (const role of ["temperature","humidity","window"])
    for (const sensor of room?.sensors?.[role] || [])
      if (sensor.entity_id === id) return {sensor, role};
  return null;
}
function showSensor(main) {
  const result = findSensor(roomById(selection.room), selection.id);
  if (!result) return showRooms(main);
  add(main, title(namedEntity(result.sensor)),
    paragraph(result.sensor.entity_id, "mono subtle"),
    card(t("identification"),
      row(t("ha_friendly_name"),result.sensor.friendly_name || "—")),
    card(t("sensor"), row(t("role"), t(result.role)),
      row(t("observed_state"), observedText(result.sensor)),
      row(t("availability"), result.sensor.available ? t("available") : t("unavailable")),
      row(t("last_updated"), display(result.sensor.last_updated))));
}
function showDevice(main) {
  const dev = deviceById(selection.room, selection.id);
  if (!dev) return showRooms(main);
  const action = dev.hvac_action == null ?
    (dev.observed?.available ? t("not_reported") : unknown()) : statusText(dev.hvac_action);
  add(main, title(namedEntity(dev.observed,dev.entity_id)),
    paragraph(dev.entity_id, "mono subtle"),
    card(t("identification"),
      row(t("ha_friendly_name"),dev.observed?.friendly_name || "—")),
    stats(stat(t("observed_state"), observedText(dev.observed)), stat(t("hvac_action"), action)),
    card(t("device"), row(t("role"), technical(dev.role)),
      row(t("device_type"), technical(dev.device_type)),
      row(t("resource"), display(dev.resource)),
      row(t("availability"), dev.observed?.available ? t("available") : t("unavailable")),
      row(t("last_updated"), display(dev.observed?.last_updated))),
    paragraph(t("no_physical_inference"), "notice"));
}
function renderInspector() {
  const pane = $("inspector");
  if (!inspectorOpen) { pane.replaceChildren(); return; }
  pane.replaceChildren(heading(t("inspector")));
  const path = findPath(selection);
  pane.append(dom("h3", "inspector-title", path?.at(-1)?.label || t("system")));
  let entity = null, updateTime = null;
  if (selection.kind === "room") {
    const room = roomById(selection.id);
    entity = room?.climate_entity;
    if (room) add(pane, row(t("room_id"), room.id), row(t("health"), statusText(room.health)));
  } else if (selection.kind === "thermostat") {
    entity = roomById(selection.room)?.climate_entity;
  } else if (selection.kind === "sensor") {
    entity = selection.id;
    updateTime = findSensor(roomById(selection.room), selection.id)?.sensor.last_updated;
  } else if (selection.kind === "device") {
    const dev = deviceById(selection.room, selection.id);
    entity = dev?.entity_id;
    updateTime = dev?.observed?.last_updated;
    if (dev) add(pane, row(t("role"), technical(dev.role)),
      row(t("device_type"), technical(dev.device_type)));
  }
  if (["provider","weather_sensor","outdoor_sensor"].includes(selection.kind)) {
    const w=snapshot.weather;
    if(selection.kind==="outdoor_sensor")
      entity=(w.physical_sensors||[]).find(s=>s.id===selection.id)?.entity_id;
    else {
      const providerId=String(selection.id||"").split(".")[0];
      entity=(w.providers||[]).find(p=>p.id===providerId)?.entity_id;
    }
  }
  if (entity) {
    pane.append(paragraph(entity, "mono source-id"));
    if (updateTime) pane.append(row(t("last_updated"), updateTime));
    const copy = dom("button", "secondary-button", t("copy_entity"));
    copy.type = "button";
    copy.onclick = async () => {
      try { await navigator.clipboard.writeText(entity); copy.textContent = t("copied"); }
      catch (_) { copy.textContent = entity; }
    };
    pane.append(copy);
  }
  pane.append(paragraph(t("inspector_note"), "subtle small"));
}
let restartRequested = false;
let restartError = "";
let restartDisconnected = false;

function renderRestartBanner() {
  const pending = !!window.DHClimateEditor?.needsRestart?.();
  const banner = $("restart-banner");
  banner.hidden = !pending;
  if (!pending) {
    restartRequested = false;
    restartError = "";
    restartDisconnected = false;
    return;
  }
  $("restart-heading").textContent = t("restart_heading");
  $("restart-details").textContent = t(
    restartRequested ? "restart_requested" : "restart_details",
  );
  const error = $("restart-error");
  error.hidden = !restartError;
  error.textContent = restartError;
  const button = $("restart-app");
  button.textContent = t("restart_button");
  button.disabled = restartRequested || !streamConnected;
}

async function restartApp() {
  if (restartRequested || !window.DHClimateEditor?.needsRestart?.()) return;
  if (!window.confirm(t("restart_confirm"))) return;
  restartRequested = true;
  restartDisconnected = false;
  restartError = "";
  renderRestartBanner();
  try {
    const response = await fetch("api/app/restart", {
      method:"POST", credentials:"same-origin",
      headers:{"Content-Type":"application/json",
        "X-Requested-With":"DHClimateExplorer"},
      body:JSON.stringify({confirm:"RESTART"}),
    });
    if (!response.ok) throw Error(t("restart_rejected") + " (HTTP " + response.status + ")");
    // 202 means queued, NOT that the new process is already running.
    // SSE reconnection + /api/config is what confirms completion.
  } catch (error) {
    restartRequested = false;
    restartError = error.message || t("restart_rejected");
    renderRestartBanner();
    return;
  }
  // Supervisor can reject a queued request after the browser received 202.
  // Do not leave the button locked indefinitely when no reconnect occurs.
  setTimeout(() => {
    if (restartRequested && window.DHClimateEditor?.needsRestart?.()) {
      restartRequested = false;
      restartError = t("restart_unconfirmed");
      renderRestartBanner();
    }
  }, 30000);
}

function render() {
  window.DHClimateEditor?.setWeatherContext?.(snapshot?.weather,weatherCatalog);
  renderRestartBanner();
  $("top-title").textContent = t("explorer");
  if (!$("save-diagnostics").disabled)
    $("save-diagnostics").textContent = t("diagnostics_save");
  $("explorer-heading").textContent = t("explorer").toUpperCase();
  $("foot-mode").textContent = window.DHClimateEditor?.viewMode() || t("read_only");
  $("connection").textContent = !streamConnected && snapshot ? t("connection_lost") : !snapshot ? t("loading") :
    snapshot.app.ha_connected ? t("online") : t("offline");
  $("connection").className = "connection " + (!streamConnected && snapshot ? "warn" : snapshot?.app.ha_connected ? "good" : "bad");
  $("foot-status").textContent = "DH Climate · " + t("explorer") +
    (snapshot ? " · v" + snapshot.app.version : "");
  renderTree(); renderBreadcrumbs();
  const main = $("content");
  if (!window.DHClimateEditor?.renderEditor(main)) {
    main.replaceChildren();
    if (!snapshot) main.append(paragraph(t("loading"), "subtle"));
    else {
      const views = {system:showSystem, weather:showWeather,
        weather_sources:showProviders, providers:showProviders, provider:showProvider,
        weather_sensor:showWeatherSensor,
        outdoor_physical:showOutdoorPhysical, outdoor_sensor:showOutdoorSensor,
        weather_priorities:showWeatherPriorities, home:showHome,
        resources:showResources, resource:showResource, parts:showParts,
        part:showPart, season:showSeason, rooms:showRooms, room:showRoom,
        thermostat:showThermostat, sensors:showSensors, sensor:showSensor,
        devices:showDevices, device:showDevice};
      (views[selection.kind] || showSystem)(main);
    }
  }
  window.DHClimateEditor?.controls(main);
  renderInspector();
  renderPanels();
}
function diagnosticContext() {
  const path=findPath(selection);
  return {
    locale,
    translations:dictionary,
    selection:{...selection},
    selected_path:path ? path.map(item=>({
      kind:item.kind,id:item.id||null,label:item.label,
    })) : [],
    expanded_nodes:Array.from(expanded),
    explorer_open:explorerOpen,
    explorer_width:explorerWidth,
    inspector_open:inspectorOpen,
    stream_connected:streamConnected,
    restart_requested:restartRequested,
    restart_error:restartError,
    tree:nodes,
    snapshot_browser_cache:snapshot,
    weather_catalog_browser_cache:weatherCatalog,
    editor:window.DHClimateEditor?.diagnosticState?.() || null,
  };
}
async function saveDiagnostics() {
  await window.DHClimateDiagnostics.save(
    diagnosticContext,$("save-diagnostics"),t);
}
async function language(code) {
  const target = ["en","ru"].includes(code) ? code : "en";
  try {
    const response = await fetch("i18n/" + target + ".json", {cache:"no-store"});
    if (!response.ok) throw Error("translations");
    dictionary = await response.json();
    locale = target;
    $("language").value = target;
    document.documentElement.lang = target;
    try { localStorage.setItem("dh-climate-language", target); } catch (_) {}
  } catch (_) {
    if (target !== "en") return language("en");
  }
  render();
}
async function connect() {
  try {
    const response = await fetch("api/snapshot", {cache:"no-store"});
    if (response.ok) { snapshot = await response.json(); streamConnected = true; render(); }
  } catch (_) { $("connection").textContent = t("offline"); }
  const events = new EventSource("api/events");
  events.addEventListener("open", () => {
    // SSE reconnect after App restart: confirm the newly loaded manifest.
    if (restartDisconnected) {
      restartRequested = false;
      restartDisconnected = false;
      restartError = "";
    }
    window.DHClimateEditor?.refreshAfterReconnect?.();
  });
  events.addEventListener("snapshot", event => {
    try { snapshot = JSON.parse(event.data); streamConnected = true; render(); }
    catch (_) { /* never replace valid data with an invalid update */ }
  });
  events.onerror = () => {
    if (restartRequested) restartDisconnected = true;
    streamConnected = false;
    renderRestartBanner();
    $("connection").textContent = t("connection_lost");
    $("connection").className = "connection warn";
  };
}
initExplorerWidth();
$("toggle-inspector").onclick = () => { inspectorOpen = !inspectorOpen; renderInspector(); renderPanels(); };
$("toggle-explorer").onclick = () => { explorerOpen = !explorerOpen; renderPanels(); };
$("collapse-all").onclick = () => { expanded.clear(); expanded.add(keyOf(nodes[0] || {kind:"system"})); renderTree(); };
$("language").onchange = e => language(e.target.value);
$("restart-app").onclick = restartApp;
$("save-diagnostics").onclick = saveDiagnostics;
(async () => {
  let preferred = locale;
  try { preferred = localStorage.getItem("dh-climate-language") || preferred; } catch (_) {}
  await language(preferred);
  await connect();
  if (window.DHClimateEditor) await window.DHClimateEditor.init(t,navigate,render);
})();
