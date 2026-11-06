// Build fast-studio's static/configurator.html from main's.
//   node port_html.mjs <main configurator.html> <out>
// 1. The client-site changes (title, badge, client view locked on, no pricing,
//    no ink coverage, the "art from a mockup" link, coming-soon filter).
// 2. The NetSuite / export-log / ink-coverage functions become stubs.
// 3. Every comment (JS, CSS, HTML) is taken out of the shipped page.
import fs from 'fs';
import * as acorn from 'acorn';

const [, , src, dst] = process.argv;
let h = fs.readFileSync(src, 'utf8');

function rep(old, neu, count = 1) {
  const n = h.split(old).length - 1;
  if (n !== count) throw new Error(`expected ${count} of ${JSON.stringify(old.slice(0, 90))}, found ${n}`);
  h = h.split(old).join(neu);
}

// ── 1. client-site changes ──────────────────────────────────────────────────
rep('<title>Production Engine — Numo</title>', '<title>Numo · This Is Fast</title>');
rep('<span class="engine-badge">PRODUCTION ENGINE</span>', '<span class="engine-badge">THIS IS FAST</span>');
rep('body.cust #ns-card,body.cust #ns-fa-card,body.cust #export-preview,body.cust #am-after{display:none!important}',
    'body.cust #ns-card,body.cust #ns-fa-card,body.cust #export-preview,body.cust #am-after{display:none!important}\n' +
    '#ink-btn,#ink-pop,#export-preview,#em-opts,#am-open-ns,.sbx-hide{display:none!important}');
rep(`<div class="az-alt"><button onclick="openTxtModal()">or add text instead</button></div>\n`,
    `<div class="az-alt"><button onclick="openTxtModal()">or add text instead</button></div>\n` +
    `<div class="az-alt cust-only"><button onclick="document.getElementById('ap-fi').click()" title="A mockup, approval form or template with your art on it: pick your art out of it">or use art from a mockup or template</button></div>\n`);
rep('    try{ _ordLite = await (await fetch("/api/products-lite")).json(); }',
    '    try{ _ordLite = (await (await fetch("/api/products-lite")).json()).filter(p => !p.coming_soon); }');
rep('<div class="cust-hide" style="display:flex;align-items:center;justify-content:space-between;padding:8px 0;border-top:1px solid var(--border);border-bottom:1px',
    '<div class="cust-hide sbx-hide" style="display:flex;align-items:center;justify-content:space-between;padding:8px 0;border-top:1px solid var(--border);border-bottom:1px');
rep('<div id="currency-row" class="cust-hide" style=', '<div id="currency-row" class="cust-hide sbx-hide" style=');
rep(`<script src="/static/ns-bridge.js"></script>
<script src="/static/signout.js" defer></script>
<script src="/static/whats-new.js" defer></script>`, `<script src="/static/client.js" defer></script>`);
// The client view, always: no artist mode, no switch, from the first paint.
rep('const ALWAYS_ARTIST = true;', 'const ALWAYS_ARTIST = false;');
rep(`let CUSTOMER = (() => {
  let on = false;
  if(ALWAYS_ARTIST){ try{ sessionStorage.removeItem("numo.customer"); }catch(e){} return false; }`,
    `let CUSTOMER = (() => {
  try{ sessionStorage.setItem("numo.customer", "1"); }catch(e){}
  return true;
  let on = false;`);
rep('var CUST_LOCKED = false;', 'var CUST_LOCKED = true;');
// Export file names: no tool prefix on the 2X2.
rep('twoByTwo: `Ttool_${stem}-2X2${rev}.png`', 'twoByTwo: `${stem}-2X2${rev}.png`');
rep('inside.push(`Ttool_${head}-', 'inside.push(`${head}-');
// "Open in NetSuite" button and the artist's Send-to options.
rep(`      <button class="bt b2" style="flex:1;display:none" onclick="artistOpenNetSuite()" id="am-open-ns">Open in NetSuite ↗</button>\n`, '');
// The artist's art-editor video isn't shipped here (clients never see its button).
rep(' poster="/static/tutorial/art-editor-poster.jpg"', '');
// Words people can see.
rep(' the quantity comes from the NetSuite order, or the QTY field in Export.', ' the quantity comes from the QTY field in Export.');
rep('title="Every item on this NetSuite order.', 'title="Every item on this order.');
rep('"This variant is a line on the NetSuite order. Remove it', '"This variant is a line on the order. Remove it');
rep('`QTY ${ns} from the NetSuite order`', '`QTY ${ns} from the order`');
rep('" The NetSuite order line and its colors are kept."', '" The order line and its colors are kept."');
rep('"✓ Not on a NetSuite line, so nothing went to Dropbox: all files are in your downloads instead. Download links below last an hour."',
    '"✓ All files are in your downloads. Download links below last an hour."');
