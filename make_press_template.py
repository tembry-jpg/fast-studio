"""
make_press_template.py — build a press template + spec for a product that shares
a base item's imprint areas but has its own cut (denim, burlap, suede ...).

Those materials don't stretch, so the flat is cut bigger than the 3m's and the
press sheets lay the koozies out on their own positions. The imprint stays the
base item's (3" x 3" sides, 1.875" bottom); only the die and the sheets differ.

Inputs, both straight out of Illustrator:
  --mass   the "Mass Export" PDF: one page per press sheet, in pairs per
           machine (STRYKER / DISCO / DBC, each plain + "- BTM"). Which page of
           a pair is the BTM one is read off the sheet (the BTM carries the
           half-moon arcs), not assumed from the page order.
  --oneup  the 1-up template: die (red), seams (purple), imprint (cyan).

Writes
  press/<pid>-24HR-1c.pdf        2 guide pages (proof shape) + the 6 sheets
  press/press_spec_<pid>.json    the spec press_layout.py reads

The guide pages are redrawn from the 1-up in the base template's colours and
page size, with the bottom circle where the base template has it, so every
proof-page constant (legend cover, info panel) carries over. The sheets get the
"NSO NUMBER" / "SPOT COLOR" captions the base template has, under the sheet's
own product line, so export stamps the order and ink on them.

    python3 tools/make_press_template.py --mass "0070 - Denim - Mass Export.pdf" \
        --oneup 0070-3u-1up_template.pdf --product 0070-3u --base 0070-3m
"""
import argparse
import json
import re
import sys
from pathlib import Path
from statistics import median

import pikepdf

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))

import measure_press_template as M          # noqa: E402

# Some 1-ups draw the imprint area in process cyan (C100) rather than the
# template teal; it renders as #00AEEF.
M.IMPRINT_RGB = list(M.IMPRINT_RGB) + [(0x00, 0xAE, 0xEF)]

MACHINES = {(23, 33): "STRYKER", (16, 23): "DISCO", (12, 14): "DBC"}
ORDER = ["STRYKER", "DISCO", "DBG", "DBC"]


def _layer_machine(pg):
    """The machine a sheet is for, from the Illustrator layer its artwork sits
    on ("DBG / JAVELIN / AUTO (16"W x 23"H) Vertical"), or None. Needed where
    two machines share a sheet size: DBG and DISCO are both 16 x 23."""
    try:
        props = pg.Resources.get("/Properties") or {}
        c = pg.obj.Contents
        d = b"".join(x.read_bytes() for x in c) if isinstance(c, pikepdf.Array) else c.read_bytes()
        parts = re.split(rb"/OC /(\w+) BDC", d)
        best = None
        for k in range(1, len(parts), 2):
            key = "/" + parts[k].decode()
            if key not in props:
                continue
            nm = str(props[key].get("/Name") or "")
            if best is None or len(parts[k + 1]) > best[1]:
                best = (nm, len(parts[k + 1]))
        if not best or best[1] < 200:
            return None
        n = best[0].upper()
        for m in ("STRYKER", "DISCO", "DBC"):
            if m in n:
                return m
        if "DBG" in n or "JAVELIN" in n:
            return "DBG"
    except Exception:
        pass
    return None

# The 1-up's CMYK guide colours -> the RGB the base templates (and
# press_layout's die fill / guide suppression) use.
DIE_RG = "0.847 0.118 0.2 RG"
SEAM_RG = "0.431 0.302 0.624 RG"
IMPRINT_RG = "0.365 0.784 0.863 RG"


def _kind(cmyk):
    c, m, y, k = cmyk
    if m > 0.8 and c < 0.3:
        return "die"
    if c > 0.5 and m > 0.5:
        return "seam"
    if c > 0.4 and m < 0.2:
        return "imprint"
    return None


