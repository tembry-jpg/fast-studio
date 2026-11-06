// "Gweg": the chat assistant on the client site - the browser half.
//
// The conversation lives here. Each turn goes to /api/assistant (assistant.py),
// which forwards it to Claude with the instructions and the tool list. When
// Claude asks for a tool, it is carried out HERE, on this page, with the same
// functions the buttons call, and the result goes back as the next turn. The
// tools only work the configurator: no export, no ordering, no sending.
// Off (no button) unless the server has ANTHROPIC_API_KEY.
(function(){
"use strict";
const A = {open: false, busy: false, msgs: [], files: {}, nfile: 0, pending: [], enabled: false};
const $ = id => document.getElementById(id);
const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}[c]));
const sleep = ms => new Promise(r => setTimeout(r, ms));

// ── the panel ────────────────────────────────────────────────────────────
const CSS = `
#ask-panel{position:fixed;top:0;right:0;bottom:0;width:min(400px,100vw);background:var(--surface);border-left:1px solid var(--border);
  box-shadow:-8px 0 24px rgba(28,20,16,.10);display:none;flex-direction:column;z-index:9000;font-family:var(--sans)}
#ask-panel.on{display:flex}
.ask-head{position:relative;display:flex;align-items:center;gap:16px;padding:14px 16px;border-bottom:1px solid var(--border);
  background:linear-gradient(to bottom,var(--border) 0,var(--border) 50%,var(--cream) 50%,var(--cream) 100%)}
.ask-name{flex:1;display:flex;flex-direction:column;line-height:1;color:var(--burgundy);padding-top:14px}
.ask-name small{font:12px var(--mono);letter-spacing:.3px;margin:0 0 10px 2px}
.ask-name b{font-family:var(--serif);font-size:42px;font-weight:500;letter-spacing:-.3px}
.ask-hbtn{position:absolute;top:8px;right:10px;display:flex;gap:6px}
.ask-hbtn button{border:1px solid rgba(107,26,42,.25);background:rgba(244,240,232,.85);border-radius:999px;padding:3px 10px;font:600 11px var(--sans);color:var(--burgundy);cursor:pointer}
.ask-hbtn button:hover{background:var(--cream)}
#ask-log{flex:1;overflow-y:auto;padding:14px;display:flex;flex-direction:column;gap:10px}
.ask-m{max-width:88%;padding:9px 12px;border-radius:12px;font-size:13px;line-height:1.5;white-space:pre-wrap;word-wrap:break-word}
.ask-m.u{align-self:flex-end;background:var(--burgundy);color:#fff;border-bottom-right-radius:4px}
.ask-m.a{align-self:flex-start;background:var(--cream-dark);color:var(--text);border-bottom-left-radius:4px}
.ask-m.e{align-self:stretch;background:#fbeaea;color:#7a1c1c;font-size:12px}
.ask-t{align-self:flex-start;font:11px var(--mono);color:var(--muted);padding:0 4px}
.ask-files{display:flex;flex-wrap:wrap;gap:6px;margin-top:6px}
.ask-chip{display:inline-flex;align-items:center;gap:5px;background:rgba(255,255,255,.18);border:1px solid rgba(255,255,255,.35);border-radius:6px;padding:2px 7px;font-size:11px}
.ask-m.a .ask-chip,.ask-pend .ask-chip{background:var(--surface);border-color:var(--border);color:var(--text)}
.ask-chip img{width:22px;height:22px;object-fit:contain;border-radius:3px;background:#fff}
.ask-pend{display:flex;flex-wrap:wrap;gap:6px;padding:0 14px}
.ask-pend .ask-chip button{border:none;background:none;color:var(--muted);cursor:pointer;font-size:13px;line-height:1;padding:0}
.ask-in{display:flex;gap:8px;align-items:flex-end;padding:10px 14px 14px;border-top:1px solid var(--border)}
#ask-text{flex:1;resize:none;min-height:38px;max-height:140px;padding:9px 11px;border:1.5px solid var(--border);border-radius:9px;
  font:13px var(--sans);background:#fff;color:var(--text);outline:none}
#ask-text:focus{border-color:var(--border-hi)}
.ask-in button{height:38px;border-radius:9px;border:1.5px solid var(--border);background:var(--surface);cursor:pointer;color:var(--text);font:600 12px var(--sans);padding:0 11px}
.ask-in button.go{background:var(--burgundy);border-color:var(--burgundy);color:#fff}
.ask-in button:disabled{opacity:.5;cursor:default}
#ask-panel.drag #ask-log{outline:2px dashed var(--burgundy);outline-offset:-8px}
.ask-hint{font-size:12px;color:var(--muted);line-height:1.5;padding:4px 2px}
.ask-dots::after{content:"…";animation:askd 1.2s steps(4) infinite}
@keyframes askd{0%{content:""}25%{content:"."}50%{content:".."}75%{content:"..."}}
.ask-swm{max-width:100%}
.ask-av-lg{width:92px;height:92px;border-radius:50%;flex:none;box-shadow:0 2px 8px rgba(28,20,16,.18)}
.ask-row{display:flex;align-items:flex-end;gap:7px;align-self:flex-start;max-width:94%}
.ask-row .ask-m{max-width:none}
.ask-av{width:44px;height:44px;border-radius:50%;flex:none;box-shadow:0 1px 4px rgba(28,20,16,.15)}
#ask-btn{position:relative;border:none;background:var(--border);color:var(--burgundy);border-radius:999px;margin-left:30px;
  padding:5px 16px 5px 24px;font:500 12px var(--mono);letter-spacing:.2px;overflow:visible}
#ask-btn:hover{background:var(--border-hi);color:var(--burgundy)}
#ask-btn img{position:absolute;left:-22px;top:50%;transform:translateY(-50%);width:40px;height:40px;border-radius:50%;
  box-shadow:0 1px 4px rgba(28,20,16,.2);margin:0}
#ask-btn.on{background:var(--burgundy);color:var(--cream)}
.ask-swh{font-size:12px;color:var(--muted);margin-bottom:6px}
.ask-sw{display:flex;flex-wrap:wrap;gap:6px}
.ask-sw button{display:flex;align-items:center;gap:6px;border:1.5px solid var(--border);background:#fff;border-radius:8px;padding:4px 9px 4px 4px;cursor:pointer;font:600 11.5px var(--sans);color:var(--text)}
.ask-sw button:hover{border-color:var(--burgundy)}
.ask-sw i{width:26px;height:26px;border-radius:6px;border:1px solid rgba(0,0,0,.12);display:block}
@media (min-width:1100px){body.ask-open{padding-right:min(400px,100vw)}}
`;

