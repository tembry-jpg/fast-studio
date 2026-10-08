"""
Pick the art out of a mockup or someone else's template.

Customers and distributors send their logo placed on a photo of the product,
on an approval form, or on another supplier's template. The vector art is in
there, among the photo, the form text and the guides. This module:

  analyze()  reads every painted thing on a page (paths, text, images) with its
             box and colour, groups touching shapes into pieces (a logo, a line
             of text), and suggests which pieces are the imprint and where each
             goes (Side 1 / Side 2 / Bottom), from where they sit on the product.
  place()    cuts the chosen pieces out as a vector PDF per location, everything
             else removed, cropped to the art and turned upright.

The configurator shows the page with the pieces outlined; the artist accepts
the suggestion or reassigns pieces with a click, then places them. The
reading and cutting reuse tif_import (the same object numbering and rewrite),
so what is chosen is exactly what comes out.
"""
import json
import secrets
import shutil
import subprocess
import tempfile
from pathlib import Path

import pikepdf

import onecolor
import tif_import

PAGES_TO_READ = 6
RENDER_LONG_SIDE = 1100            # px, the page image the editor shows
GAP_PT = 2.5                       # shapes this close are one piece
_GUIDE_WORDS = ("art", "bottom", "side", "imprint", "area", "safe", "bleed", "trim",
                "cut line", "fold", "seam", "center", "centre", "live", "top")


# ── reading ────────────────────────────────────────────────────────────────
#
# One walk over the page and every form it uses, numbered exactly as
# tif_import._walk numbers things (owner stream + op index), so tif_import's
# rewrite cuts out exactly what was chosen. On top of the boxes it tracks
# what tif_import doesn't need: colour, opacity, and the clipping in force,
# so a shape hidden by a clipping mask (a proof's leftovers, a thumbnail's
# off-canvas copy) isn't offered as art and a clipped photo has its real size.

_COLOR_OPS = ("cs", "CS", "g", "G", "rg", "RG", "k", "K", "sc", "scn", "SC", "SCN")


def _isect(a, b):
    if a is None:
        return b
    if b is None:
        return a
    x0, y0, x1, y1 = max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])
    return (x0, y0, x1, y1) if x1 > x0 and y1 > y0 else (0, 0, 0, 0)


def _box_of(pts):
    xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
    return (min(xs), min(ys), max(xs), max(ys))