rep('ARTIST.config = {passcode_required:false, netsuite_search_url:""};', 'ARTIST.config = {passcode_required:false};');
rep('if(open) open.style.display = cfg.netsuite_search_url ? "" : "none";', 'if(open) open.style.display = "none";');

// ── One imprint location (2026-10-29): items the server marks max_imprints 1
//    (the TIF pens) show both sides but print on one, picked by the client.
rep('function sidesSame(){ return hasSidePair() && S.sides !== "diff"; }',
`function sidesSame(){ return hasSidePair() && !imprintOne() && S.sides !== "diff"; }
function imprintOne(){ return Number(S.prod?.max_imprints) === 1 && hasSidePair(); }
function imprintSide(){ return S.printSide === "side2" ? "side2" : "side1"; }
function imprintOff(){ return imprintSide() === "side1" ? "side2" : "side1"; }
function imprintReal(id){ const sl = S.slots?.[id]; return !!(sl?.img && !sl.isDefault); }
function imprintPick(t){
  if(t === "side1" || t === "side2"){ S.printSide = t; return [t]; }
  if(t === "all" || t === "sides"){
    const all = RESTORE.legacySlots || S.prod?.slots?.map(s => s.id) || [];
    return (t === "sides" ? ["side1", "side2"] : all).filter(id => id !== imprintOff());
  }
  return null;
}
function imprintOneEnforce(){
  if(!imprintOne() || !S.slots) return;
  if(imprintReal(imprintOff()) && !imprintReal(imprintSide())) S.printSide = imprintOff();
  const off = imprintOff();
  if(S.slots[off]?.img){
    S.slots[off] = {img:null, ox:0, oy:0, sc:1, rot:0, file:null};
    if(S.act === off) S.act = imprintSide();
  }
  S.sides = "diff";
}
function setImprintSide(id){
  if(!imprintOne() || id === imprintSide()) return;
  const from = imprintSide(), a = S.slots[from];
  S.printSide = id;
  if(a?.img && !a.isDefault)
    S.slots[id] = {...a, ox:0, oy:0, _thumb:null, _thumbFor:null, mc: (typeof mcCloneSet === "function" ? mcCloneSet(a.mc) : a.mc)};
  S.slots[from] = {img:null, ox:0, oy:0, sc:1, rot:0, file:null};
  S.act = id;
  if(typeof MC !== "undefined"){ MC.offer = null; MC.editing = -1; }
  renderArtworkPanel(); updateAEPanel();
  if(typeof renderSeparationsPanel === "function") renderSeparationsPanel();
  R();
}`);
rep(`function uploadTargets(t){
  const all =`, `function uploadTargets(t){
  if(imprintOne()){ const one = imprintPick(t); if(one) return one; }
  const all =`);
rep(`function R(){
if(syncMatchInks()) return;`, `function R(){
if(syncMatchInks()) return;
imprintOneEnforce();`);
rep(`  if(!hasSidePair()){ el.style.display = "none"; el.innerHTML = ""; return; }
  const same = sidesSame();`, `  if(!hasSidePair()){ el.style.display = "none"; el.innerHTML = ""; return; }
  if(imprintOne()){
    const ps = imprintSide(), lab = id => (S.prod.slots.find(s => s.id === id)?.label || id);
    el.style.display = "";
    el.innerHTML = \`<div class="az-sides-lbl">Prints on one side — which one?</div>
    <div class="az-seg">
      <button class="\${ps === "side1" ? "on" : ""}" onclick="setImprintSide('side1')">\${lab("side1")}</button>
      <button class="\${ps === "side2" ? "on" : ""}" onclick="setImprintSide('side2')">\${lab("side2")}</button>
    </div>
    <div class="az-sides-note" style="font-size:11px;color:var(--muted);margin-top:5px">This item has one imprint location. The other side stays blank.</div>\`;
    return;
  }
  const same = sidesSame();`);
