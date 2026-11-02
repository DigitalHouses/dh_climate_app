"use strict";
const test=require("node:test"),assert=require("node:assert/strict");
const fs=require("node:fs"),vm=require("node:vm"),path=require("node:path");
const root=path.resolve(__dirname,"../src/dh_climate_app/web");
const app=fs.readFileSync(path.join(root,"app.js"),"utf8");
const editor=fs.readFileSync(path.join(root,"editor.js"),"utf8");
class Element {
  constructor(tag){this.tagName=tag;this.className="";this.children=[];this._text="";}
  set textContent(value){this._text=String(value);this.children=[];}
  get textContent(){return this._text+this.children.map(c=>c.textContent||"").join("");}
  append(...items){this.children.push(...items);}
  replaceChildren(...items){this._text="";this.children=[...items];}
  setAttribute(name,value){this[name]=value;}
}
const options={
  providers:[{id:"met",entity_id:"weather.forecast_home_assistant"}],
  physical_sensors:[],
  priorities:{temperature:["met.temperature"],humidity:["met.humidity"]},
  rooms:[{id:"bedroom",name:"Bedroom",temperature_sensors:["sensor.bedroom"],
    devices:[{entity:"climate.bedroom_ac",role:"fast_heat",device_type:"virtual"}]}],
};
async function setup(admin=true,pendingRestart=false){
  let writes=0;
  const window={};
  const ctx={window,document:{
    createElement:tag=>new Element(tag),getElementById:()=>({value:"ru"}),
  },fetch:async(url)=>{
    if(url==="api/config") return {ok:admin,json:async()=>({
      options,base_hash:"hash",revision:0,dirty:false,
      pending_restart:pendingRestart,
    })};
    if(url==="api/labels")return {ok:true,json:async()=>({
      labels:{},room_areas:{},revision:0,
    })};
    writes++;throw Error("Unexpected network request: "+url);
  },JSON,Promise,Date,Set,Intl,Number,Error};
  vm.runInNewContext(editor,ctx);
  const api=window.DHClimateEditor;
  await api.init(key=>key,()=>{},()=>{});
  return {api,window,writes:()=>writes};
}
test("navigation between weather branches does not enter editing mode",()=>{
  const start=app.indexOf("function navigate(item) {");
  const end=app.indexOf("function renderTree()",start);
  assert.ok(start>0 && end>start);
  let renders=0,catalogLoads=0,autoEdits=0,checks=0;
  const ctx={
    window:{DHClimateEditor:{
      onNavigate:()=>{checks++;return true;},
      enterWeatherSection:()=>{autoEdits++;},
    },matchMedia:()=>({matches:false})},
    selection:{kind:"system"},expanded:new Set(),
    closeContextMenu:()=>{},findPath:()=>[],keyOf:()=>"",
    render:()=>{renders++;},renderPanels:()=>{},
    loadWeatherCatalog:async()=>{catalogLoads++;},
  };
  vm.runInNewContext(app.slice(start,end)+
    "\nglobalThis.switchPage=navigate;globalThis.currentPage=()=>selection;",ctx);
  for(const kind of ["weather_sources","outdoor_physical","weather_priorities","season",
    "home","weather_sources","outdoor_physical","weather_priorities","system"]){
    ctx.switchPage({kind});
    assert.equal(ctx.currentPage().kind,kind);
  }
  assert.equal(autoEdits,0,"tree navigation must never call enterWeatherSection");
  assert.equal(renders,9);
  assert.equal(catalogLoads,7);
  assert.equal(checks,9);
});
test("edit mode begins only after explicit section action and has visible editing heading",async()=>{
  const {api,writes}=await setup();
  assert.equal(api.isEditing(),false);
  assert.equal(api.viewMode(),"editor.view");
  for(const kind of ["weather_sources","outdoor_physical","weather_priorities"]){
    const action=api.pageAction({kind});
    assert.ok(action);
    assert.equal(action.label,"editor.edit");
    assert.equal(api.isEditing(),false);
    assert.equal(api.onNavigate(),true,"tree must work while browsing");
    action.run();
    assert.equal(api.isEditing(),true);
    assert.equal(api.viewMode(),"editor.editing");
    assert.equal(api.pageAction({kind}),null);
    assert.equal(api.onNavigate(),false,"explicit editor protects unsaved form");
    const main=new Element("main");
    api.renderEditor(main);
    assert.equal(main.children[0].className,"editor-mode-heading");
    assert.match(main.children[0].textContent,/editor.editing/);
    assert.match(main.children[0].textContent,/editor.editing_navigation_hint/);
    const cancel=find(main,x=>x.tagName==="button" &&
      x.textContent==="editor.cancel")[0];
    assert.ok(cancel);
    cancel.onclick();
    assert.equal(api.isEditing(),false);
    assert.equal(api.onNavigate(),true,"Cancel restores free navigation");
  }
  assert.equal(writes(),0,"entering or canceling edit must not change server config");
});
function find(root,pred){
  const found=[];function visit(item){
    if(pred(item))found.push(item);
    for(const sub of item.children||[])visit(sub);
  }visit(root);return found;
}
test("room and device page editing is explicit, viewers get no edit button",async()=>{
  const {api}=await setup();
  const room=api.pageAction({kind:"room",id:"bedroom"});
  const device=api.pageAction({kind:"device",room:"bedroom",id:"climate.bedroom_ac"});
  assert.equal(room.label,"editor.edit");
  assert.equal(device.label,"editor.edit");
  assert.equal(api.isEditing(),false);
  room.run();
  assert.equal(api.isEditing(),true);
  assert.equal(api.onNavigate(),false);
  const main=new Element("main");
  api.renderEditor(main);
  assert.match(main.textContent,/editor.editing/);
  assert.ok(find(main,e=>e.tagName==="button"&&e.textContent==="editor.cancel")[0]);
  find(main,e=>e.tagName==="button"&&e.textContent==="editor.cancel")[0].onclick();
  assert.equal(api.isEditing(),false);
  device.run();
  assert.equal(api.isEditing(),true);
  const viewer=(await setup(false)).api;
  const pending=(await setup(true,true)).api;
  for(const kind of ["weather_sources","outdoor_physical","weather_priorities","room","device"])
    assert.equal(viewer.pageAction({kind,id:"bedroom",room:"bedroom"}),null);
  for(const kind of ["weather_sources","outdoor_physical","weather_priorities"])
    assert.equal(pending.pageAction({kind}),null);
  // Pending restart prevents edits to the canonical manifest, but DH label
  // changes remain an independent, non-restarting UI operation.
  assert.equal(pending.pageAction({kind:"room",id:"bedroom"}).label,"editor.rename");
  assert.equal(pending.pageAction({kind:"device",room:"bedroom",
    id:"climate.bedroom_ac"}).label,"editor.rename");
});
test("UI titles offer an explicit edit action without implicit auto editor",()=>{
  assert.match(app,/pageAction\?\.\(item\)/);
  assert.doesNotMatch(app,/window\.DHClimateEditor\?\.enterWeatherSection\?\.\(item\.kind\)/);
  const style=fs.readFileSync(path.join(root,"style.css"),"utf8");
  assert.match(style,/\.editor-mode-heading/);
  assert.match(style,/\.page-edit-button/);
  for(const locale of ["ru","en"]){
    const dict=JSON.parse(fs.readFileSync(path.join(root,"i18n",locale+".json"),"utf8"));
    for(const key of ["editor.edit","editor.editing","editor.view","editor.editing_navigation_hint"])
      assert.ok(dict[key],locale+" missing "+key);
  }
});