function build(){
  const st = document.createElement("style"); st.textContent = CSS; document.head.appendChild(st);
  const p = document.createElement("div"); p.id = "ask-panel";
  p.innerHTML = `<div class="ask-head"><img class="ask-av-lg" src="/static/img/gweg.png" alt=""><div class="ask-name"><small>chatting with:</small><b>Gweg</b></div><div class="ask-hbtn"><button onclick="askNew()" title="Start over">New chat</button><button onclick="askToggle(false)">Close</button></div></div>
    <div id="ask-log"></div><div class="ask-pend" id="ask-pend"></div>
    <div class="ask-in"><button onclick="document.getElementById('ask-file').click()" title="Attach artwork">Attach</button>
      <textarea id="ask-text" rows="1" placeholder="e.g. a navy Kolder Kaddy with this logo in white"></textarea>
      <button class="go" id="ask-go" onclick="askSend()">Send</button>
      <input type="file" id="ask-file" multiple accept=".png,.jpg,.jpeg,.svg,.pdf,.ai,.eps,.tif,.tiff,.webp,.gif" style="display:none"></div>`;
  document.body.appendChild(p);
  const t = $("ask-text");
  t.addEventListener("keydown", e => { if(e.key === "Enter" && !e.shiftKey){ e.preventDefault(); askSend(); } });
  t.addEventListener("input", () => { t.style.height = "auto"; t.style.height = Math.min(140, t.scrollHeight) + "px"; });
  $("ask-file").addEventListener("change", e => { addFiles(e.target.files); e.target.value = ""; });
  p.addEventListener("dragover", e => { e.preventDefault(); p.classList.add("drag"); });
  p.addEventListener("dragleave", () => p.classList.remove("drag"));
  p.addEventListener("drop", e => { e.preventDefault(); p.classList.remove("drag"); addFiles(e.dataTransfer.files); });
  hello();
}

function hello(){
  $("ask-log").innerHTML = `<div class="ask-row"><img class="ask-av" src="/static/img/gweg.png" alt=""><div class="ask-m a">Hi, I'm Gweg! I live in this website and have never once held a can, but I'm weirdly good at dressing them up. Tell me what you'd like and attach your logo (the Attach button or drop it here), and I'll build it while you watch. Ask me anything along the way.</div></div>
    <div class="ask-hint">Try: "a red, a blue and a purple Kolder Kaddy with this logo, as big as it fits, in yellow" or "a 4CP Pocket Coolie with a navy background and this logo".</div>`;
}

window.askToggle = function(force){
  A.open = force ?? !A.open;
  $("ask-panel")?.classList.toggle("on", A.open);
  $("ask-btn")?.classList.toggle("on", A.open);
  document.body.classList.toggle("ask-open", A.open);
  try{ window.dispatchEvent(new Event("resize")); }catch(e){}
  if(A.open) setTimeout(() => $("ask-text")?.focus(), 50);
};
window.askNew = function(){
  if(A.busy) return;
  A.msgs = []; A.pending = []; renderPending(); hello();
};

