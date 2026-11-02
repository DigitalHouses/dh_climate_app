"use strict";
const test=require("node:test"),assert=require("node:assert/strict");
const fs=require("node:fs"),path=require("node:path"),vm=require("node:vm");
const web=path.resolve(__dirname,"../src/dh_climate_app/web");
const source=fs.readFileSync(path.join(web,"app.js"),"utf8");
class Element{
  constructor(tag){this.tagName=tag;this.children=[];this.className="";this._text="";this.attributes={};}
  set textContent(value){this._text=String(value);this.children=[];}
  get textContent(){return this._text+this.children.map(x=>x.textContent||"").join("");}
  append(...items){this.children.push(...items);}
  replaceChildren(...items){this._text="";this.children=[...items];}
  setAttribute(k,v){this.attributes[k]=v;}
}
const context=vm.createContext({
  window:{},document:{createElement:tag=>new Element(tag)},
  navigator:{language:"ru"},Intl,Number,Set,
});
const boot=source.indexOf('document.addEventListener("pointerdown"');
const signalStart=source.indexOf("function signalRows(");
const signalEnd=source.indexOf("function demandRows(",signalStart);
const providerStart=source.indexOf("function showProviders(");
const providerEnd=source.indexOf("function weatherSourceMetadata(",providerStart);
const roomStart=source.indexOf("function roomSensors(");
const roomEnd=source.indexOf("function renderInspector(",roomStart);
assert.ok(boot>0 && signalStart>boot && providerStart>signalEnd &&
  roomStart>providerEnd && roomEnd>roomStart);
const dict=JSON.parse(fs.readFileSync(path.join(web,"i18n/ru.json"),"utf8"));
vm.runInContext(source.slice(0,boot)+"\n"+source.slice(signalStart,signalEnd)+"\n"+
  source.slice(providerStart,providerEnd)+"\n"+source.slice(roomStart,roomEnd)+
  "\ndictionary="+JSON.stringify(dict)+";locale='ru';"+
  "globalThis.api={buildTree,showOutdoorPhysical,showProviders,signalRows,roomSensors,showOutdoorSensor,physicalReading,entityReading};",
  context);
const api=context.api;
const state=(id,value,unit,available=true)=>({
  entity_id:id,state:value,unit,available,
  friendly_name:id,
});
function sample(){
  return {
    app:{ha_connected:true,health:"healthy",problems:[]},
    weather:{
      source_model:"sensors",providers:[
        {id:"met",entity_id:"weather.met",friendly_name:"Met.no",
         temperature:9.4,humidity:45},
      ],physical_sensors:[
        {id:"local",entity_id:"sensor.local_temperature",
         friendly_name:"Температура гостиной",quantity:"temperature",value:21.75,
         observed:state("sensor.local_temperature","21.75","°C")},
        {id:"humidity",entity_id:"sensor.local_humidity",
         friendly_name:"Влажность",quantity:"humidity",value:0,
         observed:state("sensor.local_humidity","0","%")},
        {id:"unavailable",entity_id:"sensor.offline",
         friendly_name:"Недоступный датчик",quantity:"temperature",value:null,
         observed:state("sensor.offline","unavailable","°C",false)},
        {id:"native",entity_id:"sensor.outside_f",
         friendly_name:"Сенсор Фаренгейт",quantity:"temperature",value:null,
         observed:state("sensor.outside_f","68.2","°F")},
      ],
    },
    home:{heating_source:"boiler",vrf_enabled:false,resources:[{
      id:"boiler",signals:[{...state("sensor.boiler_pressure","1.8","bar"),role:"pressure"}],
      pumps:[],circuits:[],
    }]},
    rooms:[{
      id:"livingroom",name:"Гостиная",health:"healthy",
      devices:[],sensors:{
        temperature:[state("sensor.room_temperature","23.1","°C")],
        humidity:[state("sensor.room_humidity","64","%")],
        window:[state("binary_sensor.window","on",null)],
      },
    }],
  };
}
function prepare(value){
  context.fixture=value;
  vm.runInContext("snapshot=fixture;nodes=buildTree(snapshot);globalThis.treeExport=nodes;",context);
}
function lookup(nodes,pred){
  for(const item of nodes){
    if(pred(item))return item;
    const found=lookup(item.children||[],pred);
    if(found)return found;
  }
  return null;
}
test("all hardware sensors expose temperature/humidity, zero, unavailable and native °F",()=>{
  prepare(sample());
  const main=new Element("main");
  api.showOutdoorPhysical(main);
  const rendered=main.textContent;
  assert.match(rendered,/21,8 °C/);
  assert.match(rendered,/0,0 %/);
  assert.match(rendered,/68.2 °F/);
  assert.match(rendered,/Недоступно/);
  assert.match(rendered,/sensor.local_temperature/);
  assert.match(rendered,/sensor.local_humidity/);
  assert.equal(lookup(context.treeExport,n=>n.kind==="outdoor_sensor"&&n.id==="local").reading,"21,8 °C");
  assert.equal(lookup(context.treeExport,n=>n.kind==="outdoor_sensor"&&n.id==="humidity").reading,"0,0 %");
  assert.equal(lookup(context.treeExport,n=>n.kind==="outdoor_sensor"&&n.id==="native").reading,"68.2 °F");
});
test("provider list and tree leaf sensors show current values",()=>{
  prepare(sample());
  const main=new Element("main");
  api.showProviders(main);
  assert.match(main.textContent,/9,4 °C/);
  assert.match(main.textContent,/45,0 %/);
  assert.match(main.textContent,/weather.met/);
  const tree=context.treeExport;
  assert.equal(lookup(tree,n=>n.kind==="weather_sensor"&&n.id==="met.temperature").reading,"9,4 °C");
  assert.equal(lookup(tree,n=>n.kind==="weather_sensor"&&n.id==="met.humidity").reading,"45,0 %");
});
test("room sensor and engineering signal lists preserve the HA unit and raw on/off",()=>{
  const data=sample();prepare(data);
  const room=api.roomSensors(data.rooms[0]);
  assert.match(room.textContent,/23.1 °C/);
  assert.match(room.textContent,/64 %/);
  assert.match(room.textContent,/on/);
  const resource=api.signalRows(data.home.resources[0].signals);
  assert.match(resource.textContent,/1.8 bar/);
  assert.equal(lookup(context.treeExport,n=>n.kind==="sensor"&&n.id==="sensor.room_temperature").reading,"23.1 °C");
});
test("offline readings never pretend to be live and do not become zero",()=>{
  const data=sample();data.app.ha_connected=false;prepare(data);
  const main=new Element("main");
  api.showOutdoorPhysical(main);
  assert.doesNotMatch(main.textContent,/21,8 °C|68.2 °F/);
  assert.match(main.textContent,/Недоступно/);
  assert.equal(lookup(context.treeExport,n=>n.kind==="weather_sensor"&&n.id==="met.temperature").reading,"Недоступно");
  assert.equal(lookup(context.treeExport,n=>n.kind==="sensor"&&n.id==="sensor.room_temperature").reading,"Недоступно");
});
