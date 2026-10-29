"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const path = require("node:path");

const web = path.resolve(__dirname, "../src/dh_climate_app/web");
const source = fs.readFileSync(path.join(web, "app.js"), "utf8");
const boot = source.indexOf('$("toggle-inspector").onclick =');
assert.ok(boot > 0, "separate model from browser bootstrap");
const context = vm.createContext({
  navigator: {language:"ru"},
  document: {}, window:{},
  Intl, Number, Set,
});
vm.runInContext(source.slice(0, boot) +
  "\nglobalThis.unit = {buildTree, keyOf, findPath, technical, number};", context);
const u = context.unit;
const fixture = {
  app: {version:"0.2.2", ha_connected:true, health:"healthy", problems:[]},
  weather: {season:"heat", temperature:6},
  home: {
    heating_source:"boiler", vrf_enabled:false,
    resources:[{id:"boiler", signals:[], pumps:[
      {id:"pump1",name:"Pump 1",signals:[]}], circuits:[
      {id:"c4",name:"Circuit 4",signals:[]}]}],
  },
  rooms:[{id:"bedroom",name:"Спальня",health:"healthy",
    climate_entity:"climate.dh_climate_app_bedroom",
    sensors:{temperature:[{entity_id:"sensor.bedroom_temperature"}],humidity:[],window:[]},
    devices:[{entity_id:"climate.bedroom_ac",role:"fast_heat_cool",device_type:"hardware"}],
  }],
};
const walk = (ns, predicate) => {
  for (const n of ns) {
    if (predicate(n)) return n;
    const nested=walk(n.children || [],predicate);
    if (nested) return nested;
  }
  return null;
};
test("Explorer preserves canonical system → weather / home → resources / season / rooms",()=>{
  const tree=u.buildTree(fixture);
  assert.equal(tree.length,1);
  assert.equal(tree[0].kind,"system");
  assert.deepEqual(Array.from(tree[0].children).map(n=>n.kind),["weather","home"]);
  assert.deepEqual(Array.from(tree[0].children[1].children).map(n=>n.kind),
    ["resources","season","rooms"]);
});
test("room is a first-class node; thermostat, sensors and devices are children",()=>{
  const tree=u.buildTree(fixture);
  const room=walk(tree,n=>n.kind==="room");
  assert.equal(room.label,"Спальня");
  assert.deepEqual(Array.from(room.children).map(n=>n.kind),
    ["thermostat","sensors","devices"]);
  const device=walk(tree,n=>n.kind==="device");
  assert.equal(device.id,"climate.bedroom_ac");
  const path=u.findPath(device,tree);
  assert.deepEqual(Array.from(path).map(n=>n.kind),
    ["system","home","rooms","room","devices","device"]);
});
test("physical resource parts are children; no virtual physics is generated",()=>{
  const tree=u.buildTree(fixture);
  const c4=walk(tree,n=>n.kind==="part" && n.partType==="circuits");
  assert.equal(c4.resource,"boiler");
  assert.equal(c4.id,"c4");
  assert.equal(walk(tree,n=>n.kind==="relay"),null);
});
test("configured heating resource remains visible without telemetry",()=>{
  const bare={...fixture,home:{heating_source:"central_heating",vrf_enabled:false,resources:[]}};
  const tree=u.buildTree(bare);
  assert.equal(walk(tree,n=>n.kind==="resource").label,"CENTRAL_HEATING");
  assert.equal(walk(tree,n=>n.kind==="resource").children.length,0);
});
test("technical behaviour codes are not translated",()=>{
  assert.equal(u.technical("fast_heat"),"FAST_HEAT");
  assert.equal(u.technical("slow_heat"),"SLOW_HEAT");
  assert.equal(u.technical("virtual"),"VIRTUAL");
  assert.equal(u.technical("hardware"),"HARDWARE");
});
test("keys distinguish a device from a sensor with the same entity id",()=>{
  const same="switch.control_15";
  assert.notEqual(u.keyOf({kind:"sensor",id:same,room:"bedroom"}),
    u.keyOf({kind:"device",id:same,room:"bedroom"}));
});
test("both locale JSON files expose new Explorer terms",()=>{
  const needed=["explorer","read_only","room_thermostat","sensors","not_reported"];
  for(const lang of ["en","ru"]){
    const dict=JSON.parse(fs.readFileSync(path.join(web,"i18n",lang+".json"),"utf8"));
    for(const key of needed) assert.ok(dict[key],lang+" missing "+key);
  }
});
