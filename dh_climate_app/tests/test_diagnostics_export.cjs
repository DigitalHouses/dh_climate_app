"use strict";
const test=require("node:test");
const assert=require("node:assert/strict");
const fs=require("node:fs");
const path=require("node:path");
const vm=require("node:vm");

const web=path.resolve(__dirname,"../src/dh_climate_app/web");
const source=fs.readFileSync(path.join(web,"diagnostics.js"),"utf8");

function fixture({status=200,offline=false}={}){
  const exports=[];
  let clicks=0;
  const statusElement={textContent:""};
  class Element {
    constructor(){
      this.attributes=[];this.className="card";this.textContent="Сенсор Google 9 °C";
      this.scrollWidth=400;this.scrollHeight=80;this.outerHTML="<section class=card>Сенсор Google 9 °C</section>";
    }
    cloneNode(){return this;}
    querySelectorAll(){return [];}
    getBoundingClientRect(){return {x:1,y:2,width:400,height:80};}
  }
  const element=new Element();
  const document={
    title:"DH Climate Explorer",
    styleSheets:[{ownerNode:{getAttribute:()=> "style.css"},
      cssRules:[{cssText:".card { color: white; }"}]}],
    scripts:[{getAttribute:()=> "diagnostics.js"}],
    querySelector:selector=>selector==="#content"?element:null,
    querySelectorAll:()=>[],
    getElementById:id=>id==="diagnostics-status"?statusElement:null,
    createElement:tag=>({tagName:tag.toUpperCase(),style:{},
      click(){clicks++;},remove(){},set href(value){this._href=value;},
      set download(value){this._download=value;}}),
    body:{append(){}},
  };
  const window={
    addEventListener(){},
    innerWidth:1760,innerHeight:850,devicePixelRatio:1,
    getComputedStyle:()=>({display:"block",position:"static",overflow:"auto",
      gridTemplateColumns:"",font:"14px sans-serif",backgroundColor:"rgb(0,0,0)",
      color:"white"}),
  };
  class Blob{
    constructor(parts,metadata){this.text=parts.join("");this.type=metadata.type;exports.push(this);}
  }
  const URL={createObjectURL:()=> "blob:mock",revokeObjectURL(){}};
  let requests=0;
  async function fetch(url){
    requests++;
    if(url==="api/diagnostics"){
      if(offline)throw Error("network offline");
      return {ok:status===200,status,
        json:async()=>({
          schema_version:1,
          manifest:{author_id:"private-user",options:{
            providers:[{id:"google",entity_id:"weather.asyl_mura"}],
            api_key:"SHOULD_NOT_LEAK",
          }},
          snapshot:{app:{version:"0.2.21"},weather:{
            temperature_sources:[{entity_id:"google.temperature",state:9.1}]
          }},
          runtime:{queued_commands:0,mqtt:{ever_connected:true}},
        })};
    }
    if(url==="api/snapshot")
      return {ok:true,json:async()=>({app:{version:"0.2.21"}})};
    throw Error("Unexpected request");
  }
  const context={document,window,navigator:{language:"ru-RU"},
    fetch,URL,Blob,setTimeout,clearTimeout,Date,JSON,Math,Number,Object,
    String,Array,Error,AbortController};
  vm.runInNewContext(source,context);
  return {window,exports,statusElement,getClicks:()=>clicks,getRequests:()=>requests};
}

test("top-bar control and diagnostics asset are installed",()=>{
  const html=fs.readFileSync(path.join(web,"index.html"),"utf8");
  assert.match(html,/id="save-diagnostics"/);
  assert.match(html,/src="diagnostics.js"/);
  assert.match(html,/id="diagnostics-status"/);
});

test("save report includes tree, DOM, CSS, runtime and masks sensitive fields",async()=>{
  const f=fixture();
  const button={disabled:false,textContent:"Сохранить диагностику"};
  await f.window.DHClimateDiagnostics.save(()=>({
    selection:{kind:"weather_priorities"},
    tree:[{kind:"weather",children:[{kind:"weather_priorities"}]}],
    local_unsaved:{priorities:{temperature:["google.temperature"]}},
    bearer:"Bearer hiddenValue",
  }),button,key=>key);
  assert.equal(f.getClicks(),1);
  assert.equal(f.getRequests(),1);
  assert.equal(button.disabled,false);
  const raw=f.exports[0].text;
  assert.doesNotMatch(raw,/SHOULD_NOT_LEAK|private-user|hiddenValue/);
  const report=JSON.parse(raw);
  assert.equal(report.schema_version,1);
  assert.equal(report.ui.state.selection.kind,"weather_priorities");
  assert.equal(report.ui.state.local_unsaved.priorities.temperature[0],"google.temperature");
  assert.match(report.ui.rendered_html["#content"],/Сенсор Google/);
  assert.match(report.ui.css[0].rules,/card/);
  assert.equal(report.backend.data.runtime.queued_commands,0);
  assert.equal(report.backend.data.manifest.options.api_key,"[REDACTED]");
  assert.equal(f.statusElement.textContent,"diagnostics_ready");
});

test("offline backend still yields a useful downloadable client report",async()=>{
  const f=fixture({offline:true});
  const button={disabled:false,textContent:"Save diagnostics"};
  await f.window.DHClimateDiagnostics.save(()=>({
    selection:{kind:"season"},snapshot_browser_cache:{weather:{season:"heat"}},
  }),button,key=>key);
  assert.equal(f.getClicks(),1);
  const report=JSON.parse(f.exports[0].text);
  assert.equal(report.ui.state.selection.kind,"season");
  assert.equal(report.backend.ok,false);
  assert.equal(report.backend.snapshot.app.version,"0.2.21");
});
