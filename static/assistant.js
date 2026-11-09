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
#ask-mic{width:38px;padding:0;display:none;align-items:center;justify-content:center;color:var(--burgundy)}
#ask-mic svg{width:17px;height:17px}
#ask-mic.rec{background:#c62828;border-color:#c62828;color:#fff;animation:askmic 1.2s ease-in-out infinite}
@keyframes askmic{0%,100%{box-shadow:0 0 0 0 rgba(198,40,40,.45)}50%{box-shadow:0 0 0 7px rgba(198,40,40,0)}}
#ask-text.rec{border-color:#c62828}
#ask-mic.conv{background:#c62828;border-color:#c62828;color:#fff;opacity:.75}
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
  p.innerHTML = `<div class="ask-head"><img class="ask-av-lg" src="/static/img/gweg.png" alt=""><div class="ask-name"><small>chatting with:</small><b>Gweg</b></div><div class="ask-hbtn"><button id="ask-vo" onclick="askVoice()" title="Gweg reads his answers out loud when you talk to him" style="display:none">Voice on</button><button onclick="askNew()" title="Start over">New chat</button><button onclick="askToggle(false)">Close</button></div></div>
    <div id="ask-log"></div><div class="ask-pend" id="ask-pend"></div>
    <div class="ask-in"><button onclick="document.getElementById('ask-file').click()" title="Attach artwork">Attach</button>
      <textarea id="ask-text" rows="1" placeholder="e.g. a navy Kolder Kaddy with this logo in white"></textarea>
      <button id="ask-mic" onclick="askMic()" title="Talk with Gweg" aria-label="Talk with Gweg"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="2" width="6" height="12" rx="3"/><path d="M5 10a7 7 0 0 0 14 0M12 17v4M8 21h8"/></svg></button>
      <button class="go" id="ask-go" onclick="askSend()">Send</button>
      <input type="file" id="ask-file" multiple accept=".png,.jpg,.jpeg,.svg,.pdf,.ai,.eps,.tif,.tiff,.webp,.gif" style="display:none"></div>`;
  document.body.appendChild(p);
  const t = $("ask-text");
  t.addEventListener("keydown", e => {
    if(MIC.conv && !e.isComposing && e.key.length === 1) convEnd();    // typing ends the hands-free talk
    if(e.key === "Enter" && !e.shiftKey){ e.preventDefault(); askSend(); }
  });
  t.addEventListener("input", () => { t.style.height = "auto"; t.style.height = Math.min(140, t.scrollHeight) + "px"; });
  $("ask-file").addEventListener("change", e => { addFiles(e.target.files); e.target.value = ""; });
  p.addEventListener("dragover", e => { e.preventDefault(); p.classList.add("drag"); });
  p.addEventListener("dragleave", () => p.classList.remove("drag"));
  p.addEventListener("drop", e => { e.preventDefault(); p.classList.remove("drag"); addFiles(e.dataTransfer.files); });
  if(MIC.ok) $("ask-mic").style.display = "inline-flex";
  if(MIC.ok && VO.ok){ $("ask-vo").style.display = ""; voUi(); }
  hello();
}

// ── talk instead of typing (the browser's own speech recognition) ──────────
// Chrome, Edge and Safari, desktop and phone; Firefox has none, so the mic
// button just doesn't show there.
// Tapping the mic starts a hands-free conversation: Gweg listens, sends when
// the customer stops talking, answers out loud, then listens again - until
// they tap the mic, say "stop" / "bye", type, close the chat, or go quiet.
const MIC = {ok: !!(window.SpeechRecognition || window.webkitSpeechRecognition), rec: null, on: false, conv: false, misses: 0, used: false};
const PH = "e.g. a navy Kolder Kaddy with this logo in white";
function micStop(){ if(MIC.rec){ try{ MIC.rec.stop(); }catch(e){} } }
function micUi(state){                // "listen", "busy", "talk" (Gweg speaking) or "off"
  MIC.on = state === "listen";
  const m = $("ask-mic"), t = $("ask-text");
  m?.classList.toggle("rec", state === "listen");
  m?.classList.toggle("conv", state === "busy" || state === "talk");
  t?.classList.toggle("rec", state === "listen");
  if(m) m.title = state === "off" ? "Talk with Gweg" : state === "talk" ? "Cut in" : "Stop talking with Gweg";
  if(t) t.placeholder = {listen: "Listening… just talk (tap the mic to stop)", busy: "Gweg is on it…",
                         talk: "Gweg is talking - tap the mic to cut in", off: PH}[state];
}
// ── Gweg's voice (the browser's own text-to-speech, free) ─────────────────
// When the customer talks to him, he answers out loud too; typing gets a
// quiet answer. "Voice off" in the header mutes him for good on this browser.
const VO = {ok: "speechSynthesis" in window && "SpeechSynthesisUtterance" in window, voice: null,
            muted: (() => { try{ return localStorage.getItem("gweg-voice") === "off"; }catch(e){ return false; } })()};
