"use strict";
const test=require("node:test");
const assert=require("node:assert/strict");
const fs=require("node:fs"),vm=require("node:vm"),path=require("node:path");
const root=path.resolve(__dirname,"../src/dh_climate_app/web");
const src=fs.readFileSync(path.join(root,"editor.js"),"utf8");
async function bootstrap(admin=true){
  let renders=0;
  const window={};
  const labels={schema_version:1,revision:2,labels:{
    "room:livingroom":{ru:"Гостиная"},
    "entity:sensor.th_livingroom_temperature":{ru:"Температура гостиной"},
  }};
  const state={options:{rooms:[{id:"livingroom",name:"Living Room"}]},
    base_hash:"a",revision:0,pending_restart:false,dirty:false};
  const fakeFetch=async uri=>({ok:admin||uri==="api/labels",
    json:async()=>uri==="api/labels"?labels:state});
  const ctx={window,fetch:fakeFetch,JSON,Promise,Number};
  vm.runInNewContext(src,ctx);
  const editor=window.DHClimateEditor;
  await editor.init(key=>key,()=>{},()=>{renders++});
  return {editor,renders};
}
test("DH Russian labels override HA friendly names, with separate English fallback",async()=>{
  const {editor}=await bootstrap(true);
  assert.equal(editor.displayName("room","livingroom","ru","Living Room HA"),"Гостиная");
  assert.equal(editor.displayName("room","livingroom","en","Living Room HA"),"Living Room HA");
  assert.equal(editor.displayName("entity","sensor.th_livingroom_temperature","ru","HA Source"),"Температура гостиной");
  assert.equal(editor.displayName("entity","sensor.not_set","ru","HA Source"),"HA Source");
});
test("rename action is offered for known room and entity but not folders",async()=>{
  const {editor}=await bootstrap(true);
  assert.equal(editor.menuActions({kind:"room",id:"livingroom"})[0].label,"editor.rename");
  assert.equal(editor.menuActions({kind:"sensor",id:"sensor.th_livingroom_temperature"})[0].label,"editor.rename");
  assert.equal(editor.menuActions({kind:"device",room:"livingroom",id:"climate.ac"})[0].label,"editor.rename");
  assert.equal(editor.menuActions({kind:"resource",id:"boiler"})[0].label,"editor.rename");
  assert.equal(editor.menuActions({kind:"part",resource:"boiler",partType:"pumps",id:"pump1"})[0].label,"editor.rename");
  assert.ok(editor.menuActions({kind:"rooms"}).every(x=>x.label!=="editor.rename"));
});
test("viewers see labels but cannot rename",async()=>{
  const {editor}=await bootstrap(false);
  assert.equal(editor.displayName("room","livingroom","ru","Living Room HA"),"Гостиная");
  assert.deepEqual(Array.from(editor.menuActions({kind:"room",id:"livingroom"})),[]);
});
test("translations expose independent Russian and English names",()=>{
  for(const lang of ["ru","en"]){
    const dict=JSON.parse(fs.readFileSync(path.join(root,"i18n",lang+".json"),"utf8"));
    for(const key of ["editor.rename","editor.name_ru","editor.name_en",
      "editor.ha_name","editor.save_name","ha_friendly_name"])
      assert.ok(dict[key],lang+" missing "+key);
  }
});
