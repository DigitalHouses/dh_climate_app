"use strict";
// DH Climate Explorer: one object tree, one detail pane, zero write endpoints.
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
const roomById = (id) => (snapshot?.rooms || []).find(r => r.id === id);
const resourceById = (id) => (snapshot?.home.resources || []).find(r => r.id === id);
const deviceById = (roomId, id) => roomById(roomId)?.devices.find(d => d.entity_id === id);
const observedText = (entity) => (!snapshot?.app.ha_connected || !entity?.available) ? unknown() : display(entity.state);
const demandValue = (item) => item?.active === true ? t("on") : item?.active === false ? t("off") : unknown();
const namedRoom = (room) => room?.name || room?.id || "—";

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
  const rooms = data?.rooms || [];
  const resources = [...(data?.home.resources || [])];
  // Heating source / VRF are configured resources even without telemetry.
  if (data?.home.heating_source && !resources.some(r => r.id === data.home.heating_source))
    resources.push({id:data.home.heating_source, signals:[], pumps:[], circuits:[]});
  if (data?.home.vrf_enabled === true && !resources.some(r => r.id === "vrf"))
    resources.push({id:"vrf", signals:[], pumps:[], circuits:[]});
  const roomNodes = rooms.map(room => {
    const sensors = ["temperature", "humidity", "window"].flatMap(role =>
      (room.sensors?.[role] || []).map(sensor =>
        node("sensor", sensor.entity_id, "◉", [], {room:room.id, id:sensor.entity_id, role})
      )
    );
    const devices = (room.devices || []).map(device =>
      node("device", device.entity_id, "⚙", [], {room:room.id, id:device.entity_id})
    );
    const children = [
      node("thermostat", t("room_thermostat"), "◉", [], {room:room.id, id:room.id}),
    ];
    if (sensors.length) children.push(node("sensors", t("sensors"), "▤", sensors, {room:room.id, id:room.id}));
    if (devices.length) children.push(node("devices", t("devices"), "▤", devices, {room:room.id, id:room.id}));
    return node("room", namedRoom(room), "▱", children, {id:room.id, health:room.health});
  });
  const resourceNodes = resources.map(resource => {
    const pumps = (resource.pumps || []).map(part =>
      node("part", part.name, "◉", [], {resource:resource.id, partType:"pumps", id:part.id})
    );
    const circuits = (resource.circuits || []).map(part =>
      node("part", part.name, "◉", [], {resource:resource.id, partType:"circuits", id:part.id})
    );
    const children = [];
    if (pumps.length) children.push(node("parts", t("pumps"), "▤", pumps, {resource:resource.id, partType:"pumps", id:resource.id}));
    if (circuits.length) children.push(node("parts", t("circuits"), "▤", circuits, {resource:resource.id, partType:"circuits", id:resource.id}));
    return node("resource", technical(resource.id), "▱", children, {id:resource.id});
  });
  return [node("system", "SYSTEM", "◈", [
    node("weather", "WEATHER", "☁"),
    node("home", "HOME", "⌂", [
      node("resources", "RESOURCES", "▤", resourceNodes),
      node("season", "SEASON", "◷"),
      node("rooms", "ROOMS", "▤", roomNodes),
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
  selection = {kind:item.kind, id:item.id || null, room:item.room || null,
    resource:item.resource || null, partType:item.partType || null};
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
    select.title = item.label;
    if (k === selectedKey()) select.setAttribute("aria-current", "page");
    add(select, dom("span", "tree-icon", item.icon), dom("span", "tree-text", item.label));
    select.onclick = () => navigate(item);
    line.append(toggle, select);
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
  $("inspector").hidden = !inspectorOpen;
  $("toggle-explorer").setAttribute("aria-pressed", String(explorerOpen));
  $("toggle-inspector").setAttribute("aria-pressed", String(inspectorOpen));
}
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
    line.append(paragraph(signal.entity_id, "mono subtle small"));
    return line;
  }));
}
function deviceLinks(room) {
  return listOrEmpty((room.devices || []).map(dev =>
    clickable(dev.entity_id,
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
    clickable(technical(resource.id), t("resource"), () => navigate({kind:"resource", id:resource.id}))),
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
      row(t("condition"), statusText(w.condition)),
      row(t("precipitation"), number(w.precipitation_mm, " mm")),
      row(t("data_quality"), w.stale === null ? unknown() : w.stale ? t("stale") : t("current"))),
    card(t("temperature_sources"), signalRows((w.temperature_sources || []).map(e => ({...e, role:"temperature"})))),
    card(t("humidity_sources"), signalRows((w.humidity_sources || []).map(e => ({...e, role:"humidity"})))));
}
function showSeason(main) {
  const w = snapshot.weather;
  add(main, title(t("season")), stats(stat(t("season"), statusText(w.season)),
      stat(t("avg24"), number(w.avg24, " °C"))),
    card(t("season"), paragraph(t("season_info"), "subtle")));
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
    add(main, title(technical(selection.id)),
      card(t("resource"), paragraph(t("no_resource_signals"), "subtle")));
    const matches = (snapshot.demands || []).filter(d => d.layer === selection.id);
    if (matches.length) main.append(card(t("resource_requests"), demandRows(matches)));
    return;
  }
  add(main, title(technical(resource.id)), card(t("resource"), signalRows(resource.signals)));
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
  add(main, title(result.sensor.entity_id),
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
  add(main, title(t("device")), paragraph(dev.entity_id, "mono subtle"),
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
function render() {
  $("top-title").textContent = t("explorer");
  $("explorer-heading").textContent = t("explorer").toUpperCase();
  $("foot-mode").textContent = t("read_only");
  $("connection").textContent = !streamConnected && snapshot ? t("connection_lost") : !snapshot ? t("loading") :
    snapshot.app.ha_connected ? t("online") : t("offline");
  $("connection").className = "connection " + (!streamConnected && snapshot ? "warn" : snapshot?.app.ha_connected ? "good" : "bad");
  $("foot-status").textContent = "DH Climate · " + t("explorer") +
    (snapshot ? " · v" + snapshot.app.version : "");
  renderTree(); renderBreadcrumbs();
  const main = $("content"); main.replaceChildren();
  if (!snapshot) main.append(paragraph(t("loading"), "subtle"));
  else {
    const views = {system:showSystem, weather:showWeather, home:showHome,
      resources:showResources, resource:showResource, parts:showParts,
      part:showPart, season:showSeason, rooms:showRooms, room:showRoom,
      thermostat:showThermostat, sensors:showSensors, sensor:showSensor,
      devices:showDevices, device:showDevice};
    (views[selection.kind] || showSystem)(main);
  }
  renderInspector();
  renderPanels();
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
  events.addEventListener("snapshot", event => {
    try { snapshot = JSON.parse(event.data); streamConnected = true; render(); }
    catch (_) { /* never replace valid data with an invalid update */ }
  });
  events.onerror = () => {
    streamConnected = false;
    $("connection").textContent = t("connection_lost");
    $("connection").className = "connection warn";
  };
}
$("toggle-inspector").onclick = () => { inspectorOpen = !inspectorOpen; renderInspector(); renderPanels(); };
$("toggle-explorer").onclick = () => { explorerOpen = !explorerOpen; renderPanels(); };
$("collapse-all").onclick = () => { expanded.clear(); expanded.add(keyOf(nodes[0] || {kind:"system"})); renderTree(); };
$("language").onchange = e => language(e.target.value);
(async () => {
  let preferred = locale;
  try { preferred = localStorage.getItem("dh-climate-language") || preferred; } catch (_) {}
  await language(preferred);
  await connect();
})();
