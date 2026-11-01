"use strict";
const test=require("node:test");
const assert=require("node:assert/strict");
const fs=require("node:fs");
const path=require("node:path");
const vm=require("node:vm");

const source=fs.readFileSync(
  path.join(__dirname,"../src/dh_climate_app/web/editor.js"),"utf8",
);

class Element {
  constructor(tag){
    this.tagName=tag;this.children=[];this.className="";
    this._text="";this.disabled=false;this.value="";
  }
  set textContent(value){this._text=String(value);this.children=[];}
  get textContent(){return this._text+this.children.map(e=>
    typeof e==="string"?e:e.textContent||"").join("");}
  append(...parts){this.children.push(...parts);}
  replaceChildren(...parts){this.children=[...parts];this._text="";}
  setAttribute(name,value){this[name]=String(value);}
}

const all=(element,pred)=>{
  const result=[];
  function visit(node){
    if(pred(node))result.push(node);
    for(const child of node.children||[])if(child && typeof child==="object")visit(child);
  }
  visit(element);
  return result;
};
const base={
  outdoor:{temperature_sources:[],humidity_sources:[]},
  providers:[
    {id:"p_met",entity_id:"weather.forecast_home_assistant"},
    {id:"p_google",entity_id:"weather.asyl_mura"},
    {id:"p_almaty",entity_id:"weather.almaty"},
  ],
  physical_sensors:[
    {id:"t_garden",entity_id:"sensor.garden_temperature",quantity:"temperature"},
  ],
  priorities:{
    temperature:["p_met.temperature","p_google.temperature","t_garden"],
    humidity:["p_google.humidity","p_met.humidity"],
  },
  rooms:[{id:"bedroom",name:"Bedroom",temperature_sensors:["sensor.bedroom"],
    humidity_sensors:[],window_sensors:[],devices:[]}],
};

test("weather provider row has independent, actionable T/H priority controls",async()=>{
  let saved=null,mutationCount=0;
  const document={
    createElement:tag=>new Element(tag),
    getElementById:id=>id==="language"?{value:"ru"}:null,
  };
  const window={};
  const fetch=async (url,options={})=>{
    if(url==="api/config")return {ok:true,json:async()=>({
      options:JSON.parse(JSON.stringify(base)),
      base_hash:"hash",revision:0,dirty:false,pending_restart:false,
    })};
    if(url==="api/labels")return {ok:true,json:async()=>({
      schema_version:1,revision:0,labels:{},room_areas:{},
    })};
    if(url==="api/config/draft"){
      saved=JSON.parse(options.body).options;mutationCount++;
      return {ok:true,json:async()=>({
        options:saved,base_hash:"hash",revision:1,dirty:true,
        pending_restart:false,
      })};
    }
    throw Error("unexpected API request: "+url);
  };
  vm.runInNewContext(source,{document,window,fetch,JSON,Promise,Date,Error,Set});
  const api=window.DHClimateEditor;
  await api.init(key=>key,()=>{},()=>{});
  api.startWeather();
  const main=new Element("main");

  function providerRow(id){
    api.renderEditor(main);
    return all(main,e=>e.className?.includes("editor-provider-row")&&
      e.children[0]?.textContent.includes(id))[0];
  }
  function section(row,quantity){
    return all(row,e=>e.className==="editor-provider-priority").find(e=>
      e.children[0].textContent.startsWith(
        quantity==="temperature"?
        "editor.weather_short_temperature":"editor.weather_short_humidity",
      ));
  }
  function action(row,quantity,label){
    const item=section(row,quantity);
    assert.ok(item,quantity+" priority section");
    const control=item.children.find(e=>e.tagName==="button"&&e.textContent===label);
    assert.ok(control,label+" action");
    return control;
  }

  let google=providerRow("weather.asyl_mura");
  assert.match(section(google,"temperature").textContent,/№2/);
  assert.match(section(google,"humidity").textContent,/№1/);
  assert.equal(action(google,"temperature","↑").disabled,false);
  action(google,"temperature","↑").onclick();
  google=providerRow("weather.asyl_mura");
  assert.match(section(google,"temperature").textContent,/№1/);
  assert.match(section(google,"humidity").textContent,/№1/);
  assert.equal(action(google,"temperature","↑").disabled,true);

  let almaty=providerRow("weather.almaty");
  assert.match(section(almaty,"temperature").textContent,/weather_observation_only/);
  assert.match(section(almaty,"humidity").textContent,/weather_observation_only/);
  action(almaty,"temperature","+").onclick();
  almaty=providerRow("weather.almaty");
  assert.match(section(almaty,"temperature").textContent,/№4/);
  assert.match(section(almaty,"humidity").textContent,/weather_observation_only/);
  // Removing T from priority leaves the provider and H untouched.
  action(almaty,"temperature","−").onclick();
  almaty=providerRow("weather.almaty");
  assert.match(section(almaty,"temperature").textContent,/weather_observation_only/);

  // The full priority list includes a physical sensor between providers.
  google=providerRow("weather.asyl_mura");
  action(google,"temperature","↓").onclick();
  google=providerRow("weather.asyl_mura");
  assert.match(section(google,"temperature").textContent,/№2/);
  assert.match(section(google,"humidity").textContent,/№1/);

  assert.equal(mutationCount,0,"changes stay in local draft before Save");
  api.renderEditor(main);
  const save=all(main,e=>e.tagName==="button"&&
    e.textContent==="editor.save_draft")[0];
  assert.ok(save);
  await save.onclick();
  assert.equal(mutationCount,1);
  assert.deepEqual(saved.priorities.temperature,[
    "p_met.temperature","p_google.temperature","t_garden",
  ]);
  assert.deepEqual(saved.priorities.humidity,[
    "p_google.humidity","p_met.humidity",
  ]);
  assert.equal(saved.providers.length,3);
  assert.deepEqual(saved.rooms,base.rooms,"room config remains untouched");
  assert.equal(saved.providers[2].entity_id,"weather.almaty",
    "monitoring-only provider stays registered");
});