def _walk(owner, res, ctm, out, owner_key="page", seen_stack=(), gs0=None):
    try:
        ops = pikepdf.parse_content_stream(owner)
    except Exception:
        return out
    res = res if res is not None else pikepdf.Dictionary()
    gs = dict(gs0 or {"fill": [("gray", None), [0.0]], "stroke": [("gray", None), [0.0]],
                      "alpha": 1.0, "clip": None})
    gs["ctm"] = ctm
    stack, path, clip_next = [], [], False
    tb = None
    tm = [1, 0, 0, 1, 0, 0]; tlm = [1, 0, 0, 1, 0, 0]; lead = 0.0; fsize = 0.0
    mul = tif_import._mul

    def pt(x, y, m=None):
        m = m or gs["ctm"]
        return (x * m[0] + y * m[2] + m[4], x * m[1] + y * m[3] + m[5])

    def rgb(state):
        (fam, extra), vals = state
        try:
            if fam == "tint":
                return onecolor._tint_rgb(extra, vals)
            if fam in ("pattern", "indexed"):
                return None
            return onecolor._to_rgb(fam, vals)
        except Exception:
            return None

    def rec(kind, idx, op, box, n, **kw):
        vis = _isect(box, gs["clip"])
        f = rgb(gs["fill"])
        if f is not None and gs["alpha"] < 1:
            f = tuple(1 - gs["alpha"] * (1 - c) for c in f)   # seen through: mostly paper
        r = {"kind": kind, "owner": owner_key, "idx": idx, "op": op, "bbox": vis, "raw": box, "n": n,
             "fill": f, "stroke": rgb(gs["stroke"]), "hidden": (vis[2] - vis[0]) < 0.3 or (vis[3] - vis[1]) < 0.3}
        r.update(kw)
        out.append(r)

    for i, (a, o) in enumerate(ops):
        o = str(o)
        try:
            if o == "q":
                stack.append({**gs, "fill": [gs["fill"][0], list(gs["fill"][1])],
                              "stroke": [gs["stroke"][0], list(gs["stroke"][1])]})
            elif o == "Q":
                gs = stack.pop() if stack else gs
            elif o == "cm":
                gs["ctm"] = mul([float(x) for x in a], gs["ctm"])
            elif o in _COLOR_OPS:
                key = "stroke" if o in ("G", "RG", "K", "CS", "SC", "SCN") else "fill"
                tgt = [gs[key][0], list(gs[key][1])]
                nums = [float(x) for x in a if not isinstance(x, pikepdf.Name)]
                if o in ("cs", "CS"):
                    tgt = [onecolor._cs_info(res, a[0]), [0.0]]
                elif o in ("g", "G"):
                    tgt = [("gray", None), nums]
                elif o in ("rg", "RG"):
                    tgt = [("rgb", None), nums]
                elif o in ("k", "K"):
                    tgt = [("cmyk", None), nums]
                else:
                    tgt[1] = nums
                gs[key] = tgt
            elif o == "gs":
                try:
                    g = res.ExtGState[a[0]]
                    if "/ca" in g:
                        gs["alpha"] = gs.get("alpha0", 1.0) * float(g.ca)
                except Exception:
                    pass
            elif o in ("m", "l"):
                path.append(pt(float(a[0]), float(a[1])))
            elif o == "c":
                path += [pt(float(a[0]), float(a[1])), pt(float(a[2]), float(a[3])), pt(float(a[4]), float(a[5]))]
            elif o in ("v", "y"):
                path += [pt(float(a[0]), float(a[1])), pt(float(a[2]), float(a[3]))]
            elif o == "re":
                x, y, w, h = map(float, a)
                path += [pt(x, y), pt(x + w, y + h), pt(x, y + h), pt(x + w, y)]
            elif o in ("W", "W*"):
                clip_next = True
            elif o in tif_import._PATH_PAINT:
                if path:
                    box = _box_of(path)
                    rec("path", i, o, box, len(path))
                    if clip_next:
                        gs["clip"] = _isect(gs["clip"], box)
                path, clip_next = [], False
            elif o == "n":
                if clip_next and path:
                    gs["clip"] = _isect(gs["clip"], _box_of(path))
                path, clip_next = [], False
            elif o == "BT":
                tb = {"start": i, "pts": [], "text": ""}
                tm = [1, 0, 0, 1, 0, 0]; tlm = [1, 0, 0, 1, 0, 0]
            elif o == "Tf" and len(a) == 2:
                fsize = float(a[1])
            elif o == "TL":
                lead = float(a[0])
            elif o in ("Td", "TD"):
                tx, ty = float(a[0]), float(a[1])
                if o == "TD":
                    lead = -ty
                tlm = mul([1, 0, 0, 1, tx, ty], tlm); tm = list(tlm)
            elif o == "Tm":
                tlm = [float(x) for x in a]; tm = list(tlm)
            elif o == "T*":
                tlm = mul([1, 0, 0, 1, 0, -lead], tlm); tm = list(tlm)
            elif o in tif_import._TEXT_SHOW and tb is not None:
                m = mul(tm, gs["ctm"])
                st = a[-1]
                if isinstance(st, pikepdf.Array):
                    txt = b"".join(bytes(x) for x in st if isinstance(x, pikepdf.String))
                else:
                    txt = bytes(st) if isinstance(st, pikepdf.String) else b""
                tb["text"] += txt.decode("latin-1", "replace")
                w = max(1.0, fsize * 0.55 * max(1, len(txt)))
                tb["pts"] += [pt(0, 0, m), pt(w, fsize, m)]
            elif o == "ET" and tb is not None:
                if tb["pts"]:
                    rec("text", tb["start"], "BT", _box_of(tb["pts"]), 0, end=i, text=tb["text"].strip())
                tb = None
            elif o == "Do":
                x = (res.get("/XObject") or {}).get(str(a[0]))
                if x is None:
                    continue
                if x.get("/Subtype") == "/Form":
                    if x.objgen in seen_stack:
                        continue
                    m = mul([float(v) for v in x.get("/Matrix", [1, 0, 0, 1, 0, 0])], gs["ctm"])
                    sub = {**gs, "alpha0": gs["alpha"]}
                    bb = x.get("/BBox")
                    if bb is not None:
                        b = [float(v) for v in bb]
                        sub["clip"] = _isect(gs["clip"], _box_of([pt(b[0], b[1], m), pt(b[2], b[3], m),
                                                                  pt(b[0], b[3], m), pt(b[2], b[1], m)]))
                    _walk(x, x.get("/Resources") or res, m, out, owner_key=f"form:{x.objgen}",
                          seen_stack=seen_stack + (x.objgen,), gs0=sub)
                else:
                    rec("image", i, "Do", _box_of([pt(0, 0), pt(1, 1), pt(0, 1), pt(1, 0)]), 0)
        except Exception:
            continue
    return out


def _objects(pdf, page_index):
    pg = pdf.pages[page_index]
    objs = _walk(pg, pg.obj.get("/Resources"), [1, 0, 0, 1, 0, 0], [])
    objs = [r for r in objs if not r["hidden"]]          # clipped away: nothing shows
    for n, r in enumerate(objs):
        r["id"] = n
        b = r["bbox"]
        r["area"] = max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])
    return objs


def _is_light(rgb):
    return rgb is not None and min(rgb) >= 0.85


def _guide_colour(c, guide_cols):
    """Is colour c one of the guide colours, solid or seen through?"""
    if c is None or not guide_cols:
        return False
    for g in guide_cols:
        for a in (1.0, 0.85, 0.7, 0.55, 0.45, 0.35, 0.25):
            t = tuple(1 - a * (1 - v) for v in g)
            if sum((x - y) ** 2 for x, y in zip(c, t)) ** 0.5 < 0.07:
                return True
    return False


