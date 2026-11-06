// One-color items: the ink starts as the art's own color (its nearest PMS),
// not Black, as long as the client hasn't picked an ink themselves.
function artMainHex(img){
  if(!img?.width) return null;
  const s = Math.min(1, 200 / Math.max(img.width, img.height));
  const c = document.createElement("canvas");
  c.width = Math.max(1, Math.round(img.width * s)); c.height = Math.max(1, Math.round(img.height * s));
  const g = c.getContext("2d", {willReadFrequently: true}); g.drawImage(img, 0, 0, c.width, c.height);
  let d; try{ d = g.getImageData(0, 0, c.width, c.height).data; }catch(e){ return null; }
  const bins = new Map();
  for(let i = 0; i < d.length; i += 4){
    if(d[i + 3] < 160) continue;
    const k = ((d[i] >> 3) << 10) | ((d[i + 1] >> 3) << 5) | (d[i + 2] >> 3);
    const b = bins.get(k) || [0, 0, 0, 0]; b[0]++; b[1] += d[i]; b[2] += d[i + 1]; b[3] += d[i + 2]; bins.set(k, b);
  }
  let best = null;
  for(const b of bins.values()) if(!best || b[0] > best[0]) best = b;
  if(!best) return null;
  const h = v => Math.round(v / best[0]).toString(16).padStart(2, "0");
  return "#" + h(best[1]) + h(best[2]) + h(best[3]);
}
function _hexLab(hex){
  const n = parseInt(String(hex).slice(1), 16), f = c => { c /= 255; return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4; };
  const r = f(n >> 16 & 255), g = f(n >> 8 & 255), b = f(n & 255);
  const X = (0.4124 * r + 0.3576 * g + 0.1805 * b) / 0.95047, Y = 0.2126 * r + 0.7152 * g + 0.0722 * b, Z = (0.0193 * r + 0.1192 * g + 0.9505 * b) / 1.08883;
  const t = v => v > 0.008856 ? Math.cbrt(v) : 7.787 * v + 16 / 116;
  return [116 * t(Y) - 16, 500 * (t(X) - t(Y)), 200 * (t(Y) - t(Z))];
}
async function autoInkFromArt(img){
  if(!isScreenPrint() || RESTORE.active) return;
  const cur = SP.ink?.name || null;
  if(cur && cur !== SP_DEFAULT_INK.name && cur !== SP.autoInk) return;      // picked by the client
  const hex = artMainHex(img); if(!hex) return;
  await loadPmsLibrary();
  const L = _hexLab(hex);
  let pick = null;
  if(L[0] > 92 && Math.hypot(L[1], L[2]) < 6) pick = (SP.library || []).find(c => c.name === "White");
  else if(L[0] < 22 && Math.hypot(L[1], L[2]) < 12) pick = SP_DEFAULT_INK;           // black art: Black C
  else {
    let bd = Infinity;
    for(const c of (SP.library || [])){
      if(!/^#[0-9a-f]{6}$/i.test(c.hex || "") || !/^PANTONE /.test(c.name)) continue;
      const m = _hexLab(c.hex), dd = (m[0] - L[0]) ** 2 + (m[1] - L[1]) ** 2 + (m[2] - L[2]) ** 2;
      if(dd < bd){ bd = dd; pick = c; }
    }
  }
  if(!pick || pick.name === cur) return;
  setScreenPrintInk(pick.name, pick.hex);
  SP.autoInk = pick.name;
  const fb = document.getElementById("fb");
  if(fb) fb.textContent = `✓ Ink set to ${pick.name.replace(/^PANTONE\s+/, "")} to match your art — change it any time.`;
}