rep(`  const shown = (S.prod.slots||[]).filter(sl => !(same && sl.id === "side2"))`,
    `  const shown = (S.prod.slots||[]).filter(sl => !(same && sl.id === "side2") && !(imprintOne() && sl.id === imprintOff()))`);

// ── 4CP background step (2026-10-29) ────────────────────────────────────────
{
  const BGD_JS = fs.readFileSync(new URL('./bgd.js', import.meta.url), 'utf8');
  rep('function custHasArt(){ return Object.values(S.slots || {}).some(sl => sl?.img); }',
      'function custHasArt(){ return Object.values(S.slots || {}).some(sl => sl?.img); }\n'
      + '// A 4CP item can go to review with only its background (a finished design, say).\n'
      + 'function custCanReview(){ return custHasArt() || (typeof bgdOn === "function" && bgdOn() && !!S.bleed?.img); }\n' + BGD_JS);
  rep('  if(n === 3 && !custHasArt()){ n = 2; }', '  if(n === 3 && !custCanReview()){ n = 2; }');
  rep('    next.disabled = n === 2 && !custHasArt();', '    next.disabled = n === 2 && !custCanReview();');
  rep('<button data-s="1" onclick="custStep(1)"><b>1</b>Product color</button>',
      '<button data-s="1" onclick="custStep(1)"><b>1</b><span id="cs1-lbl">Product color</span></button>');
  rep('<div id="fill-panel-wrap" style="display:none">', '<div id="bgd" class="bgd" style="display:none"></div>\n<div id="fill-panel-wrap" style="display:none">');
  rep('#ink-btn,#ink-pop,#export-preview,#em-opts,#am-open-ns,.sbx-hide{display:none!important}',
      `#ink-btn,#ink-pop,#export-preview,#em-opts,#am-open-ns,.sbx-hide{display:none!important}
body.bgd-on #fill-panel-wrap,body.bgd-on #bleed-btn-row{display:none!important}
.bgd{margin:0 0 14px}
.bgd .lbl{margin-top:14px}
.bgd-fin{border:1px dashed var(--border-hi);border-radius:10px;padding:10px 12px;font:13px/1.45 var(--sans);color:var(--text);background:var(--surface)}
.bgd-finbtn{display:block;width:100%;margin:8px 0 4px}
.bgd-hint{font:11.5px/1.4 var(--sans);color:var(--muted)}
.bgd-link{background:none;border:none;padding:2px 0;color:var(--burgundy);text-decoration:underline;cursor:pointer;font:12px var(--sans)}
.bgd-cards{display:grid;grid-template-columns:repeat(5,1fr);gap:6px}
.bgd-card{display:flex;flex-direction:column;align-items:center;gap:5px;padding:7px 2px 6px;border:1.5px solid var(--border);border-radius:9px;background:var(--surface);cursor:pointer;font:11px/1.2 var(--sans);color:var(--text)}
.bgd-card.on{border-color:var(--burgundy);box-shadow:0 0 0 2px var(--burg-lo)}
.bgd-sw{width:30px;height:30px;border-radius:7px;border:1px solid var(--border)}
.bgd-opts{margin-top:9px}
.bgd-row{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.bgd-color{width:38px;height:32px;padding:0;border:1px solid var(--border);border-radius:6px;background:none;cursor:pointer}
.bgd-hex{width:88px;padding:7px 8px;border:1px solid var(--border);border-radius:6px;font:12px var(--mono)}
.bgd-sel{padding:6px;border:1px solid var(--border);border-radius:6px;font:12px var(--sans)}
.bgd-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:6px;font:12px var(--sans);color:var(--muted)}
.bgd-pat{border:1.5px solid var(--border);border-radius:8px;padding:3px;background:var(--surface);cursor:pointer;display:flex;flex-direction:column;gap:3px}
.bgd-pat.on{border-color:var(--burgundy)}
.bgd-pat span{display:block;height:46px;border-radius:5px;background-size:cover;background-position:center}
.bgd-pat i{font:10.5px/1.2 var(--sans);font-style:normal;color:var(--text);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.bgd-add{margin-top:10px;display:flex;align-items:center;gap:10px}
.bgd-seg{margin-top:2px}
@media (max-width:640px){.bgd-cards{grid-template-columns:repeat(3,1fr)}}`);
  rep('function R(){\nif(syncMatchInks()) return;\nimprintOneEnforce();', 'function R(){\nif(syncMatchInks()) return;\nimprintOneEnforce();\nbgdSync();');
  // The design board for the background: Side 1's visible panel.
  rep('  if(id === BG_SLOT) return { W: S.prod.page_w, H: S.prod.page_h, circle: false };',
      '  if(id === BG_SLOT) return { W: S.prod.page_w, H: S.prod.page_h, circle: false };\n  if(id === BGS_SLOT){ const z = bgdZonePts("side1"); return { W: z.W, H: z.H, circle: false }; }');
  rep('  if(id === BG_SLOT) return studioLoadBg(opts);', '  if(id === BG_SLOT) return studioLoadBg(opts);\n  if(id === BGS_SLOT) return bgdLoadBoard();');
  rep('  if(id === BG_SLOT) return "Background · whole item";', '  if(id === BG_SLOT) return "Background · whole item";\n  if(id === BGS_SLOT) return "Background · Side 1";');
  rep('  if(LY.slot === BG_SLOT) return bgBaseColor();', '  if(LY.slot === BG_SLOT) return bgBaseColor();\n  if(LY.slot === BGS_SLOT) return BGD.base.type === "solid" ? (BGD.base.hex || "#ffffff") : "#ffffff";');
  rep('  else g.fillRect(0, 0, LY.W, LY.H);', '  else g.fillRect(0, 0, LY.W, LY.H);\n  if(LY.slot === BGS_SLOT && BGD.preview) g.drawImage(BGD.preview, 0, 0, LY.W, LY.H);');
  rep('if(LY.slot === BG_SLOT) break;', 'if(LY.slot === BG_SLOT || LY.slot === BGS_SLOT) break;');
  rep('if(LY.slot === BG_SLOT && !msgs.length){', 'if(LY.slot === BGS_SLOT && !msgs.length){\n    studioNote("Side 1 as it shows on the item. Anything past the edge is trimmed; your logo goes on top in the next step.");\n    return;\n  }\n  if(LY.slot === BG_SLOT && !msgs.length){');
  rep('  if(LY.slot === BG_SLOT) return;     // a background runs off the edges; the item trims it',
      '  if(LY.slot === BG_SLOT || LY.slot === BGS_SLOT) return;     // a background runs off the edges; the item trims it');
  rep('    if(LY.slot === BG_SLOT){ await bgDesignApply(d, items); return; }',
      '    if(LY.slot === BG_SLOT){ await bgDesignApply(d, items); return; }\n    if(LY.slot === BGS_SLOT){ await bgdDesignApply(d, items); return; }');
  rep('function closeLayout(){ document.getElementById("ly-scrim").classList.remove("vis"); }',
      'function closeLayout(){ document.getElementById("ly-scrim").classList.remove("vis"); if(typeof bgdLayoutClosed === "function") bgdLayoutClosed(); }');
}

