"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const path = require("node:path");
const root = path.resolve(__dirname,"../src/dh_climate_app/web");
const editor = fs.readFileSync(path.join(root,"editor.js"),"utf8");
const html = fs.readFileSync(path.join(root,"index.html"),"utf8");
const app = fs.readFileSync(path.join(root,"app.js"),"utf8");
const css = fs.readFileSync(path.join(root,"style.css"),"utf8");
const baseOptions = {
  rooms:[
    {id:"bedroom",name:"Bedroom",temperature_sensors:["sensor.bedroom"],
      devices:[{entity:"climate.bedroom_ac",role:"fast_heat",device_type:"virtual"}]}
  ],
};
function runEditor(authorized=true,pendingRestart=false) {
  const window = {};
  const context = {window,fetch:async ()=>({
    ok:authorized,json:async ()=>({
      base_hash:"hash",revision:0,dirty:false,
      pending_restart:pendingRestart,
      options:baseOptions,
    }),
  }),JSON,Promise};
  vm.runInNewContext(editor,context);
  return window.DHClimateEditor.init(key=>key,()=>{},()=>{}).then(()=>window.DHClimateEditor);
}
test("ROOMS right click offers only create-room action to admin",async()=>{
  const api=await runEditor();
  assert.deepEqual(Array.from(api.menuActions({kind:"rooms"}),a=>a.label),["editor.new_room"]);
});
test("room menu contains add/edit/delete and device menu contains edit/delete",async()=>{
  const api=await runEditor();
  assert.deepEqual(Array.from(api.menuActions({kind:"room",id:"bedroom"}),a=>a.label),
    ["editor.new_device","editor.edit_room","editor.delete_room"]);
  assert.deepEqual(Array.from(api.menuActions({kind:"device",room:"bedroom",id:"climate.bedroom_ac"}),a=>a.label),
    ["editor.edit_device","editor.delete_device"]);
  assert.deepEqual(Array.from(api.menuActions({kind:"devices",room:"bedroom"}),a=>a.label),
    ["editor.new_device"]);
  assert.equal(api.menuActions({kind:"sensor",id:"sensor.bedroom"}).length,0);
  assert.equal(api.menuActions({kind:"room",id:"missing"}).length,0);
});
test("denied or pending-restart administrators never receive edit actions",async()=>{
  const viewer=await runEditor(false);
  const pending=await runEditor(true,true);
  for(const api of [viewer,pending]){
    assert.equal(api.menuActions({kind:"rooms"}).length,0);
    assert.equal(api.menuActions({kind:"room",id:"bedroom"}).length,0);
  }
});
test("context menu and real separator replace permanent plus buttons",()=>{
  assert.match(html,/id="explorer-resizer"/);
  assert.match(html,/id="context-menu"/);
  assert.doesNotMatch(app,/tree-add|\.plusFor\(/);
  assert.match(app,/line\.oncontextmenu\s*=/);
  assert.match(app,/event\.key === "ContextMenu"/);
  assert.match(css,/--explorer-width/);
  assert.match(css,/\.context-menu\[hidden\]/);
});
test("translated context actions exist in both locales",()=>{
  for(const lang of ["en","ru"]){
    const dictionary=JSON.parse(fs.readFileSync(path.join(root,"i18n",lang+".json"),"utf8"));
    assert.ok(dictionary["editor.open"]);
    assert.ok(dictionary["editor.new_room"]);
    assert.ok(dictionary["editor.delete_device"]);
  }
});