function log(cls, html){
  const d = document.createElement("div"); d.className = cls; d.innerHTML = html;
  if(/(^|\s)ask-m a(\s|$)/.test(cls) && !/ask-swm/.test(cls)){
    const row = document.createElement("div"); row.className = "ask-row";
    const av = document.createElement("img"); av.className = "ask-av"; av.src = "/static/img/gweg.png"; av.alt = "";
    row.append(av, d);
    const l = $("ask-log"); l.appendChild(row); l.scrollTop = l.scrollHeight; return row;
  }
  const l = $("ask-log"); l.appendChild(d); l.scrollTop = l.scrollHeight; return d;
}
function mdLite(s){
  return esc(s).replace(/\*\*(.+?)\*\*/g, "<b>$1</b>").replace(/`([^`]+)`/g, "<code>$1</code>");
}

// ── attachments ──────────────────────────────────────────────────────────
function addFiles(list){
  for(const f of list || []){
    if(f.size > 50e6){ log("ask-m e", `${esc(f.name)} is over 50 MB.`); continue; }
    const id = "a" + (++A.nfile);
    A.files[id] = f; A.pending.push(id);
  }
  renderPending();
}
function chipHTML(id, removable){
  const f = A.files[id]; if(!f) return "";
  const img = /^image\/(png|jpe?g|gif|webp|svg\+xml)$/.test(f.type) ? `<img src="${URL.createObjectURL(f)}" alt="">` : "";
  return `<span class="ask-chip">${img}${esc(f.name)}${removable ? ` <button onclick="askUnattach('${id}')" title="Remove">×</button>` : ""}</span>`;
}
function renderPending(){ const p = $("ask-pend"); if(p) p.innerHTML = A.pending.map(id => chipHTML(id, true)).join(""); }
window.askUnattach = id => { A.pending = A.pending.filter(x => x !== id); renderPending(); };

// A small JPEG of an image attachment, for Claude to look at.
async function thumb(file, max = 768){
  if(!/^image\/(png|jpe?g|gif|webp|svg\+xml)$/.test(file.type)) return null;
  try{
    const url = URL.createObjectURL(file);
    const img = await new Promise((ok, no) => { const i = new Image(); i.onload = () => ok(i); i.onerror = no; i.src = url; });
    let w = img.naturalWidth || 800, h = img.naturalHeight || 800;
    const k = Math.min(1, max / Math.max(w, h)); w = Math.max(1, Math.round(w * k)); h = Math.max(1, Math.round(h * k));
    const c = document.createElement("canvas"); c.width = w; c.height = h;
    const g = c.getContext("2d"); g.fillStyle = "#c8c8c8"; g.fillRect(0, 0, w, h);   // grey, so white art shows
    g.drawImage(img, 0, 0, w, h); URL.revokeObjectURL(url);
    return c.toDataURL("image/jpeg", 0.85).split(",")[1];
  }catch(e){ return null; }
}

// ── the conversation ─────────────────────────────────────────────────────
window.askSend = async function(){
  if(A.busy) return;
  const t = $("ask-text"); const text = t.value.trim();
  if(!text && !A.pending.length) return;
  t.value = ""; t.style.height = "auto";
  const ids = A.pending; A.pending = []; renderPending();
  log("ask-m u", esc(text) + (ids.length ? `<div class="ask-files">${ids.map(id => chipHTML(id)).join("")}</div>` : ""));
  const content = [];
  if(ids.length){
    content.push({type: "text", text: "Attached: " + ids.map(id => `${A.files[id].name} (file id ${id})`).join(", ") + "."});
    for(const id of ids){
      const b = await thumb(A.files[id]);
      if(b) content.push({type: "image", source: {type: "base64", media_type: "image/jpeg", data: b}});
    }
  }
  content.push({type: "text", text: text || "(see the attached file)"});
  A.msgs.push({role: "user", content});
  await run();
};
// A swatch clicked in the chat answers for the client.
window.askSay = function(text){
  if(A.busy) return;
  const t = $("ask-text"); if(!t) return;
  t.value = text; askSend();
};

// Older pictures are dropped from what's sent again (they cost a lot and the
// latest preview is what matters).
function forSend(){
  const keep = 4;
  return A.msgs.map((m, k) => {
    if(k >= A.msgs.length - keep || !Array.isArray(m.content)) return m;
    return {...m, content: m.content.map(b => {
      if(b.type === "image") return {type: "text", text: "[picture shown earlier]"};
      if(b.type === "tool_result" && Array.isArray(b.content))
        return {...b, content: b.content.map(x => x.type === "image" ? {type: "text", text: "[preview shown earlier]"} : x)};
      return b;
    })};
  });
}

async function run(){
  A.busy = true; $("ask-go").disabled = true;
  let think = log("ask-t", `<span class="ask-dots">Thinking</span>`);
  try{
    for(let step = 0; step < 25; step++){
      const r = await fetch("/api/assistant", {method: "POST", headers: {"Content-Type": "application/json"},
                                               body: JSON.stringify({messages: forSend()})});
      const j = await r.json().catch(() => ({error: r.status === 401 ? "Your sign-in has expired - reload the page to sign in again."
                                                                        : "Gweg sent back something unreadable."}));
      if(!r.ok || j.error){
        think.remove();
        log("ask-m e", esc(j.error || `Error ${r.status}`));
        // The message that didn't get an answer is taken back, so a retry works.
        if(A.msgs.length && A.msgs[A.msgs.length - 1].role === "user" && step === 0) A.msgs.pop();
        break;
      }
      const blocks = j.content || [];
      A.msgs.push({role: "assistant", content: blocks});
      think.remove();
      for(const b of blocks) if(b.type === "text" && b.text.trim()) log("ask-m a", mdLite(b.text.trim()));
      const calls = blocks.filter(b => b.type === "tool_use");
      if(j.stop_reason !== "tool_use" || !calls.length) break;
      const results = [];
      for(const c of calls){
        const t = log("ask-t", esc(label(c)) + "…");
        let out, err = false;
        try{ out = await TOOLS[c.name]?.(c.input || {}); if(out === undefined) throw new Error("no such tool"); }
        catch(e){ out = "Error: " + (e?.message || e); err = true; }
        t.textContent = label(c) + (err ? " - didn't work" : "");
        results.push({type: "tool_result", tool_use_id: c.id,
                      content: Array.isArray(out) ? out : (typeof out === "string" ? out : JSON.stringify(out)),
                      ...(err ? {is_error: true} : {})});
      }
      A.msgs.push({role: "user", content: results});
      think = log("ask-t", `<span class="ask-dots">Thinking</span>`);
    }
  }catch(e){
    log("ask-m e", "Something went wrong: " + esc(e?.message || e));
  }finally{
    think?.remove?.();
    A.busy = false; $("ask-go").disabled = false;
    // A dangling tool call (an error mid-turn) would break the next turn.
    const last = A.msgs[A.msgs.length - 1];
    if(last?.role === "assistant" && (last.content || []).some(b => b.type === "tool_use")) A.msgs.pop();
  }
}

function label(c){
  const i = c.input || {};
  return ({get_state: "Checking the item", find_items: `Looking up "${i.query}"`, open_item: `Opening ${itemName(i.id)}`,
    set_color: `${i.picker}: ${i.color}`, add_colorway: "Adding a colorway", switch_colorway: `Colorway ${i.n}`,
    set_sides: `Sides: ${i.mode === "same" ? "same logo both sides" : "each side its own"}`,
    set_print_side: `Printing on ${locName(i.side)}`, place_art: `Placing art on ${locName(i.location)}`,
    remove_art: `Removing art from ${locName(i.location)}`, suggest_inks: `Finding ${i.color} inks`,
    set_inks: `Ink: ${(i.inks || []).filter(Boolean).join(", ")}`,
    set_white: `White: ${i.mode === "ink" ? "prints" : "cut out"}`, set_art_size: `Sizing ${locName(i.location)}`,
    move_art: `Moving ${locName(i.location)}`, rotate_art: `Rotating ${locName(i.location)}`,
    set_background: `Background: ${i.type || "update"}`, get_preview: "Looking at the mockup",
    show_lifestyle: "Opening the lifestyle photo", download_virtual: "Downloading the virtual",
    go_to_review: "Going to Review & send", get_design: `Reading the design on ${locName(i.location)}`,
    make_design: `Designing ${locName(i.location)}`, edit_design: `Editing the design on ${locName(i.location)}`,
    use_template: `Template: ${i.template}`, clear_inside: `Inner white: ${i.mode}`,
    hide_color: `${i.hidden === false ? "Bringing back" : "Leaving out"} colour ${i.n}`})[c.name] || c.name;
}

// ── the tools: the configurator's own functions ──────────────────────────
let LITE = null;                      // this site's catalog (names, coming soon)
async function catalog(){
  if(!LITE){ try{ LITE = await (await fetch("/api/products-lite")).json(); }catch(e){ LITE = []; } }
  return LITE;
}
function itemName(id){ return (LITE || []).find(p => p.id === id)?.name || id; }
function locName(id){ return S.prod?.slots?.find(s => s.id === id)?.label || id || "?"; }
function needLoc(id){
  if(!S.prod) throw new Error("No item is open.");
  if(!S.prod.slots?.some(s => s.id === id)) throw new Error(`No location "${id}" on this item. Locations: ${S.prod.slots.map(s => s.id).join(", ")}`);
  return id;
}
function needArt(id){ needLoc(id); if(!S.slots[id]?.img || S.slots[id].isDefault) throw new Error(`${locName(id)} has no art.`); return S.slots[id]; }
const r2 = v => v == null ? null : Math.round(v * 100) / 100;
const has = n => typeof window[n] === "function" || (typeof globalThis[n] === "function");

function pickers(){
  const out = [], seen = new Set();
  for(const sw of document.querySelectorAll(".cc")){
    const row = sw.parentElement; if(!row?.id || seen.has(row.id)) continue;
    if(/^fill-|^pen3pk-/.test(row.id)) continue;
    seen.add(row.id);
    const opts = [...row.querySelectorAll(".cc")].map(e => e.title).filter(Boolean);
    const cur = row.querySelector(".cc.on")?.title || null;
    out.push({picker: pickerName(row.id), options: opts, picked: cur, _row: row.id});
  }
  return out;
}
function pickerName(rid){
  if(rid === "nr") return /jotter|pen/i.test((S.prod?.material || "") + " " + (S.prod?.label || "")) ? "Pen color" : "Body";
  if(rid === "sr") return "Stitching";
  if(rid === "trr") return "Trim";
  const m = rid.match(/^pp-(.+)-cr$/); if(m) return S.prod?.parts?.find(p => p.id === m[1])?.label || m[1];
  return rid;
}
function is4(p){ return !!(p?.is_4cp || /4cp/i.test(p?.material || "")); }
function method(p){
  if(is4(p)) return "full colour (4CP), printed background + logo";
  if(/jotter/i.test(p?.material || "") || /jotter/i.test(p?.id || "")) return "full colour digital, one location";
  if(p?.is_screenprint || /1c|24HR/i.test(p?.id || "")) return "one-colour screen print (one PANTONE ink)";
  return p?.printing || "full colour";
}
function inkMode(){
  if(!S.prod) return null;
  if(typeof isScreenPrint === "function" && isScreenPrint()) return "one";
  if(typeof mcUsesSets === "function" && mcUsesSets()) return "multi";
  return "full";
}
function artInfo(id){
  const sl = S.slots[id];
  if(!sl?.img || sl.isDefault) return {location: id, name: locName(id), art: null};
  const o = {location: id, name: locName(id), art: sl._askName || sl.file?.name || (sl.txtCfg ? "text" : "art"),
             width_in: r2(artPrintedWidth(id)), height_in: r2(artPrintedHeight(id)),
             rotation_deg: Math.round((sl.rot || 0) * 180 / Math.PI)};
  if(sl.mc?.inks?.length) o.colors = sl.mc.inks.map((i, k) => ({n: k + 1, art_color: i.hex, ink: i.pms || null, hidden: !!i.hidden || undefined}));
  if(sl.mc?.hasWhite) o.white = sl.mc.whiteMode || "not chosen yet";
  return o;
}
function sidesInfo(){
  if(!(typeof hasSidePair === "function" && hasSidePair())) return null;
  if(typeof imprintOne === "function" && imprintOne())
    return {one_location: true, prints_on: imprintSide(), note: "Prints on one side only; both show on the mockup."};
  return {mode: sidesSame() ? "same" : "diff"};
}
function colorways(){
  if(!(typeof varEligible === "function" && varEligible())) return undefined;
  if(!(typeof varOn === "function" && varOn())) return {count: 1, note: "add_colorway adds another colour of this item"};
  return {count: VAR.list.length, editing: VAR.active + 1,
          list: VAR.list.map((v, i) => ({n: i + 1, label: (typeof varLabel === "function" ? varLabel(v) : `#${i + 1}`)}))};
}
async function stockList(){
  try{
    const r = await (await fetch(`/api/stock-backgrounds/${encodeURIComponent(S.pid)}`)).json();
    return (Array.isArray(r) ? r : (r.files || []));
  }catch(e){ return []; }
}
async function bgInfo(){
  if(!(typeof bgdOn === "function" && bgdOn())) return undefined;
  const b = BGD.base || {};
  const type = BGD.finished ? "finished design uploaded" : ({stock: "pattern", image: "picture"}[b.type] || b.type);
  return {type, hex: b.hex, pms: b.pms, colors: b.stops,
          direction: b.dir, pattern: b.stock ? b.stock.replace(/\.(jpg|jpeg|png)$/i, "") : undefined,
          side2: BGD.side2 === "flip" ? "upside_down" : "same", bottom: BGD.bottom?.mode,
          shapes_text_on_top: !!BGD.design,
          patterns: (await stockList()).map(f => f.replace(/\.(jpg|jpeg|png)$/i, ""))};
}