def _form_ops(oneup):
    """The 1-up's drawing as (form ops recoloured, page-level cm, page size)."""
    pdf = pikepdf.open(oneup)
    pg = pdf.pages[0]
    page_ops = pg.Contents.read_bytes().decode("latin-1") if not isinstance(pg.obj.Contents, pikepdf.Array) \
        else b"".join(c.read_bytes() for c in pg.obj.Contents).decode("latin-1")
    # Two shapes so far: the whole drawing inside one form XObject placed with
    # a cm (the denim 1-up), or drawn straight on the page with only the labels
    # as forms (the burlap 1-up).
    m = re.search(r"([-\d.]+ [-\d.]+ [-\d.]+ [-\d.]+ [-\d.]+ [-\d.]+) cm\s*(?:0 TL)?\s*/(\w+) Do", page_ops)
    if m and not re.search(r"\sK\s", page_ops):
        cm, name = m.group(1), m.group(2)
        ops = pg.Resources.XObject["/" + name].read_bytes().decode("latin-1")
    else:
        cm = "1 0 0 1 0 0"
        ops = page_ops
        ops = re.sub(r"/OC /\w+ BDC|\bEMC\b", "", ops)
        ops = re.sub(r"[-\d.]+ [-\d.]+ [-\d.]+ [-\d.]+ re\s*\nW n", "", ops)
    # Labels / arrows ("ART", "Side 1") are nested forms: guide furniture.
    ops = re.sub(r"q\s*\n(?:[^\n]*\n){0,3}?(?:0 TL)?/Fm\d+ Do\s*\nQ\s*", "", ops)
    ops = re.sub(r"[^\n]*/Fm\d+ Do[^\n]*\n", "", ops)
    out, keep = [], True
    for line in ops.split("\n"):
        mk = re.fullmatch(r"\s*([\d.]+) ([\d.]+) ([\d.]+) ([\d.]+) K\s*", line)
        if mk:
            kind = _kind([float(v) for v in mk.groups()])
            keep = kind in ("die", "seam")          # imprint boxes: the base item's, drawn by spec
            if kind == "die":
                out.append(DIE_RG)
            elif kind == "seam":
                out.append(SEAM_RG)
            continue
        if re.fullmatch(r"\s*/GS\d+ gs\s*", line):
            continue
        if keep or re.fullmatch(r"\s*[\d.\s]+ w .*d\s*|\s*\[.*\]\s*[\d.]+ d\s*", line):
            out.append(line)
    # Dropped sections are balanced on their own; an outer q whose Q fell in
    # one is closed here so the stream stays balanced.
    opens = sum(1 for l in out if re.match(r"\s*q\b", l))
    closes = sum(1 for l in out if re.fullmatch(r"\s*Q\s*", l))
    out += ["Q"] * max(0, opens - closes)
    mb = [float(v) for v in pg.MediaBox]
    return "\n".join(out), cm, (mb[2] - mb[0], mb[3] - mb[1])


def _oneup_centre(oneup):
    """The bottom circle's centre on the 1-up page, from its imprint zones."""
    pdf = pikepdf.open(oneup)
    h = float(pdf.pages[0].MediaBox[3])
    zones, _ = M.measure_guide(oneup, 1, 300, h)
    zs = sorted(zones, key=lambda z: -z["cy"])
    return zs[0]["cx"], (zs[0]["cy"] + zs[-1]["cy"]) / 2


def _caption_lines(pdf_path, pno, page_h):
    """The product line's words -> (box in PDF space, orient)."""
    import subprocess
    xml = subprocess.run(["pdftotext", "-f", str(pno), "-l", str(pno), "-bbox", pdf_path, "-"],
                         capture_output=True, text=True).stdout
    words = [(float(a), float(b), float(c), float(d), t) for a, b, c, d, t in re.findall(
        r'<word xMin="([\d.]+)" yMin="([\d.]+)" xMax="([\d.]+)" yMax="([\d.]+)">([^<]*)</word>', xml)]
    if not words:
        return None
    first = next((w for w in words if re.match(r"^\d{4}$", w[4])), words[0])
    last = words[-1] if words[-1] is not first else words[0]
    fx, fy = (first[0] + first[2]) / 2, (first[1] + first[3]) / 2
    lx, ly = (last[0] + last[2]) / 2, (last[1] + last[3]) / 2
    if abs(fx - lx) >= abs(fy - ly):
        orient = 0 if fx < lx else 180
    else:
        orient = 90 if fy > ly else 270
    x0 = min(w[0] for w in words); x1 = max(w[2] for w in words)
    y0 = min(w[1] for w in words); y1 = max(w[3] for w in words)
    # pdftotext is top-down; to PDF space
    return dict(x0=x0, x1=x1, y0=page_h - y1, y1=page_h - y0, orient=orient)


