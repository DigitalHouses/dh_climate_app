"use strict";
// DH Climate Operations v1. This UI is strictly read-only.
const $ = (id) => document.getElementById(id);
let snapshot = null;
let locale = (navigator.language || "en").toLowerCase().startsWith("ru") ? "ru" : "en";
let dictionary = {};
let selection = {kind: "system"};
let streamConnected = false;
const routes = [
  ["system", "◉", "system"],
  ["weather", "☁", "weather"],
  ["home", "⌂", "home"],
  ["resources", "♨", "resources"],
  ["season", "◷", "season"],
  ["rooms", "▦", "rooms"]
];
const t = (key) => dictionary[key] || key;
const empty = () => t("unknown");
const display = (value, suffix = "") => value === null || value === undefined || value === "" ? "—" : String(value) + suffix;
const statusText = (value) => value === null || value === undefined ? empty() : t(String(value));
const healthy = (value) => value === "healthy" ? "good" : value === "critical" ? "bad" : value === "degraded" ? "warn" : "muted";
const number = (value, suffix = "") => value === null || value === undefined ? "—" : new Intl.NumberFormat(locale, {maximumFractionDigits: 2}).format(value) + suffix;

function dom(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text !== undefined && text !== null) e.textContent = String(text);
  return e;
}
function add(parent, ...children) { children.forEach((child) => child && parent.append(child)); return parent; }
function paragraph(text, cls = "") { return dom("p", cls, text); }
function title(text) { return dom("h2", "page-title", text); }
function sectionHeading(text) { return dom("h3", "section-heading", text); }
function labelValue(label, value) {
  const row = dom("div", "kv");
  add(row, dom("span", "label", label), dom("span", "kv-value", value));
  return row;
}
function stat(label, value, tone) {
  const box = dom("div", "stat");
  add(box, dom("div", "stat-label", label), dom("div", "stat-value " + (tone || ""), value));
  return box;
}
function stats(...tiles) { const grid = dom("div", "stats"); tiles.forEach((item) => grid.append(item)); return grid; }
function card(heading, ...elements) {
  const div = dom("section", "card");
  if (heading) div.append(sectionHeading(heading));
  elements.forEach((e) => div.append(e));
  return div;
}
function selectable(label, meta, onClick, cls = "click-row") {
  const btn = dom("button", cls);
  btn.type = "button";
  add(btn, dom("span", "row-main", label), dom("span", "row-meta", meta || ""));
  btn.onclick = onClick;
  return btn;
}
function navigate(kind, id = null, room = null) {
  selection = {kind, id, room};
  render();
}
function roomById(id) { return (snapshot?.rooms || []).find((r) => r.id === id); }
function deviceById(roomId, id) { return roomById(roomId)?.devices.find((d) => d.entity_id === id); }
function resourceById(id) { return (snapshot?.home.resources || []).find((r) => r.id === id); }
function current(kind) { return selection.kind === kind || (kind === "rooms" && ["room", "device"].includes(selection.kind)) || (kind === "resources" && selection.kind === "resource"); }
function namedRoom(r) { return r.name || r.id; }
function entityText(entity) { return entity?.entity_id || "—"; }
function observedText(entity) {
  if (!snapshot?.app.ha_connected) return empty();
  if (!entity || !entity.available) return empty();
  return display(entity.state);
}
function demandValue(item) { return item?.active === true ? t("on") : item?.active === false ? t("off") : empty(); }

