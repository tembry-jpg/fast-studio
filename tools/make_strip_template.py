"""
make_strip_template.py — press template + spec for a flat strip that folds
over its middle (the key fob, 0635-3m).

Unlike the koozies there is no bottom disc and no "- BTM" sheet: each press
sheet carries a few strips, each marked by its rounded-end arcs and a pair of
short ticks on the fold. Side 1 is the left half of the strip, Side 2 the
right; both print the same way up.

Inputs:
  --mass   the Mass Export (one sheet per machine; machine read from the
           Illustrator layer, else the sheet size)
  --oneup  the 1-up: die (red), stitching (purple dashes — straight, not
           zig-zag), fold (grey), imprint areas (cyan rectangles)

    python3 tools/make_strip_template.py --mass "0635-Neo_Mass_Export.pdf" \
        --oneup 0635-3m-1up_screen_print.pdf --product 0635-3m
"""
import argparse
import json
import re
import sys
from pathlib import Path

import pikepdf

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "tools"))

import measure_press_template as M          # noqa: E402
import make_press_template as T             # noqa: E402

MARGIN = 36.0


def _page_ops(pdf_path):
    pdf = pikepdf.open(pdf_path)
    pg = pdf.pages[0]
    c = pg.obj.Contents
    d = b"".join(x.read_bytes() for x in c) if isinstance(c, pikepdf.Array) else c.read_bytes()
    mb = [float(v) for v in pg.MediaBox]
    return d.decode("latin-1"), (mb[2] - mb[0], mb[3] - mb[1])


def _geometry(oneup):
    """Imprint rectangles, fold x, stitch lines and die box, in 1-up points."""
    ops, (w, h) = _page_ops(oneup)
    blocks = re.split(r"\n([\d.]+ [\d.]+ [\d.]+ [\d.]+) K\n", "\n" + ops)
    geo = {"imprint": [], "stitch": [], "fold": None}
    for k in range(1, len(blocks), 2):
        kind = T._kind([float(v) for v in blocks[k].split()])
        cmyk = [float(v) for v in blocks[k].split()]
        body = blocks[k + 1]
        if kind == "imprint":
            for m in re.finditer(r"([-\d.]+) ([-\d.]+) ([-\d.]+) ([-\d.]+) re", body):
                x, y, rw, rh = map(float, m.groups())
                geo["imprint"].append((min(x, x + rw), min(y, y + rh), abs(rw), abs(rh)))
        lines = [(float(a), float(b), float(c2)) for a, b, c2 in re.findall(
            r"q 1 0 0 1 ([-\d.]+) ([-\d.]+) cm\n0 0 m\n0 ([-\d.]+) l\nS", body)]
        if kind == "seam":
            geo["stitch"] += [(x, min(y, y + dy), max(y, y + dy)) for x, y, dy in lines]
        elif kind is None and cmyk[:3] == [0, 0, 0] and lines:
            x, y, dy = lines[0]
            geo["fold"] = (x, min(y, y + dy), max(y, y + dy))
    geo["imprint"].sort()
    return geo, (w, h)


def _ticks(pdf, pno, w, h, dpi=150):
    """Fold ticks on a sheet: short horizontal strokes, ~30 pt wide."""
    from pdf2image import convert_from_path
    img = convert_from_path(pdf, dpi=dpi, first_page=pno, last_page=pno)[0]
    s = dpi / 72.0
    out = []
    for x0, y0, x1, y1, n in M._components(img, dpi):
        tw, th = (x1 - x0 + 1) / s, (y1 - y0 + 1) / s
        if 20 <= tw <= 45 and th <= 3:
            out.append(((x0 + x1 + 1) / 2 / s, h - (y0 + y1 + 1) / 2 / s))
    return out


def _positions(ticks):
    """Pair ticks on the same x, top with the one below it: one strip each."""
    cols = {}
    for x, y in ticks:
        key = round(x / 4)
        cols.setdefault(key, []).append((x, y))
    pos = []
    for pts in cols.values():
        pts.sort(key=lambda p: -p[1])
        for a, b in zip(pts[0::2], pts[1::2]):
            pos.append({"cx": round((a[0] + b[0]) / 2, 2), "cy": round((a[1] + b[1]) / 2, 2),
                        "gap": round(a[1] - b[1], 2), "vertical": False})
    pos.sort(key=lambda p: (-p["cy"], p["cx"]))
    return pos