def _caption_overlay(w, h, box, ink_free):
    """Content ops drawing NSO NUMBER / SPOT COLOR under the product line, in its orientation."""
    size = 24
    cx, cy = (box["x0"] + box["x1"]) / 2, (box["y0"] + box["y1"]) / 2
    o = box["orient"]
    # unit vectors: reading direction (along) and "down the page" in reading terms
    along = {0: (1, 0), 180: (-1, 0), 90: (0, 1), 270: (0, -1)}[o]
    down = {0: (0, -1), 180: (0, 1), 90: (1, 0), 270: (-1, 0)}[o]

    def place(off_down, off_along):
        return cx + down[0] * off_down + along[0] * off_along, cy + down[1] * off_down + along[1] * off_along

    lines = [("NSO NUMBER", 38), ("SPOT COLOR", 80)]
    spots = [place(d, 0) for _, d in lines]
    if not all(ink_free(x, y, 170, 34, o) for x, y in spots):
        # No room under the line: beside it, one each side.
        span = abs((box["x1"] - box["x0"]) if o in (0, 180) else (box["y1"] - box["y0"]))
        spots = [place(0, -(span / 2 + 110)), place(0, span / 2 + 110)]
    ops = []
    import math
    a = math.radians(o)
    ca, sa = math.cos(a), math.sin(a)
    for (text, _), (x, y) in zip(lines, spots):
        tw = len(text) * size * 0.62
        # text origin: centre minus half width along, minus a third of size down
        ox = x - along[0] * tw / 2 + down[0] * size * 0.35
        oy = y - along[1] * tw / 2 + down[1] * size * 0.35
        ops.append(f"BT /FCap {size} Tf {ca:.4f} {sa:.4f} {-sa:.4f} {ca:.4f} {ox:.2f} {oy:.2f} Tm 0 g ({text}) Tj ET")
    return "\n".join(ops)


