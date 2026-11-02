"use strict";
/* Configuration editing stays within the same Explorer object tree.
   No draft operation drives equipment; Apply changes next-start manifest. */
(() => {
  let info = null;
  let labelsState = {schema_version:1,revision:0,labels:{},room_areas:{}};
  let haAreaCache = null;
  let haAreaLoading = null;
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
  let weatherState = null;
  let haWeatherCatalog = null;
  let operationsState = null;
  // Presentation data: from live HA, never persisted as part of priorities.
  function setWeatherContext(weather, catalog, operations=null) {
    weatherState = weather || null;
    haWeatherCatalog = catalog || null;
    operationsState = operations;
  }
  function nativeReading(item) {
    if(!item) return "—";
    if(!item.available || item.state===null || item.state===undefined ||
       ["","unknown","unavailable"].includes(String(item.state)))
      return localize("weather_unavailable");
    const unit=typeof item.unit==="string" && item.unit ? " "+item.unit : "";
    return String(item.state)+unit;
  }
  function linkedObservation(entityId) {
    const catalog=haWeatherCatalog?.entities ||
      window.DHClimateEntityPicker?.getCatalog?.()?.entities || [];
    const registered=catalog.find(item=>item.entity_id===entityId);
    if(registered)return registered;
    for(const room of operationsState?.rooms||[]){
      for(const kind of ["temperature","humidity","window"]){
        const sensor=(room.sensors?.[kind]||[]).find(e=>e.entity_id===entityId);
        if(sensor)return sensor;
      }
      for(const dev of room.devices||[])
        if(dev.entity_id===entityId)return dev.observed;
    }
    for(const kind of ["separators","groups","circuits","pumps","actuators","valves","aggregators"])
      for(const part of operationsState?.home?.hydraulics?.[kind]||[])
        for(const signal of part.signals||[])
          if(signal.entity_id===entityId)return signal;
    for(const resource of operationsState?.home?.resources||[]){
      for(const signal of resource.signals||[])
        if(signal.entity_id===entityId)return signal;
      for(const part of [...(resource.pumps||[]),...(resource.circuits||[])])
        for(const signal of part.signals||[])
          if(signal.entity_id===entityId)return signal;
    }
    const physical=(weatherState?.physical_sensors||[])
      .find(item=>item.entity_id===entityId);
    return physical?.observed || null;
  }
  function configuredReading(entityId) {
    return nativeReading(linkedObservation(entityId));
  }
  function weatherReading(id,quantity) {
    const provider=weatherState?.providers?.find(p=>p.id===id);
    const physical=weatherState?.physical_sensors?.find(p=>p.entity_id===id);
    const value=provider ? provider[quantity] : physical?.value;
    if(value===null || value===undefined || !Number.isFinite(Number(value)))
      return physical ? configuredReading(id) : localize("weather_unavailable");
    const locale=document.getElementById("language")?.value==="en"?"en":"ru";
    return new Intl.NumberFormat(locale,{
      minimumFractionDigits:1,maximumFractionDigits:1,
    }).format(Number(value))+(quantity==="temperature"?" °C":" %");
  }
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
    if (item.kind==="provider") return "provider:" + item.id;
    if (item.kind==="weather_sensor") return "weather_sensor:" + item.id;
    if (item.kind==="outdoor_sensor") return "outdoor_sensor:" + item.id;
    if (item.kind==="sensor" || item.kind==="device") return "entity:" + item.id;
    if (item.kind==="resource") return "resource:" + item.id;
    if (item.kind==="part")
      return "part:" + item.resource + ":" + item.partType + ":" + item.id;
    return null;
  };
  const roomAreaId = id => labelsState.room_areas?.[id] || null;
  const roomAreaLabel = id => {
    const linked=roomAreaId(id);
    if (!linked) return null;
    return haAreaCache?.areas?.find(area=>area.id===linked)?.name || linked;
  };
  async function loadHAAreas() {
    if (haAreaCache && Date.now() - haAreaCache.at < 30000)
      return haAreaCache.areas;
    if (haAreaLoading) return haAreaLoading;
    haAreaLoading=(async()=>{
      const response=await fetch("api/entities",{
        cache:"no-store",credentials:"same-origin",
      });
      if (!response.ok) throw Error("HTTP "+response.status);
      const data=await response.json();
      if (!Array.isArray(data.areas)) throw Error("Invalid HA Area catalog");
      const areas=data.areas.filter(item=>item && typeof item.id==="string")
        .map(item=>({id:item.id,name:String(item.name||item.id)}));
      haAreaCache={at:Date.now(),areas};
      return areas;
    })();
    try {return await haAreaLoading;}
    finally {haAreaLoading=null;}
  }
  function displayName(kind, id, language, fallback) {
    const names=labelsState.labels?.[kind + ":" + id] || {};
    const first=language==="en"?"en":"ru";
    const second=first==="ru"?"en":"ru";
    // A custom DH name in either language takes precedence over the HA
    // friendly_name. Empty preferred translation must not hide the other.
    return (typeof names[first]==="string" && names[first].trim()) ||
      (typeof names[second]==="string" && names[second].trim()) ||
      fallback;
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
    main.append(text("h3",localize("rename"),"editor-section-title"));
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
        labelsState=result;
        if (edit.fromWeather) {
          edit={kind:edit.returnWeatherKind || "weather_sources"};
          show(localize("weather_name_saved"));
        } else {
          discardLocal();show(localize("name_saved"));
        }
      } catch(e) {
        show(e.message,true);
        await loadLabels();
      }
    }),button(localize("cancel"),()=>{
      if(edit.fromWeather){edit={kind:edit.returnWeatherKind || "weather_sources"};repaint();}
      else{discardLocal();repaint();}
    }));
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
  async function refreshAfterReconnect() {
    // SSE reconnects after HAOS App restart, but the editor's /api/config
    // state is not included in snapshots. Without refreshing, a previously
    // applied manifest leaves pending_restart=true and hides edit menus.
    // Never overwrite an unfinished local form while an admin is editing.
    if (edit) return;
    await refresh();
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
      message = "";
      failure = false;
      await refresh();
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
  function enterWeatherSection(kind) {
    // Explicit admin action only, never implicit tree navigation.
    // Both weather editors share the same canonical draft.
    if (!["weather_sources","outdoor_physical","weather_priorities"].includes(kind) ||
        !mutable() || edit) return false;
    candidate = clone(info.options);
    edit = {kind};
    message = "";
    repaint();
    return true;
  }
  function startWeather() {
    if (!mutable() || !navigateAway()) return;
    openObject({kind:"weather_sources"});
    // Compatibility with standalone editor usage/tests which have no tree.
    if (!edit) enterWeatherSection("weather_sources");
  }
  function modelConfigured() {
    return Array.isArray(candidate?.providers) &&
      Array.isArray(candidate?.physical_sensors) &&
      !!candidate?.priorities;
  }
  function uniqueSourceId(entity, prefix, used) {
    let base=prefix+String(entity).split(".",2)[1]
      .toLowerCase().replace(/[^a-z0-9_]/g,"_").slice(0,45);
    if(!/^[a-z]/.test(base))base="source_"+base;
    let next=base,idx=2;
    while(used.has(next)){next=base+"_"+idx++;if(idx>1000)throw Error("Too many duplicate IDs");}
    used.add(next);
    return next;
  }
  function convertWeatherModel() {
    if (modelConfigured())return;
    const old=candidate.outdoor||{};
    const providers=[],physical_sensors=[];
    const priorities={temperature:[],humidity:[]};
    const used=new Set(), byProvider=new Map(), byPhysical=new Map();
    for(const quantity of ["temperature","humidity"]){
      for(const entityId of (old[quantity+"_sources"]||[])){
        if(!["sensor","weather"].includes(String(entityId).split(".",1)[0]))continue;
        let key;
        if(entityId.startsWith("weather.")){
          if(!byProvider.has(entityId)){
            const id=uniqueSourceId(entityId,"p_",used);
            byProvider.set(entityId,id);
            providers.push({id,entity_id:entityId});
          }
          key=byProvider.get(entityId)+"."+quantity;
        }else{
          const ref=quantity+":"+entityId;
          if(!byPhysical.has(ref)){
            const id=uniqueSourceId(entityId,quantity==="temperature"?"t_":"h_",used);
            byPhysical.set(ref,id);
            physical_sensors.push({id,entity_id:entityId,quantity});
          }
          key=byPhysical.get(ref);
        }
        if(!priorities[quantity].includes(key))priorities[quantity].push(key);
      }
    }
    candidate.providers=providers;
    candidate.physical_sensors=physical_sensors;
    candidate.priorities=priorities;
    // Avoid shadowed legacy references in the canonical new manifest.
    candidate.outdoor={temperature_sources:[],humidity_sources:[]};
    validated=false;
    repaint();
  }
  function allSourceIds() {
    return new Set([
      ...(candidate.providers||[]).map(p=>p.id),
      ...(candidate.physical_sensors||[]).map(p=>p.id),
    ]);
  }
  function providerTitle(provider) {
    const fallback=provider.entity_id;
    const lang=document.getElementById("language")?.value==="en"?"en":"ru";
    return displayName("provider",provider.id,lang,fallback);
  }
  function weatherSensorTitle(id,quantity) {
    const lang=document.getElementById("language")?.value==="en"?"en":"ru";
    const physical=(candidate.physical_sensors||[]).find(s=>s.id===id);
    if(physical){
      return displayName("outdoor_sensor",id,lang,physical.entity_id);
    }
    const pid=String(id).split(".")[0];
    const provider=(candidate.providers||[]).find(p=>p.id===pid);
    const fallback=(quantity==="temperature"?tr("temperature"):tr("humidity"))+
      " · "+(provider?providerTitle(provider):id);
    return displayName("weather_sensor",id,lang,fallback);
  }
  function pickerSources(parent,kind,title_,items,onConfirm){
    const panel=text("section","","editor-entity-field");
    panel.append(text("h3",title_,"section-heading"));
    const list=text("div","","editor-bound-list");
    if(!items.length)list.append(text("p",localize("none"),"subtle small"));
    for(const item of items){
      const line=text("div","","editor-bound-entity");
      line.append(text("span",item.name,"mono"));
      line.append(text("span",item.reading || configuredReading(item.entity),
        "editor-bound-value"));
      const remove=button("×",()=>{
        onConfirm(items.filter(x=>x.entity!==item.entity).map(x=>x.entity));
      });
      remove.title=localize("remove_entity")+" "+item.entity;
      line.append(remove);list.append(line);
    }
    const choose=button(localize("weather_choose_sources"),()=>{
      window.DHClimateEntityPicker.open({
        kind,multiple:true,values:items.map(x=>x.entity),title:title_,tr,
        usage:usages(),
        onConfirm:next=>onConfirm(next),
      });
    });
    panel.append(list,choose);parent.append(panel);
  }
  function editWeatherName(kind,id,sourceName) {
    if(!online() || !candidate ||
      !["weather","weather_sources"].includes(edit?.kind))return;
    const key=kind+":"+id;
    const original=labelsState.labels?.[key] || {};
    // Return to the same unsaved weather form after saving the label.
    // Labels are independent UI metadata and never change source IDs.
    const liveProvider=(weatherState?.providers||[]).find(p=>
      p.id===id || p.entity_id===sourceName);
    const haEntity=(haWeatherCatalog?.entities||[]).find(item=>
      kind==="provider" ? item.entity_id===sourceName :
        item.climate_source_id===id);
    edit={kind:"label",key,technicalId:id,sourceName,
      haName:haEntity?.name || (kind==="provider"?liveProvider?.friendly_name:null) || null,
      fromWeather:true,returnWeatherKind:edit.kind,
      names:{ru:original.ru||"",en:original.en||""}};
    message="";
    repaint();
  }

  function weatherProviderEditor(parent) {
    const listed=(candidate.providers||[]).map(provider=>({
      entity:provider.entity_id,name:providerTitle(provider)+" ["+provider.entity_id+"]",
      reading:weatherReading(provider.id,"temperature")+" · "+
        weatherReading(provider.id,"humidity"),
    }));
    pickerSources(parent,"provider",localize("weather_providers"),listed,next=>{
      const current=candidate.providers||[];
      const known=new Map(current.map(p=>[p.entity_id,p]));
      const used=allSourceIds();
      candidate.providers=next.map(entityId=>known.get(entityId)||{
        id:uniqueSourceId(entityId,"p_",used),entity_id:entityId,
      });
      const available=new Set(candidate.providers.map(p=>p.id));
      for(const quantity of ["temperature","humidity"]){
        candidate.priorities[quantity]=candidate.priorities[quantity].filter(key=>
          !key.includes(".")||available.has(key.split(".")[0])
        );
      }
      validated=false;repaint();
    });
    if(!(candidate.providers||[]).length)return;
    const details=text("section","","editor-entity-field");
    details.append(
      text("h3",localize("weather_names"),"section-heading"),
      text("p",localize("weather_names_help"),"subtle small"),
    );
    for(const provider of candidate.providers){
      const providerLine=text("div","","editor-bound-entity");
      providerLine.append(
        text("span",providerTitle(provider)+" · "+provider.entity_id,"mono"),
        text("span",weatherReading(provider.id,"temperature")+" · "+
          weatherReading(provider.id,"humidity"),"editor-bound-value"),
        button(localize("rename"),
          ()=>editWeatherName("provider",provider.id,provider.entity_id)),
      );
      details.append(providerLine);
      for(const quantity of ["temperature","humidity"]){
        const logicalId=provider.id+"."+quantity;
        const expectedEntityId="sensor.dh_climate_app_weather_"+
          provider.id+"_"+quantity;
        const sensorLine=text("div","","editor-bound-entity");
        sensorLine.append(
          text("span",weatherSensorTitle(logicalId,quantity)+
            " · "+expectedEntityId,"mono"),
          text("span",weatherReading(provider.id,quantity),"editor-bound-value"),
          button(localize("rename"),
            ()=>editWeatherName("weather_sensor",logicalId,provider.entity_id)),
        );
        details.append(sensorLine);
      }
    }
    parent.append(details);
  }
  function weatherPhysicalEditor(parent,quantity) {
    const sources=(candidate.physical_sensors||[]).filter(s=>s.quantity===quantity);
    if(quantity==="temperature")
      parent.append(text("p",localize("weather_sensor_hint"),"subtle small"));
    const listed=sources.map(s=>({
      entity:s.entity_id,name:weatherSensorTitle(s.id,quantity)+" ["+s.entity_id+"]",
      reading:weatherReading(s.entity_id,quantity),
    }));
    pickerSources(parent,"physical-"+quantity,localize("weather_physical")+" · "+
      (quantity==="temperature"?tr("temperature"):tr("humidity")),listed,next=>{
      const known=new Map(sources.map(s=>[s.entity_id,s]));
      const used=allSourceIds();
      const accepted=next.map(entityId=>known.get(entityId)||{
        id:uniqueSourceId(entityId,quantity==="temperature"?"t_":"h_",used),
        entity_id:entityId,quantity,
      });
      const ids=new Set(accepted.map(s=>s.id));
      const removed=new Set(sources.filter(s=>!ids.has(s.id)).map(s=>s.id));
      candidate.physical_sensors=[
        ...(candidate.physical_sensors||[]).filter(s=>s.quantity!==quantity),
        ...accepted,
      ];
      candidate.priorities[quantity]=candidate.priorities[quantity]
        .filter(key=>!removed.has(key));
      validated=false;repaint();
    });
  }
  function priorityCandidates(quantity) {
    return [
      ...(candidate.providers||[]).map(p=>({
        id:p.id+"."+quantity,label:weatherSensorTitle(p.id+"."+quantity,quantity),
      })),
      ...(candidate.physical_sensors||[])
        .filter(s=>s.quantity===quantity)
        .map(s=>({id:s.id,label:weatherSensorTitle(s.id,quantity)})),
    ];
  }
  function priorityMetadata(id,quantity) {
    const physical=(candidate.physical_sensors || []).find(p=>p.id===id);
    const realId=physical?.entity_id;
    const live=(weatherState?.[quantity+"_sources"] || [])
      .find(s=>s.entity_id===id);
    // HA entity catalogue uniquely matches derived MQTT sensors by their
    // unchanged MQTT unique_id, even when user renames entity_id in HA.
    const ha=(haWeatherCatalog?.entities || []).find(item=>
      item.climate_source_id===id ||
      (realId && item.entity_id===realId));
    const fallbackId=realId || "sensor.dh_climate_app_weather_"+
      id.replace(".", "_");
    const name=ha?.name || weatherSensorTitle(id,quantity);
    const value=live ? live.state : ha?.state;
    const invalid=(value===null || value===undefined ||
      value==="" || value==="unknown" || value==="unavailable" ||
      !Number.isFinite(Number(value)));
    const unit=quantity==="temperature"?"°C":"%";
    const numeric=invalid?localize("weather_unavailable"):
      new Intl.NumberFormat(document.getElementById("language")?.value==="en"?"en":"ru",{
        minimumFractionDigits:1,maximumFractionDigits:1,
      }).format(Number(value))+" "+unit;
    return {
      label:name,entityId:ha?.entity_id || fallbackId,
      numeric,invalid,
      active:weatherState?.[quantity==="temperature"?"source":"humidity_source"]===id,
    };
  }
  function priorityField(parent,quantity) {
    const panel=text("section","","editor-entity-field");
    panel.append(text("h3",
      quantity==="temperature"?localize("weather_temperature_sources"):
        localize("weather_humidity_sources"),"section-heading"),
      text("p",localize("weather_drag_help"),"subtle small"));
    const refs=candidate.priorities[quantity];
    const list=text("div","","editor-bound-list editor-priority-list");
    let draggingIndex=-1;
    function move(from,to){
      if(from<0 || to<0 || from>=refs.length || to>=refs.length || from===to)return;
      const [id]=refs.splice(from,1);
      refs.splice(to,0,id);
      validated=false;repaint();
    }
    if(!refs.length)list.append(text("p",localize("none"),"subtle small"));
    refs.forEach((id,index)=>{
      const detail=priorityMetadata(id,quantity);
      const line=text("div","","editor-bound-entity editor-priority-row");
      line.draggable=refs.length>1;
      line.setAttribute("data-source-id",id);
      const grip=text("span","⠿","editor-drag-handle");
      grip.title=localize("weather_drag_handle");
      grip.setAttribute("aria-hidden","true");
      const rank=text("strong",String(index+1)+".","editor-priority-rank");
      const info=text("div","","editor-priority-info");
      const nameRow=text("div","","editor-priority-title-line");
      nameRow.append(text("span",detail.label,"editor-priority-name"));
      if(detail.active)
        nameRow.append(text("span",tr("weather_active"),"weather-active-indicator"));
      info.append(nameRow,text("span",detail.entityId,"editor-priority-entity mono"));
      const value=text("span",detail.numeric,
        "editor-priority-value"+(detail.invalid?" unavailable":""));
      const actions=text("span","","editor-source-actions");
      const up=button("↑",()=>move(index,index-1));
      up.disabled=index===0;
      up.title=localize("weather_move_up");
      up.setAttribute("aria-label",up.title+" "+detail.label);
      const down=button("↓",()=>move(index,index+1));
      down.disabled=index===refs.length-1;
      down.title=localize("weather_move_down");
      down.setAttribute("aria-label",down.title+" "+detail.label);
      const remove=button("×",()=>{
        refs.splice(index,1);validated=false;repaint();
      });
      remove.title=localize("weather_remove_priority");
      remove.setAttribute("aria-label",remove.title+" "+detail.label);
      actions.append(up,down,remove);
      line.append(grip,rank,info,value,actions);
      line.ondragstart=event=>{
        draggingIndex=index;
        event.dataTransfer.effectAllowed="move";
        event.dataTransfer.setData("text/plain",id);
      };
      line.ondragover=event=>{
        if(draggingIndex<0)return;
        event.preventDefault();
        event.dataTransfer.dropEffect="move";
      };
      line.ondrop=event=>{
        if(draggingIndex<0)return;
        event.preventDefault();
        const from=draggingIndex;
        draggingIndex=-1;
        move(from,index);
      };
      line.ondragend=()=>{draggingIndex=-1;};
      list.append(line);
    });
    panel.append(list);
    const options=priorityCandidates(quantity)
      .filter(entry=>!refs.includes(entry.id));
    if(options.length){
      const addition=text("div","","editor-priority-add");
      const select=document.createElement("select");
      select.className="editor-ha-area-select";
      for(const entry of options){
        const detail=priorityMetadata(entry.id,quantity);
        const opt=document.createElement("option");
        opt.value=entry.id;
        opt.textContent=detail.label+" · "+detail.numeric+" ["+detail.entityId+"]";
        select.append(opt);
      }
      const add=button(localize("weather_add_priority"),()=>{
        if(select.value && !refs.includes(select.value)){
          refs.push(select.value);validated=false;repaint();
        }
      });
      addition.append(select,add);
      panel.append(addition);
    }
    parent.append(panel);
  }
  function weatherForm(main) {
    main.append(text("h3",localize("weather_editor_title"),"editor-section-title"));
    const box=text("section","","card");
    if(!modelConfigured()){
      box.append(text("p",localize("weather_legacy_notice"),"warn"),
        text("p",JSON.stringify(candidate.outdoor||{}),"mono small"));
      const control=text("div","","editor-actions");
      control.append(button(localize("weather_convert"),convertWeatherModel),
        button(localize("cancel"),()=>{discardLocal();repaint();}));
      box.append(control);main.append(box);
      return;
    }
    box.append(text("p",localize("weather_providers_note"),"subtle"));
    weatherProviderEditor(box);
    const controls=text("div","","editor-actions");
    controls.append(button(localize("save_draft"),persist),
      button(localize("cancel"),()=>{discardLocal();repaint();}));
    box.append(controls);main.append(box);
  }
  function hardwareWeatherForm(main) {
    main.append(text("h3",localize("weather_hardware_title"),"editor-section-title"));
    const box=text("section","","card");
    if (!modelConfigured()) {
      box.append(text("p",localize("weather_legacy_notice"),"warn"),
        text("p",JSON.stringify(candidate.outdoor||{}),"mono small"));
      const actions=text("div","","editor-actions");
      actions.append(button(localize("weather_convert"),convertWeatherModel),
        button(localize("cancel"),()=>{discardLocal();repaint();}));
      box.append(actions);main.append(box);return;
    }
    box.append(text("p",localize("weather_hardware_note"),"subtle"));
    weatherPhysicalEditor(box,"temperature");
    weatherPhysicalEditor(box,"humidity");
    const actions=text("div","","editor-actions");
    actions.append(button(localize("save_draft"),persist),
      button(localize("cancel"),()=>{discardLocal();repaint();}));
    box.append(actions);main.append(box);
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
    const language=document.getElementById("language")?.value==="en"?"en":"ru";
    for(const room of (candidate?.rooms || info?.options?.rooms || [])){
      const roomTitle=displayName("room",room.id,language,room.name || room.id);
      for(const key of ["temperature_sensors","humidity_sensors","window_sensors"]) {
        for(const id of room[key] || []) (result[id] ||= []).push(roomTitle);
      }
      for(const device of room.devices || []) {
        if(device.entity)(result[device.entity] ||= []).push(roomTitle);
      }
    }
    return result;
  }
  function entityField(parent,label,value,kind,onChange,
                       {multiple=false,roomName="",roomId=""}={}){
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
      line.append(name,
        text("span",configuredReading(id),"editor-bound-value"),
        remove);list.append(line);
    }
    const choose=button(ids.length?localize("change_binding"):localize("add_binding"),
      ()=>window.DHClimateEntityPicker.open({
        kind,multiple,values:ids,title:label,
        areaId:roomId ? roomAreaId(roomId) : null,
        areaHint:roomName,
        areaHints:[roomName, ...((candidate?.rooms || []).filter(room=>room.name===roomName)
          .map(room=>displayName("room",room.id,
            document.getElementById("language")?.value==="en"?"en":"ru",roomName)))],
        usage:usages(),tr,
        onConfirm:next=>{
          onChange(next);
          validated=false;
          repaint();
        },
      }));
    section.append(list,choose);parent.append(section);
  }
  function roomAreaField(parent,room) {
    const wrap=text("section","","editor-entity-field");
    wrap.append(text("p",localize("ha_area"),"editor-entity-title"));
    const selection=document.createElement("select");
    selection.setAttribute("aria-label",localize("ha_area"));
    selection.className="editor-ha-area-select";
    const option=(value,label)=>{
      const el=document.createElement("option");
      el.value=value;el.textContent=label;selection.append(el);
    };
    option("",localize("no_ha_area"));
    const assigned=roomAreaId(room.id);
    if (assigned) option(assigned,assigned);
    selection.value=assigned || "";
    const feedback=text("p",localize("area_hint"),"subtle small");
    const save=button(localize("save_area"),async()=>{
      const area_id=selection.value || null;
      if (area_id && !haAreaCache?.areas?.some(area=>area.id===area_id)) {
        feedback.textContent=localize("area_missing");
        feedback.className="editor-notice bad";
        return;
      }
      save.disabled=true;
      try {
        const response=await fetch("api/room-area",{
          method:"POST",credentials:"same-origin",
          headers:{"Content-Type":"application/json","X-Requested-With":"DHClimateExplorer"},
          body:JSON.stringify({room_id:room.id,area_id,revision:labelsState.revision}),
        });
        const result=await response.json();
        if(!response.ok)throw Error(result.error||"HTTP "+response.status);
        labelsState=result;
        feedback.textContent=localize("area_saved");
        feedback.className="editor-notice good";
      }catch(e){
        feedback.textContent=e.message;
        feedback.className="editor-notice bad";
        // On conflicting revisions, refresh state without repainting the
        // configuration form (which might contain unsaved sensor changes).
        try {
          const response=await fetch("api/labels",{cache:"no-store",credentials:"same-origin"});
          if(response.ok)labelsState=await response.json();
        }catch(_){}
      }finally{save.disabled=false;}
    });
    const exists=(info?.options?.rooms || []).some(item=>item.id===room.id);
    if (!exists || !room.id) {
      selection.disabled=true;
      save.disabled=true;
      feedback.textContent=localize("area_requires_saved_room");
    }
    wrap.append(selection,save,feedback);parent.append(wrap);
    if (!exists) return;
    loadHAAreas().then(areas=>{
      if(!wrap.isConnected)return;
      const old=selection.value;
      selection.replaceChildren();
      option("",localize("no_ha_area"));
      for(const area of areas)option(area.id,area.name);
      if (old && !areas.some(area=>area.id===old)) {
        option(old,localize("area_unavailable")+" ("+old+")");
        feedback.textContent=localize("area_missing");
        feedback.className="editor-notice bad";
      }
      selection.value=old;
    }).catch(_=>{
      if(wrap.isConnected) {
        feedback.textContent=localize("area_catalog_error");
        feedback.className="editor-notice bad";
      }
    });
  }
  function optional(obj,key,value) {
    const v=value.trim();
    if (v) obj[key]=v; else delete obj[key];
  }
  function roomForm(main) {
    const room=rooms()[edit.index];
    if (!room) return;
    main.append(text("h3", edit.id?localize("edit_room"):localize("new_room"),"editor-section-title"));
    const box=text("section","","card");
    field(box,localize("room_id"),room.id,v=>room.id=v.trim().toLowerCase(),false,!!edit.id);
    field(box,localize("room_name"),room.name,v=>room.name=v);
    roomAreaField(box,room);
    for (const [key,label,kind] of [
      ["temperature_sensors","temperature_sensors","temperature"],
      ["humidity_sensors","humidity_sensors","humidity"],
      ["window_sensors","window_sensors","window"]]) {
      entityField(box,localize(label),room[key]||[],kind,
        value=>{room[key]=value;},
        {multiple:true,roomName:room.name,roomId:room.id});
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
    main.append(text("h3",localize("edit_device"),"editor-section-title"));
    const box=text("section","","card");
    entityField(box,localize("entity"),device.entity,
      device.device_type==="hardware"?"actuator-hardware":"actuator-virtual",
      value=>{device.entity=value||"";},{roomName:room.name,roomId:room.id});
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
      },{roomName:room.name,roomId:room.id});
    selectField(box,localize("screed_missing"),device.screed_sensor_unavailable||"",
      [["",localize("none")],["open","OPEN"],["closed","CLOSED"]],
      v=>{if(v)device.screed_sensor_unavailable=v;else delete device.screed_sensor_unavailable;});
    const controls=text("div","","editor-actions");
    controls.append(button(localize("save_draft"),persist),
      button(localize("cancel"),()=>{discardLocal();repaint();}));
    box.append(controls);
    main.append(box);
  }
  function weatherPriorityForm(main) {
    main.append(text("h3",localize("weather_priorities_page"),"editor-section-title"),
      text("p",localize("weather_priority_help"),"subtle small"));
    const box=text("section","","card");
    if (!modelConfigured()){
      box.append(text("p",localize("weather_legacy_notice"),"subtle"),
        button(localize("weather_convert"),convertWeatherModel));
    } else {
      priorityField(box,"temperature");
      priorityField(box,"humidity");
      const actions=text("div","","editor-actions");
      actions.append(button(localize("save_draft"),persist),
        button(localize("cancel"),()=>{discardLocal();repaint();}));
      box.append(actions);
    }
    main.append(box);
  }

  // Canonical hydraulic graph: configuration objects have exactly one owner;
  // references from groups/contours point to those objects. Editing here
  // changes only the validated manifest draft, never live equipment.
  const hydraulicKinds=["separators","groups","circuits","pumps",
    "actuators","valves","aggregators"];
  const hydraulicTitle=kind => tr("hydraulic_"+kind);
  const hydroConfig=()=>candidate?.hydraulics||{};
  const hydroList=kind=>hydroConfig()[kind]||[];
  const hydroLookup=(kind,id)=>hydroList(kind).find(item=>item.id===id);
  const slugPattern=/^[a-z0-9][a-z0-9_]*$/;
  const hydraulicRoles=[
    "supply_temperature","return_temperature","temperature",
    "supply_pressure","return_pressure","pressure",
    "state","status","powered","power","rpm","position","flow",
    "heat_request","pump_request","dhw","leak","fault",
  ];
  function hydraulicSignalKind(role) {
    if(role.includes("temperature"))return "hydraulic-temperature";
    if(role.includes("pressure"))return "hydraulic-pressure";
    if(role==="rpm")return "hydraulic-rpm";
    if(role==="power")return "hydraulic-power";
    return "hydraulic-signal";
  }
  function beginHydraulic(type,id=null,preset={}) {
    if(!mutable() || !navigateAway() || !hydraulicKinds.includes(type))return false;
    candidate=clone(info.options);
    if(!candidate.hydraulics)candidate.hydraulics={};
    if(!Array.isArray(candidate.hydraulics[type]))candidate.hydraulics[type]=[];
    const list=candidate.hydraulics[type];
    let index=id ? list.findIndex(part=>part.id===id) : list.length;
    if(index<0){discardLocal();return false;}
    if(!id) {
      const next={id:"",name:"",signals:{},...preset};
      if(type==="groups"&&!next.temperature_class)next.temperature_class="high";
      if(type==="aggregators"&&!next.device_type)next.device_type="hardware";
      list.push(next);
    }
    edit={kind:"hydraulic",type,index,id,isNew:!id};
    message="";repaint();return true;
  }
  function beginHydraulicCreator(type="separators"){
    if(!mutable() || !navigateAway())return false;
    candidate=clone(info.options);
    edit={kind:"hydraulic_create",type};
    message="";repaint();return true;
  }
  function createFromHydraulicCreator(type) {
    if(!edit || edit.kind!=="hydraulic_create")return;
    if(!candidate.hydraulics)candidate.hydraulics={};
    if(!Array.isArray(candidate.hydraulics[type]))candidate.hydraulics[type]=[];
    const list=candidate.hydraulics[type];
    const item={id:"",name:"",signals:{}};
    if(type==="groups")item.temperature_class="high";
    if(type==="aggregators")item.device_type="hardware";
    list.push(item);
    edit={kind:"hydraulic",type,index:list.length-1,id:null,isNew:true};
    message="";repaint();
  }
  function dependencyNames(type,id,hydraulics) {
    const uses=[];
    for(const [kind,field,target] of [
      ["groups","separator_id","separators"],
      ["groups","aggregator_id","aggregators"],
      ["circuits","group_id","groups"],
      ["groups","pump_ids","pumps"],["circuits","pump_ids","pumps"],
      ["groups","actuator_ids","actuators"],["circuits","actuator_ids","actuators"],
      ["groups","valve_ids","valves"],["circuits","valve_ids","valves"],
    ]) {
      if(target!==type)continue;
      for(const part of hydraulics?.[kind]||[]) {
        const ref=part[field];
        if(Array.isArray(ref)?ref.includes(id):ref===id)
          uses.push(kind+"/"+part.id);
      }
    }
    return uses;
  }
  function deleteHydraulic(type,id) {
    if(!mutable() || !navigateAway() || !hydraulicKinds.includes(type))return;
    const dependencies=dependencyNames(type,id,info.options.hydraulics);
    if(dependencies.length) {
      show(localize("hydraulic_delete_blocked")+": "+dependencies.join(", "),true);
      return;
    }
    confirmAction("hydraulic_delete_confirm",async()=>{
      candidate=clone(info.options);
      if(!candidate.hydraulics || !Array.isArray(candidate.hydraulics[type]))return;
      candidate.hydraulics[type]=candidate.hydraulics[type].filter(item=>item.id!==id);
      await persist();
    });
  }
  function simpleSelect(parent,label,value,options,onChange) {
    const choices=[["",localize("none")],
      ...options.map(x=>[x.id,x.name||x.id])];
    selectField(parent,label,value||"",choices,
      v=>onChange(v||null));
  }
  function linkField(parent,label,part,key,type) {
    const section=text("section","","editor-entity-field");
    section.append(text("p",label,"editor-entity-title"));
    const selected=new Set(part[key]||[]);
    const choices=hydroList(type);
    if(!choices.length)section.append(text("p",localize("hydraulic_no_equipment"),"subtle small"));
    for(const target of choices) {
      const line=text("label","","editor-hydraulic-link");
      const input=document.createElement("input");
      input.type="checkbox";input.checked=selected.has(target.id);
      input.onchange=()=>{
        if(input.checked)selected.add(target.id);else selected.delete(target.id);
        const ids=choices.filter(item=>selected.has(item.id)).map(item=>item.id);
        if(ids.length)part[key]=ids;else delete part[key];
        validated=false;
      };
      line.append(input,text("span",target.name+" · "+target.id));section.append(line);
    }
    parent.append(section);
  }
  function hydroSignalAdd(parent,part) {
    const section=text("section","","card");
    section.append(text("h3",localize("hydraulic_signals"),"section-heading"),
      text("p",localize("hydraulic_signals_help"),"subtle small"));
    const signals=part.signals||{};
    part.signals=signals;
    for(const [role,id] of Object.entries(signals)){
      entityField(section,tr(role)===role?role:tr(role),id,
        hydraulicSignalKind(role),next=>{
          if(next)signals[role]=next;else delete signals[role];
        });
    }
    const roleRow=text("div","","editor-actions");
    const roleInput=document.createElement("input");
    roleInput.type="text";roleInput.className="editor-hydraulic-role";
    roleInput.placeholder=localize("hydraulic_signal_role");
    roleInput.setAttribute("list","hydraulic-role-suggestions");
    const suggestions=document.createElement("datalist");
    suggestions.id="hydraulic-role-suggestions";
    for(const role of hydraulicRoles) {
      const opt=document.createElement("option");opt.value=role;
      suggestions.append(opt);
    }
    roleRow.append(roleInput,suggestions,
      button(localize("hydraulic_add_signal"),()=>{
        const role=roleInput.value.trim().toLowerCase();
        if(!slugPattern.test(role)) {
          show(localize("hydraulic_invalid_id"),true);return;
        }
        if(Object.prototype.hasOwnProperty.call(signals,role)) {
          show(localize("hydraulic_duplicate_signal"),true);return;
        }
        window.DHClimateEntityPicker.open({
          kind:hydraulicSignalKind(role),title:role,
          multiple:false,values:[],usage:usages(),tr,
          onConfirm:entity=>{
            if(!entity)return;
            signals[role]=entity;validated=false;repaint();
          },
        });
      }));
    section.append(roleRow);parent.append(section);
  }
  function hydraulicTerminalFields(parent,part) {
    const section=text("section","","card");
    section.append(text("h3",localize("hydraulic_terminals"),"section-heading"));
    const terminals=part.terminals||[];
    part.terminals=terminals;
    for(const [i,terminal] of terminals.entries()) {
      const panel=text("div","","editor-hydraulic-terminal");
      field(panel,localize("hydraulic_id"),terminal.id,v=>terminal.id=v.trim().toLowerCase());
      field(panel,localize("hydraulic_name"),terminal.name,v=>terminal.name=v);
      simpleSelect(panel,localize("hydraulic_room"),terminal.room_id,
        candidate.rooms||[],v=>{if(v)terminal.room_id=v;else delete terminal.room_id;});
      entityField(panel,localize("hydraulic_terminal_entity"),terminal.entity_id,
        "hydraulic-signal",v=>{
          if(v)terminal.entity_id=v;else delete terminal.entity_id;
        },{roomId:terminal.room_id||part.room_id||""});
      panel.append(button(localize("hydraulic_remove_terminal"),()=>{
        terminals.splice(i,1);validated=false;repaint();
      }));
      section.append(panel);
    }
    section.append(button(localize("hydraulic_add_terminal"),()=>{
      terminals.push({id:"",name:""});validated=false;repaint();
    }));
    parent.append(section);
  }
  function hydraulicForm(main) {
    const type=edit.type;
    const part=hydroList(type)[edit.index];
    if(!part)return;
    main.append(text("h3",hydraulicTitle(type),"editor-section-title"),
      text("p",localize("hydraulic_not_live"),"subtle small"));
    const section=text("section","","card");
    field(section,localize("hydraulic_id"),part.id,
      v=>part.id=v.trim().toLowerCase(),false,!edit.isNew);
    field(section,localize("hydraulic_name"),part.name,v=>part.name=v);
    if(type==="aggregators")selectField(section,localize("hydraulic_controller_type"),
      part.device_type||"hardware",[
        ["hardware",tr("hardware")],["virtual",tr("virtual")],
      ],v=>part.device_type=v);
    if(type==="groups"){
      selectField(section,localize("hydraulic_temperature_class"),
        part.temperature_class||"high",[
          ["high",tr("high")],["low",tr("low")],
        ],v=>part.temperature_class=v);
      simpleSelect(section,localize("hydraulic_parent_separator"),
        part.separator_id,hydroList("separators"),
        v=>{if(v)part.separator_id=v;else delete part.separator_id;});
      simpleSelect(section,localize("hydraulic_parent_aggregator"),
        part.aggregator_id,hydroList("aggregators"),
        v=>{if(v)part.aggregator_id=v;else delete part.aggregator_id;});
    }
    if(type==="circuits"){
      simpleSelect(section,localize("hydraulic_parent_group"),
        part.group_id,hydroList("groups"),
        v=>{if(v)part.group_id=v;else delete part.group_id;});
      simpleSelect(section,localize("hydraulic_room"),
        part.room_id,candidate.rooms||[],
        v=>{if(v)part.room_id=v;else delete part.room_id;});
    }
    if(["groups","circuits"].includes(type))
      for(const [key,target] of [["pump_ids","pumps"],
        ["actuator_ids","actuators"],["valve_ids","valves"]])
        linkField(section,localize("hydraulic_link_"+target),part,key,target);
    main.append(section);
    hydroSignalAdd(main,part);
    if(type==="circuits")hydraulicTerminalFields(main,part);
    const actions=text("div","","editor-actions");
    actions.append(button(localize("save_draft"),persist),
      button(localize("cancel"),()=>{discardLocal();repaint();}));
    main.append(actions);
  }
  function hydraulicCreatorForm(main) {
    main.append(text("h3",localize("hydraulic_new_object"),"editor-section-title"));
    const box=text("section","","card");
    selectField(box,localize("hydraulic_object_type"),edit.type,
      hydraulicKinds.map(x=>[x,hydraulicTitle(x)]),
      v=>edit.type=v);
    const actions=text("div","","editor-actions");
    actions.append(button(localize("hydraulic_continue"),
        ()=>createFromHydraulicCreator(edit.type)),
      button(localize("cancel"),()=>{discardLocal();repaint();}));
    box.append(actions);main.append(box);
  }
  function hydraulicPageAction(item) {
    if(item.kind==="hydraulics")
      return {label:localize("hydraulic_new_object"),run:()=>beginHydraulicCreator()};
    if(item.kind==="hydraulic_collection"){
      if(["aggregators","separators"].includes(item.id))
        return {label:localize("hydraulic_add_"+item.id),
          run:()=>beginHydraulic(item.id)};
      if(item.id==="direct_groups")
        return {label:localize("hydraulic_add_groups"),
          run:()=>beginHydraulic("groups")};
      if(item.id==="direct_circuits")
        return {label:localize("hydraulic_add_circuits"),
          run:()=>beginHydraulic("circuits")};
      return {label:localize("hydraulic_new_object"),run:()=>beginHydraulicCreator()};
    }
    if(item.kind==="hydraulic_temperature") {
      const [separator,type]=String(item.id||"").split(":");
      return {label:localize("hydraulic_add_groups"),
        run:()=>beginHydraulic("groups",null,{
          ...(separator!=="direct"?{separator_id:separator}:{}),
          temperature_class:type==="low"?"low":"high",
        })};
    }
    if(item.kind==="hydraulic_item") {
      const [type,id]=String(item.id||"").split(":");
      if(hydraulicKinds.includes(type) &&
         (info.options.hydraulics?.[type]||[]).some(part=>part.id===id))
        return {label:localize("edit"),run:()=>beginHydraulic(type,id)};
    }
    return null;
  }
  function hydraulicMenuActions(item) {
    const actions=[];
    const action=hydraulicPageAction(item);
    if(action)actions.push(action);
    if(item.kind==="hydraulics") {
      // The creator handles all seven object types without pseudo-devices.
      return actions;
    }
    if(item.kind==="hydraulic_item") {
      const [type,id]=String(item.id||"").split(":");
      if(type==="separators")
        actions.unshift({label:localize("hydraulic_add_groups"),
          run:()=>beginHydraulic("groups",null,{separator_id:id,temperature_class:"high"})});
      if(type==="groups")
        actions.unshift({label:localize("hydraulic_add_circuits"),
          run:()=>beginHydraulic("circuits",null,{group_id:id})});
      if(type==="circuits")
        actions.unshift({label:localize("hydraulic_edit_terminals"),
          run:()=>beginHydraulic("circuits",id)});
      if((info.options.hydraulics?.[type]||[]).some(part=>part.id===id))
        actions.push({label:localize("hydraulic_delete"),
          run:()=>deleteHydraulic(type,id),destructive:true});
    }
    return actions;
  }
  function previewHydraulics(live) {
    if(!info || (!info.dirty&&!info.pending_restart) || !info.options.hydraulics)
      return live;
    const projected={};
    const connected=operationsState?.app?.ha_connected===true;
    for(const type of hydraulicKinds) {
      projected[type]=(info.options.hydraulics[type]||[]).map(part=>{
        const previous=(live?.[type]||[]).find(old=>old.id===part.id);
        const changed=!previous||previous.name!==part.name;
        const signals=Object.entries(part.signals||{}).map(([role,id])=>{
          const old=previous?.signals?.find(s=>s.role===role&&s.entity_id===id);
          const obs=old||(connected?linkedObservation(id):null);
          return {role,entity_id:id,friendly_name:obs?.friendly_name||obs?.name||null,
            state:connected?obs?.state??null:null,
            unit:connected?obs?.unit??null:null,
            available:connected&&obs?.available===true,
            last_updated:connected?obs?.last_updated||null:null,attributes:{}};
        });
        const terminals=(part.terminals||[]).map(t=>{
          const old=previous?.terminals?.find(x=>x.id===t.id&&x.entity_id===t.entity_id);
          const obs=old?.observed||(connected&&t.entity_id?linkedObservation(t.entity_id):null);
          return {...t,observed:obs||null};
        });
        return {...part,name:changed?part.name+" ["+localize("draft_marker")+"]":part.name,
          signals,terminals};
      });
    }
    return projected;
  }

  function renderEditor(main) {
    if (!edit) return false;
    main.replaceChildren();
    const heading=text("header","","editor-mode-heading");
    heading.append(text("h2",localize("editing"),"page-title"),
      text("p",localize("editing_navigation_hint"),"subtle small"));
    main.append(heading);
    if (edit.kind==="label") labelForm(main);
    if (edit.kind==="weather" || edit.kind==="weather_sources") weatherForm(main);
    if (edit.kind==="outdoor_physical") hardwareWeatherForm(main);
    if (edit.kind==="weather_priorities") weatherPriorityForm(main);
    if (edit.kind==="room") roomForm(main);
    if (edit.kind==="device") deviceForm(main);
    if (edit.kind==="hydraulic_create") hydraulicCreatorForm(main);
    if (edit.kind==="hydraulic") hydraulicForm(main);
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
      // Persistent banner above the workbench owns the restart instruction.
      // Keep the editor immutable until the new App process is observed.
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
  function pageAction(item) {
    // Right-click actions remain available, but a click on the tree only
    // browses. The ordinary page heading owns entry to edit mode.
    if (!item || edit || !info) return null;
    if (mutable()) {
      const hydraulic=hydraulicPageAction(item);
      if(hydraulic)return hydraulic;
      if (item.kind==="weather_sources" || item.kind==="outdoor_physical" ||
          item.kind==="weather_priorities")
        return {label:localize("edit"),
          run:()=>enterWeatherSection(item.kind)};
      if (item.kind==="room" &&
          (info.options.rooms||[]).some(r=>r.id===item.id))
        return {label:localize("edit"),
          run:()=>startRoom(item.id)};
      if (item.kind==="device" &&
          (info.options.rooms||[]).find(r=>r.id===item.room)
            ?.devices?.some(d=>d.entity===item.id))
        return {label:localize("edit"),
          run:()=>startDevice(item.room,item.id)};
      if (item.kind==="rooms")
        return {label:localize("new_room"),run:()=>startRoom()};
    }
    if (labelKey(item) && (item.kind!=="room" ||
      (info.options.rooms||[]).some(r=>r.id===item.id)))
      return {label:localize("rename"),run:()=>startLabel(item)};
    return null;
  }

  function menuActions(item) {
    if (!online()) return [];
    const actions=[];
    if (labelKey(item) &&
        (item.kind !== "room" ||
         (info.options.rooms || []).some(room=>room.id===item.id)))
      actions.push({label:localize("rename"),run:()=>startLabel(item)});
    if (!mutable()) return actions;
    if(["hydraulics","hydraulic_collection","hydraulic_temperature","hydraulic_item"].includes(item.kind))
      return [...actions,...hydraulicMenuActions(item)];
    if (item.kind === "weather")
      actions.push({label:localize("weather_edit"),run:startWeather});
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
  function viewMode(){ return edit?localize("editing"):localize("view"); }
  function diagnosticState() {
    // Local unsaved edits matter for reproducing UI bugs. Never export the
    // APPLY confirmation phrase, authentication headers or callbacks.
    return {
      manifest_editor_available:!!info,
      manifest:info ? clone(info) : null,
      candidate: candidate ? clone(candidate) : null,
      editing: edit ? {
        kind:edit.kind || null,id:edit.id || null,roomId:edit.roomId || null,
        index:edit.index ?? null,returnWeatherKind:edit.returnWeatherKind || null,
      } : null,
      validated,confirmation_pending:!!confirmation,
      message,failure,
      labels:clone(labelsState),
      weather_context_loaded:!!weatherState,
      ha_catalog_cached:!!haWeatherCatalog,
    };
  }
  window.DHClimateEditor = {
    init, canEdit:online, canChange:mutable, menuActions,pageAction,
    startRoom,startDevice,startWeather,enterWeatherSection,setWeatherContext,
    beginHydraulic,beginHydraulicCreator,previewHydraulics,
    refreshAfterReconnect,
    renderEditor, controls, onNavigate,
    isEditing:()=>!!edit, needsRestart:()=>!!info?.pending_restart,
    viewMode, previewRooms, previewRoom,
    displayName, loadLabels, roomAreaId, roomAreaLabel,
    diagnosticState,
  };
})();