// Colour words -> a target colour, for suggest_inks.
const FAMILY = {yellow: "#FFD100", gold: "#C69214", orange: "#FF8200", red: "#D50032", maroon: "#7A2531",
  burgundy: "#7A2531", pink: "#F57EB6", "hot pink": "#E0457B", magenta: "#CE0058", purple: "#653279",
  violet: "#5C068C", lavender: "#B4A7D6", navy: "#13294B", blue: "#0057B8", "royal blue": "#003DA5",
  "light blue": "#7BAFD4", "sky blue": "#62B5E5", teal: "#008C95", turquoise: "#00B2A9", aqua: "#00A3AD",
  green: "#009A44", "kelly green": "#00843D", "lime": "#97D700", "forest green": "#205C40", olive: "#5E7E29",
  brown: "#6E4C1E", tan: "#C4A77D", beige: "#D7C4A3", grey: "#8A8D8F", gray: "#8A8D8F", silver: "#A2AAAD",
  black: "#2D2926", white: "#FFFFFF", cream: "#F1E6B2", mint: "#A0DAB3", coral: "#FF6A61", peach: "#F8B888"};
function labOf(hex){
  const n = parseInt(String(hex).slice(1), 16), f = c => { c /= 255; return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4; };
  const r = f(n >> 16 & 255), g = f(n >> 8 & 255), b = f(n & 255);
  const X = (0.4124 * r + 0.3576 * g + 0.1805 * b) / 0.95047, Y = 0.2126 * r + 0.7152 * g + 0.0722 * b, Z = (0.0193 * r + 0.1192 * g + 0.9505 * b) / 1.08883;
  const t = v => v > 0.008856 ? Math.cbrt(v) : 7.787 * v + 16 / 116;
  return [116 * t(Y) - 16, 500 * (t(X) - t(Y)), 200 * (t(Y) - t(Z))];
}
function swatchesHTML(list){
  return `<div class="ask-sw">${list.map(c => `<button onclick="askSay(${esc(JSON.stringify("Use " + c.name))})" title="${esc(c.name)}">`
    + `<i style="background:${esc(c.hex)}"></i>${esc(c.name.replace(/^PANTONE\s+/, ""))}</button>`).join("")}</div>`;
}

