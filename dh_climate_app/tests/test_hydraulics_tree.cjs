"use strict";
const test=require("node:test");
const assert=require("node:assert/strict");
const fs=require("node:fs");
const vm=require("node:vm");
const path=require("node:path");

const source=fs.readFileSync(path.resolve(__dirname,"../src/dh_climate_app/web/app.js"),"utf8");
const boot=source.indexOf('document.addEventListener("pointerdown"');
const priorityStart=source.indexOf("function weatherSourceMetadata(");
const seasonStart=source.indexOf("function seasonSourceNode(");
const seasonEnd=source.indexOf("function showHome(",seasonStart);
assert.ok(boot>0 && priorityStart>boot && seasonEnd>seasonStart);
const context=vm.createContext({navigator:{language:"ru"},document:{},window:{},
  Intl, Number, Set});
vm.runInContext(source.slice(0,boot)+"\n"+source.slice(priorityStart,seasonEnd)+
  "\nglobalThis.view={buildTree,findPath,hydraulicTree,entityReading};",context);
const view=context.view;
const walk=(ns,pred)=>{
  for(const n of ns) {
    if(pred(n)) return n;
    const x=walk(n.children||[],pred);
    if(x) return x;
  }
  return null;
};
const reading=(role,entity,state,unit,available=true)=>({
  role,entity_id:entity, friendly_name:role, state, unit, available,
});
const fixture={
  app:{ha_connected:true,problems:[]},
  weather:{season:"heat"},
  home:{
    heating_source:"boiler",vrf_enabled:false,resources:[],
    hydraulics:{
      aggregators:[{id:"logo",name:"Siemens LOGO!",device_type:"hardware",signals:[]}],
      separators:[{id:"header",name:"Гидрострелка",signals:[]}],
      groups:[
        {id:"high",name:"Высокая",separator_id:"header",temperature_class:"high",
          pump_ids:["shared"],actuator_ids:[],valve_ids:[],signals:[]},
        {id:"low",name:"Низкая",separator_id:"header",temperature_class:"low",
          pump_ids:["shared"],actuator_ids:[],valve_ids:[],
          signals:[reading("supply_temperature","sensor.low_supply","0","°C")]},
      ],
      pumps:[{id:"shared",name:"Общий насос",signals:[
        reading("state","binary_sensor.pump","on",null)]}],
      actuators:[{id:"a1",name:"Сервопривод",signals:[
        reading("powered","binary_sensor.a1","off",null)]}],
      valves:[],
      circuits:[{id:"floor",name:"ТП",group_id:"low",room_id:"hall",
        pump_ids:[],actuator_ids:["a1"],valve_ids:[],
        signals:[reading("return_pressure","sensor.floor_p","1.8","bar")],
        terminals:[{id:"emitter",name:"Тёплый пол",room_id:"hall",entity_id:null}]}],
    },
  },
  rooms:[{id:"hall",name:"Зал",sensors:{temperature:[],humidity:[],window:[]},
    devices:[],health:"healthy"}],
};
test("tree is backward compatible when no hydraulic model is configured",()=>{
  const old={...fixture,home:{heating_source:"boiler",vrf_enabled:false,resources:[]}};
  const tree=view.buildTree(old);
  const branch=walk(tree,n=>n.kind==="hydraulics");
  assert.ok(branch,"empty hydraulic configuration section should be visible");
  assert.deepEqual(Array.from(branch.children).map(n=>n.id),
    ["aggregators","separators"]);
  assert.equal(walk(tree,n=>n.kind==="hydraulic_item"),null,
    "an empty section cannot fabricate equipment");
  assert.equal(walk(tree,n=>n.kind==="resource").id,"boiler");
});
test("separator has exactly two temperature group categories",()=>{
  const tree=view.buildTree(fixture);
  const separator=walk(tree,n=>n.kind==="hydraulic_item" && n.id==="separators:header");
  assert.ok(separator);
  assert.deepEqual(Array.from(separator.children).map(n=>n.kind),
    ["hydraulic_temperature","hydraulic_temperature"]);
  const low=walk([separator],n=>n.kind==="hydraulic_temperature"&&n.id==="header:low");
  assert.ok(low);
  assert.equal(low.children[0].id,"groups:low");
  const circuit=walk([low],n=>n.kind==="hydraulic_item"&&n.id==="circuits:floor");
  assert.ok(circuit);
  assert.equal(walk([circuit],n=>n.kind==="hydraulic_terminal").id,"floor:emitter");
});
test("same canonical pump is referenced in multiple groups",()=>{
  const tree=view.buildTree(fixture);
  const shared=[];
  function visit(ns){for(const n of ns){
    if(n.id==="pumps:shared")shared.push(n);
    visit(n.children||[]);
  }}
  visit(tree);
  assert.equal(shared.length,2);
  assert.equal(fixture.home.hydraulics.pumps.length,1);
});
test("all configured sensors retain real value and HA units, including numeric zero",()=>{
  const tree=view.buildTree(fixture);
  const sensor=walk(tree,n=>n.kind==="hydraulic_signal" &&
    n.id==="groups:low:supply_temperature");
  assert.equal(sensor.reading,"0 °C");
  assert.equal(sensor.sourceName,"sensor.low_supply");
  const pump=walk(tree,n=>n.kind==="hydraulic_signal" && n.id==="pumps:shared:state");
  assert.equal(pump.reading,"on");
});
test("unavailable readings never infer OFF",()=>{
  const reading= view.entityReading({state:null,available:false,unit:"bar"});
  assert.notEqual(reading,"0 bar");
  assert.notEqual(reading,"off");
});
test("groups and circuits without a separator are supported",()=>{
  const plain=structuredClone(fixture);
  plain.home.hydraulics.separators=[];
  plain.home.hydraulics.groups.forEach(g=>{g.separator_id=null;});
  const tree=view.buildTree(plain);
  assert.ok(walk(tree,n=>n.kind==="hydraulic_collection" && n.id==="direct_groups"));
});
