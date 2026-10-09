"""Press template and spec for the 5010 Daily Grind tote, This Is Fast
(5010-TIF-10-1C natural, 5010-TIF-CC-1C colored canvas).

Sources (press/tif/):
  5010-CC - Daily Grind - THIS IS FAST.pdf  the template customers fill in
                                            (Side 1 Front only - 1 Side)
  5010 - Canvas Mass Export.pdf             7 press sheets
  5010-1up.pdf                              the die drawing (red die, green
                                            body, purple sew lines, grey hem)

Output press/5010-TIF-1C.pdf = page 1 the TIF template (the guide), pages 2-8
the mass export with "NSO NUMBER" / "SPOT COLOR" captions added beside each
sheet's own label so the export stamps the order and ink there.

Geometry, all measured off the files:
  die 1224 x 2448 pt (17" x 34"): two 17"-wide halves, Front on top, Back
  below, hem (grey, folds inside) at each end, the bag bottom between.
  Imprint 793.8 x 828 pt (11.03" x 11.5"), centred across the die,
  566.3 pt from the registration targets at the Front's hem end.
  Every sheet carries the die's own registration targets (circle + cross,
  504 pt apart, 54.07 pt in from the hem edge), so each imprint is placed
  from the targets:
    sheets 1-4, 6, 7  one half of the die on its side, hem at the left:
                      art reads toward the hem (turned 90 deg)
    sheet 5           the whole die upright, Side 1 above Side 2 (head-down)

    python3 tools/make_5010_template.py
"""
import json
from pathlib import Path
import pikepdf
from reportlab.pdfgen import canvas as rlcanvas

HERE = Path(__file__).resolve().parent.parent
TIF = HERE / "press" / "tif" / "5010-CC - Daily Grind - THIS IS FAST.pdf"
MASS = HERE / "press" / "tif" / "5010 - Canvas Mass Export.pdf"
OUT = HERE / "press" / "5010-TIF-1C.pdf"
SPEC = HERE / "press" / "press_spec_5010.json"

ZW, ZH = 793.8, 828.0
T_TO_Z = 2395.312 - 1829.009     # targets -> Side 1 centre, along the die (566.30)
D = 1829.009 - 1225.439          # die middle -> each imprint centre (603.57)

# Mass export pages: (target x, target y centres, side, artboard name, press,
# caption anchor (x, y, rot)) - sideways halves. The names are the mass
# export's own artboard names (read from its Illustrator data).
SIDEWAYS = {
    1: (261.7, [576.0, 1800.0], "side1", "STRYKER 2 pz Front", "STRYKER", (900, 1176, 180)),
    2: (261.7, [576.0, 1800.0], "side2", "STRYKER 2 pz Back", "STRYKER", (900, 1176, 180)),
    3: (261.7, [1188.0], "side1", "STRYKER 1 pz Front", "STRYKER", (900, 1788, 180)),
    4: (261.7, [1188.0], "side2", "STRYKER 1 pz Back", "STRYKER", (900, 1788, 180)),
    6: (84.9, [828.0], "side1", "AUTO Front", "AUTO", (760, 1428, 180)),
    7: (84.9, [828.0], "side2", "AUTO Back", "AUTO", (760, 1428, 180)),
}
# Sheet 5: the die upright, targets at x 576 / 1080, y 18.2 (Back end) and
# 2357.9 (Front end): the die's middle at y 2357.9 - (2395.312 - 1225.439).
P5_CX, P5_CY = 828.0, round(2357.9 - (2395.312 - 1225.439), 2)

src_t = pikepdf.open(str(TIF))
src_m = pikepdf.open(str(MASS))
out = pikepdf.new()
out.pages.append(src_t.pages[0])
for p in src_m.pages:
    out.pages.append(p)


def captions(pg_index, w, h, anchor):
    """Live 'NSO NUMBER' and 'SPOT COLOR' beside the sheet's label (the
    export finds them and prints the order number and ink there)."""
    x, y, rot = anchor
    tmp = OUT.with_suffix(f".cap{pg_index}.pdf")
    c = rlcanvas.Canvas(str(tmp), pagesize=(w, h))
    c.setFont("Helvetica", 16)
    c.setFillColorRGB(0, 0, 0)
    c.translate(x, y)
    c.rotate(rot)
    c.drawString(0, 0, "NSO NUMBER")
    c.drawString(150, 0, "SPOT COLOR")
    c.save()
    with pikepdf.open(str(tmp)) as cap:
        out.pages[pg_index].add_overlay(cap.pages[0])
    tmp.unlink()


