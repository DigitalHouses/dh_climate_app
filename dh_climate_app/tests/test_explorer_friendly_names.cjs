"use strict";
const test=require("node:test"),assert=require("node:assert/strict");
const fs=require("node:fs"),vm=require("node:vm"),path=require("node:path");
const root=path.resolve(__dirname,"../src/dh_climate_app/web");
const source=fs.readFileSync(path.join(root,"app.js"),"utf8");
const beforeBoot=source.indexOf('document.addEventListener("pointerdown"');
assert.ok(beforeBoot>0);
const dict=JSON.parse(fs.readFileSync(path.join(root,"i18n","ru.json"),"utf8"));
const ctx=vm.createContext({navigator:{language:"ru"},Intl,Set,Number,window:{},document:{}});
vm.runInContext(source.slice(0,beforeBoot)+
  '\ndictionary='+JSON.stringify(dict)+
  '\nlocale="ru"; globalThis.testApi={buildTree,findPath,keyOf,namedRoom,namedEntity};',ctx);
const api=ctx.testApi;
const states=(entity_id,friendly_name)=>({entity_id,friendly_name,available:true,state:"22",last_updated:null});
function fixture(named=true) {
 return {
   home:{heating_source:"boiler",vrf_enabled:false,resources:[]},
   rooms:[{
     id:"livingroom",name:"Living Room",friendly_name:named?"Гостиная":null,
     health:"healthy",climate_entity:"climate.dh_climate_app_livingroom",
     sensors:{temperature:[states("sensor.livingroom_temp",named?"Температура гостиной":null)],
       humidity:[],window:[]},
     devices:[{entity_id:"climate.livingroom",role:"fast_heat",device_type:"hardware",
       observed:states("climate.livingroom",named?"Термостат гостиной":null)}]
   }]
 };
}
const locate=(items,predicate)=>{
 for(const item of items) {
   if(predicate(item))return item;
   const nested=locate(item.children||[],predicate);
   if(nested)return nested;
 }
 return null;
};
test("Russian locale localizes structural tree nodes and resources",()=>{
 const nodes=api.buildTree(fixture());
 assert.equal(nodes[0].label,"Система");
 assert.equal(nodes[0].children[0].label,"Погода");
 assert.equal(nodes[0].children[1].label,"Дом");
 assert.equal(nodes[0].children[1].children[0].label,"Ресурсы");
 assert.equal(nodes[0].children[1].children[2].label,"Комнаты");
 assert.equal(locate(nodes,n=>n.kind==="resource").label,"Котёл");
});
test("HA friendly names appear in the tree without changing entity identity",()=>{
 const tree=api.buildTree(fixture());
 const room=locate(tree,n=>n.kind==="room");
 const sensor=locate(tree,n=>n.kind==="sensor");
 const device=locate(tree,n=>n.kind==="device");
 assert.equal(room.label,"Гостиная");
 assert.equal(sensor.label,"Температура гостиной");
 assert.equal(device.label,"Термостат гостиной");
 assert.equal(sensor.id,"sensor.livingroom_temp");
 assert.equal(device.id,"climate.livingroom");
 assert.equal(room.id,"livingroom");
 assert.deepEqual(Array.from(api.findPath(device,tree)).map(n=>n.kind),
  ["system","home","rooms","room","devices","device"]);
});
test("missing HA friendly names fall back to canonical room and entity identifiers",()=>{
 const tree=api.buildTree(fixture(false));
 assert.equal(locate(tree,n=>n.kind==="room").label,"Living Room");
 assert.equal(locate(tree,n=>n.kind==="sensor").label,"sensor.livingroom_temp");
 assert.equal(locate(tree,n=>n.kind==="device").label,"climate.livingroom");
});
test("unknown preview device still uses its entity_id",()=>{
 const obj=fixture();
 obj.rooms[0].devices[0].observed=null;
 assert.equal(locate(api.buildTree(obj),n=>n.kind==="device").label,"climate.livingroom");
});