// ── One-color ink follows the art's color (2026-10-29) ─────────────────────
{
  const AUTO_JS = fs.readFileSync(new URL('./autoink.js', import.meta.url), 'utf8');
  rep('function setScreenPrintInk(name, hex){', AUTO_JS + '\nfunction setScreenPrintInk(name, hex){');
  rep('      S._glassMulti = 0;', '      S._glassMulti = 0;\n      { const _s0 = S.slots[slots[0]]; autoInkFromArt(_s0?.srcImg || _s0?.img); }');
}

// ── Ask Gweg button and script (2026-11-04) ────────────────────────────────
rep('<button class="tut-btn" id="tut-btn" onclick="openTutorial(\'replay\')"',
    '<button class="tut-btn" id="ask-btn" onclick="askToggle()" title="Ask Gweg: tell him what you want and he sets it up for you"><img src="/static/img/gweg.png" alt=""> Ask Gweg</button>\n'
    + '<button class="tut-btn" id="tut-btn" onclick="openTutorial(\'replay\')"');
rep('<script src="/static/client.js" defer></script>', '<script src="/static/client.js" defer></script>\n<script src="/static/assistant.js?v=10" defer></script>');

// The review step lists every colorway on the order (the bot can add them).
rep('const rows = [["Product", e(document.getElementById("prod-label")?.textContent || S.prod?.name || S.pid || "")]];',
    'const rows = [["Product", e(document.getElementById("prod-label")?.textContent || S.prod?.name || S.pid || "")]];\n'
    + '  if(typeof varOn === "function" && varOn()) rows.push(["Colors on this order", VAR.list.map(v => e(varLabel(v))).join("<br>")]);');

