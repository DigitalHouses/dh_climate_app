"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const path = require("node:path");

const web = path.resolve(__dirname, "../src/dh_climate_app/web");
const source = fs.readFileSync(path.join(web, "app.js"), "utf8");
const boot = source.indexOf('document.addEventListener("pointerdown"');
assert.ok(boot > 0, "separate model from browser bootstrap");
const context = vm.createContext({
  navigator: {language:"ru"},
  document: {}, window:{},
  Intl, Number, Set,
});
// Import only the pure view functions: boot handlers need a full browser.
const priorityStart = source.indexOf("function weatherSourceMetadata(");
const seasonStart = source.indexOf("function seasonSourceNode(");
const seasonEnd = source.indexOf("function showHome(", seasonStart);
assert.ok(priorityStart > boot && seasonStart > priorityStart && seasonEnd > seasonStart);
vm.runInContext(source.slice(0, boot) + "\n" +
  source.slice(priorityStart, seasonEnd) +
  "\nglobalThis.unit = {buildTree, keyOf, findPath, technical, number, showSeason, showWeatherPriorities};", context);
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
test("weather has exactly three first-class branches; season is not duplicated under home",()=>{
  const tree=u.buildTree(fixture);
  assert.equal(tree.length,1);
  assert.equal(tree[0].kind,"system");
  assert.deepEqual(Array.from(tree[0].children).map(n=>n.kind),["weather","home"]);
  assert.deepEqual(Array.from(tree[0].children[0].children).map(n=>n.kind),
    ["weather_sources","weather_priorities","season"]);
  assert.deepEqual(Array.from(tree[0].children[1].children).map(n=>n.kind),
    ["resources","rooms"]);
  assert.deepEqual(Array.from(u.findPath(walk(tree,n=>n.kind==="season"),tree))
    .map(n=>n.kind),["system","weather","season"]);
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
test("one provider expands into two sensor nodes with stable IDs",()=>{
  const weather={
    ...fixture.weather,source_model:"sensors",
    providers:[{id:"google",entity_id:"weather.asyl_mura",
      friendly_name:"Asyl Mura",temperature:11.3,humidity:48}],
    physical_sensors:[{id:"garden",entity_id:"sensor.garden",
      quantity:"temperature",friendly_name:"Garden thermometer",value:10.3}],
    temperature_sources:[{entity_id:"google.temperature"}],
    humidity_sources:[{entity_id:"google.humidity"}],
  };
  const tree=u.buildTree({...fixture,weather});
  const provider=walk(tree,n=>n.kind==="provider");
  assert.equal(provider.id,"google");
  assert.equal(provider.sourceName,"weather.asyl_mura");
  assert.deepEqual(Array.from(provider.children).map(n=>n.id),
    ["google.temperature","google.humidity"]);
  const physical=walk(tree,n=>n.kind==="outdoor_sensor");
  assert.equal(physical.sourceName,"sensor.garden");
  const priorities=walk(tree,n=>n.kind==="weather_priorities");
  assert.ok(priorities);
  assert.deepEqual(Array.from(u.findPath(provider.children[0],tree)).map(n=>n.kind),
    ["system","weather","weather_sources","provider","weather_sensor"]);
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

test("season diagnostics render actual sensor and weather ancestry without controls",()=>{
  class Element {
    constructor(tag){this.tagName=tag;this.children=[];this.className="";this._text="";}
    set textContent(v){this._text=String(v);this.children=[];}
    get textContent(){return this._text+this.children.map(x=>x.textContent||"").join("");}
    append(...items){this.children.push(...items);}
  }
  context.document.createElement=tag=>new Element(tag);
  context.caseSeason={
    app:{ha_connected:true},weather:{
      season:"heat",avg24:9.8,source:"google.temperature",
      stale:false,heat_threshold:10.5,cool_threshold:19.5,
      season_hysteresis:1.0,
      providers:[{id:"google",entity_id:"weather.asyl_mura",
        friendly_name:"Google Weather"}],
      physical_sensors:[],
      temperature_sources:[{entity_id:"google.temperature",
        original_entity_id:"weather.asyl_mura",state:11.2}],
      avg24_input_sources:["google.temperature","sensor.backup"],
    },
  };
  context.caseCatalog={entities:[
    {entity_id:"sensor.actual_google",climate_source_id:"google.temperature",
      name:"Температура Google"},
    {entity_id:"sensor.avg24_renamed",climate_avg24_sensor:true,
      name:"Средняя за сутки"},
  ]};
  vm.runInContext("snapshot=caseSeason;weatherCatalog=caseCatalog;",context);
  const main=new Element("main");
  context.unit.showSeason(main);
  const rendered=main.textContent;
  assert.match(rendered,/Средняя за сутки/);
  assert.match(rendered,/sensor.avg24_renamed/);
  assert.match(rendered,/Температура Google/);
  assert.match(rendered,/sensor.actual_google/);
  assert.match(rendered,/weather.asyl_mura → temperature/);
  assert.match(rendered,/sensor.backup/);
  assert.match(rendered,/10,5.*°C/);
  assert.equal((function visit(e){return (e.tagName==="input"||e.tagName==="button"?1:0)+
    e.children.reduce((n,x)=>n+visit(x),0);})(main),0);
});

test("read-only priorities mark just Engine-selected temperature and humidity sources",()=>{
  class Element {
    constructor(tag){this.tagName=tag;this.children=[];this.className="";this._text="";}
    set textContent(v){this._text=String(v);this.children=[];}
    get textContent(){return this._text+this.children.map(x=>x.textContent||"").join("");}
    append(...items){this.children.push(...items);}
  }
  function all(e,kind) {
    return [
      ...(e.className===kind?[e]:[]),
      ...e.children.flatMap(c=>all(c,kind)),
    ];
  }
  context.document.createElement=tag=>new Element(tag);
  context.window.DHClimateEditor={canChange:()=>false};
  context.caseWeather={
    app:{ha_connected:true},
    weather:{
      source:"met.temperature",humidity_source:"google.humidity",
      providers:[
        {id:"met",entity_id:"weather.forecast_home_assistant",
         friendly_name:"Met.no"},
        {id:"google",entity_id:"weather.asyl_mura",
         friendly_name:"Google"},
      ],
      physical_sensors:[],
      temperature_sources:[
        {entity_id:"met.temperature",state:9.4,available:true},
        {entity_id:"google.temperature",state:3.2,available:true},
      ],
      humidity_sources:[
        {entity_id:"google.humidity",state:69,available:true},
        {entity_id:"met.humidity",state:34,available:true},
      ],
    },
  };
  vm.runInContext("snapshot=caseWeather;weatherCatalog=null;",context);
  let main=new Element("main");
  context.unit.showWeatherPriorities(main);
  let rows=all(main,"weather-priority-readonly");
  assert.equal(rows.length,4);
  assert.deepEqual(rows.map(r=>all(r,"weather-active-indicator").length),[1,0,1,0]);
  assert.equal(all(main,"weather-active-indicator").length,2);
  context.caseWeather.weather.source="google.temperature";
  vm.runInContext("snapshot=caseWeather;",context);
  main=new Element("main");
  context.unit.showWeatherPriorities(main);
  rows=all(main,"weather-priority-readonly");
  assert.deepEqual(rows.map(r=>all(r,"weather-active-indicator").length),[0,1,1,0]);
});
