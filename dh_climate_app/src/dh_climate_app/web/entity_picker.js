"use strict";
/* A single reusable read-only HA entity search/select dialog.
   Selection edits the form in memory; it NEVER calls a climate service. */
(() => {
  let dialog = null;
  const el = (tag, cls="", label=null) => {
    const node=document.createElement(tag);
    if (cls) node.className=cls;
    if (label!==null) node.textContent=String(label);
    return node;
  };
  const domainsFor = kind => {
    if (kind==="actuator-hardware") return ["climate"];
    if (kind==="actuator-virtual") return ["climate","switch"];
    if (kind==="humidity-actuator") return ["humidifier","switch"];
    if (kind==="weather") return ["weather","sensor"];
    if (kind==="binary") return ["binary_sensor"];
    return ["sensor"];
  };
  const classesFor = kind => ({
    temperature:["temperature"],
    humidity:["humidity"],
    window:["window","door","opening","garage_door"],
    power:["power"],
    pressure:["pressure"],
    rpm:["frequency","speed"],
  })[kind] || [];
  function match(item,filters) {
    const {kind,query,area,domain,availability,includeOther}=filters;
    if (!domainsFor(kind).includes(item.domain)) return false;
    if (domain!=="all" && item.domain!==domain) return false;
    if (area==="none" && item.area_id) return false;
    if (area!=="all" && area!=="none" && item.area_id!==area) return false;
    if (availability==="available" && !item.available) return false;
    if (availability==="unavailable" && item.available) return false;
    const classes=classesFor(kind);
    if (classes.length && !includeOther &&
        item.device_class && !classes.includes(item.device_class)) return false;
    const phrase=(item.name+" "+item.entity_id+" "+(item.area_name||"")+
      " "+(item.device_name||"")).toLocaleLowerCase();
    return phrase.includes(query.toLocaleLowerCase().trim());
  }
  function close() {
    if (!dialog) return;
    dialog.remove();
    dialog=null;
  }
  function option(select,value,name) {
    const opt=el("option","",name);opt.value=value;select.append(opt);
  }
  async function open({kind="temperature",multiple=false,values=[],title="",
                       areaHint="",usage={},tr=x=>x,onConfirm}) {
    close();
    const initial=[...new Set(values.filter(Boolean))];
    const chosen=new Set(initial);
    const backdrop=el("div","picker-backdrop");
    const sheet=el("section","picker-dialog");
    sheet.setAttribute("role","dialog");
    sheet.setAttribute("aria-modal","true");
    sheet.setAttribute("aria-label",title||tr("picker.title"));
    dialog=backdrop;
    backdrop.append(sheet);document.body.append(backdrop);
    const closeOnEscape=event=>{
      if(event.key==="Escape"){event.preventDefault();event.stopPropagation();close();}
    };
    backdrop.addEventListener("keydown",closeOnEscape);
    backdrop.addEventListener("click",event=>{if(event.target===backdrop)close();});
    const header=el("div","picker-header");
    const heading=el("h2","",title||tr("picker.title"));
    const exit=el("button","secondary-button","×");exit.type="button";
    exit.setAttribute("aria-label",tr("picker.cancel"));exit.onclick=close;
    header.append(heading,exit);sheet.append(header);
    const status=el("p","subtle",tr("picker.loading"));sheet.append(status);

    let catalog;
    try {
      const response=await fetch("api/entities",{cache:"no-store",credentials:"same-origin"});
      if(!response.ok)throw Error(tr("picker.error")+" (HTTP "+response.status+")");
      catalog=await response.json();
      if(!Array.isArray(catalog.entities)||!Array.isArray(catalog.areas))
        throw Error(tr("picker.error"));
    }catch(exc){
      if(dialog===backdrop)status.textContent=exc.message||tr("picker.error");
      return;
    }
    if(dialog!==backdrop)return;
    status.remove();
    const filters={kind,query:"",area:"all",domain:"all",availability:"all",includeOther:false};
    const matchedArea=catalog.areas.find(a=>
      a.name?.toLocaleLowerCase()===areaHint?.trim().toLocaleLowerCase());
    if(matchedArea)filters.area=matchedArea.id;
    const row=el("div","picker-filters");
    const search=el("input","picker-search");
    search.type="search"; search.placeholder=tr("picker.search");
    search.setAttribute("aria-label",tr("picker.search"));
    const area=el("select");area.setAttribute("aria-label",tr("picker.area"));
    option(area,"all",tr("picker.all_areas"));
    option(area,"none",tr("picker.no_area"));
    for(const item of catalog.areas)option(area,item.id,item.name||item.id);
    area.value=filters.area;
    const domain=el("select");domain.setAttribute("aria-label",tr("picker.domain"));
    option(domain,"all",tr("picker.all_types"));
    for(const d of domainsFor(kind))option(domain,d,d);
    const availability=el("select");
    availability.setAttribute("aria-label",tr("picker.availability"));
    for(const [v,key] of [["all","picker.all"],["available","picker.available"],
                           ["unavailable","picker.unavailable"]])
      option(availability,v,tr(key));
    row.append(search,area,domain,availability);sheet.append(row);
    const advanced=el("label","picker-advanced");
    const toggle=el("input");toggle.type="checkbox";
    advanced.append(toggle,document.createTextNode(" "+tr("picker.all_classes")));
    sheet.append(advanced);
    if(!classesFor(kind).length)advanced.hidden=true;

    const description=el("p","subtle small");sheet.append(description);
    const list=el("div","picker-results");list.setAttribute("role","listbox");
    list.setAttribute("aria-multiselectable",String(!!multiple));sheet.append(list);
    const footer=el("div","picker-footer");
    const selectedLabel=el("span","subtle small");
    const cancel=el("button","secondary-button",tr("picker.cancel"));cancel.onclick=close;
    const confirm=el("button","secondary-button",tr("picker.attach"));
    confirm.onclick=()=>{
      const result=Array.from(chosen);
      close();onConfirm(multiple?result:(result[0]||null));
    };
    footer.append(selectedLabel,cancel,confirm);sheet.append(footer);
    const refresh=()=>{
      if(dialog!==backdrop)return;
      const found=catalog.entities.filter(item=>match(item,filters));
      // Keep already assigned values visible even if HA registry/state lacks them.
      const known=new Map(catalog.entities.map(item=>[item.entity_id,item]));
      const missing=Array.from(chosen).filter(id=>!known.has(id));
      const sorted=found.slice().sort((a,b)=>{
        const aSelected=chosen.has(a.entity_id)?-1:0;
        const bSelected=chosen.has(b.entity_id)?-1:0;
        if(aSelected!==bSelected)return aSelected-bSelected;
        return a.name.localeCompare(b.name);
      });
      description.textContent=tr("picker.results")+": "+found.length+
        (found.length>150?" · "+tr("picker.refine"):"")+
        (catalog.truncated?" · "+tr("picker.truncated"):"");
      list.replaceChildren();
      const displayed=[...missing.map(id=>({
        entity_id:id,name:id,domain:id.split(".")[0],available:false,
        missing:true
      })),...sorted.slice(0,150)];
      for(const item of displayed){
        const used=usage[item.entity_id]||[];
        const itemLine=el("button","picker-result"+(chosen.has(item.entity_id)?" is-selected":""));
        itemLine.type="button";
        itemLine.setAttribute("role","option");
        itemLine.setAttribute("aria-selected",String(chosen.has(item.entity_id)));
        const tick=el("span","picker-tick",chosen.has(item.entity_id)?"☑":"□");
        const information=el("span","picker-info");
        information.append(el("strong","",item.name||item.entity_id),
          el("span","mono subtle",item.entity_id),
          el("span","subtle small",
            [item.area_name||tr("picker.no_area"),item.device_name,
             item.device_class,item.unit].filter(Boolean).join(" · ")));
        if(used.length)information.append(el("span","picker-in-use",
          tr("picker.used")+": "+used.join(", ")));
        const state=el("span","picker-state",
          item.missing?tr("picker.not_in_ha"):
          item.available?(item.state??"—"):tr("picker.unavailable"));
        itemLine.append(tick,information,state);
        itemLine.onclick=()=>{
          if(chosen.has(item.entity_id))chosen.delete(item.entity_id);
          else if(multiple)chosen.add(item.entity_id);
          else{chosen.clear();chosen.add(item.entity_id);}
          refresh();
        };
        list.append(itemLine);
      }
      if(!displayed.length)list.append(el("p","subtle",tr("picker.none")));
      selectedLabel.textContent=tr("picker.selected")+": "+chosen.size;
      confirm.disabled=chosen.size===0;
    };
    search.oninput=()=>{filters.query=search.value;refresh();};
    area.onchange=()=>{filters.area=area.value;refresh();};
    domain.onchange=()=>{filters.domain=domain.value;refresh();};
    availability.onchange=()=>{filters.availability=availability.value;refresh();};
    toggle.onchange=()=>{filters.includeOther=toggle.checked;refresh();};
    refresh();
    search.focus();
  }
  window.DHClimateEntityPicker={open,close,match,domainsFor,classesFor};
})();
