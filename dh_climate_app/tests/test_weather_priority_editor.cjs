"use strict";
const test=require("node:test");
const assert=require("node:assert/strict");
const fs=require("node:fs");
const path=require("node:path");
const vm=require("node:vm");
const source=fs.readFileSync(
  path.join(__dirname,"../src/dh_climate_app/web/editor.js"),"utf8");

class Element {
  constructor(tag){
    this.tagName=tag;this.children=[];this.className="";
    this._text="";this.disabled=false;this.draggable=false;this.value="";
  }
  set textContent(s){this._text=String(s);this.children=[];}
  get textContent(){return this._text+this.children.map(x=>
    typeof x==="string"?x:x.textContent||"").join("");}
  append(...items){this.children.push(...items);}
  replaceChildren(...items){this._text="";this.children=[...items];}
  setAttribute(k,v){this[k]=String(v);}
}
function find(root,predicate) {
  const found=[];
  function visit(x){
    if (predicate(x)) found.push(x);
    for(const c of x.children||[])if(c && typeof c==="object")visit(c);
  }
  visit(root);return found;
}
const base={
  outdoor:{temperature_sources:[],humidity_sources:[]},
  providers:[
    {id:"met",entity_id:"weather.forecast_home_assistant"},
    {id:"google",entity_id:"weather.asyl_mura"},
    {id:"almaty",entity_id:"weather.almaty"},
  ],
  physical_sensors:[{id:"garden",quantity:"temperature",
    entity_id:"sensor.garden_temperature"}],
  priorities:{
    temperature:["met.temperature","google.temperature","garden"],
    humidity:["google.humidity","met.humidity"],
  },
  rooms:[{id:"bedroom",name:"Bedroom",temperature_sensors:["sensor.bedroom"],
    devices:[]}],
};
const weather={
  source_model:"sensors",
  source:"met.temperature",
  humidity_source:"google.humidity",
  providers:[
    {id:"met",entity_id:"weather.forecast_home_assistant",friendly_name:"Forecast"},
    {id:"google",entity_id:"weather.asyl_mura",friendly_name:"Google"},
    {id:"almaty",entity_id:"weather.almaty",friendly_name:"Almaty"},
  ],
  temperature_sources:[
    {entity_id:"met.temperature",state:9.3,available:true},
    {entity_id:"google.temperature",state:2.7,available:true},
    {entity_id:"garden",state:null,available:false},
  ],
  humidity_sources:[
    {entity_id:"google.humidity",state:72,available:true},
    {entity_id:"met.humidity",state:35,available:true},
  ],
};
const catalog={entities:[
  {entity_id:"sensor.custom_ha_meto",climate_source_id:"met.temperature",
   name:"Полное имя из HA · Met.no температура",state:"9.3"},
  {entity_id:"sensor.custom_ha_google",climate_source_id:"google.temperature",
   name:"Google температура на улице",state:"2.7"},
  {entity_id:"sensor.garden_temperature",name:"Физическая температура сада",
   state:"unavailable"},
]};
test("separate priority page shows HA names, values, allows arrow and drag without mutating humidity",async()=>{
  let posted=null,requests=0;
  const window={};
  const context={window,document:{
    createElement:tag=>new Element(tag),
    getElementById:id=>id==="language"?{value:"ru"}:null,
  },fetch:async(url,args={})=>{
    if(url==="api/config")return {ok:true,json:async()=>({
      options:JSON.parse(JSON.stringify(base)),base_hash:"x",
      revision:0,dirty:false,pending_restart:false,
    })};
    if(url==="api/labels")return {ok:true,json:async()=>({
      schema_version:1,revision:0,labels:{},room_areas:{},
    })};
    if(url==="api/config/draft") {
      posted=JSON.parse(args.body).options;requests++;
      return {ok:true,json:async()=>({
        options:posted,base_hash:"x",revision:1,
        dirty:true,pending_restart:false,
      })};
    }
    throw Error("Unexpected request "+url);
  },JSON,Promise,Date,Set,Intl,Number,Error};
  vm.runInNewContext(source,context);
  const api=window.DHClimateEditor;
  await api.init(x=>x,()=>{},()=>{});
  api.setWeatherContext(weather,catalog);
  assert.equal(api.enterWeatherSection("weather_priorities"),true);
  const main=new Element("main");
  function rows(){
    api.renderEditor(main);
    return find(main,x=>x.className?.includes("editor-priority-row"));
  }
  let all=rows();
  assert.equal(all.length,5);
  assert.equal(all.filter(r=>r.textContent.includes("weather_active")).length,2);
  assert.match(all[0].textContent,/weather_active/);
  assert.match(all[3].textContent,/weather_active/);
  assert.match(all[0].textContent,/Полное имя из HA/);
  assert.match(all[0].textContent,/sensor.custom_ha_meto/);
  assert.match(all[0].textContent,/9,3.*°C/);
  assert.match(all[2].textContent,/Недоступно|weather_unavailable/);
  const up=find(all[1],x=>x.tagName==="button"&&x.textContent==="↑")[0];
  assert.ok(up);
  up.onclick(); // Google becomes T #1, humidity unchanged.
  all=rows();
  assert.match(all[0].textContent,/Google температура/);
  assert.doesNotMatch(all[0].textContent,/weather_active/);
  assert.match(all[1].textContent,/weather_active/);
  assert.match(all[3].textContent,/weather_active/);
  // Live Engine selection follows the source, not row position.
  api.setWeatherContext({...weather,source:"google.temperature"},catalog);
  all=rows();
  assert.match(all[0].textContent,/weather_active/);
  assert.doesNotMatch(all[1].textContent,/weather_active/);

  // Drag physical sensor from T #3 to T #1. Humidity remains unchanged.
  let started=null,prevented=0;
  all[2].ondragstart({dataTransfer:{
    effectAllowed:null,setData:(type,value)=>{started=value;},
  }});
  assert.equal(started,"garden");
  all[0].ondragover({preventDefault:()=>{prevented++;},dataTransfer:{}});
  all[0].ondrop({preventDefault:()=>{prevented++;}});
  assert.equal(prevented,2);
  all=rows();
  assert.match(all[0].textContent,/Физическая температура сада/);
  const save=find(main,x=>x.tagName==="button"&&x.textContent==="editor.save_draft")[0];
  assert.ok(save);
  assert.equal(requests,0,"Arrow/drag never perform Apply or server write");
  await save.onclick();
  assert.equal(requests,1);
  assert.deepEqual(Array.from(posted.priorities.temperature),
    ["garden","google.temperature","met.temperature"]);
  assert.deepEqual(Array.from(posted.priorities.humidity),
    ["google.humidity","met.humidity"]);
  assert.deepEqual(JSON.parse(JSON.stringify(posted.rooms)),base.rooms);
  assert.deepEqual(JSON.parse(JSON.stringify(posted.providers)),base.providers);
});