def _role(r, page_area):
    """What a painted thing is, before any grouping."""
    big = r["area"] / page_area
    if r["kind"] == "image":
        # A picture behind the whole sheet (a proof flattened onto an image,
        # a scanned form) is the page, not the product.
        return "background" if big >= 0.6 else ("photo" if big >= 0.06 else "art")
    if r["kind"] == "text":
        t = (r.get("text") or "").strip().lower()
        if t and len(t) <= 24 and any(w == t or t.startswith(w + " ") or t.endswith(" " + w)
                                      for w in _GUIDE_WORDS):
            return "guide"
        return "text"
    stroke_only = r["op"] in ("S", "s")
    if big >= 0.25:
        # A fill over most of the page: the product body (a template's die,
        # a colour block) when it has colour, a watermark or paper when light.
        return "body" if (not stroke_only and r["fill"] is not None and not _is_light(r["fill"])) \
            else "background"
    if stroke_only and (r["n"] <= 5 or big >= 0.02):
        return "guide"                     # lines, boxes, die outlines
    if not stroke_only and r["fill"] is None and big >= 0.02:
        return "background"                # a pattern or shading behind things
    return "art"


def _text_lines(pdf_path, page_index, mediabox):
    """Lines of text with their boxes (page points, origin bottom left), read
    by poppler: a proof's text is often one text object for the whole sheet,
    so the lines and labels come from here."""
    import html, re as _re
    try:
        out = subprocess.run(["pdftotext", "-bbox-layout", "-f", str(page_index + 1),
                              "-l", str(page_index + 1), str(pdf_path), "-"],
                             capture_output=True, text=True, timeout=60).stdout
    except Exception:
        return []
    top = mediabox[3]
    lines = []
    for m in _re.finditer(r'<line xMin="([\d.]+)" yMin="([\d.]+)" xMax="([\d.]+)" yMax="([\d.]+)">(.*?)</line>',
                          out, _re.S):
        words = _re.findall(r">([^<]*)</word>", m.group(5))
        text = html.unescape(" ".join(w.strip() for w in words)).strip()
        if not text:
            continue
        x0, y0, x1, y1 = (float(m.group(i)) for i in range(1, 5))
        lines.append({"text": text, "bbox": (mediabox[0] + x0, top - y1, mediabox[0] + x1, top - y0)})
    return lines


_LOC_WORDS = {"side 1": "side1", "side1": "side1", "side one": "side1", "front": "side1", "side a": "side1",
              "side 2": "side2", "side2": "side2", "side two": "side2", "back": "side2", "side b": "side2",
              "bottom": "bottom", "base": "bottom"}
_SIZE = r'([\d.]+)\s*(?:"|”|″|\'\'|in\b|inch(?:es)?)?\s*w?\s*[x×]\s*([\d.]+)\s*(?:"|”|″|\'\'|in\b|inch(?:es)?)?\s*h?'


def _loc_of(label, slot_ids):
    t = " ".join(str(label).lower().replace(":", " ").split())
    sid = _LOC_WORDS.get(t)
    return sid if sid in slot_ids else None


def proof_info(lines, slot_ids):
    """
    What a proof or approval form says about the job, in its own words:
      sizes {slot: {"w_in", "h_in"}}, same (bool), item_color, thread,
      inks [text], nso. Only what is written on the page; nothing guessed.
    """
    import re as _re
    info = {}
    sizes = {}
    for ln in lines:
        t = ln["text"]
        m = _re.match(r"^\s*(side\s*[12ab]|side\s+(?:one|two)|front|back|bottom|base)\s*:\s*" + _SIZE, t, _re.I)
        if m:
            sid = _loc_of(m.group(1), slot_ids)
            if sid:
                sizes[sid] = {"w_in": float(m.group(2)), "h_in": float(m.group(3))}
            continue
        m = _re.search(r"\b(?:art|imprint|logo)\s+size\s*:\s*" + _SIZE, t, _re.I)
        if m:
            for sid in slot_ids:
                if sid != "bottom":
                    sizes.setdefault(sid, {"w_in": float(m.group(1)), "h_in": float(m.group(2))})
    sizes = {k: v for k, v in sizes.items() if 0.1 <= v["w_in"] <= 30}
    if sizes:
        info["sizes"] = sizes
    text = "\n".join(ln["text"] for ln in lines)
    if _re.search(r"\b(two|2|both)\s+sides?\s+(?:the\s+)?same\b|\bsame\s+(?:art\s+)?(?:on\s+)?both\s+sides\b", text, _re.I):
        info["same"] = True
    elif _re.search(r"\b(two|2|both)\s+sides?\s+different\b|\bdifferent\s+(?:art\s+)?(?:on\s+)?(?:each|both)\s+sides?\b",
                    text, _re.I):
        info["same"] = False
    m = _re.search(r"\b(?:item|product|koozie|neoprene|body)\s+colou?r\s*:\s*([^|\n]+)", text, _re.I)
    if m and m.group(1).strip():
        info["item_color"] = m.group(1).strip().rstrip(".")
    m = _re.search(r"\b(?:thread|stitch(?:ing)?)(?:\s+colou?r)?\s*:\s*([^|\n]+)", text, _re.I)
    if m and m.group(1).strip():
        info["thread"] = m.group(1).strip().rstrip(".")
    inks = []
    for ln in lines:
        t = ln["text"]
        if _re.search(r"\bPMS\b|\bpantone\b|\b(?:imprint|ink)\s+colou?rs?\s*:|\binks?\s*:", t, _re.I) \
                and not _re.search(r"see below|screen ?print", t, _re.I):
            inks.append(t)
    if inks:
        info["inks"] = inks[:6]
    m = _re.search(r"\bNSO[-\s]?\d{5,}\b", text)
    if m:
        info["nso"] = m.group(0).replace(" ", "")
    return info