press = {}
for mp in range(1, 8):
    pg = out.pages[mp]          # mass page mp is output page mp + 1
    mb = [float(v) for v in pg.obj.MediaBox]
    w, h = mb[2] - mb[0], mb[3] - mb[1]
    if mp in SIDEWAYS:
        tx, ys, side, name, machine, anchor = SIDEWAYS[mp]
        cx = round(tx + T_TO_Z, 2)
        # rot is the turn Side 1 gets; Side 2 gets rot + 180, so a Back-only
        # sheet records -90 to give its art the same 90-degree turn.
        rot = 90 if side == "side1" else -90
        positions = [{"cx": cx, "cy": y, "gap": 0.0, "vertical": True,
                      "axis": [0, 0], "rot": rot} for y in ys]
        layout = "1side"
        sides = [side]
        name_at = [anchor[0] - 420 if anchor[2] == 180 else anchor[0], anchor[1], anchor[2]]
    else:
        anchor = (1426, 1700, 90)
        name, machine, layout, sides = "STRYKER 1 pz 2 Side diff", "STRYKER", "2diff", ["side1", "side2"]
        positions = [{"cx": P5_CX, "cy": P5_CY, "gap": 0.0, "vertical": True,
                      "axis": [0, 1], "rot": 0}]
        name_at = [1426, 2120, 90]
    captions(mp, w, h, anchor)
    press[str(mp + 1)] = {"page": [w, h], "rotation": 0, "positions": positions,
                          "artboard": name, "machine": machine, "layout": layout,
                          "sides": sides, "name_at": name_at}
out.save(str(OUT))

# TIF template (page 1): die [573.5, 74.4, 1797.5, 2522.3]; cyan imprint
# boxes measured from its dashed sides.
Z1 = {"cx": 1186.9, "cy": 1902.8, "w": ZW, "h": ZH, "left": 790.0, "top": 2316.8}
spec = {
    "_scope": "5010 Daily Grind tote, This Is Fast: 5010-TIF-10-1C (natural) and 5010-TIF-CC-1C (colored canvas) - one die, one template, one mass export; only the canvas colour differs.",
    "_template_file": "5010-TIF-1C.pdf (tools/make_5010_template.py): page 1 = '5010-CC - Daily Grind - THIS IS FAST' (1 Side, Front); pages 2-8 = '5010 - Canvas Mass Export' with NSO NUMBER / SPOT COLOR captions added.",
    "_measured_by": "each sheet's registration targets (the die's own, 504 pt apart, 54.07 pt in from the hem edge); the imprint is 566.30 pt from them along the die, centred across it, as on the 1-up and the TIF template.",
    "_unverified": "Never checked against a printed sheet. Confirm on the first job: the art lands in the imprint, and on the sideways sheets it reads toward the hem (the targets' side).",
    "template": "5010 - Daily Grind",
    "product": "5010-TIF-10-1C",
    "products": ["5010-TIF-10-1C", "5010-TIF-CC-1C"],
    "guide_pages": {"1": {"sides": ["side1"], "zones": {"side1": Z1}}},
    "offsets": {"side_w": ZW, "side_h": ZH, "circle_d": 0.0,
                "d_side1": round(D, 3), "d_side2": round(-D, 3)},
    "press_pages": press,
    "proof_cover": [0, 0, 0, 0],
    "info_panel": {"x": 30, "y_top": 1400, "w": 520, "scale": 1.0},
    "flat_proof": {"always_show": ["side1", "side2"], "handles": True},
    # The die is a plain shape on this template, painted over the template's
    # grey "not printed" Back so both panels show in the canvas colour.
    "die_fill": [[573.5, 1419.9, 1224.0, 1102.4],
                 [726.5, 1176.8, 918.0, 243.1],
                 [573.5, 74.4, 1224.0, 1102.4]],
    "die_folds": [1447.0, 1149.6],
    # The bag's faces (purple outline): Front between its bottom fold and the
    # hem fold, Back the same, below.
    "die_regions": {"1": {"x": [752.6, 1618.4], "panels": [[1447.0, 2432.3], [164.3, 1149.6]]}},
}
SPEC.write_text(json.dumps(spec, indent=1))
print(OUT, SPEC, P5_CY)
