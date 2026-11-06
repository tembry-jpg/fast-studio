// ── 4CP BACKGROUND STEP (client site) ───────────────────────────────────────
// 4CP insulators start with the background: a solid colour, a gradient, a
// stock pattern, the client's own picture or nothing, with shapes and text on
// top if they like. Side 1 is designed; Side 2 is the same or upside down;
// the bottom carries the background on or takes a solid colour. The server
// lays it onto the print sheet (/api/bg-sheet) and it becomes the item's
// full-bleed background. A finished whole-item design can be dropped in
// instead (upBleed). The logo goes on top in step 2.
const BGS_SLOT = "__bgside";
const BGD = { pid: null, base: { type: "solid", hex: "#FFFFFF", pms: null }, side2: "same",
              bottom: { mode: "same", hex: "#FFFFFF" }, design: null, seq: 0, t: null,
              stock: null, img: null, imgFor: null, built: null, finished: false, pmsOpen: false };
function bgdOn(){
  const z = S.prod?.bleed_zones;
  return !!(typeof CUSTOMER !== "undefined" && CUSTOMER && typeof bgBoardOk === "function" && bgBoardOk()
            && z?.side1 && z?.side2);
}
function bgdZonePts(id){
  const z = S.prod.bleed_zones[id], W = S.prod.page_w, H = S.prod.page_h;
  return { W: z.w * W, H: z.h * H };
}
function bgdSync(){
  const el = document.getElementById("bgd");
  if(!el) return;
  const on = bgdOn();
  document.body.classList.toggle("bgd-on", on);
  const lbl = document.getElementById("cs1-lbl");
  if(lbl) lbl.textContent = on ? "Background" : "Product color";
  CUST_HD[1] = on ? "Design your background" : "Pick your product color";
  const hd = document.getElementById("cust-hd");
  if(hd && typeof CSTEP !== "undefined" && CSTEP === 1 && hd.textContent !== CUST_HD[1]) hd.textContent = CUST_HD[1];
  if(!on){ el.style.display = "none"; return; }
  if(BGD.pid !== S.pid){
    Object.assign(BGD, { pid: S.pid, base: { type: "solid", hex: "#FFFFFF", pms: null }, side2: "same",
                         bottom: { mode: "same", hex: "#FFFFFF" }, design: null, stock: null, img: null,
                         built: null, finished: false });
    el.style.display = "";
    bgdRender();
  }
  // A finished design dropped in with "Upload a finished design".
  const fin = !!(S.bleed?.img && !S.bleed._bgd && !S.bleed._isStockBg);
  if(fin !== BGD.finished){ BGD.finished = fin; bgdRender(); }
}
function bgdEsc(t){ return String(t ?? "").replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c])); }
function bgdRender(){
  const el = document.getElementById("bgd"); if(!el || !bgdOn()) return;
  const b = BGD.base, t = b.type;
  const card = (k, label, sw) => `<button class="bgd-card${t === k ? " on" : ""}" onclick="bgdType('${k}')"><span class="bgd-sw" style="${sw}"></span>${label}</button>`;
  let opts = "";
  if(t === "solid"){
    opts = `<div class="bgd-row"><input type="color" value="${bgdEsc(b.hex)}" oninput="bgdSolid(this.value)" class="bgd-color">
      <input class="bgd-hex" value="${bgdEsc(b.hex)}" maxlength="7" onchange="bgdSolid(this.value)">
      <button class="bgd-link" onclick="bgdPmsToggle()">${b.pms ? "PMS " + bgdEsc(String(b.pms).replace(/^PANTONE\s+/, "")) : "Pick a PMS"}</button></div>
      <div id="bgd-pms" style="display:${BGD.pmsOpen ? "" : "none"}"><input class="pms-search" placeholder="Search PMS — 186 C, 7621…" oninput="bgdPmsList(this.value)"><div id="bgd-pms-list" style="max-height:180px;overflow-y:auto"></div></div>`;
  } else if(t === "gradient"){
    const s = b.stops || ["#FFFFFF", "#1C4FD0"];
    opts = `<div class="bgd-row"><input type="color" value="${s[0]}" oninput="bgdStop(0,this.value)" class="bgd-color"> → <input type="color" value="${s[1]}" oninput="bgdStop(1,this.value)" class="bgd-color">
      <select onchange="bgdDir(this.value)" class="bgd-sel">${[["down","Top to bottom"],["right","Left to right"],["diag","Diagonal"]].map(([v, l]) => `<option value="${v}"${(b.dir || "down") === v ? " selected" : ""}>${l}</option>`).join("")}</select></div>`;
  } else if(t === "stock"){
    opts = `<div class="bgd-grid" id="bgd-stock">Loading patterns…</div>`;
    setTimeout(bgdStockGrid, 0);
  } else if(t === "image"){
    opts = `<div class="bgd-row"><button class="bt b2" onclick="document.getElementById('bgd-fi').click()">${b.path ? "Replace picture" : "↑ Upload a picture"}</button>
      <span class="bgd-hint">${b.path ? bgdEsc(b.name || "your picture") : "JPG, PNG or PDF — it covers each side"}</span></div>`;
  } else {
    opts = `<div class="bgd-hint">Plain white — your logo goes on the white item.</div>`;
  }
  const s0 = (b.stops || ["#FFFFFF", "#1C4FD0"]);
  el.innerHTML = BGD.finished ? `
    <div class="bgd-fin">✓ Your finished design is on the item.
      <div class="bgd-hint">Add a logo on top in the next step if you like, or go straight to review.</div>
      <button class="bgd-link" onclick="bgdUnfinish()">Design a background here instead</button></div>` : `
    <div class="bgd-fin">Have the whole design finished already?
      <button class="bt b2 bgd-finbtn" onclick="upBleed()">↑ Upload a finished design</button>
      <div class="bgd-hint">One file laid out like our template: Side 1, the bottom, Side 2.
        <a class="bgd-link" href="/api/bg-template/${encodeURIComponent(S.pid)}" download>Download the template (PDF)</a></div></div>
    <div class="lbl">Background</div>
    <div class="bgd-cards">
      ${card("solid", "Solid color", `background:${bgdEsc(b.type === "solid" ? b.hex : "#3a7bd5")}`)}
      ${card("gradient", "Gradient", `background:linear-gradient(${s0[0]},${s0[1]})`)}
      ${card("stock", "Pattern", "background:repeating-linear-gradient(45deg,#6b1a2a 0 4px,#e9d8c4 4px 8px)")}
      ${card("image", "Your picture", "background:linear-gradient(135deg,#9bc 0,#fc9 100%)")}
      ${card("none", "None", "background:#fff")}
    </div>
    <div class="bgd-opts">${opts}</div>
    <div class="bgd-add">
      <button class="bt b2" onclick="bgdOpenDesign()">✎ ${BGD.design ? "Edit shapes &amp; text" : "Add shapes &amp; text on top"}</button>
      ${BGD.design ? `<button class="bgd-link" onclick="bgdClearDesign()">remove</button>` : ""}
    </div>
    <div class="lbl">Side 2</div>
    <div class="az-seg bgd-seg">
      <button class="${BGD.side2 === "same" ? "on" : ""}" onclick="bgdSide2('same')">Same as Side 1</button>
      <button class="${BGD.side2 === "flip" ? "on" : ""}" onclick="bgdSide2('flip')">Upside down</button>
    </div>
    <div class="lbl">Bottom</div>
    <div class="az-seg bgd-seg">
      <button class="${BGD.bottom.mode === "same" ? "on" : ""}" onclick="bgdBottom('same')">Same background</button>
      <button class="${BGD.bottom.mode === "solid" ? "on" : ""}" onclick="bgdBottom('solid')">Solid color</button>
    </div>
    ${BGD.bottom.mode === "solid" ? `<div class="bgd-row"><input type="color" value="${bgdEsc(BGD.bottom.hex)}" oninput="bgdBottomHex(this.value)" class="bgd-color"><span class="bgd-hint">the bottom's color</span></div>` : ""}
    <div class="bgd-hint" id="bgd-status">${BGD.built ? "✓ Background is on the item." : ""}</div>
    <input type="file" id="bgd-fi" accept=".jpg,.jpeg,.png,.webp,.pdf,.ai,.eps,.svg" style="display:none" onchange="bgdPicture(this)">`;
}
function bgdType(k){
  if(BGD.base.type === k) return;
  const keep = BGD.base;
  BGD.base = k === "solid" ? { type: "solid", hex: keep.hex || "#FFFFFF", pms: keep.pms || null }
           : k === "gradient" ? { type: "gradient", stops: keep.stops || ["#FFFFFF", "#1C4FD0"], dir: keep.dir || "down" }
           : k === "stock" ? { type: "stock", stock: keep.stock || null }
           : k === "image" ? { type: "image", path: keep.path || null, name: keep.name || "" }
           : { type: "none" };
  bgdRender();
  if(k === "solid" || k === "gradient" || k === "none" || (k === "stock" && BGD.base.stock) || (k === "image" && BGD.base.path)) bgdBuild();
}
function bgdSolid(v){
  v = String(v || "").trim(); if(!/^#?[0-9a-f]{6}$/i.test(v)) return;
  if(v[0] !== "#") v = "#" + v;
  BGD.base = { type: "solid", hex: v.toUpperCase(), pms: null };
  const hx = document.querySelector("#bgd .bgd-hex"); if(hx && document.activeElement !== hx) hx.value = BGD.base.hex;
  const col = document.querySelector("#bgd .bgd-color"); if(col && document.activeElement !== col) col.value = BGD.base.hex;
  const pm = document.querySelector("#bgd .bgd-row .bgd-link"); if(pm) pm.textContent = "Pick a PMS";
  bgdBuild();
}
async function bgdPmsToggle(){ BGD.pmsOpen = !BGD.pmsOpen; bgdRender(); if(BGD.pmsOpen){ await loadPmsLibrary(); bgdPmsList(""); } }
function bgdPmsList(q){ pmsPickerFill(document.getElementById("bgd-pms-list"), q, "bgdPmsPick", []); }
function bgdPmsPick(name, hex){ BGD.base = { type: "solid", hex: String(hex).toUpperCase(), pms: name }; BGD.pmsOpen = false; bgdRender(); bgdBuild(); }
function bgdStop(i, v){ const s = (BGD.base.stops || ["#FFFFFF", "#1C4FD0"]).slice(); s[i] = v.toUpperCase(); BGD.base.stops = s; bgdBuild(); }
function bgdDir(v){ BGD.base.dir = v; bgdBuild(); }
function bgdSide2(m){ BGD.side2 = m; bgdRender(); bgdBuild(); }
function bgdBottom(m){ BGD.bottom.mode = m; bgdRender(); bgdBuild(); }
function bgdBottomHex(v){ BGD.bottom.hex = v.toUpperCase(); bgdBuild(); }
function bgdUnfinish(){ S.bleed = { img: null, ox: 0, oy: 0, sc: 1, rot: 0 }; BGD.finished = false; BGD.built = null; bgdRender(); R(); }
function bgdClearDesign(){ BGD.design = null; bgdRender(); bgdBuild(); }
async function bgdStockGrid(){
  const box = document.getElementById("bgd-stock"); if(!box) return;
  try{
    if(!BGD.stock) BGD.stock = await (await fetch(`/api/stock-backgrounds/${encodeURIComponent(S.pid)}`)).json();
    const r = BGD.stock, files = Array.isArray(r) ? r : (r.files || []);
    const base = Array.isArray(r) ? `/static/assets/${assetId()}/stockbackgrounds` : (r.base_url || `/static/assets/${assetId()}/stockbackgrounds`);
    BGD.stockBase = base;
    if(!files.length){ box.textContent = "No patterns for this item."; return; }
    box.innerHTML = files.map(f => {
      const nm = f.replace(/\.(jpg|jpeg|png)$/i, "");
      const th = r.thumb_base ? `${r.thumb_base}/${encodeURIComponent(nm)}.jpg` : `${base}/${encodeURIComponent(f)}`;
      return `<button class="bgd-pat${BGD.base.stock === f ? " on" : ""}" title="${bgdEsc(nm)}" onclick="bgdStock(${bgdEsc(JSON.stringify(f))})"><span style="background-image:url('${th}')"></span><i>${bgdEsc(nm)}</i></button>`;
    }).join("");
  }catch(e){ box.textContent = "Patterns couldn't be loaded."; }
}
function bgdStock(f){ BGD.base = { type: "stock", stock: f }; bgdRender(); bgdBuild(); }
async function bgdPicture(inp){
  const f = inp.files?.[0]; inp.value = ""; if(!f) return;
  const st = document.getElementById("bgd-status"); if(st) st.textContent = "⏳ Reading your picture…";
  const fd = new FormData(); fd.append("file", f, f.name); fd.append("slot_id", "bgimg"); fd.append("purpose", "layout");
  if(S.pid) fd.append("product_id", S.pid);
  try{
    const r = await (await fetch("/api/rasterize", { method: "POST", body: fd })).json();
    if(r.error) throw new Error(r.error);
    const img = new Image();
    await new Promise((res, rej) => { img.onload = res; img.onerror = rej; img.src = `data:${r.preview_mime};base64,${r.preview_b64}`; });
    BGD.img = img;
    BGD.base = { type: "image", path: r.saved_path, name: f.name };
    bgdRender(); bgdBuild();
  }catch(e){ if(st) st.textContent = "⚠ " + e.message; }
}
function bgdBuild(){
  clearTimeout(BGD.t);
  BGD.t = setTimeout(bgdBuildNow, 250);
}
async function bgdBuildNow(){
  const seq = ++BGD.seq;
  const st = () => document.getElementById("bgd-status");
  if(st()) st().textContent = "⏳ Updating the background…";
  try{
    const r = await fetch("/api/bg-sheet", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ product_id: S.pid, base: BGD.base, design_pdf: BGD.design?.pdf || null,
                             side2: BGD.side2, bottom: BGD.bottom }) });
    const d = await r.json();
    if(!r.ok || d.error) throw new Error(d.error || "The background couldn't be built.");
    const fd = new FormData(); fd.append("server_path", d.saved_path); fd.append("slot_id", "bleed");
    if(S.pid) fd.append("product_id", S.pid);
    const p = await (await fetch("/api/rasterize", { method: "POST", body: fd })).json();
    if(p.error) throw new Error(p.error);
    const img = new Image();
    await new Promise((res, rej) => { img.onload = res; img.onerror = rej; img.src = `data:${p.preview_mime};base64,${p.preview_b64}`; });
    if(seq !== BGD.seq) return;                     // a newer change is on its way
    if(typeof S_FILL !== "undefined" && S_FILL) S_FILL.mode = "none";
    S.bleed = { img, ox: 0, oy: 0, sc: 1, rot: 0, file: null, cb: { x: 0, y: 0, w: img.width, h: img.height },
                savedPath: d.saved_path, _fromLayout: true, _bgd: true };
    BGD.built = d.saved_path; BGD.finished = false;
    if(st()) st().textContent = "✓ Background is on the item.";
    R();
  }catch(e){ if(seq === BGD.seq && st()) st().textContent = "⚠ " + e.message; }
}
// The side's background on its own (no shapes), for the design board.
async function bgdBasePreview(W, H){
  const k = Math.min(4, 1200 / Math.max(W, H)), c = document.createElement("canvas");
  c.width = Math.round(W * k); c.height = Math.round(H * k);
  const g = c.getContext("2d"), b = BGD.base;
  g.fillStyle = "#ffffff"; g.fillRect(0, 0, c.width, c.height);
  const cover = img => { const s = Math.max(c.width / img.width, c.height / img.height);
    g.drawImage(img, (c.width - img.width * s) / 2, (c.height - img.height * s) / 2, img.width * s, img.height * s); };
  if(b.type === "solid"){ g.fillStyle = b.hex || "#ffffff"; g.fillRect(0, 0, c.width, c.height); }
  else if(b.type === "gradient"){
    const s = b.stops || ["#FFFFFF", "#1C4FD0"], d = b.dir || "down";
    const gr = d === "right" ? g.createLinearGradient(0, 0, c.width, 0) : d === "diag" ? g.createLinearGradient(0, 0, c.width, c.height) : g.createLinearGradient(0, 0, 0, c.height);
    gr.addColorStop(0, s[0]); gr.addColorStop(1, s[1]); g.fillStyle = gr; g.fillRect(0, 0, c.width, c.height);
  } else if(b.type === "stock" && b.stock){
    const img = new Image(); img.crossOrigin = "anonymous";
    await new Promise(res => { img.onload = res; img.onerror = res; img.src = `${BGD.stockBase || `/static/assets/${assetId()}/stockbackgrounds`}/${encodeURIComponent(b.stock)}`; });
    if(img.width) cover(img);
  } else if(b.type === "image" && BGD.img) cover(BGD.img);
  return c;
}
async function bgdOpenDesign(){
  if(!bgdOn()) return;
  BGD.preview = await bgdBasePreview(bgdZonePts("side1").W, bgdZonePts("side1").H);
  await openLayout(BGS_SLOT, {});
  const loc = document.getElementById("ly-slot")?.closest("label"); if(loc) loc.style.display = "none";
}
function bgdLayoutClosed(){
  const loc = document.getElementById("ly-slot")?.closest("label"); if(loc) loc.style.display = "";
}
async function bgdDesignApply(d, items){
  BGD.design = { pdf: d.saved_path, items: items.map(it => ({ ...it })), board: { W: LY.W, H: LY.H } };
  closeLayout(); bgdLayoutClosed();
  bgdRender(); await bgdBuildNow();
}
function bgdLoadBoard(){
  LY.undo = []; LY.redo = []; LY.sel = -1;
  const ds = BGD.design;
  if(ds?.board){
    const f = Math.min(LY.W / ds.board.W, LY.H / ds.board.H);
    LY.items = ds.items.map(it => ({ ...it, x: it.x * f, y: it.y * f,
      ...(it.size ? { size: it.size * f } : {}), ...(it.w ? { w: it.w * f } : {}), ...(it.h ? { h: it.h * f } : {}) }));
  } else LY.items = [];
  LY.sel = LY.items.length - 1;
}
