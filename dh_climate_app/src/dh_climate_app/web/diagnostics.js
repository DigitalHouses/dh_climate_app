"use strict";
/* On-demand diagnostics. No polling, no edits, no browser URL or credentials. */
(() => {
  const browserErrors = [];
  const secretField = /password|passwd|secret|token|credential|authorization|cookie|api[_-]?key|private[_-]?key|access[_-]?key|session[_-]?id|author[_-]?id|user[_-]?id/i;
  const sensitiveQuery = /([?&](?:access_token|token|api_key|password|secret|signature|auth|code|key)=)[^&#\s]+/gi;
  const authHeader = /\b(Bearer|Basic)\s+[A-Za-z0-9._~+/-]+={0,2}/gi;
  const urlPassword = /(https?:\/\/)[^/\s:@]+:[^/\s@]+@/gi;
  const ingressPath = /(\/(?:api\/hassio_ingress|hassio\/ingress)\/)[^/?#\s"\x27]+/gi;

  function safeText(value) {
    return String(value)
      .replace(sensitiveQuery, "$1[REDACTED]")
      .replace(authHeader, "$1 [REDACTED]")
      .replace(urlPassword, "$1[REDACTED]@")
      .replace(ingressPath, "$1[REDACTED]");
  }
  function sanitize(value, depth=0) {
    if (depth >= 24) return "[DEPTH LIMIT]";
    if (Array.isArray(value)) return value.map(item => sanitize(item,depth+1));
    if (value && typeof value === "object") {
      const copy = {};
      for (const [key,item] of Object.entries(value))
        copy[key] = secretField.test(key) ? "[REDACTED]" : sanitize(item,depth+1);
      return copy;
    }
    if (typeof value === "string") return safeText(value);
    if (typeof value === "number") return Number.isFinite(value) ? value : null;
    if (value === null || typeof value === "boolean") return value;
    return value === undefined ? null : safeText(value);
  }
  function rememberError(type, message, location="", line=null) {
    browserErrors.push({at:new Date().toISOString(),type,
      message:safeText(message).slice(0,2000),
      source:safeText(location).split(/[?#]/)[0].split("/").pop().slice(0,120),line});
    if (browserErrors.length>50) browserErrors.shift();
  }
  window.addEventListener("error",event=>{
    rememberError("javascript",event.message,event.filename,event.lineno);
  });
  window.addEventListener("unhandledrejection",event=>{
    rememberError("promise",String(event.reason?.message || event.reason || "Unknown"));
  });

  function safeHtml(element) {
    if (!element) return null;
    const clone = element.cloneNode(true);
    // Text, labels and structure are useful; never store control secrets or URLs.
    for (const field of clone.querySelectorAll("input,textarea,select")) {
      field.removeAttribute("value");
      field.removeAttribute("placeholder");
      if (field.tagName==="TEXTAREA") field.textContent="";
      // Select option labels and their order matter for reconstructing UI.
    }
    for (const child of clone.querySelectorAll("*")) {
      for (const attribute of Array.from(child.attributes)) {
        if (secretField.test(attribute.name) ||
            ["href","src","action","formaction"].includes(attribute.name))
          child.removeAttribute(attribute.name);
        else if (secretField.test(child.getAttribute("name") || "") &&
                 attribute.name==="value")
          child.setAttribute("value","[REDACTED]");
      }
    }
    return safeText(clone.outerHTML).slice(0,1100000);
  }
  function rect(element) {
    const bound=element.getBoundingClientRect();
    const css=window.getComputedStyle(element);
    return {
      x:Math.round(bound.x),y:Math.round(bound.y),
      width:Math.round(bound.width),height:Math.round(bound.height),
      scroll_width:element.scrollWidth,scroll_height:element.scrollHeight,
      display:css.display,position:css.position,overflow:css.overflow,
      grid_columns:css.gridTemplateColumns,
      font:css.font,background:css.backgroundColor,color:css.color,
    };
  }
  function layout() {
    const selectors=[
      ".topbar","#explorer","#explorer-resizer","#tree","#workspace",
      "#breadcrumbs","#content","#inspector","#context-menu",
      "#restart-banner",".statusbar",
    ];
    const details={};
    for (const selector of selectors) {
      const el=document.querySelector(selector);
      if (el) details[selector]=rect(el);
    }
    const rows=Array.from(document.querySelectorAll(
      "#content .card,#content .editor-priority-row,"+
      "#content .editor-priority-list,#content .editor-priority-info,"+
      "#tree .tree-item"
    )).slice(0,400);
    details.rows=rows.map(el=>({
      kind:el.className,
      text:safeText(el.textContent).trim().slice(0,140),
      ...rect(el),
    }));
    return details;
  }
  function visibleFormState() {
    return Array.from(document.querySelectorAll(
      "#content input,#content select,#content textarea"
    )).map((element,index)=>{
      const id=element.id || null;
      const name=element.name || null;
      const sensitive=element.type==="password" ||
        secretField.test(name || "") || secretField.test(id || "");
      return {
        index,id,name,tag:element.tagName,type:element.type,
        value:sensitive ? "[REDACTED]" : safeText(element.value),
        checked:element.checked ?? null,
        disabled:element.disabled,read_only:element.readOnly ?? false,
      };
    });
  }
  function captureUi(context) {
    const areas={};
    for (const selector of [
      "#tree","#breadcrumbs","#content","#inspector","#context-menu",
      "#restart-banner",".topbar",".statusbar",
    ]) areas[selector]=safeHtml(document.querySelector(selector));
    let css=null;
    try {
      css=Array.from(document.styleSheets).map(sheet=>({
        source:(sheet.ownerNode?.getAttribute("href")||"inline").split("?")[0],
        rules:Array.from(sheet.cssRules||[]).map(rule=>rule.cssText).join("\n"),
      }));
    } catch (error) { css={error:safeText(error.message)}; }
    return {
      state:context,
      title:document.title,
      viewport:{
        width:window.innerWidth,height:window.innerHeight,
        device_pixel_ratio:window.devicePixelRatio,
        language:navigator.language,
      },
      loaded_assets:{
        scripts:Array.from(document.scripts).map(el=>el.getAttribute("src")),
        styles:Array.from(document.querySelectorAll("link[rel=stylesheet]"))
          .map(el=>el.getAttribute("href")),
      },
      rendered_html:areas,
      visible_form_fields:visibleFormState(),
      layout:layout(),
      css,
      javascript_errors:browserErrors.slice(),
    };
  }
  async function loadBackend() {
    const controller=new AbortController();
    const timeout=setTimeout(()=>controller.abort(),35000);
    try {
      const response=await fetch("api/diagnostics",{
        cache:"no-store",credentials:"same-origin",
        signal:controller.signal,
      });
      if(!response.ok)throw Error("Diagnostics HTTP "+response.status);
      return {ok:true,data:await response.json()};
    } catch (error) {
      const failure=safeText(error.message || String(error));
      try {
        const response=await fetch("api/snapshot",{
          cache:"no-store",credentials:"same-origin",
        });
        if(response.ok)return {
          ok:false,error:failure,partial:true,snapshot:await response.json(),
        };
      } catch (_) { /* browser capture can still be saved offline */ }
      return {ok:false,error:failure,partial:true};
    } finally {
      clearTimeout(timeout);
    }
  }
  let activeUrl=null;
  async function save(contextProvider,button,translation) {
    if (button.disabled) return;
    const t=translation || (key=>key);
    const previous=button.textContent;
    const before=typeof contextProvider==="function"?contextProvider():{};
    const ui=captureUi(before);
    button.disabled=true;
    button.textContent=t("diagnostics_collecting");
    const status=document.getElementById("diagnostics-status");
    try {
      const backend=await loadBackend();
      const report=sanitize({
        format:"dh_climate_app_support_diagnostics",
        schema_version:1,
        captured_at:new Date().toISOString(),
        privacy:"Contains HA entity names, states and configuration. Access tokens and passwords are redacted; review before sharing publicly.",
        ui,backend,
      });
      const blob=new Blob([JSON.stringify(report,null,2)+"\n"],
        {type:"application/json;charset=utf-8"});
      const url=URL.createObjectURL(blob);
      const link=document.createElement("a");
      link.href=url;
      const time=new Date().toISOString().replace(/[:.]/g,"-");
      link.download="dh-climate-diagnostics-"+time+".json";
      link.style.display="none";
      document.body.append(link);
      link.click();
      link.remove();
      if (activeUrl) URL.revokeObjectURL(activeUrl);
      activeUrl=url;
      if (status) status.textContent=t("diagnostics_ready");
    } catch (error) {
      rememberError("export",error.message || error);
      if (status) status.textContent=t("diagnostics_error")+": "+safeText(error.message);
    } finally {
      button.disabled=false;
      button.textContent=previous;
    }
  }
  window.addEventListener("pagehide",()=>{
    if (activeUrl) URL.revokeObjectURL(activeUrl);
  });
  window.DHClimateDiagnostics={save,sanitize};
})();