function renderRail() {
  const rail = $("rail");
  rail.replaceChildren();
  routes.forEach(([kind, icon, key]) => {
    const btn = dom("button", "rail-button" + (current(kind) ? " selected" : ""), icon);
    btn.title = t(key);
    btn.setAttribute("aria-label", t(key));
    btn.setAttribute("aria-current", current(kind) ? "page" : "false");
    btn.onclick = () => navigate(kind);
    rail.append(btn);
  });
}
function renderContext() {
  const pane = $("context");
  pane.replaceChildren(dom("h2", "pane-heading", t("navigation")));
  const addLink = (text, kind, id, room) => {
    pane.append(selectable(text, "", () => navigate(kind, id, room), "context-link" +
      (selection.kind === kind && selection.id === id ? " active" : "")));
  };
  if (["room", "device", "rooms"].includes(selection.kind)) {
    pane.append(sectionHeading(t("rooms")));
    for (const room of snapshot?.rooms || []) addLink(namedRoom(room), "room", room.id);
    const selectedRoom = roomById(selection.kind === "device" ? selection.room : selection.id);
    if (selectedRoom) {
      pane.append(sectionHeading(t("devices")));
      for (const device of selectedRoom.devices) addLink(device.entity_id, "device", device.entity_id, selectedRoom.id);
    }
  } else if (["resources", "resource", "home"].includes(selection.kind)) {
    pane.append(sectionHeading(t("resources")));
    for (const resource of snapshot?.home.resources || []) addLink(resource.id, "resource", resource.id);
    pane.append(sectionHeading(t("rooms")));
    for (const room of snapshot?.rooms || []) addLink(namedRoom(room), "room", room.id);
  } else if (selection.kind === "weather") {
    pane.append(sectionHeading(t("temperature_sources")));
    (snapshot?.weather.temperature_sources || []).forEach((item) =>
      pane.append(paragraph(item.entity_id, "context-source")));
    pane.append(sectionHeading(t("humidity_sources")));
    (snapshot?.weather.humidity_sources || []).forEach((item) =>
      pane.append(paragraph(item.entity_id, "context-source")));
  } else {
    pane.append(sectionHeading(t("overview")));
    [["weather", "weather"], ["home", "home"], ["season", "season"], ["rooms", "rooms"]]
      .forEach(([kind, key]) => addLink(t(key), kind, null));
  }
}
function problemsForRoom(id) {
  return (snapshot?.app.problems || []).filter((p) => p.room_id === id);
}
function displayProblems(problems) {
  const wrap = dom("div", "list");
  if (!problems.length) { wrap.append(paragraph(t("no_problems"), "subtle")); return wrap; }
  problems.forEach((p) => {
    const item = dom("div", "problem");
    add(item, dom("strong", healthy(p.severity === "critical" ? "critical" : "degraded"), t("problem." + p.code) === "problem." + p.code ? p.code : t("problem." + p.code)));
    if (p.entity_id) item.append(paragraph(p.entity_id, "mono subtle"));
    if (p.details) item.append(paragraph(p.details, "subtle"));
    wrap.append(item);
  });
  return wrap;
}
function signalRows(signals) {
  const group = dom("div", "list");
  for (const signal of signals || []) {
    const line = dom("div", "signal");
    add(line, labelValue(t(signal.role), observedText(signal)), paragraph(signal.entity_id, "mono subtle small"));
    group.append(line);
  }
  if (!group.childElementCount) group.append(paragraph(t("not_configured"), "subtle"));
  return group;
}
function showSystem(main) {
  const app = snapshot.app;
  add(main, title(t("system")),
    stats(stat(t("health"), statusText(app.health), healthy(app.health)),
      stat(t("ha_connection"), app.ha_connected ? t("online") : t("offline"), app.ha_connected ? "good" : "bad"),
      stat(t("rooms"), snapshot.rooms.length),
      stat(t("problems"), app.problems.length)),
    card(t("about"), labelValue(t("version"), app.version),
      paragraph(t("read_only_info"), "subtle")),
    card(t("problems"), displayProblems(app.problems)));
}
function showWeather(main) {
  const w = snapshot.weather;
  add(main, title(t("weather")),
    stats(stat(t("temperature"), number(w.temperature, " °C")),
      stat(t("raw_temperature"), number(w.raw_temperature, " °C")),
      stat(t("avg24"), number(w.avg24, " °C")),
      stat(t("humidity"), number(w.humidity, " %"))),
    card(t("source"), labelValue(t("temperature"), display(w.source)),
      labelValue(t("condition"), statusText(w.condition)),
      labelValue(t("precipitation"), number(w.precipitation_mm, " mm")),
      labelValue(t("data_quality"), w.stale === null ? empty() : w.stale ? t("stale") : t("current"))),
    card(t("temperature_sources"), signalRows((w.temperature_sources || []).map((e) => ({...e, role: "temperature"})))),
    card(t("humidity_sources"), signalRows((w.humidity_sources || []).map((e) => ({...e, role: "humidity"})))));
}
function showSeason(main) {
  const w = snapshot.weather;
  add(main, title(t("season")), stats(stat(t("season"), statusText(w.season)),
    stat(t("avg24"), number(w.avg24, " °C"))),
    card(t("season"), paragraph(t("season_info"), "subtle")));
}
function showHome(main) {
  add(main, title(t("home")), card(t("home"),
    labelValue(t("heating_source"), statusText(snapshot.home.heating_source)),
    labelValue(t("vrf_enabled"), snapshot.home.vrf_enabled === null ? empty() : snapshot.home.vrf_enabled ? t("yes") : t("no")),
    labelValue(t("presence"), observedText(snapshot.home.presence)),
    labelValue(t("night"), observedText(snapshot.home.night))),
    card(t("resources"), resourceLinks()),
    card(t("rooms"), roomLinks()));
}
function resourceLinks() {
  const box = dom("div", "list");
  for (const resource of snapshot.home.resources || []) {
    box.append(selectable(resource.id, t("resource"), () => navigate("resource", resource.id)));
  }
  if (!box.childElementCount) box.append(paragraph(t("no_resource_signals"), "subtle"));
  return box;
}
function roomLinks() {
  const box = dom("div", "list");
  for (const room of snapshot.rooms) {
    const meta = display(room.temperature, " °C") + " · " + statusText(room.hvac_action);
    box.append(selectable(namedRoom(room), meta, () => navigate("room", room.id)));
  }
  if (!box.childElementCount) box.append(paragraph(t("no_rooms"), "subtle"));
  return box;
}
function showResources(main) {
  add(main, title(t("resources")), card(t("resources"), resourceLinks()));
  const demand = (snapshot.demands || []).filter((d) => ["boiler", "central_heating", "vrf"].includes(d.layer));
  if (demand.length) main.append(card(t("resource_requests"), demandRows(demand)));
}
function demandRows(items) {
  const box = dom("div", "list");
  items.forEach((d) => box.append(labelValue(d.layer + " · " + d.direction, demandValue(d))));
  return box;
}
function showResource(main) {
  const resource = resourceById(selection.id);
  if (!resource) return showResources(main);
  add(main, title(resource.id), card(t("resource"), signalRows(resource.signals)));
  for (const part of resource.pumps) main.append(card(t("pump") + " · " + part.name, signalRows(part.signals)));
  for (const part of resource.circuits) main.append(card(t("circuit") + " · " + part.name, signalRows(part.signals)));
}
function showRooms(main) { add(main, title(t("rooms")), card(t("rooms"), roomLinks())); }
function showRoom(main) {
  const room = roomById(selection.id);
  if (!room) return showRooms(main);
  add(main, title(namedRoom(room)), paragraph(room.id, "mono subtle"),
    stats(stat(t("temperature"), number(room.temperature, " °C")),
      stat(t("target"), number(room.target, " °C")),
      stat(t("humidity"), number(room.humidity, " %")),
      stat(t("health"), statusText(room.health), healthy(room.health))),
    card(t("room_climate"),
      labelValue(t("profile"), statusText(room.profile)),
      labelValue(t("hvac_mode"), statusText(room.hvac_mode)),
      labelValue(t("hvac_action"), statusText(room.hvac_action)),
      labelValue(t("window"), statusText(room.window_state))),
    card(t("devices"), deviceLinks(room)),
    card(t("problems"), displayProblems(problemsForRoom(room.id))));
}
function deviceLinks(room) {
  const box = dom("div", "list");
  for (const dev of room.devices) box.append(selectable(dev.entity_id,
    t(dev.role) + " · " + t(dev.device_type) + " · " + observedText(dev.observed),
    () => navigate("device", dev.entity_id, room.id)));
  if (!box.childElementCount) box.append(paragraph(t("no_devices"), "subtle"));
  return box;
}
function showDevice(main) {
  const dev = deviceById(selection.room, selection.id);
  if (!dev) return showRooms(main);
  add(main, title(t("device")), paragraph(dev.entity_id, "mono subtle"),
    stats(stat(t("observed_state"), observedText(dev.observed)),
      stat(t("hvac_action"), statusText(dev.hvac_action))),
    card(t("device"), labelValue(t("role"), t(dev.role)),
      labelValue(t("device_type"), t(dev.device_type)),
      labelValue(t("resource"), display(dev.resource)),
      labelValue(t("availability"), dev.observed?.available ? t("available") : empty())),
    paragraph(t("no_physical_inference"), "notice"));
}
function renderInspector() {
  const pane = $("inspector");
  pane.replaceChildren(dom("h2", "pane-heading", t("inspector")));
  let entity = null;
  let heading = "";
  if (selection.kind === "room") {
    const room = roomById(selection.id);
    heading = room ? namedRoom(room) : "";
    entity = room?.climate_entity;
    if (room) add(pane, labelValue(t("room_id"), room.id), labelValue(t("health"), statusText(room.health)));
  } else if (selection.kind === "device") {
    const dev = deviceById(selection.room, selection.id);
    heading = t("device");
    entity = dev?.entity_id;
    if (dev) add(pane, labelValue(t("device_type"), t(dev.device_type)),
      labelValue(t("role"), t(dev.role)));
  } else if (selection.kind === "resource") {
    heading = selection.id;
  } else {
    heading = t(selection.kind);
  }
  pane.append(dom("h3", "inspector-title", heading));
  if (entity) {
    pane.append(paragraph(entity, "mono source-id"));
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
  $("top-title").textContent = t("operations");
  $("connection").textContent = !snapshot ? t("loading") :
    (snapshot.app.ha_connected ? t("online") : t("offline"));
  $("connection").className = "connection " + (snapshot?.app.ha_connected ? "good" : "bad");
  $("foot-status").textContent = "DH Climate · " + t("operations") +
    (snapshot ? " · v" + snapshot.app.version : "");
  renderRail(); renderContext();
  const main = $("workspace");
  main.replaceChildren();
  if (!snapshot) { main.append(paragraph(t("loading"), "subtle")); renderInspector(); return; }
  const handlers = {system: showSystem, weather: showWeather, home: showHome,
    resources: showResources, resource: showResource, season: showSeason,
    rooms: showRooms, room: showRoom, device: showDevice};
  (handlers[selection.kind] || showSystem)(main);
  renderInspector();
}
async function language(code) {
  const next = ["en", "ru"].includes(code) ? code : "en";
  try {
    const response = await fetch("i18n/" + next + ".json", {cache: "no-store"});
    if (!response.ok) throw new Error("translations unavailable");
    dictionary = await response.json();
    locale = next;
    document.documentElement.lang = locale;
    $("language").value = locale;
    try { localStorage.setItem("dh-climate-language", locale); } catch (_) {}
  } catch (_) {
    if (next !== "en") return language("en");
  }
  render();
}
async function connect() {
  try {
    const response = await fetch("api/snapshot", {cache: "no-store"});
    if (response.ok) { snapshot = await response.json(); render(); }
  } catch (_) { $("connection").textContent = t("offline"); }
  const events = new EventSource("api/events");
  events.addEventListener("snapshot", (event) => {
    try { snapshot = JSON.parse(event.data); streamConnected = true; render(); }
    catch (_) { /* Ignore malformed updates, keep last known view. */ }
  });
  events.onerror = () => {
    streamConnected = false;
    $("connection").textContent = t("connection_lost");
    $("connection").className = "connection warn";
  };
}
(async () => {
  let preferred = locale;
  try { preferred = localStorage.getItem("dh-climate-language") || preferred; } catch (_) {}
  await language(preferred);
  await connect();
})();
