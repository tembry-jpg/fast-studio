"""Press template and spec for the 5020 Shamwow tote, This Is Fast
(5020-TIF-10-1C natural, 5020-TIF-CC-1C colored canvas).

Sources (press/tif/):
  5020-CC - Shamwow - THIS IS FAST.pdf  the template customers fill in
                                        (Side 1 Front only - 1 Side)
  5020 - Canvas Mass Export.pdf         5 press sheets
  5020-1up.pdf                          the die drawing

Output press/5020-TIF-1C.pdf = page 1 the TIF template (the guide), pages 2-6
the mass export with "NSO NUMBER" / "SPOT COLOR" captions added beside each
sheet's own label so the export stamps the order and ink there.

Geometry, all measured off the files:
  die 1224 x 2700 pt (17" x 37.5"): Front half on top, Back half below, a
  hem at each end, the bottom between (the notch).
  Imprint 1080 x 936 pt (15" x 13"), its two lower corners cut off (2.06" x
  3") where the bag's boxed bottom folds; the zone is its 15" x 13" box.
  Imprint centre: across the die's middle, 611.26 pt (Front) / 611.05 pt
  (Back) along the die from the dots by its hem (54.4 pt in from the edge).
  Sheets:
    1, 2  STRYKER Front / Back, 2 pieces: halves on their side, hem at the
          left, placed from the dots (circles) the sheet carries
    3     STRYKER front + back: the whole die upright, placed from the
          bottom notch's corner marks (die x + 215.0, die y - 162.7)
    4, 5  JAVELIN AUTO Front / Back: halves on their side, hem at the left
          (off the sheet), placed from the corner marks at the notch end,
          541.2 / 541.45 pt from the imprint centre as on sheets 1 and 2
  Art reads toward the hem on the sideways sheets.

    python3 tools/make_5020_template.py
"""
import json
from pathlib import Path
import pikepdf
from reportlab.pdfgen import canvas as rlcanvas

HERE = Path(__file__).resolve().parent.parent
TIF = HERE / "press" / "tif" / "5020-CC - Shamwow - THIS IS FAST.pdf"
MASS = HERE / "press" / "tif" / "5020 - Canvas Mass Export.pdf"
OUT = HERE / "press" / "5020-TIF-1C.pdf"
SPEC = HERE / "press" / "press_spec_5020.json"

ZW, ZH = 1080.0, 936.0
D1, D2 = 2035.19 - 1350.65, 666.15 - 1350.65     # die middle -> imprint centres

# Sideways halves: mass page -> (imprint centre x, centre ys, side, artboard,
# press, caption anchor (x, y, rot)). Artboard names are the mass export's own.
SIDEWAYS = {
    1: (268.55 + 611.26, [575.8, 1799.95], "side1", "STRYKER 1 Side Front (2 pz)", "STRYKER", (1150, 1177, 180)),
    2: (268.10 + 611.05, [576.05, 1800.05], "side2", "STRYKER 2 Side Back (2pz)", "STRYKER", (1150, 1177, 180)),
    4: (1147.5 - 541.19, [828.7], "side1", "JAVELIN AUTO FRONT", "JAVELIN AUTO", (880, 1428, 180)),
    5: (1089.1 - 541.45, [823.7], "side2", "JAVELIN AUTO BACK", "JAVELIN AUTO", (820, 1424, 180)),
}
P3_CX, P3_CY = 612.58 + 215.0, 1350.65 - 162.7   # sheet 3: the die upright

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
for mp in range(1, 6):
    pg = out.pages[mp]          # mass page mp is output page mp + 1
    mb = [float(v) for v in pg.obj.MediaBox]
    w, h = mb[2] - mb[0], mb[3] - mb[1]
    if mp in SIDEWAYS:
        cx, ys, side, name, machine, anchor = SIDEWAYS[mp]
        # rot is the turn Side 1 gets; Side 2 gets rot + 180, so a Back-only
        # sheet records -90 to give its art the same 90-degree turn.
        rot = 90 if side == "side1" else -90
        positions = [{"cx": round(cx, 2), "cy": y, "gap": 0.0, "vertical": True,
                      "axis": [0, 0], "rot": rot} for y in ys]
        layout, sides = "1side", [side]
        name_at = [anchor[0] - 420, anchor[1], anchor[2]]
    else:
        anchor = (1428, 1600, 90)
        name, machine, layout, sides = "STRYKER front  back", "STRYKER", "2diff", ["side1", "side2"]
        positions = [{"cx": round(P3_CX, 2), "cy": round(P3_CY, 2), "gap": 0.0,
                      "vertical": True, "axis": [0, 1], "rot": 0}]
        name_at = [1428, 2050, 90]
    captions(mp, w, h, anchor)
    press[str(mp + 1)] = {"page": [w, h], "rotation": 0, "positions": positions,
                          "artboard": name.replace("  ", " "), "machine": machine, "layout": layout,
                          "sides": sides, "name_at": name_at}
out.save(str(OUT))

# TIF template (page 1): die [1069.1, 191.2, 2293.2, 2891.5].
Z1 = {"cx": 1681.1, "cy": 2225.9, "w": ZW, "h": ZH, "left": 1141.1, "top": 2693.9}
spec = {
    "_scope": "5020 Shamwow tote, This Is Fast: 5020-TIF-10-1C (natural) and 5020-TIF-CC-1C (colored canvas) - one die, one template, one mass export; only the canvas colour differs.",
    "_template_file": "5020-TIF-1C.pdf (tools/make_5020_template.py): page 1 = '5020-CC - Shamwow - THIS IS FAST' (1 Side, Front); pages 2-6 = '5020 - Canvas Mass Export' with NSO NUMBER / SPOT COLOR captions added.",
    "_measured_by": "the 1-up's dots and imprint boxes; on the sheets the dots (1, 2), the notch corner marks (3) and the notch-end corner marks (4, 5).",
    "_unverified": "Never checked against a printed sheet. Confirm on the first job: the art lands in the imprint, and on the sideways sheets it reads toward the hem.",
    "template": "5020 - Shamwow",
    "product": "5020-TIF-10-1C",
    "products": ["5020-TIF-10-1C", "5020-TIF-CC-1C"],
    "guide_pages": {"1": {"sides": ["side1"], "zones": {"side1": Z1}}},
    "offsets": {"side_w": ZW, "side_h": ZH, "circle_d": 0.0,
                "d_side1": round(D1, 3), "d_side2": round(D2, 3)},
    "press_pages": press,
    "proof_cover": [0, 0, 0, 0],
    "info_panel": {"x": 30, "y_top": 1700, "w": 520, "scale": 1.0},
    "flat_proof": {"always_show": ["side1", "side2"], "handles": True},
    # Painted over the template's grey "not printed" Back so both panels show
    # in the canvas colour: the two halves and the band at the notch.
    "die_fill": [[1069.1, 1685.2, 1224.1, 1206.3],
                 [1240.0, 1397.2, 882.2, 288.0],
                 [1069.1, 191.2, 1224.1, 1206.0]],
    "die_folds": [1685.2, 1397.2],
    "die_regions": {"1": {"x": [1069.1, 2293.2], "panels": [[1685.2, 2801.4], [281.3, 1397.2]]}},
}
SPEC.write_text(json.dumps(spec, indent=1))
print(OUT, SPEC)
