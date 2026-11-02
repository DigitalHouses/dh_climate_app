"use strict";
const test=require("node:test"),assert=require("node:assert/strict");
const fs=require("node:fs"),vm=require("node:vm"),path=require("node:path");
const root=path.resolve(__dirname,"../src/dh_climate_app/web");
const script=fs.readFileSync(path.join(root,"editor.js"),"utf8");
const pickerScript=fs.readFileSync(path.join(root,"entity_picker.js"),"utf8");

class Element {
  constructor(tag){
    this.tagName=tag;this.className="";this.children=[];
    this._text="";this.type="";this.value="";this.checked=false;
  }
  set textContent(value){this._text=String(value);this.children=[];}
  get textContent(){return this._text+this.children.map(c=>c.textContent||"").join("");}
  append(...items){this.children.push(...items);}
  prepend(...items){this.children.unshift(...items);}
  replaceChildren(...items){this._text="";this.children=[...items];}
  setAttribute(key,value){this[key]=value;}
}
const find=(root,predicate)=>{
  const matches=[];function visit(item){
    if(predicate(item))matches.push(item);
    for(const child of item.children||[])visit(child);
  }visit(root);return matches;
};
const baseOptions={
  heating_source:"boiler",
  rooms:[{id:"hall",name:"Зал",temperature_sensors:["sensor.hall_air"],
    devices:[]}],
};
async function setup(authorized=true,pendingRestart=false,options=baseOptions) {
  const state={options:JSON.parse(JSON.stringify(options)),revision:0,
    dirty:false,pending_restart:pendingRestart};
  const requests=[];
  const pickerCalls=[];
  const window={DHClimateEntityPicker:{open:args=>pickerCalls.push(args),
    getCatalog:()=>({entities:[]})}};
  const context={window,document:{
    createElement:tag=>new Element(tag),
    getElementById:()=>({value:"ru"}),
  },fetch:async(url,params={})=>{
    requests.push({url,params});
    if(url==="api/config")return {ok:authorized,json:async()=>({
      ...JSON.parse(JSON.stringify(state)),base_hash:"hash",
    })};
    if(url==="api/labels")return {ok:true,json:async()=>({
      labels:{},room_areas:{},revision:0,
    })};
    if(url==="api/config/draft"){
      const body=JSON.parse(params.body);
      state.options=body.options;state.dirty=true;state.revision++;
      return {ok:true,json:async()=>({...state,base_hash:"hash"})};
    }
    throw new Error("Unexpected request "+url);
  },JSON,Promise,Date,Set,Intl,Number,Error};
  vm.runInNewContext(script,context);
  const api=window.DHClimateEditor;
  await api.init(key=>key,()=>{},()=>{});
  return {api,requests,state,pickerCalls};
}
test("empty hydraulic graph is editable only by administrator and not pending restart",async()=>{
  const admin=(await setup()).api;
  const viewer=(await setup(false)).api;
  const pending=(await setup(true,true)).api;
  assert.equal(admin.pageAction({kind:"hydraulics",id:"hydraulics"}).label,
    "editor.hydraulic_new_object");
  assert.equal(viewer.pageAction({kind:"hydraulics"}),null);
  assert.equal(pending.pageAction({kind:"hydraulics"}),null);
  assert.deepEqual(Array.from(admin.menuActions({kind:"hydraulic_collection",id:"separators"}),
    a=>a.label),["editor.hydraulic_add_separators"]);
});
test("creating separator binds an actual HA sensor without touching devices",async()=>{
  const {api,requests,pickerCalls,state}=await setup();
  assert.equal(api.beginHydraulic("separators"),true);
  const main=new Element("main");
  assert.equal(api.renderEditor(main),true);
  const idField=find(main,e=>e.className==="editor-field" &&
    e._text==="editor.hydraulic_id")[0];
  const nameField=find(main,e=>e.className==="editor-field" &&
    e._text==="editor.hydraulic_name")[0];
  assert.ok(idField&&nameField);
  idField.children[0].value="header";idField.children[0].oninput();
  nameField.children[0].value="Гидрострелка";nameField.children[0].oninput();
  const role=find(main,e=>e.placeholder==="editor.hydraulic_signal_role")[0];
  role.value="supply_temperature";
  find(main,e=>e.tagName==="button" &&
    e.textContent==="editor.hydraulic_add_signal")[0].onclick();
  assert.equal(pickerCalls.length,1);
  assert.equal(pickerCalls[0].kind,"hydraulic-temperature");
  pickerCalls[0].onConfirm("sensor.header_supply");
  const candidate=api.diagnosticState().candidate;
  assert.equal(candidate.hydraulics.separators[0].id,"header");
  assert.equal(candidate.hydraulics.separators[0].name,"Гидрострелка");
  assert.equal(candidate.hydraulics.separators[0].signals.supply_temperature,
    "sensor.header_supply");
  assert.equal(requests.filter(x=>x.url==="api/config/draft").length,0);
  const updated=new Element("main");api.renderEditor(updated);
  await find(updated,e=>e.tagName==="button" &&
    e.textContent==="editor.save_draft")[0].onclick();
  assert.equal(api.isEditing(),false);
  assert.equal(state.dirty,true);
  assert.equal(state.options.hydraulics.separators[0].id,"header");
  assert.equal(requests.filter(x=>x.url==="api/config/draft").length,1);
  assert.equal(requests.some(r=>r.url.includes("services")),false);
});
test("saved draft shows pending configuration without inventing sensor values",async()=>{
  const options={...baseOptions,hydraulics:{
    separators:[{id:"header",name:"Гидрострелка",
      signals:{supply_temperature:"sensor.header_supply"}}],
  }};
  const {api}=await setup(true,false,options);
  const live={separators:[],groups:[],circuits:[],pumps:[],actuators:[],
    valves:[],aggregators:[]};
  assert.equal(api.previewHydraulics(live),live,"active graph remains authoritative");
  api.beginHydraulic("pumps");
  const main=new Element("main");api.renderEditor(main);
  for(const [label,value] of [
    ["editor.hydraulic_id","pump"],["editor.hydraulic_name","Насос"]]){
    const field=find(main,e=>e.className==="editor-field" && e._text===label)[0];
    field.children[0].value=value;field.children[0].oninput();
  }
  await find(main,e=>e.tagName==="button" &&
    e.textContent==="editor.save_draft")[0].onclick();
  const preview=api.previewHydraulics(live);
  assert.equal(preview.pumps[0].name,"Насос [editor.draft_marker]");
  assert.equal(preview.separators[0].signals[0].state,null);
  assert.equal(preview.separators[0].signals[0].available,false);
});
test("groups can reference shared pumps and existing physical separator",async()=>{
  const opts={...baseOptions,hydraulics:{
    separators:[{id:"header",name:"Гидрострелка"}],
    pumps:[{id:"shared",name:"Общий насос"}],
  }};
  const {api}=await setup(true,false,opts);
  assert.equal(api.beginHydraulic("groups",null,{
    separator_id:"header",temperature_class:"low",
  }),true);
  const main=new Element("main");api.renderEditor(main);
  const link=find(main,e=>e.className==="editor-hydraulic-link")[0];
  assert.ok(link);assert.match(link.textContent,/Общий насос/);
  link.children[0].checked=true;link.children[0].onchange();
  const item=api.diagnosticState().candidate.hydraulics.groups[0];
  assert.deepEqual(Array.from(item.pump_ids),["shared"]);
  assert.equal(item.separator_id,"header");
  assert.equal(item.temperature_class,"low");
});
test("dependent equipment cannot be removed until relationships are removed",async()=>{
  const opts={...baseOptions,hydraulics:{
    groups:[{id:"low",name:"ТП",temperature_class:"low",pump_ids:["shared"]}],
    pumps:[{id:"shared",name:"Общий насос"}],
  }};
  const {api,requests}=await setup(true,false,opts);
  const actions=api.menuActions({kind:"hydraulic_item",id:"pumps:shared"});
  const removal=actions.find(x=>x.label==="editor.hydraulic_delete");
  assert.ok(removal);
  removal.run();
  assert.match(api.diagnosticState().message,/groups\/low/);
  assert.equal(api.diagnosticState().confirmation_pending,false);
  assert.equal(requests.filter(x=>x.url==="api/config/draft").length,0);
});
test("hydraulic picker filters match declared read-model domains",()=>{
  const context={window:{},document:{},fetch:()=>{},Set,Array};
  vm.runInNewContext(pickerScript,context);
  const domains=context.window.DHClimateEntityPicker.domainsFor;
  assert.deepEqual(Array.from(domains("hydraulic-temperature")),["sensor"]);
  assert.deepEqual(Array.from(domains("hydraulic-pressure")),["sensor"]);
  for(const domain of ["sensor","binary_sensor","switch","climate","valve","select"])
    assert.ok(Array.from(domains("hydraulic-signal")).includes(domain),domain);
});
