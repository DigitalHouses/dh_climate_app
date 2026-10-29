"use strict";
/* Configuration editing stays within the same Explorer object tree.
   No draft operation drives equipment; Apply changes next-start manifest. */
(() => {
  let info = null;
  let edit = null;
  let candidate = null;
  let validated = false;
  let message = "";
  let failure = false;
  let repaint = () => {};
  let openObject = () => {};
  let tr = key => key;
  const clone = value => JSON.parse(JSON.stringify(value));
  const text = (tag, value, cls = "") => {
    const el = document.createElement(tag);
    el.textContent = String(value);
    if (cls) el.className = cls;
    return el;
  };
  const button = (label, action, className="secondary-button") => {
    const el = text("button", label, className);
    el.type = "button";
    el.onclick = action;
    return el;
  };
  const online = () => !!info;
  const mutable = () => !!info && !info.pending_restart;
  const rooms = () => candidate?.rooms || [];
  function roomById(id) { return rooms().find(r => r.id === id); }
  function show(text_, bad=false) {
    message = String(text_); failure = bad; repaint();
  }
  function localize(key) { return tr("editor." + key); }
  function discardLocal() {
    edit = null; candidate = null;
  }
  function navigateAway() {
    if (!edit) return true;
    if (!window.confirm(localize("leave_warning"))) return false;
    discardLocal(); return true;
  }
  async function api(path, payload) {
    const response = await fetch("api/config/" + path, {
      method:"POST", credentials:"same-origin",
      headers:{"Content-Type":"application/json", "X-Requested-With":"DHClimateExplorer"},
      body:JSON.stringify(payload),
    });
    let body;
    try { body = await response.json(); } catch (_) { body={error:"HTTP "+response.status}; }
    if (!response.ok) {
      if (response.status === 409) info = null; // force a refresh on conflict
      throw Error(body.error || "HTTP " + response.status);
    }
    return body;
  }
  function requestMeta() { return {base_hash:info.base_hash,revision:info.revision}; }
  async function refresh() {
    try {
      const response = await fetch("api/config", {cache:"no-store",credentials:"same-origin"});
      if (!response.ok) { info=null; return; }
      info = await response.json();
    } catch (_) { info=null; }
    repaint();
  }
  async function persist() {
    if (!mutable() || !candidate) return;
    try {
      info = await api("draft",{...requestMeta(),options:candidate});
      validated = false; discardLocal(); show(localize("draft_saved"));
    } catch (e) { show(e.message,true); await refresh(); }
  }
  async function validate() {
    try {
      const report = await api("validate",requestMeta());
      validated = true;
      show(localize("valid")+": "+report.rooms+" "+tr("rooms")+", "+report.devices+" "+tr("devices"));
    } catch(e) { validated = false; show(e.message,true); }
  }
  async function apply() {
    if (!validated || !mutable()) return;
    const keyword = window.prompt(localize("apply_warning")+" "+localize("type_apply"));
    if (keyword !== "APPLY") return;
    try {
      await api("apply",requestMeta());
      validated = false;
      await refresh();
      show(localize("pending_restart"));
    } catch(e) { show(e.message,true); }
  }
  async function discard() {
    if (!window.confirm(localize("discard_warning"))) return;
    try {
      info = await api("discard",requestMeta());
      validated=false; discardLocal(); show(localize("draft_discarded"));
    } catch(e) { show(e.message,true); }
  }
  function startRoom(id=null) {
    if (!mutable() || !navigateAway()) return;
    candidate = clone(info.options);
    if (!Array.isArray(candidate.rooms)) candidate.rooms=[];
    if (id && !candidate.rooms.some(r=>r.id===id)) return;
    if (!id) candidate.rooms.push({
      id:"",name:"",temperature_sensors:[],humidity_sensors:[],
      window_sensors:[],devices:[],
    });
    edit = {kind:"room",id, index:id?candidate.rooms.findIndex(r=>r.id===id):candidate.rooms.length-1};
    message = "";
    repaint();
  }
  function startDevice(roomId, entityId=null) {
    if (!mutable() || !navigateAway()) return;
    candidate = clone(info.options);
    const room = roomById(roomId);
    if (!room) return;
    if (!Array.isArray(room.devices)) room.devices=[];
    const index = entityId ? room.devices.findIndex(d=>d.entity===entityId) : room.devices.length;
    if (index < 0) return;
    if (!entityId) room.devices.push({entity:"",role:"fast_heat",device_type:"virtual"});
    edit = {kind:"device",roomId,index};
    message = "";
    repaint();
  }
  function deleteRoom(id) {
    if (!mutable() || !navigateAway() || !window.confirm(localize("delete_room_warning"))) return;
    candidate = clone(info.options);
    candidate.rooms = (candidate.rooms || []).filter(r=>r.id!==id);
    persist();
  }
  function deleteDevice(roomId, id) {
    if (!mutable() || !navigateAway() || !window.confirm(localize("delete_device_warning"))) return;
    candidate = clone(info.options);
    const room = roomById(roomId);
    if (!room) return;
    room.devices = (room.devices || []).filter(d=>d.entity!==id);
    persist();
  }
  function field(parent, label, value, update, multiline=false, readonly=false) {
    const wrap = text("label", label, "editor-field");
    const el = document.createElement(multiline ? "textarea" : "input");
    if (!multiline) el.type = "text";
    el.value = value ?? "";
    el.readOnly = readonly;
    if (multiline) el.rows = 3;
    el.oninput = () => { update(el.value); validated=false; };
    wrap.append(el);
    parent.append(wrap);
    return el;
  }
  function selectField(parent, label, value, values, update) {
    const wrap = text("label", label, "editor-field");
    const select = document.createElement("select");
    for (const [val,display] of values) {
      const option = document.createElement("option");
      option.value = val; option.textContent = display;
      select.append(option);
    }
    select.value = value || "";
    select.onchange = () => {update(select.value);validated=false;};
    wrap.append(select); parent.append(wrap);
  }
  function lines(text_) { return text_.split(/[\n,]/).map(v=>v.trim()).filter(Boolean); }
  function optional(obj,key,value) {
    const v=value.trim();
    if (v) obj[key]=v; else delete obj[key];
  }
  function roomForm(main) {
    const room=rooms()[edit.index];
    if (!room) return;
    main.append(text("h2", edit.id?localize("edit_room"):localize("new_room"),"page-title"));
    const box=text("section","","card");
    field(box,localize("room_id"),room.id,v=>room.id=v.trim().toLowerCase(),false,!!edit.id);
    field(box,localize("room_name"),room.name,v=>room.name=v);
    for (const [key,label] of [
      ["temperature_sensors","temperature_sensors"],
      ["humidity_sensors","humidity_sensors"],
      ["window_sensors","window_sensors"]]) {
      field(box,localize(label),(room[key]||[]).join("\n"),v=>room[key]=lines(v),true);
    }
    const controls=text("div","","editor-actions");
    controls.append(button(localize("save_draft"),persist),
      button(localize("cancel"),()=>{discardLocal();repaint();}));
    box.append(controls);
    main.append(box);
  }
  function deviceForm(main) {
    const room=roomById(edit.roomId);
    const device=room?.devices?.[edit.index];
    if (!device) return;
    main.append(text("h2",localize("edit_device"),"page-title"));
    const box=text("section","","card");
    field(box,localize("entity"),device.entity||"",v=>device.entity=v.trim());
    selectField(box,localize("role"),device.role,
      [["fast_heat","FAST_HEAT"],["fast_cool","FAST_COOL"],["slow_heat","SLOW_HEAT"]],
      v=>device.role=v);
    selectField(box,localize("device_type"),device.device_type,
      [["virtual","VIRTUAL"],["hardware","HARDWARE"]],
      v=>device.device_type=v);
    selectField(box,localize("resource"),device.resource||"",
      [["",localize("none")],["home_heating","HOME_HEATING"],
        ["vrf","VRF"],["independent","INDEPENDENT"]],
      v=>{if(v)device.resource=v;else delete device.resource;});
    selectField(box,localize("reversible"),device.reversible?"true":"false",
      [["false",tr("no")],["true",tr("yes")]],v=>device.reversible=v==="true");
    selectField(box,localize("actuator"),device.actuator||"",
      [["",localize("none")],["normal_open","NORMAL_OPEN"],["normal_closed","NORMAL_CLOSED"]],
      v=>{if(v)device.actuator=v;else delete device.actuator;});
    field(box,localize("external_sensor"),device.temperature_sensor||"",
      v=>optional(device,"temperature_sensor",v));
    selectField(box,localize("screed_missing"),device.screed_sensor_unavailable||"",
      [["",localize("none")],["open","OPEN"],["closed","CLOSED"]],
      v=>{if(v)device.screed_sensor_unavailable=v;else delete device.screed_sensor_unavailable;});
    const controls=text("div","","editor-actions");
    controls.append(button(localize("save_draft"),persist),
      button(localize("cancel"),()=>{discardLocal();repaint();}));
    box.append(controls);
    main.append(box);
  }
  function renderEditor(main) {
    if (!edit) return false;
    main.replaceChildren();
    if (edit.kind==="room") roomForm(main);
    if (edit.kind==="device") deviceForm(main);
    return true;
  }
  function controls(main) {
    if (!info) return;
    if (message) main.append(text("p",message,"editor-notice "+(failure?"bad":"good")));
    if (info.pending_restart) {
      main.append(text("p",localize("pending_restart"),"notice warn"));
      return;
    }
    if (!info.dirty) return;
    const toolbar=text("section","","card editor-review");
    toolbar.append(text("h3",localize("draft"),"section-heading"),
      text("p",localize("draft_info"),"subtle"));
    const buttons=text("div","","editor-actions");
    buttons.append(button(localize("validate"),validate),
      button(localize("apply"),apply),
      button(localize("discard"),discard));
    buttons.children[1].disabled=!validated;
    toolbar.append(buttons);
    main.prepend(toolbar);
  }
  function toolbar(main,kind, id=null,roomId=null) {
    if (!mutable()) return;
    if (kind==="room" && (info.options.rooms||[]).some(r=>r.id===id)) {
      const b=text("div","","editor-actions");
      b.append(button(localize("edit_room"),()=>startRoom(id)),
        button(localize("delete_room"),()=>deleteRoom(id)));
      main.prepend(b);
    } else if (kind==="device" && id && roomId) {
      const b=text("div","","editor-actions");
      b.append(button(localize("edit_device"),()=>startDevice(roomId,id)),
        button(localize("delete_device"),()=>deleteDevice(roomId,id)));
      main.prepend(b);
    } else if(kind==="rooms") {
      const b=text("div","","editor-actions");
      b.append(button(localize("new_room"),()=>startRoom()));
      main.prepend(b);
    } else if(kind==="devices" && roomId) {
      const b=text("div","","editor-actions");
      b.append(button(localize("new_device"),()=>startDevice(roomId)));
      main.prepend(b);
    }
  }
  function previewRooms(liveRooms) {
    if (!info || (!info.dirty && !info.pending_restart)) return liveRooms;
    const configured = info.options.rooms || [];
    const result = liveRooms.map(live => {
      const next = configured.find(r => r.id === live.id);
      if (!next) return {...live, name:live.name + " [" + localize("pending_delete") + "]"};
      if (next.name !== live.name) return {...live, name:next.name + " [" + localize("draft_marker") + "]"};
      return live;
    });
    for (const item of configured) {
      if (liveRooms.some(r => r.id === item.id)) continue;
      result.push(previewRoom(item.id));
    }
    return result;
  }
  function previewRoom(id) {
    if (!info || (!info.dirty && !info.pending_restart)) return null;
    const room = (info.options.rooms || []).find(r => r.id === id);
    if (!room) return null;
    const sensor = name => ({entity_id:name,available:false,state:null,last_updated:null});
    return {
      id:room.id, name:room.name + " [" + localize("draft_marker") + "]",
      climate_entity:"climate.dh_climate_app_" + room.id,
      health:"unknown", temperature:null,humidity:null,target:null,
      profile:null,hvac_mode:null,hvac_action:null,window_state:null,
      sensors:{
        temperature:(room.temperature_sensors || []).map(sensor),
        humidity:(room.humidity_sensors || []).map(sensor),
        window:(room.window_sensors || []).map(sensor),
      },
      devices:(room.devices || []).map(d => ({
        entity_id:d.entity, device_type:d.device_type,
        role:d.role==="fast_heat"&&d.reversible?"fast_heat_cool":d.role,
        resource:d.resource,observed:null,hvac_action:null,
      })),
    };
  }
  function plusFor(node) {
    if (!mutable()) return null;
    if (node.kind==="rooms")
      return () => startRoom();
    if (node.kind==="devices")
      return () => startDevice(node.room);
    if (node.kind==="room")
      return () => startDevice(node.id);
    return null;
  }
  async function init(t,navigate,render) {
    tr=t; openObject=navigate; repaint=render;
    await refresh();
  }
  function onNavigate(){ return navigateAway(); }
  function viewMode(){ return !info?tr("read_only"):localize("administrator"); }
  window.DHClimateEditor = {
    init, canEdit:online, canChange:mutable, plusFor,
    startRoom,startDevice, renderEditor, controls, toolbar, onNavigate,
    isEditing:()=>!!edit, viewMode, previewRooms, previewRoom,
  };
})();