// ── 2. NetSuite / export log / ink coverage: stubs ──────────────────────────
const STUBS = {
  explogLookup: '{ return; }',
  logExport: '{}',
  varSaveFinalArtwork: '{ return; }',
  ensureInkPaths: '{ return; }',
  inkCoverageNow: '{ return null; }',
  renderInkCoverage: '{ return; }',
  renderInkPanel: '{ return; }',
  varFromOrder: '{ return; }',
  ordLineDetails: '{ return; }',
  nsLineInfo: '{ return null; }',
  nsLineBody: '{ return null; }',
  nsFilesList: '{ return []; }',
  nsPreview: '{ return; }',
};
{
  const a = h.indexOf('<script>') + 8, b = h.indexOf('</script>', a);
  let js = h.slice(a, b);
  const ast = acorn.parse(js, { ecmaVersion: 'latest', sourceType: 'script' });
  const edits = [];
  const seen = new Set();
  for (const n of ast.body) {
    if (n.type === 'FunctionDeclaration' && STUBS[n.id.name]) {
      edits.push([n.body.start, n.body.end, STUBS[n.id.name]]);
      seen.add(n.id.name);
    }
    // The bridge card's tidy-up (static/ns-bridge.js isn't on this site).
    if (n.type === 'ExpressionStatement' && js.slice(n.start, n.end).includes('#ns-card .ns-file-meta')) {
      edits.push([n.start, n.end, '']);
      seen.add('(ns-card tidy)');
    }
  }
  // The "open the order" link's function goes altogether (its button is gone).
  for (const n of ast.body)
    if (n.type === 'FunctionDeclaration' && n.id.name === 'artistOpenNetSuite') { edits.push([n.start, n.end, '']); seen.add('artistOpenNetSuite'); }
  const missing = Object.keys(STUBS).filter(k => !seen.has(k));
  if (missing.length || !seen.has('(ns-card tidy)')) throw new Error('not found: ' + missing.join(', '));
  edits.sort((x, y) => y[0] - x[0]);
  for (const [s, e, t] of edits) js = js.slice(0, s) + t + js.slice(e);

  // ── 3a. JS comments out (exact ranges from the parser) ────────────────────
  const comments = [];
  acorn.parse(js, { ecmaVersion: 'latest', sourceType: 'script',
                    onComment: (block, text, s, e) => comments.push([s, e]) });
  comments.sort((x, y) => y[0] - x[0]);
  for (const [s, e] of comments) js = js.slice(0, s) + js.slice(e);
  // Lines left empty or with only trailing spaces by that.
  js = js.replace(/[ \t]+$/gm, '').replace(/\n{3,}/g, '\n\n');
  acorn.parse(js, { ecmaVersion: 'latest', sourceType: 'script' });      // still valid
  h = h.slice(0, a) + js + h.slice(b);
}

// ── 3b. CSS and HTML comments out ───────────────────────────────────────────
h = h.replace(/<style>([\s\S]*?)<\/style>/g, (m, css) =>
  '<style>' + css.replace(/\/\*[\s\S]*?\*\//g, '').replace(/[ \t]+$/gm, '').replace(/\n{2,}/g, '\n') + '</style>');
{
  const a = h.indexOf('<script>'), b = h.indexOf('</script>', a);
  const strip = s => s.replace(/<!--[\s\S]*?-->/g, '').replace(/[ \t]+$/gm, '').replace(/\n{3,}/g, '\n\n');
  h = strip(h.slice(0, a)) + h.slice(a, b) + strip(h.slice(b));
}

fs.writeFileSync(dst, h);
console.log('ok', h.length, 'bytes', h.split('\n').length, 'lines');