test("sources page is separate from priority editing",async()=>{
  const context={window:{},document:{createElement:tag=>new Element(tag),
    getElementById:()=>({value:"ru"})},
  fetch:async url=>({ok:true,json:async()=>url==="api/labels"?
    {revision:0,labels:{},room_areas:{}}:
    {options:JSON.parse(JSON.stringify(base)),base_hash:"x",
     revision:0,dirty:false,pending_restart:false}}),
  JSON,Promise,Set,Date,Intl,Number};
  vm.runInNewContext(source,context);
  const api=context.window.DHClimateEditor;
  await api.init(x=>x,()=>{},()=>{});
  api.setWeatherContext(weather,catalog);
  assert.equal(api.enterWeatherSection("weather_sources"),true);
  const main=new Element("main");
  api.renderEditor(main);
  const content=main.textContent;
  assert.match(content,/editor.weather_providers/);
  assert.doesNotMatch(content,/editor.weather_physical/);
  assert.doesNotMatch(content,/editor.weather_priorities_page/);
  assert.doesNotMatch(content,/editor.weather_drag_help/);
  // Naming panel must show HA original, not a dash.
  const providerRow=find(main,x=>x.className==="editor-bound-entity" &&
    x.textContent.includes("weather.almaty") &&
    find(x,y=>y.tagName==="button" &&
      y.textContent==="editor.rename").length>0)[0];
  assert.ok(providerRow);
  const rename=find(providerRow,x=>x.tagName==="button" &&
    x.textContent==="editor.rename")[0];
  assert.ok(rename);
  rename.onclick();
  api.renderEditor(main);
  assert.match(main.textContent,/Almaty/);
  assert.match(main.textContent,/editor.ha_name/);
  // Separate branch and editor owns existing HA sensor.* sources.
  const cancel=find(main,x=>x.tagName==="button" &&
    x.textContent==="editor.cancel")[0];
  assert.ok(cancel);
  cancel.onclick();
  assert.equal(api.isEditing(),false);
  assert.equal(api.enterWeatherSection("outdoor_physical"),true);
  api.renderEditor(main);
  assert.match(main.textContent,/editor.weather_hardware_title/);
  assert.match(main.textContent,/editor.weather_physical/);
  assert.doesNotMatch(main.textContent,/editor.weather_providers/);
});
