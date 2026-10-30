"use strict";
/* Configuration editing stays within the same Explorer object tree.
   No draft operation drives equipment; Apply changes next-start manifest. */
(() => {
  let info = null;
  let labelsState = {schema_version:1,revision:0,labels:{}};
  let edit = null;
  let candidate = null;
  let validated = false;
  let approvalPhrase = "";
  let confirmation = null;
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
  const labelKey = item => {
    if (item.kind==="room") return "room:" + item.id;
    if (item.kind==="sensor" || item.kind==="device") return "entity:" + item.id;
    if (item.kind==="resource") return "resource:" + item.id;
    if (item.kind==="part")
      return "part:" + item.resource + ":" + item.partType + ":" + item.id;
    return null;
  };
  function displayName(kind, id, language, fallback) {
    const text=labelsState.labels?.[kind + ":" + id]?.[language];
    return text || fallback;
  }
  async function loadLabels() {
    try {
      const response=await fetch("api/labels",{cache:"no-store",credentials:"same-origin"});
      if (response.ok) {
        const next=await response.json();
        if (next && typeof next.labels==="object" && Number.isInteger(next.revision))
          labelsState=next;
      }
    } catch (_) { /* HA read-only Explorer still works without label service */ }
    repaint();
  }
  function startLabel(item) {
    if (!online() || !navigateAway()) return;
    const key=labelKey(item);
    if (!key) return;
    // Right-click action edits the object itself, not the formerly selected page.
    openObject(item);
    const original=labelsState.labels?.[key] || {};
    edit={kind:"label",key,technicalId:item.technicalId || item.id,
      haName:item.haName || null, sourceName:item.sourceName || null,
      names:{ru:original.ru || "",en:original.en || ""}};
    message="";
    repaint();
  }
  function labelForm(main) {
    main.append(text("h2",localize("rename"),"page-title"));
    const section=text("section","","card");
    const values=edit.names;
    field(section,localize("name_ru"),values.ru,v=>values.ru=v);
    field(section,localize("name_en"),values.en,v=>values.en=v);
    section.append(text("h3",localize("reference"),"section-heading"));
    if (edit.sourceName) section.append(text("p",
      localize("configuration_name")+": "+edit.sourceName,"subtle"));
    section.append(text("p",localize("ha_name")+": "+(edit.haName || "—"),"subtle"));
    section.append(text("p",localize("technical_id")+": "+edit.technicalId,"mono subtle"));
    section.append(text("p",localize("empty_default"),"subtle small"));
    const actions=text("div","","editor-actions");
    actions.append(button(localize("save_name"),async()=>{
      try {
        const response=await fetch("api/labels",{
          method:"POST",credentials:"same-origin",
          headers:{"Content-Type":"application/json","X-Requested-With":"DHClimateExplorer"},
          body:JSON.stringify({key:edit.key,names:values,revision:labelsState.revision}),
        });
        const result=await response.json();
        if(!response.ok)throw Error(result.error || "HTTP "+response.status);
        labelsState=result;discardLocal();show(localize("name_saved"));
      } catch(e) {
        show(e.message,true);
        await loadLabels();
      }
    }),button(localize("cancel"),()=>{discardLocal();repaint();}));
    section.append(actions);
    main.append(section);
  }
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
    // A blocked navigation warning belongs to the unsaved form only.
    // It must not persist on ROOMS after pressing Cancel.
    if (message === localize("save_or_cancel")) {
      message = "";
      failure = false;
    }
  }
  function navigateAway() {
    if (!edit) {
      if (message === localize("save_or_cancel")) {
        message = "";
        failure = false;
      }
      return true;
    }
    show(localize("save_or_cancel"),true);
    return false;
  }
  function confirmAction(description, action) {
    confirmation = {description:localize(description), action};
    repaint();
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
      validated = false; approvalPhrase = "";
      discardLocal(); show(localize("draft_saved"));
    } catch (e) { show(e.message,true); await refresh(); }
  }
  async function validate() {
    try {
      const report = await api("validate",requestMeta());
      validated = true; approvalPhrase = "";
      show(localize("valid")+": "+report.rooms+" "+tr("rooms")+", "+report.devices+" "+tr("devices"));
    } catch(e) { validated = false; show(e.message,true); }
  }
  async function apply() {
    if (!validated || !mutable() || approvalPhrase !== "APPLY") return;
    try {
      await api("apply",{...requestMeta(),confirm:"APPLY"});
      validated = false; approvalPhrase = "";
      await refresh();
      show(localize("pending_restart"));
    } catch(e) { show(e.message,true); }
  }
  function discard() {
    confirmAction("discard_warning", async () => {
      try {
        info = await api("discard",requestMeta());
        validated=false; approvalPhrase = "";
        discardLocal(); show(localize("draft_discarded"));
      } catch(e) { show(e.message,true); }
    });
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
    if (!mutable() || !navigateAway()) return;
    confirmAction("delete_room_warning", async () => {
      candidate = clone(info.options);
      candidate.rooms = (candidate.rooms || []).filter(r=>r.id!==id);
      await persist();
    });
  }
  function deleteDevice(roomId, id) {
    if (!mutable() || !navigateAway()) return;
    confirmAction("delete_device_warning", async () => {
      candidate = clone(info.options);
      const room = roomById(roomId);
      if (!room) return;
      room.devices = (room.devices || []).filter(d=>d.entity!==id);
      await persist();
    });
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
  function usages() {
    const result={};
    for(const room of (candidate?.rooms || info?.options?.rooms || [])){
      for(const key of ["temperature_sensors","humidity_sensors","window_sensors"]) {
        for(const id of room[key] || []) (result[id] ||= []).push(room.name || room.id);
      }
      for(const device of room.devices || []) {
        if(device.entity)(result[device.entity] ||= []).push(room.name || room.id);
      }
    }
    return result;
  }
  function entityField(parent,label,value,kind,onChange,{multiple=false,roomName=""}={}){
    const section=text("div","","editor-entity-field");
    section.append(text("p",label,"editor-entity-title"));
    const list=text("div","","editor-bound-list");
    const ids=(multiple ? (value || []) : [value]).filter(Boolean);
    if(!ids.length)list.append(text("p",localize("none"),"subtle small"));
    for(const id of ids){
      const line=text("div","","editor-bound-entity");
      const name=text("span",id,"mono");
      name.title=id;
      const remove=button("×",()=>{
        const next=multiple ? ids.filter(x=>x!==id) : null;
        onChange(next);
        validated=false;
        repaint();
      });
      remove.setAttribute("aria-label",localize("remove_entity")+" "+id);
      line.append(name,remove);list.append(line);
    }
    const choose=button(ids.length?localize("change_binding"):localize("add_binding"),
      ()=>window.DHClimateEntityPicker.open({
        kind,multiple,values:ids,title:label,
        areaHint:roomName,usage:usages(),tr,
        onConfirm:next=>{
          onChange(next);
          validated=false;
          repaint();
        },
      }));
    section.append(list,choose);parent.append(section);
  }
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
    for (const [key,label,kind] of [
      ["temperature_sensors","temperature_sensors","temperature"],
      ["humidity_sensors","humidity_sensors","humidity"],
      ["window_sensors","window_sensors","window"]]) {
      entityField(box,localize(label),room[key]||[],kind,
        value=>{room[key]=value;},{multiple:true,roomName:room.name});
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
    entityField(box,localize("entity"),device.entity,
      device.device_type==="hardware"?"actuator-hardware":"actuator-virtual",
      value=>{device.entity=value||"";},{roomName:room.name});
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
    entityField(box,localize("external_sensor"),device.temperature_sensor,
      "temperature",value=>{
        if(value)device.temperature_sensor=value;
        else delete device.temperature_sensor;
      },{roomName:room.name});
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
    if (edit.kind==="label") labelForm(main);
    if (edit.kind==="room") roomForm(main);
    if (edit.kind==="device") deviceForm(main);
    return true;
  }
  function controls(main) {
    if (!info) return;
    if (message) main.append(text("p",message,"editor-notice "+(failure?"bad":"good")));
    if (confirmation) {
      const panel=text("section","","card editor-review");
      panel.append(text("p",confirmation.description,"warn"));
      const actions=text("div","","editor-actions");
      actions.append(button(localize("confirm"),async()=>{
        const action=confirmation.action; confirmation=null;
        await action();
      }),button(localize("cancel"),()=>{confirmation=null;repaint();}));
      panel.append(actions);
      main.prepend(panel);
    }
    if (info.pending_restart) {
      main.append(text("p",localize("pending_restart"),"notice warn"));
      return;
    }
    if (!info.dirty) return;
    const toolbar=text("section","","card editor-review");
    toolbar.append(text("h3",localize("draft"),"section-heading"),
      text("p",localize("draft_info"),"subtle"));
    const buttons=text("div","","editor-actions");
    buttons.append(button(localize("validate"),validate));
    if (validated) {
      const confirmField=text("label",localize("apply_warning"),"editor-field");
      const input=document.createElement("input");
      input.type="text"; input.placeholder="APPLY"; input.value=approvalPhrase;
      const applyButton=button(localize("apply"),apply);
      applyButton.disabled=approvalPhrase!=="APPLY";
      input.oninput=()=>{
        approvalPhrase=input.value;
        applyButton.disabled=approvalPhrase!=="APPLY";
      };
      confirmField.append(input);
      toolbar.append(confirmField);
      buttons.append(applyButton);
    }
    buttons.append(button(localize("discard"),discard));
    toolbar.append(buttons);
    main.prepend(toolbar);
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
  function menuActions(item) {
    if (!online()) return [];
    const actions=[];
    if (labelKey(item) &&
        (item.kind !== "room" ||
         (info.options.rooms || []).some(room=>room.id===item.id)))
      actions.push({label:localize("rename"),run:()=>startLabel(item)});
    if (!mutable()) return actions;
    if (item.kind === "rooms") {
      actions.push({label:localize("new_room"), run:()=>startRoom()});
    } else if (item.kind === "room") {
      const exists=(info.options.rooms || []).some(room=>room.id===item.id);
      if (exists) {
        actions.push({label:localize("new_device"), run:()=>startDevice(item.id)});
        actions.push({label:localize("edit_room"), run:()=>startRoom(item.id)});
        actions.push({label:localize("delete_room"), run:()=>deleteRoom(item.id), destructive:true});
      }
    } else if (item.kind === "devices") {
      if ((info.options.rooms || []).some(room=>room.id===item.room))
        actions.push({label:localize("new_device"), run:()=>startDevice(item.room)});
    } else if (item.kind === "device") {
      const configured=(info.options.rooms || []).find(room=>room.id===item.room);
      if (configured?.devices?.some(device=>device.entity===item.id)) {
        actions.push({label:localize("edit_device"), run:()=>startDevice(item.room,item.id)});
        actions.push({label:localize("delete_device"), run:()=>deleteDevice(item.room,item.id), destructive:true});
      }
    }
    return actions;
  }
  async function init(t,navigate,render) {
    tr=t; openObject=navigate; repaint=render;
    await Promise.all([refresh(),loadLabels()]);
  }
  function onNavigate(){ return navigateAway(); }
  function viewMode(){ return !info?tr("read_only"):localize("administrator"); }
  window.DHClimateEditor = {
    init, canEdit:online, canChange:mutable, menuActions,
    startRoom,startDevice, renderEditor, controls, onNavigate,
    isEditing:()=>!!edit, viewMode, previewRooms, previewRoom,
    displayName, loadLabels,
  };
})();