const VO_PICK = [/Microsoft (Andrew|Guy|Christopher|Eric|Davis|Brian) Online/i, /Microsoft (Andrew|Guy|Christopher|Eric|Davis|Brian)/i,
                 /^(Aaron|Evan|Nathan|Tom|Alex)\b/i, /Google UK English Male/i, /^(Daniel|Arthur|Oliver)\b/i,
                 /\bmale\b/i, /Google US English/i];
function voPick(){
  if(!VO.ok) return null;
  const vs = speechSynthesis.getVoices().filter(v => /^en(-|_|$)/i.test(v.lang));
  for(const re of VO_PICK){ const v = vs.find(x => re.test(x.name)); if(v) return v; }
  return vs.find(v => /en-US/i.test(v.lang)) || vs[0] || null;
}
if(VO.ok){ VO.voice = voPick(); speechSynthesis.addEventListener?.("voiceschanged", () => { VO.voice = voPick(); }); }
function voUi(){ const b = $("ask-vo"); if(b){ b.textContent = VO.muted ? "Voice off" : "Voice on"; b.style.opacity = VO.muted ? ".6" : ""; } }
function voStop(){ if(VO.ok) try{ speechSynthesis.cancel(); }catch(e){} }
window.askVoice = function(){
  VO.muted = !VO.muted; voUi();
  try{ localStorage.setItem("gweg-voice", VO.muted ? "off" : "on"); }catch(e){}
  if(VO.muted) voStop();
};
function voSay(text, force){
  if(!VO.ok || VO.muted || !(A.spoken || force)) return;
  const plain = String(text)
    .replace(/https?:\/\/\S+/g, "the link")
    .replace(/[*_`#>|]+/g, "")
    .replace(/\bPMS\b/g, "P M S").replace(/\b4CP\b/gi, "four C P").replace(/\boz\b/gi, "ounce")
    .replace(/\s+/g, " ").trim();
  if(!plain) return;
  // One sentence per utterance: Chrome cuts long ones off after ~15 seconds.
  for(const part of plain.match(/[^.!?]+[.!?]*\s*/g) || [plain]){
    const u = new SpeechSynthesisUtterance(part.trim());
    if(VO.voice){ u.voice = VO.voice; u.lang = VO.voice.lang; }
    u.rate = 1.05; u.pitch = 0.95;
    speechSynthesis.speak(u);
  }
}

function convEnd(say){
  MIC.conv = false; MIC.misses = 0;
  micStop(); micUi("off");
  if(say) voSay(say, true);
}
const STOP_WORDS = /^(stop|bye|goodbye|good bye|bye bye|that's all|that is all|that's it|i'm done|im done|never ?mind|nevermind|quit|exit|cancel)[.!]?$/i;
function listen(){
  if(!MIC.conv || A.busy || !A.open) return;
  voStop();
  const R = window.SpeechRecognition || window.webkitSpeechRecognition;
  const r = new R();
  r.lang = navigator.language || "en-US";
  r.continuous = false; r.interimResults = true;     // ends by itself when they pause
  const t = $("ask-text");
  const base = t.value.trim() ? t.value.trim() + " " : "";
  let done = "", live = "", blocked = false;
  r.onresult = e => {
    live = "";
    for(let i = e.resultIndex; i < e.results.length; i++){
      const txt = e.results[i][0].transcript;
      if(e.results[i].isFinal) done += txt; else live += txt;
    }
    t.value = (base + done + live).replace(/\s+/g, " ").replace(/^\s/, "");
    t.dispatchEvent(new Event("input"));
  };
  r.onerror = e => {
    if(e.error === "not-allowed" || e.error === "service-not-allowed"){
      blocked = true;
      log("ask-m e", "I can't hear you - the browser blocked the microphone. Click the mic or lock icon by the web address, allow the microphone, and try again. (Typing works too!)");
    } else if(e.error === "audio-capture"){
      blocked = true;
      log("ask-m e", "I couldn't find a microphone on this device. Typing works too!");
    }
  };
  r.onend = () => {
    MIC.rec = null;
    if(!MIC.conv){ micUi("off"); return; }
    if(blocked) return convEnd();
    const said = (done || live).trim();
    if(!said){
      if(++MIC.misses >= 2){ convEnd(); log("ask-hint", "I'll stop listening for now - tap the mic when you want to talk again."); return; }
      return listen();
    }
    MIC.misses = 0;
    if(STOP_WORDS.test(said)){ t.value = ""; t.dispatchEvent(new Event("input")); return convEnd("Talk soon!"); }
    MIC.used = true; micUi("busy");
    askSend();
  };
  try{ r.start(); MIC.rec = r; micUi("listen"); }catch(e){ convEnd(); }
}
// After Gweg's answer: wait for him to finish talking, then listen again.
function convNext(){
  if(!MIC.conv) return;
  if(!A.open) return convEnd();
  micUi(VO.ok && !VO.muted ? "talk" : "busy");
  const wait = () => {
    if(!MIC.conv || A.busy) return;
    if(VO.ok && (speechSynthesis.speaking || speechSynthesis.pending)) return setTimeout(wait, 250);
    setTimeout(listen, 250);
  };
  setTimeout(wait, 400);
}
window.askMic = function(){
  if(!MIC.ok) return;
  if(MIC.conv){
    // Cut in while he's talking; otherwise this ends the conversation.
    if(!A.busy && !MIC.on && VO.ok && (speechSynthesis.speaking || speechSynthesis.pending)){ voStop(); return listen(); }
    return convEnd();
  }
  voStop();
  if(VO.ok && !VO.muted) try{ speechSynthesis.speak(new SpeechSynthesisUtterance("")); }catch(e){}   // unlocks speech on iPhone
  MIC.conv = true; MIC.misses = 0;
  listen();
};

function hello(){
  $("ask-log").innerHTML = `<div class="ask-row"><img class="ask-av" src="/static/img/gweg.png" alt=""><div class="ask-m a">Hi, I'm Gweg! I live in this website and have never once held a can, but I'm weirdly good at dressing them up. Tell me what you'd like and attach your logo (the Attach button or drop it here), and I'll build it while you watch. Ask me anything along the way.</div></div>
    <div class="ask-hint">${MIC.ok ? "Rather talk? Tap the mic and just chat with me - I'll talk back. " : ""}Try: "a red, a blue and a purple Kolder Kaddy with this logo, as big as it fits, in yellow" or "a 4CP Pocket Coolie with a navy background and this logo".</div>`;
}

window.askToggle = function(force){
  A.open = force ?? !A.open;
  if(!A.open){ voStop(); convEnd(); }
  $("ask-panel")?.classList.toggle("on", A.open);
  $("ask-btn")?.classList.toggle("on", A.open);
  document.body.classList.toggle("ask-open", A.open);
  try{ window.dispatchEvent(new Event("resize")); }catch(e){}
  if(A.open) setTimeout(() => $("ask-text")?.focus(), 50);
};
window.askNew = function(){
  if(A.busy) return;
  voStop(); convEnd(); A.spoken = false;
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
  if(MIC.on) micStop();
  const t = $("ask-text"); const text = t.value.trim();
  if(MIC.conv && !MIC.used) convEnd();         // they typed and pressed Send
  if(!text && !A.pending.length) return;
  A.spoken = !!MIC.used; MIC.used = false;      // answer out loud only when they talked
  voStop();
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
  if(A.spoken && VO.ok && !VO.muted)
    content.push({type: "text", text: "(Said out loud - your reply is read aloud: keep it short and easy to listen to, no lists.)"});
  A.msgs.push({role: "user", content});
  await run();
};
// A swatch clicked in the chat answers for the client.
window.askSay = function(text){
  if(A.busy) return;
  const t = $("ask-text"); if(!t) return;
  MIC.used = A.spoken;                              // a tap keeps the conversation's voice
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
      for(const b of blocks) if(b.type === "text" && b.text.trim()){ log("ask-m a", mdLite(b.text.trim())); voSay(b.text.trim()); }
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
    setTimeout(convNext, 0);
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
    go_to_review: "Going to Review & send", art_colors: "Looking at the art's colours",
    set_art_colors: "Choosing which colours print", get_design: `Reading the design on ${locName(i.location)}`,
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
  if(!(typeof bgBoardOk === "function" && bgBoardOk())) return undefined;
  const b = S.bleed || {};
  let type, out = {};
  if(b.img && b._isStockBg){ type = "pattern"; out.pattern = String(b._stockFile || "").replace(/\.(jpg|jpeg|png)$/i, ""); }
  else if(b.img && b._fromLayout) type = "designed in the background editor";
  else if(b.img) type = "uploaded full-bleed background";
  else if(S_FILL.mode === "solid"){ type = "solid"; out.hex = S_FILL.solid.hex; out.pms = S_FILL.solid.pms || undefined; }
  else if(S_FILL.mode === "gradient"){ type = "gradient"; out.colors = S_FILL.gradient.stops.map(x => x.hex); out.direction = S_FILL.gradient.dir; }
  else type = "none";
  return {type, ...out, patterns: (await stockList()).map(f => f.replace(/\.(jpg|jpeg|png)$/i, ""))};
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
const isBg = loc => String(loc || "").toLowerCase() === "background";
function lyLoc(location){
  if(isBg(location)){
    if(!(typeof bgBoardOk === "function" && bgBoardOk())) throw new Error("Only the 4CP items have a background to design.");
    return BG_SLOT;
  }
  needLoc(location);
  return (typeof sidesSame === "function" && sidesSame() && location === "side2") ? "side1" : location;
}
async function lyOpen(location){
  const id = lyLoc(location);
  if(lyBusy()) closeLayout();
  try{ custStep(id === BG_SLOT ? 1 : 2); }catch(e){}
  await openLayout(id, id === BG_SLOT ? {bg: true} : undefined); await sleep(200);
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
  if(isBg(location)) return {background: await bgInfo()};
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
function lyShape(shape, gw, gh, Z){
  Z = Z || {w: LY.W, h: LY.H};
  const s = Math.min(Z.w, Z.h), st = Math.max(1.5, s * 0.02);
  const b = {type: "shape", shape, color: "#000000", x: LY.W / 2, y: LY.H / 2, stroke: st};
  if(shape === "line") b.w = Math.max(Z.w * 0.3, gw * 0.7);
  else if(shape === "block") Object.assign(b, {w: Z.w * 0.5, h: Z.h * 0.12});
  else if(shape === "band") Object.assign(b, {shape: "block", w: Z.w * 1.3, h: Math.max(gh * 1.4, Z.h * 0.22)});
  else if(shape === "ring") b.w = Math.max(gw, gh) * 1.3 || s * 0.9;
  else if(shape === "frame") Object.assign(b, {w: (gw || Z.w * 0.7) * 1.15 + s * 0.06, h: (gh || Z.h * 0.6) * 1.2 + s * 0.06});
  else b.w = s * 0.12;                                     // star, dot
  return b;
}

// A 4CP background panel (Side 1, Side 2, bottom) on the whole-item board.
function lyZone(id){
  const z = S.prod?.bleed_zones?.[id];
  if(!z) throw new Error(`This item has no ${id} panel.`);
  return {cx: (z.x + z.w / 2) * LY.W, cy: (z.y + z.h / 2) * LY.H, w: z.w * LY.W, h: z.h * LY.H};
}
// Side 2 sits upside down on the print sheet, so it reads right on the item.
function lyTurn(it, from, to){
  it.x = to.cx - (it.x - from.cx); it.y = to.cy - (it.y - from.cy);
  it.rot = ((it.rot || 0) + 180) % 360;
  return it;
}
function lyBounds(items){
  let x0 = 1e9, y0 = 1e9, x1 = -1e9, y1 = -1e9;
  for(const it of items){ const b = studioBox(it); x0 = Math.min(x0, b.x0); y0 = Math.min(y0, b.y0); x1 = Math.max(x1, b.x1); y1 = Math.max(y1, b.y1); }
  return {x0, y0, x1, y1};
}
// Shrink a group to fit its panel (never grow), keeping it centred there.
function lyFitZone(items, Z, k){
  if(!items.length) return;
  const b = lyBounds(items.filter(it => !(it.type === "shape" && it.shape === "block" && it.w > Z.w)));
  const f = Math.min(1, (Z.w * k) / Math.max(1, b.x1 - b.x0), (Z.h * k) / Math.max(1, b.y1 - b.y0));
  for(const it of items){
    it.x = Z.cx + (it.x - Z.cx) * f; it.y = Z.cy + (it.y - Z.cy) * f;
    if(it.size) it.size *= f; if(it.w) it.w *= f; if(it.h) it.h *= f;
  }
}
function lyLogoFromSlot(){
  const sl = S.slots?.side1?.img ? S.slots.side1 : Object.values(S.slots || {}).find(x => x?.img);
  if(!sl) return null;
  return typeof layoutArtFromSlot === "function" ? layoutArtFromSlot(sl) : null;
}
// Lay pieces out top-to-bottom (or in a row) around the centre of zone Z.
async function lyBuild(pieces, arrange, Z, logo, location){
  const hasText = pieces.some(p => p.type === "text" && (p.text || "").trim());
  const flow = [], around = [];
  for(const p of pieces){
    if(p.type === "logo"){
      if(!logo) throw new Error(isBg(location) ? "There's no logo placed yet - place_art first, or add it as type 'art' with the attachment id."
                                              : `${locName(location)} has no logo yet - place_art first, or add it as type 'art' with the attachment id.`);
      const it = {...logo};
      it.w = hasText ? Math.min(Z.w * (arrange === "row" ? 0.45 : 0.8), Z.h * (arrange === "row" ? 0.8 : 0.5) / studioArtAspect(it))
                     : (it.w || Math.min(Z.w * 0.8, Z.h * 0.8 / studioArtAspect(it)));
      flow.push(it);
    } else if(p.type === "art"){
      const f = A.files[p.file];
      if(!f) throw new Error(`No attachment "${p.file}".`);
      const it = await lyArt(f);
      it.w = Math.min(Z.w * 0.6, Z.h * 0.6 / studioArtAspect(it));
      flow.push(it);
    } else if(p.type === "text"){
      if(!(p.text || "").trim()) continue;
      const it = studioNewText(String(p.text), Math.max(6, Z.h * (TSIZE[p.size] || TSIZE.medium)));
      Object.assign(it, {font: await lyFont(p.font), bold: !!p.bold, italic: !!p.italic, rot: 0,
                         curve: clamp(p.curve, -100, 100), spacing: clamp(p.spacing, 0, 400), color: "#000000", pms: null});
      await lyColor(it, p.color);
      flow.push(it);
    } else if(p.type === "shape"){
      if(["ring", "frame", "band"].includes(p.shape)) around.push(p); else flow.push({_shape: p});
    }
  }
  await Promise.all(flow.filter(i => i.type === "text").map(i => layoutEnsureFont(i.font, i.bold, i.italic)));
  const gap = (arrange === "row" ? Z.w : Z.h) * 0.05;
  let span = 0;
  const placed = [];
  for(const x of flow){
    let it = x;
    if(x._shape){
      const gw = Math.max(0, ...placed.map(q => { const b = studioBox(q); return b.x1 - b.x0; }));
      it = lyShape(x._shape.shape, gw, 0, Z); await lyColor(it, x._shape.color);
    }
    it.x = 0; it.y = 0;
    const b = studioBox(it), w = b.x1 - b.x0, h = b.y1 - b.y0;
    if(arrange === "row"){ it.x = span - b.x0; it.y = -(b.y0 + b.y1) / 2; span += w + gap; }
    else { it.y = span - b.y0; it.x = -(b.x0 + b.x1) / 2; span += h + gap; }
    placed.push(it);
  }
  const g = placed.length ? lyBounds(placed) : {x0: 0, y0: 0, x1: 0, y1: 0};
  for(const it of placed){ it.x += Z.cx - (g.x0 + g.x1) / 2; it.y += Z.cy - (g.y0 + g.y1) / 2; }
  const back = [];
  for(const p of around){
    const sh = lyShape(p.shape, g.x1 - g.x0, g.y1 - g.y0, Z);
    sh.x = Z.cx; sh.y = Z.cy;
    await lyColor(sh, p.color); back.push(sh);
  }
  return [...back, ...placed];
}

// ── one-ink items: which of the art's colours print ─────────────────────────
// The page's own one-colour engine (/api/one-color) splits the art into its
// colours; each prints in the ink, becomes a gap (the item shows through, so
// detail inside the design stays visible), or is dropped.
const ART_STATE = {print: "prints", knockout: "gap", remove: "dropped"};
const STATE_IN = {print: "print", prints: "print", keep: "print", gap: "knockout", gaps: "knockout",
                  knockout: "knockout", drop: "remove", dropped: "remove", remove: "remove"};
const NAMES = {white: "#FFFFFF", black: "#111111", gray: "#8A8D8F", silver: "#C0C0C0", brown: "#6E4C1E", tan: "#C9A77C",
               cream: "#F3E7C9", pink: "#F4A7C0", purple: "#6E3FA0", "light blue": "#7BAFD4", "dark green": "#1E5C3A"};
function colourName(hex){
  const L = labOf(hex);
  let best = "colour", d0 = 1e9;
  for(const [n, h] of Object.entries({...FAMILY, ...NAMES})){
    const m = labOf(h), d = (m[0] - L[0]) ** 2 + (m[1] - L[1]) ** 2 + (m[2] - L[2]) ** 2;
    if(d < d0){ d0 = d; best = n; }
  }
  return best;
}
async function artColours(location, overrides){
  const sl = needArt(location);
  if(inkMode() !== "one") throw new Error("This item prints in full colour, so the art's colours don't need choosing.");
  const src = sl.oneColor?.src;
  if(!src) return {sl, src: null};
  const r = await fetch("/api/one-color", {method: "POST", headers: {"Content-Type": "application/json"},
    body: JSON.stringify({art_path: src, decisions: overrides ?? sl.oneColor.overrides ?? {}})});
  const d = await r.json();
  if(!r.ok || d.error) throw new Error(d.error || "Couldn't read the art's colours.");
  const total = d.groups.reduce((a, g) => a + g.area, 0) || 1;
  const groups = d.groups.map((g, k) => {
    const st = new Set(g.shapes.map(i => d.decisions[String(i)]));
    return {n: k + 1, colour: colourName(g.hex), hex: g.hex, share: Math.max(1, Math.round(100 * g.area / total)) + "%",
            now: st.size === 1 ? ART_STATE[[...st][0]] : "mixed", shapes: g.shapes};
  });
  return {sl, src, d, groups};
}
function artColoursChips(groups){
  const say = g => g.now === "prints" ? `Leave the ${g.colour} out` : `Print the ${g.colour}`;
  return `<div class="ask-swh">Colours in your art (one ink prints - tap to change):</div><div class="ask-sw">${groups.map(g =>
    `<button onclick="askSay(${esc(JSON.stringify(say(g)))})" title="${esc(g.hex)} · ${esc(g.now)}"><i style="background:${esc(g.hex)}"></i>${g.n}. ${esc(g.colour)} · ${esc(g.now)}</button>`).join("")}</div>`;
}

const TOOLS = {
  async art_colors({location}){
    const {src, groups} = await artColours(location);
    if(!src) return {location, note: "This art is already one colour - nothing to choose."};
    log("ask-m a ask-swm", artColoursChips(groups));
    return {location, ink: SP.ink?.name || null, colours: groups.map(({shapes, ...g}) => g),
            how: "prints = in the ink; gap = left open so the item shows through (keeps detail inside the design); dropped = gone"};
  },

  async set_art_colors({location, colours}){
    const {sl, src, d: d0, groups} = await artColours(location);
    if(!src) throw new Error("This art is already one colour.");
    const over = {...(sl.oneColor.overrides || {})};
    for(const c of colours || []){
      const g = groups.find(x => x.n === Number(c.n));
      const st = STATE_IN[String(c.state || "").toLowerCase()];
      if(!g) throw new Error(`No colour ${c.n}. Colours: ${groups.map(x => `${x.n} ${x.colour}`).join(", ")}`);
      if(!st) throw new Error(`State "${c.state}" - use prints, gap or dropped.`);
      for(const i of g.shapes) over[String(i)] = st;
    }
    if(!groups.some(g => g.shapes.some(i => (over[String(i)] ?? d0.decisions[String(i)]) === "print")))
      throw new Error("That would leave nothing to print - keep at least one colour printing.");
    const r = await fetch("/api/one-color", {method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({art_path: src, decisions: over})});
    const d = await r.json();
    if(!r.ok || d.error) throw new Error(d.error === "That removes everything." ? "That would leave nothing to print - keep at least one colour." : (d.error || "Couldn't change the colours."));
    const mask = await _ocImg(d.preview_b64);
    const ids = (typeof pairedIds === "function" ? pairedIds(location) : [location]).filter(t => S.slots[t]?.oneColor?.src === src);
    ocCommit(ids.length ? ids : [location], d, mask, src, over);
    if(MC.reduce) clearSeparations();
    renderArtworkPanel(); renderSeparationsPanel?.(); R();
    await settle();
    const now = (await artColours(location, over)).groups;
    log("ask-m a ask-swm", artColoursChips(now));
    return {...artInfo(location), colours: now.map(({shapes, ...g}) => g)};
  },

  
  async get_design({location}){
    const id = lyLoc(location);
    if(lyBusy()) throw new Error("The customer has the layout tool open - let them finish, or ask them to close it.");
    await layoutFonts();
    LY.slot = id;
    studioLoad(id, {});
    await lyFonts();
    if(id === BG_SLOT) return {location: "background", pieces: lyDescribe(), base: await bgInfo(),
            panels: "pieces go on panel 'sides' (Side 1, repeated on Side 2 the right way up), 'side1', 'side2' or 'bottom'",
            colours: "each piece can have its own colour", fonts: (LY.fonts || []).map(f => f.label || f.key),
            shapes: ["line", "ring", "frame", "band", "star", "dot", "block"]};
    return {location, print_area_in: [r2(LY.W / 72), r2(LY.H / 72)], pieces: lyDescribe(),
            colours: layoutUsesColor() ? "each piece can have its own colour" : "everything prints in the one ink",
            fonts: (LY.fonts || []).map(f => f.label || f.key), shapes: ["line", "ring", "frame", "star", "dot", "block"],
            templates: studioTemplates().map(t => t.name)};
  },

  async make_design({location, pieces, arrange}){
    if(!(pieces || []).length) throw new Error("No pieces given.");
    const id = await lyOpen(location);
    const logo = id === BG_SLOT ? lyLogoFromSlot() : LY.items.find(i => i.type === "art");
    if(logo?._uploading){ try{ await logo._uploading; }catch(e){ closeLayout(); throw e; } }
    try{
      if(id === BG_SLOT){
        // Keep the base (pattern / picture covering the item); lay pieces out per panel.
        const keep = LY.items.filter(it => it.type === "art" && it.w >= LY.W * 0.95);
        const groups = {};
        for(const p of pieces) (groups[(p.panel || "sides") + "|" + (p.spot || "middle")] ||= []).push(p);
        const out = [];
        for(const [key, ps] of Object.entries(groups)){
          const [panel, spot] = key.split("|");
          if(!["sides", "side1", "side2", "bottom"].includes(panel)) throw new Error(`Unknown panel "${panel}" - use sides, side1, side2 or bottom.`);
          const zid = panel === "sides" ? "side1" : panel;
          const Z = lyZone(zid);
          // top / bottom: the upper or lower part of the panel, clear of a logo in the middle.
          const Zs = (spot === "top" || spot === "bottom") && zid !== "bottom"
            ? {cx: Z.cx, w: Z.w, h: Z.h * 0.26, cy: Z.cy + (spot === "top" ? -1 : 1) * Z.h * 0.35} : Z;
          const items = await lyBuild(ps, arrange, Zs, logo, location);
          lyFitZone(items, Zs, zid === "bottom" ? 0.7 : 0.88);
          if(panel === "side2") items.forEach(it => lyTurn(it, Z, Z));
          out.push(...items);
          if(panel === "sides"){ const Z2 = lyZone("side2"); out.push(...items.map(it => lyTurn({...it}, Z, Z2))); }
        }
        LY.items = [...keep, ...out];
      } else {
        LY.items = await lyBuild(pieces, arrange, {cx: LY.W / 2, cy: LY.H / 2, w: LY.W, h: LY.H}, logo, location);
      }
    }catch(e){ closeLayout(); throw e; }
    if(!LY.items.length){ closeLayout(); throw new Error("Nothing to put on - add some text or art."); }
    studioPush(); if(id !== BG_SLOT) studioFitAll();
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
    if(sl.oneColor?.src && inkMode() === "one")
      white = "This art has several colours and this item prints one ink, so it was made one colour automatically. "
            + "Call art_colors, show the customer what prints now, and ask which colours they want to keep.";
    if($("aw-scrim")){ $("aw-scrim").remove(); white = (white ? white + " " : "") + "This art has white in it: ask whether the white prints white or is cut out (the item shows through), then set_white."; }
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
    if(!(typeof bgBoardOk === "function" && bgBoardOk())) throw new Error("Only the 4CP items have a printed background.");
    try{ custStep(1); }catch(e){}
    const hexOk = h => /^#?[0-9a-f]{6}$/i.test(String(h || "")) ? (String(h)[0] === "#" ? String(h) : "#" + h).toUpperCase() : null;
    const clearBleed = () => {
      if(S.bleed?.img){ S.bleed = {img: null, ox: 0, oy: 0, sc: 1, rot: 0}; const nm = $("fill-stock-bg-name"); if(nm) nm.textContent = "— None —"; }
    };
    if(i.type === "finished" || i.type === "picture"){
      const f = A.files[i.file];
      if(!f) throw new Error(`No attachment "${i.file}".`);
      const before = S.bleed?.img;
      S.ub = true; S.ut = null;
      await onFile({files: [f], value: ""});
      for(let k = 0; k < 120 && !(S.bleed?.img && S.bleed.img !== before); k++) await sleep(500);
      if(!(S.bleed?.img && S.bleed.img !== before)) throw new Error("The background didn't go on: " + (($("fb")?.textContent || "").trim() || "check the file"));
      await settle();
      return {background: i.type === "finished" ? "finished design for the whole item" : "their picture, full bleed",
              note: "It covers the whole item (Side 1, bottom, Side 2 as laid out in the file)."};
    }
    if(i.type === "pattern"){
      const files = await stockList();
      const want = String(i.pattern || "").toLowerCase();
      const f = files.find(x => x.replace(/\.(jpg|jpeg|png)$/i, "").toLowerCase() === want)
             || files.find(x => x.toLowerCase().includes(want));
      if(!f) throw new Error(`No pattern "${i.pattern}". Patterns: ${files.map(x => x.replace(/\.(jpg|jpeg|png)$/i, "")).join(", ")}`);
      selectStockBg(f);
      for(let k = 0; k < 40 && S.bleed?._stockFile !== f; k++) await sleep(250);
      await settle();
      return {background: await bgInfo()};
    }
    clearBleed();
    if(i.type === "solid"){
      setFillMode("solid");
      if(i.pms){
        if(!SP.loaded) await loadPmsLibrary();
        const k = _findInk(i.pms) || _findInk("PANTONE " + String(i.pms).replace(/^(pms|pantone)\s*/i, ""));
        if(!k) throw new Error(`Unknown PANTONE "${i.pms}".`);
        Object.assign(S_FILL.solid, {hex: k.hex, pms: k.name, pmsHex: k.hex, near: null});
        for(const id of ["fill-solid-picker", "fill-solid-hex"]){ const el = $(id); if(el) el.value = k.hex; }
        const pv = $("fill-solid-preview"); if(pv) pv.style.background = k.hex;
        fillSolidBadge(); R();
      } else {
        const h = hexOk(i.hex); if(!h) throw new Error("Give a hex colour like #1C4FD0 (or a pms).");
        await onFillSolidHex(h);
      }
    } else if(i.type === "gradient"){
      const cs = (i.colors || []).map(hexOk).filter(Boolean);
      if(cs.length < 2) throw new Error("A gradient needs two to four hex colours.");
      S_FILL.gradient.stops = cs.slice(0, 4).map(hex => ({hex, pms: null}));
      setFillMode("gradient"); renderGradientStops();
      setGradientDir({down: "to bottom", right: "to right", diag: "135deg", up_right: "45deg"}[i.direction] || "to bottom");
    } else if(i.type === "none"){
      setFillMode("none");
    } else throw new Error(`Unknown background type "${i.type}".`);
    await settle();
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