def build(mass, oneup, pid, out_pdf, out_spec):
    import press_layout as PL
    import derive_artboards as DA
    geo, (w1, h1) = _geometry(oneup)
    if len(geo["imprint"]) != 2 or not geo["fold"]:
        raise SystemExit(f"1-up: expected two imprint areas and a fold, got {geo}")
    m = MARGIN
    gw, gh = w1 + 2 * m, h1 + 2 * m

    # ── guide pages: the 1-up redrawn in the template colours ───────────────
    out = pikepdf.new()
    ops, cm, _ = T._form_ops(oneup)
    guide_ops = f"q 1 0 0 1 {m} {m} cm\nq {cm} cm\n1 J 1 j 1 w\n{ops}\nQ\nQ\n"
    for _ in range(2):
        out.pages.append(pikepdf.Page(pikepdf.Dictionary(
            Type=pikepdf.Name.Page, MediaBox=[0, 0, gw, gh], Resources=pikepdf.Dictionary(),
            Contents=out.make_stream(guide_ops.encode("latin-1")))))

    # ── sheets ───────────────────────────────────────────────────────────────
    src = pikepdf.open(mass)
    sheets = []
    for i, pg in enumerate(src.pages):
        w, h = [float(v) for v in list(pg.MediaBox)[2:]]
        mach = T._layer_machine(pg) or T.MACHINES.get((round(w / 72), round(h / 72)))
        if not mach:
            print(f"  ! sheet {i+1}: no machine — skipped")
            continue
        sheets.append((mach, i, w, h))
    order = {k: n for n, k in enumerate(T.ORDER)}
    sheets.sort(key=lambda t: order.get(t[0], 9))
    for mach, i, w, h in sheets:
        out.pages.append(src.pages[i])
    out.save(out_pdf)

    # ── spec ─────────────────────────────────────────────────────────────────
    fx, fy0, fy1 = geo["fold"]
    (ax, ay, aw, ah), (bx, by, bw, bh) = geo["imprint"]
    zone = lambda x, y, zw, zh: {"left": x + m, "top": y + zh + m, "w": zw, "h": zh,
                                 "cx": x + zw / 2 + m, "cy": y + zh / 2 + m}
    z1, z2 = zone(ax, ay, aw, ah), zone(bx, by, bw, bh)
    off = {"side_w": aw, "side_h": ah, "circle_d": 0.0,
           "d_side1": (ax + aw / 2) - fx, "d_side2": (bx + bw / 2) - fx}
    # The die's extent, from its stroke on the guide page.
    from pdf2image import convert_from_path
    s = 300 / 72
    gimg = convert_from_path(str(out_pdf), dpi=300, first_page=2, last_page=2)[0].convert("RGB")
    pts = M._mask_points(gimg, M.DIE_RGB)
    xs = [x for x, _ in pts]; ys = [y for _, y in pts]
    die = {"x": [min(xs) / s, max(xs) / s], "y": [gh - max(ys) / s, gh - min(ys) / s],
           "fold_x": fx + m}
    die["panels"] = [die["y"], die["y"]]
    press_pages = {}
    for n, (mach, i, w, h) in enumerate(sheets, start=3):
        press_pages[str(n)] = {"page": [w, h], "rotation": 0,
                               "positions": _positions(_ticks(str(out_pdf), n, w, h)),
                               "artboard": mach, "_artboard_as_drawn": mach, "machine": mach, "layout": None}
    caps = PL.find_template_labels(str(out_pdf), len(sheets) + 2)
    for pn, pp in press_pages.items():
        cap = (caps.get(int(pn)) or {}).get("spot")
        if cap:
            spot = DA.clear_spot_near_slug(str(out_pdf), int(pn), cap, pp["page"][1])
            if spot:
                pp["name_at"] = list(spot)
    spec = {
        "_scope": f"CALIBRATED FOR {pid} ONLY — do not use for any other product",
        "_template_file": f"{Path(mass).name} (press sheets) + guide pages redrawn from {Path(oneup).name}",
        "_measured_by": "tools/make_strip_template.py",
        "template": f"{pid.upper()} - folded strip",
        "product": pid, "products": [pid],
        "guide_pages": {"1": {"sides": ["side1"], "zones": {"side1": z1}},
                        "2": {"sides": ["side1", "side2"], "zones": {"side1": z1, "side2": z2}}},
        "offsets": off,
        "side2_turn": 0,
        "press_pages": press_pages,
        "die_regions": {"1": die, "2": die},
        "seams": {"style": "straight", "xs": [x + m for x, _, _ in geo["stitch"]],
                  "bands": [[y0 + m, y1 + m] for _, y0, y1 in geo["stitch"]]},
        "fold_lines": [[fx + m, fy0 + m, fx + m, fy1 + m]],
        "flat_proof": {"layout": "strip", "always_show": ["side1", "side2"]},
        "proof_cover": [0, 0, 0, 0],
        "info_panel": {"x": 4, "y_top": -1000, "w": 10, "scale": 0.1},
    }
    Path(out_spec).write_text(json.dumps(spec, indent=1) + "\n")
    return spec


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--mass", required=True)
    ap.add_argument("--oneup", required=True)
    ap.add_argument("--product", required=True)
    a = ap.parse_args()
    out_pdf = HERE / "press" / f"{a.product}-24HR-1c.pdf"
    out_spec = HERE / "press" / f"press_spec_{a.product}.json"
    sp = build(a.mass, a.oneup, a.product, out_pdf, out_spec)
    print(out_pdf.name, out_spec.name)
    print(" offsets", {k: round(v, 2) for k, v in sp["offsets"].items()})
    print(" zones", json.dumps(sp["guide_pages"]["2"]["zones"]))
    print(" seams", sp["seams"], "fold", sp["fold_lines"], "die", sp["die_regions"]["1"])
    for pn, pp in sp["press_pages"].items():
        print(f"  p{pn} {pp['artboard']:<8} {pp['positions']}  name_at {pp.get('name_at')}")