def _cluster(objs):
    """Group touching shapes (within GAP_PT) into pieces. A grid keeps it fast
    on logos made of thousands of paths."""
    parent = list(range(len(objs)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    cell = 24.0
    grid = {}
    for k, r in enumerate(objs):
        b = r["bbox"]
        for gx in range(int((b[0] - GAP_PT) // cell), int((b[2] + GAP_PT) // cell) + 1):
            for gy in range(int((b[1] - GAP_PT) // cell), int((b[3] + GAP_PT) // cell) + 1):
                grid.setdefault((gx, gy), []).append(k)
    for members in grid.values():
        for x in range(len(members)):
            a = objs[members[x]]["bbox"]
            for y in range(x + 1, len(members)):
                i, j = members[x], members[y]
                if find(i) == find(j):
                    continue
                b = objs[j]["bbox"]
                if a[0] - GAP_PT <= b[2] and b[0] - GAP_PT <= a[2] and \
                   a[1] - GAP_PT <= b[3] and b[1] - GAP_PT <= a[3]:
                    parent[find(i)] = find(j)
    groups = {}
    for k in range(len(objs)):
        groups.setdefault(find(k), []).append(objs[k])
    return list(groups.values())


PICK_BG = (0xFB, 0xEE, 0xDE)        # #FBEEDE, the picker's page colour


def _render(pdf_path, page_index, scale_to):
    with pikepdf.open(str(pdf_path)) as p:
        mb = [float(v) for v in p.pages[page_index].mediabox]
    w, h = mb[2] - mb[0], mb[3] - mb[1]
    dpi = max(36, min(200, int(72 * scale_to / max(w, h))))
    with tempfile.TemporaryDirectory() as d:
        # Rendered see-through and laid on the picker's cream (PICK_BG), so
        # white art on an empty page shows; white the file itself draws (a
        # white box, a white page) stays white.
        subprocess.run(["pdftocairo", "-png", "-transp", "-singlefile", "-r", str(dpi),
                        "-f", str(page_index + 1), "-l", str(page_index + 1),
                        str(pdf_path), str(Path(d) / "p")], check=True,
                       capture_output=True, timeout=90)
        try:
            from PIL import Image
            im = Image.open(Path(d) / "p.png").convert("RGBA")
            bg = Image.new("RGBA", im.size, PICK_BG + (255,))
            bg.alpha_composite(im)
            bg.convert("RGB").save(Path(d) / "q.png", optimize=True)
            return (Path(d) / "q.png").read_bytes(), dpi / 72.0, mb
        except Exception:
            return (Path(d) / "p.png").read_bytes(), dpi / 72.0, mb


# ── suggestion ─────────────────────────────────────────────────────────────

def _inside(pt, box, pad=0.0):
    return box[0] - pad <= pt[0] <= box[2] + pad and box[1] - pad <= pt[1] <= box[3] + pad


def _same_art(pieces, a_ids, b_ids, tol=1.6):
    """Do two sets of pieces draw the same thing? Every shape's size has a
    partner within `tol` points (rotation by 180 keeps sizes; the rounding of
    a copied logo can move them a point)."""
    a = sorted(s for p in pieces if p["id"] in a_ids for s in p["sig"])
    b = sorted(s for p in pieces if p["id"] in b_ids for s in p["sig"])
    if not a or not b or abs(len(a) - len(b)) > 0.1 * max(len(a), len(b)):
        return False
    left = list(b)
    hit = 0
    for k, w, h in a:
        for j, (k2, w2, h2) in enumerate(left):
            if k2 == k and abs(w2 - w) <= tol and abs(h2 - h) <= tol:
                hit += 1
                del left[j]
                break
    return hit >= 0.9 * max(len(a), len(b))


def _art_sheet(pieces, slot_ids, guides):
    """
    An art sheet: the imprints laid out apart on a blank page (Side 1 art at
    the left, Side 2 art at the right, a round bottom design below or in a
    circle guide). Pieces close together are one imprint; each imprint goes
    to a location. None when the page isn't laid out that way.
    """
    cand = [p for p in pieces if p["role"] in ("art", "text")]
    if len(cand) < 2:
        return None
    top = max(p["area"] for p in cand)
    cand = [p for p in cand if p["area"] >= 0.0005 * top or p["role"] == "art"]
    # Regions: pieces within REGION_GAP of each other.
    GAP = 36.0
    regs = []
    for p in sorted(cand, key=lambda p: -p["area"]):
        b = p["bbox"]
        hit = [r for r in regs if b[0] - GAP <= r["b"][2] and r["b"][0] - GAP <= b[2]
               and b[1] - GAP <= r["b"][3] and r["b"][1] - GAP <= b[3]]
        if not hit:
            regs.append({"ps": [p], "b": list(b)}); continue
        r0 = hit[0]
        for r in hit[1:]:
            r0["ps"] += r["ps"]; r0["b"] = [min(r0["b"][0], r["b"][0]), min(r0["b"][1], r["b"][1]),
                                            max(r0["b"][2], r["b"][2]), max(r0["b"][3], r["b"][3])]
            regs.remove(r)
        r0["ps"].append(p)
        r0["b"] = [min(r0["b"][0], b[0]), min(r0["b"][1], b[1]), max(r0["b"][2], b[2]), max(r0["b"][3], b[3])]
    # Merging can make neighbours touch: settle.
    changed = True
    while changed:
        changed = False
        for i in range(len(regs)):
            for j in range(i + 1, len(regs)):
                a, c = regs[i]["b"], regs[j]["b"]
                if a[0] - GAP <= c[2] and c[0] - GAP <= a[2] and a[1] - GAP <= c[3] and c[1] - GAP <= a[3]:
                    regs[i]["ps"] += regs[j]["ps"]
                    regs[i]["b"] = [min(a[0], c[0]), min(a[1], c[1]), max(a[2], c[2]), max(a[3], c[3])]
                    del regs[j]; changed = True; break
            if changed:
                break
    # A round guide (the bottom's circle) holds the bottom design.
    circles = [g for g in guides if 0.8 <= (g[2] - g[0]) / max(1e-6, g[3] - g[1]) <= 1.25]
    def in_circle(r):
        return any(_inside(((r["b"][0] + r["b"][2]) / 2, (r["b"][1] + r["b"][3]) / 2), g) for g in circles)
    # Each imprint is a real design: a small mark beside a big logo (a "by
    # COMPANY" line, a TM) is part of that logo, not another location's art.
    big = max((r["b"][2] - r["b"][0]) * (r["b"][3] - r["b"][1]) for r in regs)
    thick = max(min(r["b"][2] - r["b"][0], r["b"][3] - r["b"][1]) for r in regs)
    regs = [r for r in regs if in_circle(r) or (
        (r["b"][2] - r["b"][0]) * (r["b"][3] - r["b"][1]) >= 0.15 * big
        # A thin line of type (a tagline) belongs with the logo it sits by.
        and min(r["b"][2] - r["b"][0], r["b"][3] - r["b"][1]) >= 0.3 * thick)]
    if not (2 <= len(regs) <= len(slot_ids) + 1):
        return None
    sugg = {}
    rest = []
    for r in regs:
        cx, cy = (r["b"][0] + r["b"][2]) / 2, (r["b"][1] + r["b"][3]) / 2
        if "bottom" in slot_ids and any(_inside((cx, cy), g) for g in circles) and \
                not any(v == "bottom" for v in sugg.values()):
            for p in r["ps"]:
                sugg[p["id"]] = "bottom"
        else:
            rest.append(r)
    if "bottom" in slot_ids and not any(v == "bottom" for v in sugg.values()) and len(rest) == 3:
        # Three imprints and no circle: the lowest one is the bottom.
        low = min(rest, key=lambda r: (r["b"][1] + r["b"][3]) / 2)
        for p in low["ps"]:
            sugg[p["id"]] = "bottom"
        rest.remove(low)
    sides = [s for s in slot_ids if s != "bottom"]
    # Reading order: top row first, left to right.
    rest.sort(key=lambda r: (-round(((r["b"][1] + r["b"][3]) / 2) / 80.0), r["b"][0]))
    for r, sid in zip(rest, sides):
        for p in r["ps"]:
            sugg[p["id"]] = sid
    return sugg


def _suggest(pieces, product_box, layout, slot_ids, guides=()):
    """Location per piece (or None), the rotation per location, and whether
    both sides carry the same art."""
    sugg = {}
    rot = {}
    if product_box is None:
        sheet = _art_sheet(pieces, slot_ids, list(guides))
        if sheet:
            same = not any(v == "side2" for v in sheet.values())
            return sheet, rot, same
        # Nothing to go by: the largest coloured pieces in the middle of the page.
        cand = [p for p in pieces if p["role"] == "art"]
        if cand:
            top = max(p["area"] for p in cand)
            for p in cand:
                if p["area"] >= 0.08 * top:
                    sugg[p["id"]] = slot_ids[0]
        return sugg, rot, True
    def share_inside(b):
        ix = max(0.0, min(b[2], product_box[2]) - max(b[0], product_box[0]))
        iy = max(0.0, min(b[3], product_box[3]) - max(b[1], product_box[1]))
        a = max(1e-6, (b[2] - b[0]) * (b[3] - b[1]))
        return ix * iy / a if a > 1e-3 else float(_inside(((b[0] + b[2]) / 2, (b[1] + b[3]) / 2), product_box))
    # On the product, not just overlapping it: a form's header that runs
    # across the page past the photo is not the imprint.
    cand = [p for p in pieces if p["role"] in ("art", "text") and share_inside(p["bbox"]) >= 0.8]
    if layout == "template" and "side1" in slot_ids:
        # A flat template: upper panel, the bottom circle in the middle, lower
        # panel turned 180 (how every can and bottle template is laid out).
        y0, y1 = product_box[1], product_box[3]
        third = (y1 - y0) / 3.0
        # Pieces stacked close together are one imprint (a logo with a name
        # and date under it, a lone "1" set apart): bands, placed as a whole.
        bands = []
        for p in sorted(cand, key=lambda p: -p["bbox"][3]):
            b = bands[-1] if bands else None
            if b and p["bbox"][3] >= b["lo"] - 18:
                b["ps"].append(p); b["lo"] = min(b["lo"], p["bbox"][1])
            else:
                bands.append({"ps": [p], "lo": p["bbox"][1], "hi": p["bbox"][3]})
        for b in bands:
            hi = max(p["bbox"][3] for p in b["ps"])
            cy = (hi + b["lo"]) / 2
            if cy >= y1 - third:
                sid = "side1"
            elif cy <= y0 + third:
                sid = "side2" if "side2" in slot_ids else "side1"
            else:
                sid = "bottom" if "bottom" in slot_ids else None
            for p in b["ps"]:
                sugg[p["id"]] = sid
        if "side2" in slot_ids:
            rot["side2"] = 180
        s1 = {i for i, s in sugg.items() if s == "side1"}
        s2 = {i for i, s in sugg.items() if s == "side2"}
        same = _same_art(pieces, s1, s2)
        return {k: v for k, v in sugg.items() if v}, rot, same or not s2
    # A photo or drawing of the product: what sits on it is the imprint, shown
    # on the front. It goes on Side 1, same art both sides by default.
    for p in cand:
        if p["role"] == "text" and p["area"] < 0.002 * (product_box[2] - product_box[0]) * (product_box[3] - product_box[1]):
            continue
        sugg[p["id"]] = slot_ids[0]
    return sugg, rot, True


def _suggest_flats(pieces, panels, lines, slot_ids):
    """
    The product drawn flat as separate shapes (a proof's Side 1, Side 2 and
    Bottom). Each shape is a location: by its label when one sits on or just
    under it, otherwise round and small -> Bottom, the rest left to right.
    The art on a shape goes to that shape's location.
    """
    labels = []
    for ln in lines:
        sid = _loc_of(ln["text"], slot_ids)
        if sid:
            labels.append((sid, ((ln["bbox"][0] + ln["bbox"][2]) / 2, (ln["bbox"][1] + ln["bbox"][3]) / 2)))
    owner = {}
    used = set()
    for k, pb in enumerate(panels):
        best = None
        for sid, c in labels:
            # On the shape, or within a label's height or two below / above it.
            if pb[0] - 20 <= c[0] <= pb[2] + 20 and pb[1] - 60 <= c[1] <= pb[3] + 30:
                d = abs(c[0] - (pb[0] + pb[2]) / 2) + min(abs(c[1] - pb[1]), abs(c[1] - pb[3]))
                if best is None or d < best[0]:
                    best = (d, sid)
        if best and best[1] not in used:
            owner[k] = best[1]; used.add(best[1])
    rest = [k for k in range(len(panels)) if k not in owner]
    if rest and "bottom" in slot_ids and "bottom" not in used:
        def roundish(k):
            b = panels[k]; w, h = b[2] - b[0], b[3] - b[1]
            return 0.85 <= (w / h if h else 0) <= 1.18
        big = max((panels[k][2] - panels[k][0]) * (panels[k][3] - panels[k][1]) for k in range(len(panels)))
        circ = [k for k in rest if roundish(k)
                and (panels[k][2] - panels[k][0]) * (panels[k][3] - panels[k][1]) < 0.7 * big]
        if circ:
            owner[circ[0]] = "bottom"; used.add("bottom"); rest.remove(circ[0])
    free = [s for s in slot_ids if s not in used and s != "bottom"]
    for k in sorted(rest, key=lambda k: (-(panels[k][1] + panels[k][3]) // 200, panels[k][0])):
        if free:
            owner[k] = free.pop(0)
    sugg = {}
    for p in pieces:
        if p["role"] not in ("art", "text"):
            continue
        b = p["bbox"]
        a = max(1e-6, (b[2] - b[0]) * (b[3] - b[1]))
        for k, pb in enumerate(panels):
            ix = max(0.0, min(b[2], pb[2]) - max(b[0], pb[0]))
            iy = max(0.0, min(b[3], pb[3]) - max(b[1], pb[1]))
            if ix * iy / a >= 0.8 and k in owner:
                sugg[p["id"]] = owner[k]
                break
    s1 = {i for i, s in sugg.items() if s == "side1"}
    s2 = {i for i, s in sugg.items() if s == "side2"}
    same = _same_art(pieces, s1, s2) if s1 and s2 else not s2
    return sugg, {}, same, {owner[k]: panels[k] for k in owner}


# ── public ─────────────────────────────────────────────────────────────────

def pick_dir(root):
    d = Path(root) / "_pick"
    d.mkdir(parents=True, exist_ok=True)
    return d


def analyze(pdf_path, root, slot_ids, page_index=None):
    """
    Read a page and return what the editor needs:
      {token, page, pages, png (bytes), scale, size [w, h] (pt),
       pieces [{id, box [x, y, w, h] in image px, role, suggest, kinds}],
       layout, rot {slot: 180}, same}
    page_index None: the page with the most art among the first few.
    """
    token = secrets.token_hex(8)
    work = pick_dir(root) / token
    work.mkdir(parents=True)
    src = work / "src.pdf"
    shutil.copy2(str(pdf_path), str(src))
    with pikepdf.open(str(src)) as pdf:
        npages = len(pdf.pages)
        if page_index is None:
            best = (-1, 0)
            for pi in range(min(npages, PAGES_TO_READ)):
                try:
                    objs = _objects(pdf, pi)
                except Exception:
                    continue
                n = sum(1 for r in objs if r["kind"] != "text")
                if n > best[0]:
                    best = (n, pi)
            page_index = best[1]
        page_index = max(0, min(npages - 1, int(page_index)))
        objs = _objects(pdf, page_index)
        mb = [float(v) for v in pdf.pages[page_index].mediabox]
    pw, ph = mb[2] - mb[0], mb[3] - mb[1]
    page_area = max(1.0, pw * ph)
    for r in objs:
        r["role"] = _role(r, page_area)

    # The product on the page: a photo of it, or a template's coloured die.
    photos = [r for r in objs if r["role"] == "photo"]
    bodies = [r for r in objs if r["role"] == "body"]
    layout, product_box = "plain", None
    if bodies:
        b = max(bodies, key=lambda r: r["area"])
        layout, product_box = "template", b["bbox"]
    elif photos:
        b = max(photos, key=lambda r: r["area"])
        layout, product_box = "photo", b["bbox"]
    panels = []
    if not bodies and not photos:
        # The product drawn flat as separate shapes (a proof's Side 1, Side 2
        # and Bottom): solid fills of one colour, each big enough to carry art.
        cands = [r for r in objs if r["role"] == "art" and r["kind"] == "path"
                 and r["op"] not in ("S", "s") and r["fill"] is not None and not _is_light(r["fill"])
                 and r["area"] >= 0.015 * page_area]
        groups = {}
        for r in cands:
            groups.setdefault(tuple(round(c * 20) for c in r["fill"]), []).append(r)
        for grp in groups.values():
            uniq = []
            for r in sorted(grp, key=lambda r: -r["area"]):
                if not any(all(abs(a - b) < 3 for a, b in zip(r["bbox"], u["bbox"])) for u in uniq):
                    uniq.append(r)

            def holds(r):
                b = r["bbox"]
                return sum(1 for o in objs if o is not r and o["role"] in ("art", "text") and o["area"] < r["area"]
                           and _inside(((o["bbox"][0] + o["bbox"][2]) / 2, (o["bbox"][1] + o["bbox"][3]) / 2), b)
                           and o["fill"] != r["fill"]) >= 3
            # Panels carry the art: at least one of them holds other things in
            # another colour. Big shapes of one colour that hold nothing (the
            # strokes of a script word, a solid black illustration) are art.
            if uniq and any(holds(u) for u in uniq):
                panels += [u["bbox"] for u in uniq]
                for r in grp:
                    r["role"] = "body"
    if panels:
        # The shapes' own outlines and shadows are the product too.
        for r in objs:
            if r["role"] in ("art", "guide") and any(all(abs(a - b) < 4 for a, b in zip(r["bbox"], pb))
                                                     for pb in panels):
                r["role"] = "body"
        layout = "flats"
        product_box = (min(b[0] for b in panels), min(b[1] for b in panels),
                       max(b[2] for b in panels), max(b[3] for b in panels))
    elif not bodies and not photos:
        # A template drawn in outline only: its biggest guide box is the die.
        guides = [r for r in objs if r["role"] == "guide" and r["kind"] == "path"]
        if guides:
            g = max(guides, key=lambda r: r["area"])
            if g["area"] >= 0.08 * page_area:
                layout, product_box = "template", g["bbox"]

    # Template guides in colour (the die line's red, the safe-area cyan) mark
    # everything else drawn in that colour as a guide too: a dashed circle,
    # "ART ↑ Bottom" — often drawn see-through, so lighter than the line.
    guide_cols = {tuple(round(c, 2) for c in r["stroke"]) for r in objs
                  if r["kind"] == "path" and r["op"] in ("S", "s") and r["role"] in ("guide", "background")
                  and r["stroke"] is not None}
    guide_cols = [c for c in guide_cols if max(c) - min(c) > 0.15]      # coloured, not black/grey
    for r in objs:
        if r["role"] == "art" and r["kind"] == "path":
            c = r["stroke"] if r["op"] in ("S", "s") else r["fill"]
            if _guide_colour(c, guide_cols):
                r["role"] = "guide"

    pieces = []

    def add_piece(part):
        xs0 = min(r["bbox"][0] for r in part); ys0 = min(r["bbox"][1] for r in part)
        xs1 = max(r["bbox"][2] for r in part); ys1 = max(r["bbox"][3] for r in part)
        if xs1 - xs0 < 1.5 and ys1 - ys0 < 1.5:
            return
        role = "photo" if any(r["role"] == "photo" for r in part) else \
               ("text" if all(r["role"] == "text" for r in part) else "art")
        pieces.append({
            "id": len(pieces), "role": role,
            "bbox": [xs0, ys0, xs1, ys1],
            "center": ((xs0 + xs1) / 2, (ys0 + ys1) / 2),
            "area": (xs1 - xs0) * (ys1 - ys0),
            "objs": [[r["owner"], r["idx"]] for r in part],
            "sig": [(r["kind"], round(r["bbox"][2] - r["bbox"][0], 1), round(r["bbox"][3] - r["bbox"][1], 1))
                    for r in part],
            "kinds": sorted({r["kind"] for r in part}),
        })

    # A photo is its own piece: the logo sitting on it must not join it, nor
    # join everything else the photo touches.
    for r in objs:
        if r["role"] == "photo":
            add_piece([r])
    # Art and text group separately: a proof's text is often one text object
    # running down the whole sheet, and would swallow every logo it crosses.
    for grp in _cluster([r for r in objs if r["role"] == "art"]):
        add_piece(grp)
    # A text object covering a good part of the sheet is the form itself; it
    # isn't offered (it would catch every click on the page).
    for grp in _cluster([r for r in objs if r["role"] == "text" and r["area"] < 0.05 * page_area]):
        add_piece(grp)

    lines = _text_lines(src, page_index, mb)
    info = proof_info(lines, slot_ids)
    panel_of = {}
    if layout == "flats":
        sugg, rot, same, panel_of = _suggest_flats(pieces, panels, lines, slot_ids)
    else:
        sugg, rot, same = _suggest(pieces, product_box, layout, slot_ids,
                                   guides=[r["bbox"] for r in objs if r["role"] == "guide" and r["kind"] == "path"])
    if "same" in info and "side2" in slot_ids:
        same = info["same"]             # the page says so

    png, scale, _ = _render(src, page_index, RENDER_LONG_SIDE)
    (work / "pieces.json").write_text(json.dumps({
        "page_index": page_index, "mediabox": mb,
        "pieces": [{k: p[k] for k in ("id", "objs", "bbox", "role")} for p in pieces]}))

    def px_box(b):
        return [round((b[0] - mb[0]) * scale, 1), round((mb[3] - b[3]) * scale, 1),
                round((b[2] - b[0]) * scale, 1), round((b[3] - b[1]) * scale, 1)]

    return {
        "token": token, "page": page_index + 1, "pages": npages,
        "png": png, "scale": scale, "size": [pw, ph], "layout": layout,
        "product_box": px_box(product_box) if product_box else None,
        "pieces": [{"id": p["id"], "box": px_box(p["bbox"]), "role": p["role"],
                    "kinds": p["kinds"], "suggest": sugg.get(p["id"])} for p in pieces],
        "rot": rot, "same": same, "info": info,
        "panels": {k: px_box(v) for k, v in panel_of.items()},
    }


def place(root, token, assign, rot=None):
    """
    assign: {slot_id: [piece ids]}; rot: {slot_id: 0 | 180}.
    Writes <slot>.pdf per location (only the chosen pieces, cropped to them,
    upright) and returns {slot_id: {"path", "w_in", "h_in"}}.
    """
    work = pick_dir(root) / token
    meta = json.loads((work / "pieces.json").read_text())
    pi = meta["page_index"]
    by_id = {p["id"]: p for p in meta["pieces"]}
    out = {}
    for sid, ids in assign.items():
        chosen = [by_id[i] for i in ids if i in by_id]
        if not chosen:
            continue
        keep = {(o[0], o[1]) for p in chosen for o in p["objs"]}
        stripped = work / f"{sid}.stripped.pdf"
        shutil.copy2(str(work / "src.pdf"), str(stripped))
        with pikepdf.open(str(stripped), allow_overwriting_input=True) as pdf:
            tif_import._rewrite(pdf, lambda r, keep=keep: (r["owner"], r["idx"]) in keep, pi)
            pdf.save(str(stripped))
        x0 = min(p["bbox"][0] for p in chosen) - 1; y0 = min(p["bbox"][1] for p in chosen) - 1
        x1 = max(p["bbox"][2] for p in chosen) + 1; y1 = max(p["bbox"][3] for p in chosen) + 1
        dest = work / f"art-{sid}.pdf"
        tif_import._crop(stripped, (x0, y0, x1, y1), int((rot or {}).get(sid) or 0), dest, pi)
        # Tighten to what actually paints (a clipped photo edge or an empty
        # group would otherwise pad the box).
        try:
            from screenprint import ink_bbox_points
            w, h = x1 - x0, y1 - y0
            ib = ink_bbox_points(str(dest), (0, 0, w, h))
            if ib and (ib[2] - ib[0]) > 2 and (ib[3] - ib[1]) > 2 and \
                    ((ib[2] - ib[0]) < w - 3 or (ib[3] - ib[1]) < h - 3):
                tight = work / f"art-{sid}.tight.pdf"
                tif_import._crop(dest, (ib[0] - 1, ib[1] - 1, ib[2] + 1, ib[3] + 1), 0, tight, 0)
                tight.replace(dest)
                x1, y1, x0, y0 = ib[2], ib[3], ib[0], ib[1]
        except Exception as e:
            print(f"art pick: tighten skipped: {e}")
        stripped.unlink(missing_ok=True)
        out[sid] = {"path": str(dest), "w_in": round((x1 - x0) / 72, 2), "h_in": round((y1 - y0) / 72, 2)}
    return out