def build(mass, oneup, pid, base, out_pdf, out_spec):
    base_spec = json.loads((HERE / "press" / f"press_spec_{base}.json").read_text()) \
        if (HERE / "press" / f"press_spec_{base}.json").exists() else None
    if base_spec is None:
        import press_layout as PL
        base_spec = json.loads(Path(PL.PRESS_TEMPLATES[base]["spec"]).read_text())
    import press_layout as PL
    base_pdf = pikepdf.open(PL.PRESS_TEMPLATES[base]["template"])
    gw, gh = [float(v) for v in list(base_pdf.pages[1].MediaBox)[2:]]
    bz = base_spec["guide_pages"]["2"]["zones"]
    bcx, bcy = bz["bottom"]["cx"], bz["bottom"]["cy"]

    # ── classify the sheets ──────────────────────────────────────────────────
    # Sheets come in pairs of the same size (plain + - BTM, either order). A
    # machine can have more than one pair: the 1080's STRYKER is laid out once
    # for one side and once for two different sides, told apart the way
    # derive_artboards names them (two-sided sheets sit on the centre line).
    import derive_artboards as DA
    src = pikepdf.open(mass)
    info = []
    for i, pg in enumerate(src.pages):
        w, h = [float(v) for v in list(pg.MediaBox)[2:]]
        mach = MACHINES.get((round(w / 72), round(h / 72)))
        if not mach:
            print(f"  ! sheet {i+1}: {w/72:.0f}x{h/72:.0f} in is no known machine — skipped")
            continue
        by_layer = _layer_machine(pg)
        if by_layer and by_layer != mach:
            mach = by_layer                 # same sheet size, different machine
        pos = M.press_positions(mass, i + 1, w, h, dpi=100)
        info.append({"i": i, "w": w, "h": h, "mach": mach, "pos": pos})
    # Pair each machine's - BTM sheets with its plain ones in the order they
    # appear: next to each other (most exports) or all plain then all BTM (0262).
    pairs = []
    for mach in dict.fromkeys(x["mach"] for x in info):
        btms = [x for x in info if x["mach"] == mach and x["pos"]]
        plains = [x for x in info if x["mach"] == mach and not x["pos"]]
        if len(btms) != len(plains):
            raise SystemExit(f"{mach}: {len(btms)} - BTM sheet(s) but {len(plains)} plain one(s)")
        for btm, plain in zip(btms, plains):
            nm = DA.name_for((btm["w"], btm["h"]), btm["pos"], True, offsets=base_spec["offsets"]) or btm["mach"]
            _, layout = DA.parse_name(nm) if nm.startswith(btm["mach"]) else (None, None)
            pairs.append({"mach": btm["mach"], "layout": layout, "btm": btm, "plain": plain})
    layouts = {}
    for pr in pairs:
        layouts.setdefault(pr["mach"], set()).add(pr["layout"])
    for pr in pairs:                       # one layout on a machine: no layout to choose
        if len(layouts[pr["mach"]]) == 1:
            pr["layout"] = None
    order = {m: n for n, m in enumerate(ORDER)}
    pairs.sort(key=lambda pr: (order.get(pr["mach"], 9), str(pr["layout"])))

    # ── output pdf: guides then sheets ───────────────────────────────────────
    out = pikepdf.new()
    if oneup:
        ops, cm, _ = _form_ops(oneup)
        ux, uy = _oneup_centre(oneup)
        dx, dy = bcx - ux, bcy - uy
        guide_ops = f"q 1 0 0 1 {dx:.4f} {dy:.4f} cm\nq {cm} cm\n1 J 1 j 1 w\n{ops}\nQ\nQ\n"
        for _ in range(2):
            pg = pikepdf.Page(pikepdf.Dictionary(
                Type=pikepdf.Name.Page, MediaBox=[0, 0, gw, gh],
                Resources=pikepdf.Dictionary(),
                Contents=out.make_stream(guide_ops.encode("latin-1"))))
            out.pages.append(pg)
    else:
        # Same cut as the base item: its own guide pages, as they are.
        for gi in (0, 1):
            out.pages.append(base_pdf.pages[gi])

    font = out.make_indirect(pikepdf.Dictionary(Type=pikepdf.Name.Font, Subtype=pikepdf.Name.Type1,
                                                BaseFont=pikepdf.Name.Helvetica,
                                                Encoding=pikepdf.Name.WinAnsiEncoding))
    from pdf2image import convert_from_path
    import numpy as np
    plan = []
    for n, pr in enumerate(pairs):
        for kind in ("plain", "btm"):
            sh = pr[kind]
            plan.append((n, kind, sh["i"], sh["w"], sh["h"]))
    src_caps = PL.find_template_labels(str(mass), len(src.pages))
    for mach, kind, i, w, h in plan:
        out.pages.append(src.pages[i])
        pg = out.pages[-1]
        pg.contents_coalesce()
        # Sheets that already carry the captions (the burlap's) keep their own.
        has_caps = len((src_caps.get(i + 1) or {})) == 2
        box = None if has_caps else _caption_lines(mass, i + 1, h)
        if box:
            img = np.asarray(convert_from_path(mass, dpi=72, first_page=i + 1, last_page=i + 1)[0].convert("L")) < 245

            def ink_free(x, y, bw, bh, o):
                if o in (90, 270):
                    bw, bh = bh, bw
                x0, x1 = int(x - bw / 2), int(x + bw / 2)
                y0, y1 = int(h - y - bh / 2), int(h - y + bh / 2)
                if x0 < 0 or y0 < 0 or x1 >= img.shape[1] or y1 >= img.shape[0]:
                    return False
                return not img[y0:y1, x0:x1].any()

            cap = _caption_overlay(w, h, box, ink_free)
            res = pg.obj.Resources
            if "/Font" not in res:
                res.Font = pikepdf.Dictionary()
            res.Font.FCap = font
            data = pg.obj.Contents.read_bytes() + b"\nq\n" + cap.encode("latin-1") + b"\nQ\n"
            pg.obj.Contents = out.make_stream(data)
    out.save(out_pdf)

    # ── spec ─────────────────────────────────────────────────────────────────
    from pdf2image import convert_from_path
    s = 300 / 72
    gimg = convert_from_path(str(out_pdf), dpi=300, first_page=2, last_page=2)[0].convert("RGB")
    if oneup:
        regions = M.die_regions(gimg, s, gh)
        seams = M.seam_lines(gimg, s, gh)
    else:
        regions = (base_spec.get("die_regions") or {}).get("2") or M.die_regions(gimg, s, gh)
        seams = base_spec.get("seams")
    panels = regions["panels"]                       # [top panel], [bottom panel]
    cy = bcy
    d1 = (panels[0][0] + panels[0][1]) / 2 - cy
    d2 = (panels[1][0] + panels[1][1]) / 2 - cy
    off = dict(base_spec["offsets"])
    if oneup:
        off.update({"d_side1": d1, "d_side2": d2})
    sw, sh, cd = off["side_w"], off["side_h"], off["circle_d"]

    def zone(cx_, cy_, w_, h_):
        return {"left": cx_ - w_ / 2, "top": cy_ + h_ / 2, "w": w_, "h": h_, "cx": cx_, "cy": cy_}
    z2 = {"side1": zone(bcx, cy + d1, sw, sh), "side2": zone(bcx, cy + d2, sw, sh),
          "bottom": zone(bcx, cy, cd, cd)}
    guides = {"1": {"sides": ["side1"], "zones": {"side1": z2["side1"], "bottom": z2["bottom"]}},
              "2": {"sides": ["side1", "side2"], "zones": z2}}
    if not oneup:
        guides = base_spec["guide_pages"]

    press_pages = {}
    gaps = []
    measured = {}
    for n, (pi, kind, i, w, h) in enumerate(plan, start=3):
        if kind == "btm":
            measured[pi] = M.press_positions(str(out_pdf), n, w, h, dpi=100)
            gaps += [p["gap"] for p in measured[pi]]
    g = median(gaps)
    for n, (pi, kind, i, w, h) in enumerate(plan, start=3):
        if kind == "btm":
            measured[pi] = M.press_positions(str(out_pdf), n, w, h, dpi=100, expected_gap=g)
    for n, (pi, kind, i, w, h) in enumerate(plan, start=3):
        mach, layout = pairs[pi]["mach"], pairs[pi]["layout"]
        name = mach + (" - BTM" if kind == "btm" else "")
        pp = {"page": [w, h], "positions": [{k: (round(v, 2) if isinstance(v, float) else v)
                                              for k, v in p.items()} for p in measured[pi]],
              "artboard": name, "_artboard_as_drawn": name, "machine": mach, "layout": layout}
        if kind == "plain":
            pp["positions_from"] = str(n + 1)
        press_pages[str(n)] = pp

    caps = PL.find_template_labels(str(out_pdf), len(plan) + 2)
    for pn, pp in press_pages.items():
        cap = (caps.get(int(pn)) or {}).get("spot")
        if cap:
            spot = DA.clear_spot_near_slug(str(out_pdf), int(pn), cap, pp["page"][1])
            if spot:
                pp["name_at"] = list(spot)

    spec = {
        "_scope": f"CALIBRATED FOR {pid} ONLY — do not use for any other product",
        "_template_file": f"{Path(mass).name} (press sheets) + " + (f"guide pages redrawn from {Path(oneup).name}" if oneup else f"the {base} guide pages (same cut)"),
        "_measured_by": "tools/make_press_template.py",
        "template": f"{pid.upper()} - own cut, {base} imprint areas",
        "product": pid,
        "guide_pages": guides,
        "offsets": off,
        "press_pages": press_pages,
        "die_regions": (base_spec.get("die_regions") if not oneup and base_spec.get("die_regions")
                        else {"1": regions, "2": regions}),
        "seams": seams,
        "products": [pid],
        "_arcless_pages_filled": [f"page {n} uses page {n+1} positions"
                                  for n in range(3, 3 + len(plan), 2)],
    }
    for k in ("proof_cover", "info_panel", "flat_proof"):
        if k in base_spec:
            spec[k] = base_spec[k]
    Path(out_spec).write_text(json.dumps(spec, indent=1) + "\n")
    return spec


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--mass", required=True)
    ap.add_argument("--oneup", default=None,
                    help="the 1-up; leave out when the cut is the base item's (its guide pages are used)")
    ap.add_argument("--product", required=True)
    ap.add_argument("--base", required=True)
    a = ap.parse_args()
    out_pdf = HERE / "press" / f"{a.product}-24HR-1c.pdf"
    out_spec = HERE / "press" / f"press_spec_{a.product}.json"
    sp = build(a.mass, a.oneup, a.product, a.base, out_pdf, out_spec)
    print(f"{out_pdf.name}, {out_spec.name}")
    print(" offsets", {k: round(v, 2) for k, v in sp["offsets"].items()})
    for pn, pp in sp["press_pages"].items():
        print(f"  p{pn} {pp['artboard']:<16} {len(pp['positions'])} positions  name_at {pp.get('name_at')}")
