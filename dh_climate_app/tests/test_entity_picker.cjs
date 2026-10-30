"use strict";
const test=require("node:test"),assert=require("node:assert/strict");
const fs=require("node:fs"),vm=require("node:vm"),path=require("node:path");
const src=fs.readFileSync(path.resolve(__dirname,"../src/dh_climate_app/web/entity_picker.js"),"utf-8");
const ctx=vm.createContext({window:{},document:{},fetch:()=>{},console,Set,Array});
vm.runInContext(src,ctx);
const {match,domainsFor,classesFor}=ctx.window.DHClimateEntityPicker;
const base={entity_id:"sensor.th_livingroom_temperature",name:"Температура гостиной",
  domain:"sensor",device_class:"temperature",available:true,
  area_id:"living",area_name:"Гостиная",device_name:"Zigbee TH"};
const filters=(override={})=>({kind:"temperature",domain:"all",query:"",area:"all",
  availability:"all",includeOther:false,...override});
test("sensor temperature context excludes humidity and inappropriate domains",()=>{
  assert.equal(match(base,filters()),true);
  assert.equal(match({...base,device_class:"humidity"},filters()),false);
  assert.equal(match({...base,domain:"climate"},filters()),false);
  assert.equal(match({...base,device_class:null},filters()),false);
  assert.equal(match({...base,device_class:null,unit:"°C"},filters()),true);
  assert.equal(match({...base,device_class:null},filters({includeOther:true})),true);
  assert.equal(match({...base,device_class:"humidity"},filters({includeOther:true})),true);
});
test("window context only offers binary_sensor, never sensor counting metrics",()=>{
  const windowFilters=filters({kind:"window"});
  assert.deepEqual(Array.from(domainsFor("window")),["binary_sensor"]);
  assert.equal(match({...base,entity_id:"sensor.count_binary_sensor",domain:"sensor",
    name:"Binary sensors count",device_class:null},windowFilters),false);
  assert.equal(match({...base,entity_id:"binary_sensor.window",domain:"binary_sensor",
    name:"Окно",device_class:"window"},windowFilters),true);
  assert.equal(match({...base,entity_id:"binary_sensor.window",domain:"binary_sensor",
    name:"Окно",device_class:null},windowFilters),false);
  assert.equal(match({...base,entity_id:"binary_sensor.window",domain:"binary_sensor",
    name:"Окно",device_class:null},filters({kind:"window",includeOther:true})),true);
});
test("unclassified phone/system sensors are hidden by temperature filter",()=>{
  assert.equal(match({...base,device_class:null,unit:null,
    entity_id:"sensor.phone_activity",state:"Stationary"},filters()),false);
  assert.equal(match({...base,device_class:null,unit:null,
    entity_id:"sensor.phone_app_version",state:"2026.10"},filters()),false);
  assert.equal(match({...base,device_class:null,unit:"%"},
    filters({kind:"humidity"})),false);
});
test("area and availability filters act independently",()=>{
  assert.equal(match(base,filters({area:"living"})),true);
  assert.equal(match(base,filters({area:"bedroom"})),false);
  assert.equal(match({...base,area_id:null},filters({area:"none"})),true);
  assert.equal(match({...base,area_id:null},filters({area:"living"})),false);
  assert.equal(match({...base,available:false},filters({availability:"available"})),false);
  assert.equal(match({...base,available:false},filters({availability:"unavailable"})),true);
});
test("search considers name, entity id, device, area",()=>{
  for(const word of ["гостиной","LIVINGROOM","zigbee","гостиная"])
    assert.equal(match(base,filters({query:word})),true);
  assert.equal(match(base,filters({query:"sitting room"})),false);
});
test("domain constraints follow hardware and virtual actuator requirements",()=>{
  assert.deepEqual(Array.from(domainsFor("actuator-hardware")),["climate"]);
  assert.deepEqual(Array.from(domainsFor("actuator-virtual")),["climate","switch"]);
  assert.deepEqual(Array.from(classesFor("window")),["window","door","opening","garage_door"]);
  assert.equal(match({...base,domain:"switch",device_class:null},
    filters({kind:"actuator-hardware"})),false);
  assert.equal(match({...base,domain:"switch",device_class:null},
    filters({kind:"actuator-virtual"})),true);
});
test("picker contains only expected read-only HA API and draft callback",()=>{
  assert.match(src,/fetch\("api\/entities"/);
  assert.doesNotMatch(src,/api\/config\/apply|call_service|api\/services/);
  assert.match(src,/onConfirm\(/);
});