// ── the layout tool (text, shapes, arranging art) ─────────────────────────
const TSIZE = {small: 0.12, medium: 0.2, large: 0.3, huge: 0.45};   // of the print area's height
const clamp = (v, a, b) => Math.max(a, Math.min(b, Number(v) || 0));
function lyBusy(){ return $("ly-scrim")?.classList.contains("vis"); }
function lyLoc(location){
  needLoc(location);
  if(typeof BG_SLOT !== "undefined" && location === BG_SLOT) throw new Error("Use set_background for the 4CP background.");
  return (typeof sidesSame === "function" && sidesSame() && location === "side2") ? "side1" : location;
}
async function lyOpen(location){
  const id = lyLoc(location);
  if(lyBusy()) closeLayout();
  try{ custStep(2); }catch(e){}
  await openLayout(id); await sleep(200);
  return id;
}
async function lyFont(name){
  const fonts = await layoutFonts();
  if(!name) return "Oswald";
  const n = String(name).toLowerCase().replace(/[^a-z0-9]/g, "");
  const f = fonts.find(x => x.key.toLowerCase() === n || String(x.label).toLowerCase().replace(/[^a-z0-9]/g, "") === n)
         || fonts.find(x => x.key.toLowerCase().includes(n) || n.includes(x.key.toLowerCase()));
  if(!f) throw new Error(`No font "${name}". Fonts: ${fonts.map(x => x.label || x.key).join(", ")}`);
  return f.key;
}
async function lyColor(it, c){
  if(!c || isScreenPrint()) return;                        // one-ink items print everything in the ink
  const s = String(c).trim();
  if(/^#?[0-9a-f]{6}$/i.test(s)){ it.color = (s[0] === "#" ? s : "#" + s).toUpperCase(); it.pms = null; return; }
  if(!SP.loaded && typeof loadPmsLibrary === "function") await loadPmsLibrary();
  const k = /^white$/i.test(s) ? {name: "White", hex: "#FFFFFF"} : (_findInk(s) || _findInk("PANTONE " + s.replace(/^(pms|pantone)\s*/i, "")));
  if(k){ it.color = k.hex; it.pms = k.name; return; }
  const h = FAMILY[s.toLowerCase()];
  if(h){ it.color = h; it.pms = null; return; }
  throw new Error(`Unknown colour "${c}" - use a hex or a PANTONE name.`);
}
async function lyArt(f){
  const fd = new FormData();
  fd.append("file", f, f.name); fd.append("slot_id", LY.slot || "layout");
  fd.append("product_id", S.pid || ""); fd.append("purpose", "layout");
  const d = await (await fetch("/api/rasterize", {method: "POST", body: fd})).json();
  if(d.error) throw new Error(`${f.name}: ${d.error}`);
  let img = new Image();
  await new Promise((ok, no) => { img.onload = ok; img.onerror = no; img.src = `data:${d.preview_mime};base64,${d.preview_b64}`; });
  try{ const ko = knockoutRasterBackground(img); if(ko) img = ko; }catch(e){}
  const it = {type: "art", src: d.saved_path, name: f.name, img, x: LY.W / 2, y: LY.H / 2};
  it.w = Math.min(LY.W * 0.6, LY.H * 0.6 / studioArtAspect(it));
  return it;
}
async function lyFonts(){ await Promise.all(LY.items.filter(i => i.type === "text").map(i => layoutEnsureFont(i.font, i.bold, i.italic))); }
async function lyApply(location){
  await lyFonts();
  studioRender();
  await layoutDone();
  if(lyBusy()){
    const why = ($("ly-note")?.textContent || "").replace(/^⚠\s*/, "").trim();
    closeLayout();
    throw new Error("The design didn't go on" + (why ? `: ${why}` : "."));
  }
  await settle();
  for(const t of pairedIds(lyLoc(location))) if(S.slots[t]) S.slots[t]._askName = "design (art/text from the layout tool)";
  const out = artInfo(location);
  const w = typeof layoutTypeWarning === "function" ? layoutTypeWarning(lyLoc(location)) : "";
  if(w) out.warning = w;
  return out;
}
function lyDescribe(){
  return LY.items.map((it, i) => it.type === "text"
      ? {index: i, type: "text", text: it.text, font: it.font, size_pt: Math.round(it.size), bold: !!it.bold || undefined,
         italic: !!it.italic || undefined, curve: it.curve || undefined, spacing: it.spacing || undefined,
         color: layoutUsesColor() ? (it.pms || it.color) : undefined}
    : it.type === "art" ? {index: i, type: "art", name: String(it.name || "art").replace(/^[a-z0-9]+_[0-9a-f]{10}_/i, "").replace(/\.(preview|press|octrace|4cp)[^/]*$/i, "")}
    : {index: i, type: "shape", shape: it.shape, color: layoutUsesColor() ? (it.pms || it.color) : undefined});
}
function lyShape(shape, gw, gh){
  const s = Math.min(LY.W, LY.H), st = Math.max(1.5, s * 0.02);
  const b = {type: "shape", shape, color: "#000000", x: LY.W / 2, y: LY.H / 2, stroke: st};
  if(shape === "line") b.w = Math.max(LY.W * 0.3, gw * 0.7);
  else if(shape === "block") Object.assign(b, {w: LY.W * 0.5, h: LY.H * 0.12});
  else if(shape === "ring") b.w = Math.max(gw, gh) * 1.3 || s * 0.9;
  else if(shape === "frame") Object.assign(b, {w: (gw || LY.W * 0.7) * 1.15 + s * 0.06, h: (gh || LY.H * 0.6) * 1.2 + s * 0.06});
  else b.w = s * 0.12;                                     // star, dot
  return b;
}

const TOOLS = {
  async get_design({location}){
    const id = lyLoc(location);
    if(lyBusy()) throw new Error("The customer has the layout tool open - let them finish, or ask them to close it.");
    await layoutFonts();
    LY.slot = id; studioLoad(id, {});
    await lyFonts();
    return {location, print_area_in: [r2(LY.W / 72), r2(LY.H / 72)], pieces: lyDescribe(),
            colours: layoutUsesColor() ? "each piece can have its own colour" : "everything prints in the one ink",
            fonts: (LY.fonts || []).map(f => f.label || f.key), shapes: ["line", "ring", "frame", "star", "dot", "block"],
            templates: studioTemplates().map(t => t.name)};
  },

  async make_design({location, pieces, arrange}){
    if(!(pieces || []).length) throw new Error("No pieces given.");
    await lyOpen(location);
    const logo = LY.items.find(i => i.type === "art");
    if(logo?._uploading){ try{ await logo._uploading; }catch(e){ closeLayout(); throw e; } }
    const hasText = pieces.some(p => p.type === "text" && (p.text || "").trim());
    const flow = [], around = [], extra = [];
    for(const p of pieces){
      if(p.type === "logo"){
        if(!logo){ closeLayout(); throw new Error(`${locName(location)} has no logo yet - place_art first, or add it as type 'art' with the attachment id.`); }
        const it = {...logo};
        if(hasText) it.w = Math.min(LY.W * (arrange === "row" ? 0.45 : 0.8), LY.H * (arrange === "row" ? 0.8 : 0.5) / studioArtAspect(it));
        flow.push(it);
      } else if(p.type === "art"){
        const f = A.files[p.file];
        if(!f){ closeLayout(); throw new Error(`No attachment "${p.file}".`); }
        flow.push(await lyArt(f));
      } else if(p.type === "text"){
        if(!(p.text || "").trim()) continue;
        const it = studioNewText(String(p.text), Math.max(10, LY.H * (TSIZE[p.size] || TSIZE.medium)));
        Object.assign(it, {font: await lyFont(p.font), bold: !!p.bold, italic: !!p.italic,
                           curve: clamp(p.curve, -100, 100), spacing: clamp(p.spacing, 0, 400), color: "#000000", pms: null});
        await lyColor(it, p.color);
        flow.push(it);
      } else if(p.type === "shape"){
        (["ring", "frame"].includes(p.shape) ? around : extra).push(p);
        if(!["ring", "frame"].includes(p.shape)) flow.push({_shape: p});
      }
    }
    LY.items = flow.filter(x => !x._shape);
    await lyFonts();
    // Lay the pieces out in a stack (or a row), then centre the group.
    const gap = (arrange === "row" ? LY.W : LY.H) * 0.05;
    let span = 0, cross = 0;
    const placed = [];
    for(const x of flow){
      let it = x;
      if(x._shape){
        const gw = Math.max(0, ...placed.map(q => { const b = studioBox(q); return b.x1 - b.x0; }));
        it = lyShape(x._shape.shape, gw, 0); await lyColor(it, x._shape.color);
      }
      it.x = 0; it.y = 0;
      const b = studioBox(it), w = b.x1 - b.x0, h = b.y1 - b.y0;
      if(arrange === "row"){ it.x = span - b.x0; it.y = -(b.y0 + b.y1) / 2; span += w + gap; cross = Math.max(cross, h); }
      else { it.y = span - b.y0; it.x = -(b.x0 + b.x1) / 2; span += h + gap; cross = Math.max(cross, w); }
      placed.push(it);
    }
    let x0 = 1e9, y0 = 1e9, x1 = -1e9, y1 = -1e9;
    for(const it of placed){ const b = studioBox(it); x0 = Math.min(x0, b.x0); y0 = Math.min(y0, b.y0); x1 = Math.max(x1, b.x1); y1 = Math.max(y1, b.y1); }
    for(const it of placed){ it.x += LY.W / 2 - (x0 + x1) / 2; it.y += LY.H / 2 - (y0 + y1) / 2; }
    const back = [];
    for(const p of around){ const s = lyShape(p.shape, x1 - x0, y1 - y0); await lyColor(s, p.color); back.push(s); }
    LY.items = [...back, ...placed];
    if(!LY.items.length){ closeLayout(); throw new Error("Nothing to put on - add some text or art."); }
    studioPush(); studioFitAll();
    return {...await lyApply(location), pieces: lyDescribe()};
  },

  async edit_design({location, changes}){
    await lyOpen(location);
    if(!LY.items.length){ closeLayout(); throw new Error(`${locName(location)} has no design yet - use make_design.`); }
    studioPush();
    const del = [];
    for(const c of changes || []){
      const it = LY.items[c.index];
      if(!it){ closeLayout(); throw new Error(`No piece ${c.index}. Pieces: ${JSON.stringify(lyDescribe())}`); }
      if(c.delete){ del.push(c.index); continue; }
      if(it.type === "text"){
        if(c.text != null) it.text = String(c.text);
        if(c.font) it.font = await lyFont(c.font);
        if(c.bold != null) it.bold = !!c.bold;
        if(c.italic != null) it.italic = !!c.italic;
        if(c.curve != null) it.curve = clamp(c.curve, -100, 100);
        if(c.spacing != null) it.spacing = clamp(c.spacing, 0, 400);
      }
      if(c.color && it.type !== "art") await lyColor(it, c.color);
      if(c.scale){
        const k = clamp(c.scale, 0.2, 5);
        if(it.size) it.size *= k; if(it.w) it.w *= k; if(it.h) it.h *= k;
        if(it.stroke && it.type === "shape" && it.shape !== "line") it.stroke *= Math.sqrt(k);
      }
      if(c.nudge){
        const st = 0.05;
        if(c.nudge === "left") it.x -= LY.W * st; if(c.nudge === "right") it.x += LY.W * st;
        if(c.nudge === "up") it.y -= LY.H * st;   if(c.nudge === "down") it.y += LY.H * st;
      }
    }
    for(const i of del.sort((a, b) => b - a)) LY.items.splice(i, 1);
    await lyFonts();
    LY.items.forEach(studioKeepIn);
    if(!LY.items.length){ closeLayout(); removeArtFromSlot(lyLoc(location)); await sleep(150); return `Everything removed from ${locName(location)}.`; }
    return {...await lyApply(location), pieces: lyDescribe()};
  },

  async use_template({location, template, texts}){
    await lyOpen(location);
    const list = studioTemplates(), want = String(template || "").toLowerCase();
    const t = list.find(x => x.name.toLowerCase() === want) || list.find(x => x.name.toLowerCase().includes(want) || want.includes(x.name.toLowerCase()));
    if(!t){ closeLayout(); throw new Error(`No template "${template}". Templates: ${list.map(x => x.name).join(", ")}`); }
    studioPush();
    LY.items = t.make().map(it => ({...it}));
    const tx = LY.items.filter(i => i.type === "text");
    (texts || []).forEach((s, k) => { if(tx[k] && s != null) tx[k].text = String(s); });
    LY.items = LY.items.filter(i => i.type !== "text" || (i.text || "").trim());
    await lyFonts(); studioFitAll();
    return {...await lyApply(location), pieces: lyDescribe(),
            note: tx.length > (texts || []).length ? "Some template lines still have placeholder text - fill them with edit_design." : undefined};
  },

  async clear_inside({location, mode}){
    const sl = needArt(location);
    if(!sl.koSrc) throw new Error("This art has no removed background to adjust (only pictures whose background was taken out have this).");
    await setClearInner(location, mode === "clear"); await settle();
    return {...artInfo(location), inner_white: mode === "clear" ? "cleared (item shows through)" : "prints"};
  },

  async hide_color({location, n, hidden}){
    needArt(location);
    if(!(typeof mcUsesSets === "function" && mcUsesSets())) throw new Error("This item doesn't list the logo's colours separately.");
    const e = mcSets().find(x => x.ids.includes(location));
    const ink = e?.set?.inks?.[(Number(n) || 0) - 1];
    if(!ink) throw new Error(`No colour ${n}. Colours: ${JSON.stringify(artInfo(location).colors || [])}`);
    const want = hidden !== false;
    if(!!ink.hidden !== want) toggleMcHidden(e.id, n - 1);
    await sleep(250);
    return artInfo(location);
  },

  async get_state(){
    await catalog();
    if(!S.prod) return {item: null, note: "No item open - use find_items and open_item."};
    const mode = inkMode();
    return {
      item: {id: S.pid, name: itemName(S.pid), prints: method(S.prod),
             inks: mode === "one" ? "one PANTONE ink" : mode === "multi" ? "full colour; the logo's colours can be matched to PANTONEs"
                 : "full colour (no ink to pick)",
             lifestyle_photo: !!S.prod.lifestyle_assets},
      colors: pickers().map(({_row, ...p}) => p),
      sides: sidesInfo(),
      colorways: colorways(),
      background_4cp: await bgInfo(),
      locations: (S.prod.slots || []).map(s => artInfo(s.id)),
      ink: mode === "one" ? (SP.ink?.name || null) : undefined,
      warnings: (typeof artRiskSummary === "function" ? artRiskSummary() : []),
      open_dialog: openDialog(),
      attached_files: Object.entries(A.files).map(([id, f]) => ({id, name: f.name})),
    };
  },

  async find_items({query}){
    const all = await catalog();
    const words = String(query || "").toLowerCase().split(/[^a-z0-9.]+/).filter(Boolean);
    const score = p => {
      const name = String(p.name || p.display_label || p.label || "");
      const initials = name.replace(/^This Is Fast\s+/i, "").split(/\s+/).filter(w => /^[a-z]/i.test(w)).map(w => w[0]).join("");
      const hay = [p.id, name, p.material_label, p.printing, p.shape, p.fits, initials, initials.slice(0, 2), "tif this is fast"].join(" ").toLowerCase();
      return words.reduce((n, w) => n + (hay.includes(w) ? (String(p.id).toLowerCase().startsWith(w) ? 3 : 1) : 0), 0);
    };
    const hits = all.map(p => [score(p), p]).filter(x => x[0] > 0).sort((a, b) => b[0] - a[0]).slice(0, 15);
    if(!hits.length) return {matches: all.filter(p => !p.coming_soon).map(p => ({id: p.id, name: p.name})),
                             note: "Nothing matched those words; these are all the items."};
    return {matches: hits.map(([, p]) => p.coming_soon ? {id: p.id, name: p.name, coming_soon: true}
                                                       : {id: p.id, name: p.name, prints: method(p), fits: p.fits || undefined})};
  },

  async open_item({id}){
    const all = await catalog();
    const lite = all.find(x => x.id === id);
    if(!lite) throw new Error(`No item "${id}" on this site. Use find_items.`);
    if(lite.coming_soon) throw new Error(`${lite.name} is coming soon and can't be built yet.`);
    if(!(S.ap || []).some(x => x.id === id)) throw new Error(`"${id}" can't be opened here.`);
    const sel = $("psel"); sel.value = id;
    await onProduct();
    if(typeof setV === "function") setV("proof");
    try{ history.replaceState(null, "", "/" + id + location.search); }catch(e){}
    await sleep(500);
    try{ closeTutorial(); }catch(e){}
    try{ custStep(1); }catch(e){}
    return TOOLS.get_state();
  },

  async set_color({picker, color}){
    const ps = pickers();
    const p = ps.find(x => x.picker.toLowerCase() === String(picker).toLowerCase()) || (ps.length === 1 ? ps[0] : null)
           || ps.find(x => /body|pen/i.test(x.picker) && /body|color|colour|neoprene|canvas|foam|pen/i.test(picker));
    if(!p) throw new Error(`No colour picker "${picker}". Pickers: ${ps.map(x => x.picker).join(", ")}`);
    const want = String(color).toLowerCase().trim();
    const el = [...document.querySelectorAll(`#${p._row} .cc`)];
    const hit = el.find(e => e.title.toLowerCase() === want) || el.find(e => e.title.toLowerCase().includes(want))
             || el.find(e => want.includes(e.title.toLowerCase()));
    if(!hit) throw new Error(`"${color}" isn't offered for ${p.picker}. Options: ${p.options.join(", ")}`);
    hit.click(); await sleep(250);
    return `${p.picker} is now ${hit.title}.`;
  },

  async add_colorway(){
    if(!(typeof varEligible === "function" && varEligible())) throw new Error("This item takes one colour at a time (pens: use the 'Pen colors on this order' list).");
    varAdd(); await sleep(300);
    return {colorways: colorways(), note: "Now editing the new colorway: set its colours with set_color."};
  },

  async switch_colorway({n}){
    if(!(typeof varOn === "function" && varOn())) throw new Error("There's only one colorway.");
    const i = (Number(n) || 1) - 1;
    if(!VAR.list[i]) throw new Error(`There are ${VAR.list.length} colorways.`);
    varSwitch(i); await sleep(300);
    return {colorways: colorways()};
  },

  async set_sides({mode}){
    if(!(typeof hasSidePair === "function" && hasSidePair())) throw new Error("This item doesn't have Side 1 / Side 2.");
    if(typeof imprintOne === "function" && imprintOne()) throw new Error("This item prints on one side only - use set_print_side.");
    const was = window.confirm; window.confirm = () => true;          // the page asks before replacing art
    try{ setSidesMode(mode === "diff" ? "diff" : "same"); } finally { window.confirm = was; }
    await sleep(200);
    return sidesInfo();
  },

  async set_print_side({side}){
    if(!(typeof imprintOne === "function" && imprintOne())) throw new Error("This item isn't a one-location item - use set_sides.");
    setImprintSide(side === "side2" ? "side2" : "side1"); await sleep(250);
    return sidesInfo();
  },

  async place_art({location, file}){
    needLoc(location);
    const f = A.files[file];
    if(!f) throw new Error(`No attachment "${file}". Attached: ${Object.keys(A.files).join(", ") || "none"}`);
    const before = S.slots[location];
    try{ custStep(2); }catch(e){}
    S.ut = location; S.ub = false;
    await onFile({files: [f], value: ""});
    for(let k = 0; k < 120; k++){                                   // up to a minute (vector art goes to the server)
      const sl = S.slots[location];
      if(sl?.img && sl !== before && !sl.isDefault) break;
      if(document.querySelector("#art-reject:not([style*='none']), .art-reject.vis")) break;
      await sleep(500);
    }
    await settle();
    const sl = S.slots[location];
    for(const t of (typeof pairedIds === "function" ? pairedIds(location) : [location])) if(S.slots[t]) S.slots[t]._askName = f.name;
    if(!sl?.img || sl.isDefault){
      const why = ($("fb")?.textContent || "").trim();
      throw new Error("The art didn't go on" + (why ? `: ${why}` : "."));
    }
    let white = null;
    if($("aw-scrim")){ $("aw-scrim").remove(); white = "This art has white in it: ask whether the white prints white or is cut out (the item shows through), then set_white."; }
    return {...artInfo(location), ink: inkMode() === "one" ? (SP.ink?.name || null) : undefined,
            note: white, warnings: (typeof artRiskSummary === "function" ? artRiskSummary() : [])};
  },

  async remove_art({location}){
    needArt(location);
    removeArtFromSlot(location); await sleep(150);
    return `Art removed from ${locName(location)}.`;
  },

  async suggest_inks({color, count}){
    if(!SP.loaded && typeof loadPmsLibrary === "function") await loadPmsLibrary();
    const c = String(color || "").toLowerCase().trim();
    const hex = /^#?[0-9a-f]{6}$/i.test(c) ? (c[0] === "#" ? c : "#" + c)
              : (FAMILY[c] || FAMILY[Object.keys(FAMILY).filter(k => c.includes(k)).sort((a, b) => b.length - a.length)[0]]);
    if(!hex) throw new Error(`No colour family "${color}". Try a plain colour word (yellow, navy, kelly green) or a hex.`);
    const n = Math.max(3, Math.min(8, Number(count) || 6));
    const L = labOf(hex);
    const lib = (SP.library || []).filter(x => /^PANTONE [0-9A-Za-z ]+ C$/.test(x.name) && /^#[0-9a-f]{6}$/i.test(x.hex || "")
                                             && !/^PANTONE 1[0-9]{4} C$/.test(x.name));   // the plain chips, not the 10000s
    const scored = lib.map(x => { const m = labOf(x.hex); return [((m[0] - L[0]) ** 2 + (m[1] - L[1]) ** 2 + (m[2] - L[2]) ** 2), x]; })
                      .sort((a, b) => a[0] - b[0]);
    // Spread across the family: skip near-duplicates of a pick already made.
    const out = [];
    for(const [, x] of scored){
      if(out.length >= n) break;
      const m = labOf(x.hex);
      if(out.some(o => { const q = labOf(o.hex); return (q[0] - m[0]) ** 2 + (q[1] - m[1]) ** 2 + (q[2] - m[2]) ** 2 < 40; })) continue;
      out.push({name: x.name, hex: x.hex});
    }
    if(/^(white)$/.test(c)) out.unshift({name: "White", hex: "#FFFFFF"});
    log("ask-m a ask-swm", `<div class="ask-swh">Pick one:</div>` + swatchesHTML(out));
    return {shown_to_customer: out.map(o => o.name),
            note: "These are on screen as swatches the customer can click; ask them to choose (or choose for them if they said they don't mind)."};
  },

  async set_inks({location, inks}){
    const sl = needArt(location);
    const mode = inkMode();
    if(!SP.loaded && typeof loadPmsLibrary === "function") await loadPmsLibrary();
    const find = n => {
      if(n == null) return null;
      const s = String(n).trim();
      if(/^white$/i.test(s)) return _findInk("White") || {name: "White", hex: "#FFFFFF"};
      return _findInk(s) || _findInk("PANTONE " + s.replace(/^(pms|pantone)\s*/i, "")) || null;
    };
    if(mode === "one"){
      const k = find((inks || []).find(Boolean));
      if(!k) throw new Error(`Unknown ink "${(inks || [])[0]}". Use a PANTONE name like "PANTONE 186 C".`);
      setScreenPrintInk(k.name, k.hex); await sleep(200);
      return `Ink is now ${k.name}.`;
    }
    if(mode !== "multi" || !sl.mc?.inks?.length) throw new Error("This item prints full colour - there's no ink to pick.");
    const e = mcSets().find(x => x.ids.includes(location));
    if(!e) throw new Error("No ink list for that location.");
    const bad = [], done = [];
    (inks || []).forEach((n, i) => {
      if(n == null || i >= e.set.inks.length) return;
      const k = find(n); if(!k){ bad.push(n); return; }
      setMcInk(e.id, i, k.name, k.hex); done.push(`${i + 1}: ${k.name}`);
    });
    await sleep(250);
    if(bad.length && !done.length) throw new Error(`Unknown ink(s): ${bad.join(", ")}`);
    return {set: done, unknown: bad.length ? bad : undefined, location: artInfo(location)};
  },

  async set_white({location, mode}){
    const sl = needArt(location);
    if(!sl.mc?.hasWhite) throw new Error("There's no white in this art to print or cut out.");
    setArtWhiteMode(sl.mc, mode === "ink" ? "ink" : "cut"); $("aw-scrim")?.remove(); await sleep(200);
    return artInfo(location);
  },

  async set_art_size({location, fit, width_in, height_in, percent}){
    const sl = needArt(location);
    S.act = location;
    if(fit || (!width_in && !height_in && !percent)) fitZone();
    else{
      let k = 1;
      if(width_in) k = width_in / (artPrintedWidth(location) || width_in);
      else if(height_in) k = height_in / (artPrintedHeight(location) || height_in);
      else if(percent) k = percent / 100;
      sl.sc = clampSc(location, (sl.sc || 1) * k);
      const o = clampOxy(location, sl.ox || 0, sl.oy || 0); sl.ox = o.ox; sl.oy = o.oy;
      updateAEPanel(); R();
    }
    await sleep(150);
    const out = artInfo(location);
    if(width_in && out.width_in && out.width_in < width_in - 0.05) out.note = "That's as big as fits in the print area.";
    return out;
  },

  async move_art({location, to, amount}){
    const sl = needArt(location);
    const z = S.zones[location], a = Math.max(0, Math.min(1, amount ?? 0.1));
    if(to === "center"){ sl.ox = 0; sl.oy = 0; }
    else{
      const dx = to === "left" ? -1 : to === "right" ? 1 : 0, dy = to === "up" ? -1 : to === "down" ? 1 : 0;
      sl.ox = (sl.ox || 0) + dx * a * z.w * S.gW; sl.oy = (sl.oy || 0) + dy * a * z.h * S.gH;
    }
    const o = clampOxy(location, sl.ox, sl.oy); sl.ox = o.ox; sl.oy = o.oy;
    R(); await sleep(100);
    return `Moved ${to}.`;
  },

  async rotate_art({location, degrees}){
    const sl = needArt(location);
    sl.rot = (Number(degrees) || 0) * Math.PI / 180;
    afterRotate(location); R(); await sleep(100);
    return artInfo(location);
  },

  async set_background(i){
    if(!(typeof bgdOn === "function" && bgdOn())) throw new Error("Only the 4CP items have a printed background.");
    try{ custStep(1); }catch(e){}
    const was = BGD.seq;
    const hexOk = h => /^#?[0-9a-f]{6}$/i.test(String(h || "")) ? (String(h)[0] === "#" ? String(h) : "#" + h).toUpperCase() : null;
    if(i.type === "finished"){
      const f = A.files[i.file];
      if(!f) throw new Error(`No attachment "${i.file}".`);
      S.ub = true; S.ut = null;
      await onFile({files: [f], value: ""});
      for(let k = 0; k < 120 && !(S.bleed?.img && !S.bleed._bgd); k++) await sleep(500);
      if(!(S.bleed?.img && !S.bleed._bgd)) throw new Error("The finished design didn't go on: " + (($("fb")?.textContent || "").trim() || "check the file"));
      await sleep(300); bgdSync();
      return {background: "finished design for the whole item", note: "If it's laid out wrongly, they can download the template from the Background step."};
    }
    if(BGD.finished) bgdUnfinish();
    if(i.type === "solid"){
      if(i.pms){
        if(!SP.loaded) await loadPmsLibrary();
        const k = _findInk(i.pms) || _findInk("PANTONE " + String(i.pms).replace(/^(pms|pantone)\s*/i, ""));
        if(!k) throw new Error(`Unknown PANTONE "${i.pms}".`);
        bgdPmsPick(k.name, k.hex);
      } else {
        const h = hexOk(i.hex); if(!h) throw new Error("Give a hex colour like #1C4FD0 (or a pms).");
        bgdType("solid"); bgdSolid(h);
      }
    } else if(i.type === "gradient"){
      const cs = (i.colors || []).map(hexOk).filter(Boolean);
      if(cs.length < 2) throw new Error("A gradient needs two hex colours.");
      bgdType("gradient"); BGD.base.stops = cs.slice(0, 2); BGD.base.dir = i.direction || BGD.base.dir || "down"; bgdRender(); bgdBuild();
    } else if(i.type === "pattern"){
      const files = await stockList();
      const want = String(i.pattern || "").toLowerCase();
      const f = files.find(x => x.replace(/\.(jpg|jpeg|png)$/i, "").toLowerCase() === want)
             || files.find(x => x.toLowerCase().includes(want));
      if(!f) throw new Error(`No pattern "${i.pattern}". Patterns: ${files.map(x => x.replace(/\.(jpg|jpeg|png)$/i, "")).join(", ")}`);
      bgdType("stock"); bgdStock(f);
    } else if(i.type === "picture"){
      const f = A.files[i.file]; if(!f) throw new Error(`No attachment "${i.file}".`);
      bgdType("image"); await bgdPicture({files: [f], value: ""});
    } else if(i.type === "none"){
      bgdType("none");
    }
    if(i.side2) bgdSide2(i.side2 === "upside_down" ? "flip" : "same");
    if(i.bottom === "solid"){ bgdBottom("solid"); const h = hexOk(i.bottom_hex); if(h) bgdBottomHex(h); }
    else if(i.bottom === "same") bgdBottom("same");
    // Wait for the server to lay it out.
    for(let k = 0; k < 120; k++){
      await sleep(400);
      const st = ($("bgd-status")?.textContent || "");
      if(BGD.seq !== was && st.includes("✓")) break;
      if(st.startsWith("⚠")) throw new Error(st.replace(/^⚠\s*/, ""));
    }
    return {background: await bgInfo()};
  },

  async get_preview(){
    if(S.view !== "proof") setV("proof");
    R(); await sleep(400);
    const k = Math.min(1, 1000 / Math.max(cv.width, cv.height));
    const c = document.createElement("canvas"); c.width = Math.round(cv.width * k); c.height = Math.round(cv.height * k);
    const g = c.getContext("2d"); g.fillStyle = "#fff"; g.fillRect(0, 0, c.width, c.height); g.drawImage(cv, 0, 0, c.width, c.height);
    return [{type: "image", source: {type: "base64", media_type: "image/jpeg", data: c.toDataURL("image/jpeg", 0.82).split(",")[1]}},
            {type: "text", text: "The mockup as it shows now."}];
  },

  async show_lifestyle(){
    if(!S.prod?.lifestyle_assets) throw new Error("This item has no lifestyle photo yet.");
    lifestyleOpen(); return "The lifestyle photo is open on screen (it has a Download button).";
  },

  async download_virtual(){ dlProof(); return "The virtual picture is downloading."; },

  async go_to_review(){
    custStep(3); await sleep(200);
    return "Step 3 (Review & send) is open: the customer presses 'Get my proof' to download the proof PDF.";
  },
};

// After an upload the page opens its art editor (clients see its Colors
// view). The assistant has done what that's for, so close it once it's open.
async function settle(){
  for(let k = 0; k < 12; k++){
    await sleep(400);
    const ae = typeof AE !== "undefined" && AE.open;
    const ly = $("ly-scrim")?.classList.contains("vis");
    if(ae){ try{ await aeDone(); }catch(e){ try{ await closeArtEditor(); }catch(_){} } continue; }
    if(ly && k >= 5){ try{ closeLayout(); }catch(e){} continue; }
    if(!ly && k >= 4) break;
  }
  if(typeof AE !== "undefined" && !AE.open && typeof LY !== "undefined" && LY.inAE) LY.inAE = false;
}

// A dialog waiting on the client (Claude is told, so it doesn't talk over it).
function openDialog(){
  const d = document.querySelector("#ap-scrim.vis, #rd-scrim.vis, #oc-scrim.vis, #ae-scrim.vis, #ly-scrim.vis, "
                                   + "#tut-bg.open, #export-modal.open, #aw-scrim, #bleed-dim-modal");
  if(!d) return null;
  const known = {"ap-scrim": "Pick the art (choose the art out of the file they sent)", "ly-scrim": "Design studio",
                 "tut-bg": "the getting-started guide", "export-modal": "Get your proof (the proof download)",
                 "bleed-dim-modal": "the background picture is the wrong shape for this item"};
  return known[d.id] || d.querySelector("h3, .oc-hd, b")?.textContent || "a dialog is open on screen";
}

// ── switched on only when the server has a key ───────────────────────────
async function boot(){
  try{
    const j = await (await fetch("/api/assistant/status")).json();
    if(!j.enabled) return;
  }catch(e){ return; }
  A.enabled = true;
  build();
  $("ask-btn")?.classList.add("vis");
}
if(document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot); else boot();
window.ASK = A;  // for debugging
})();
