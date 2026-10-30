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
  assert.equal(match({...base,device_class:null},filters()),true);
  assert.equal(match({...base,device_class:"humidity"},filters({includeOther:true})),true);
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
