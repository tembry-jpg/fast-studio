"""Build press/0799-3m.pdf + press/press_spec_0799-3m.json for the 0799 Liam
Can Insulator (one long neoprene panel with a single side seam, sewn to a
bottom circle; colored bias binding along the top edge).

Template pages:
  1  guide, ONE side: the panel (Center imprint, opposite the seam) + bottom circle
  2  guide, TWO sides: the panel (Side 1 / Side 2, opposite each other) + bottom circle
  3-9  Numo's "0799 - Neo - Mass Export" artboards 01-07:
       STRYKER, DBG JAVELIN AUTO 2 pcs, DBG JAVELIN AUTO 3 pcs, DISCO,
       DISCO Bottom, DBC, DBC Bottom

Measured from the vector files (1-ups: panel 614.875 x 306.14 pt, three 216 pt
imprint squares centred 154.44 / 307.44 / 460.44 pt from the panel's left,
153.07 pt up; bias band 25.17 pt on top, 18.64 pt sewing band with a centre
notch at the bottom. Bottom: 180 pt die, 129.6 pt imprint circle). Sheets:
crop-mark corners and registration targets of each panel cell; bottom sheets:
the quarter notches of each circle.

    python3 tools/make_0799_template.py MASS.pdf PANEL_1UP.pdf BOTTOM_1UP.pdf
"""
import json, sys
from pathlib import Path
import pikepdf
from pikepdf import Pdf, Page

HERE = Path(__file__).resolve().parent.parent
MASS, PANEL, BOTTOM = sys.argv[1:4]

PW, PH = 614.875, 306.14          # panel 1-up
IMP = 216.0                       # imprint square
IMP_X = (154.44, 307.44, 460.44)  # side1, center, side2 (from panel left)
IMP_Y = 153.07                    # from panel bottom
D = IMP_X[2] - IMP_X[1]           # 153.0: side1/side2 from the panel centre
CB = 181.0                        # bottom 1-up page (die 180 pt, centred)
CD_DIE, CD_IMP = 180.0, 129.6

# ── guide page: panel on top, bottom circle under it, room below for the info panel
GW, GH = 700.0, 1180.0
PX, PY = (GW - PW) / 2, 820.0     # panel origin (bottom-left)
CX, CY = GW / 2, 700.0            # bottom circle centre
SHIFT_INFO_TOP = 580

out = Pdf.new()
panel, bottom, mass = Pdf.open(PANEL), Pdf.open(BOTTOM), Pdf.open(MASS)
for _ in (1, 2):
    pg = out.add_blank_page(page_size=(GW, GH))
    fp = out.copy_foreign(Page(panel.pages[0]).as_form_xobject())
    fb = out.copy_foreign(Page(bottom.pages[0]).as_form_xobject())
    pg.obj.Resources = pikepdf.Dictionary(XObject=pikepdf.Dictionary(P=fp, B=fb))
    s = (f"q 1 0 0 1 {PX:.3f} {PY:.3f} cm /P Do Q\n"
         f"q 1 0 0 1 {CX - CB / 2:.3f} {CY - CB / 2:.3f} cm /B Do Q\n")
    pg.obj.Contents = out.make_stream(s.encode())
for p in mass.pages:
    out.pages.append(p)
out.save(str(HERE / "press" / "0799-3m.pdf"))


def zone(cx, cy, w, h):
    return {"cx": round(cx, 2), "cy": round(cy, 2), "w": w, "h": h,
            "left": round(cx - w / 2, 2), "top": round(cy + h / 2, 2)}


zc = PY + IMP_Y
bottom_z = zone(CX, CY, CD_IMP, CD_IMP)
guide = {
    "1": {"sides": ["side1"], "zones": {"side1": zone(PX + IMP_X[1], zc, IMP, IMP), "bottom": bottom_z}},
    "2": {"sides": ["side1", "side2"], "zones": {"side1": zone(PX + IMP_X[0], zc, IMP, IMP),
                                                 "side2": zone(PX + IMP_X[2], zc, IMP, IMP),
                                                 "bottom": bottom_z}},
}

# ── press sheets (template page = mass page + 2) ────────────────────────────
# A panel position is the panel's centre. "rot" turns the art the way the
# panel is turned on the sheet; "axis" is the direction from the panel's centre
# toward the 1-up's RIGHT end (Side 2), so Side 1 sits at -d along it.
UP_LEFT = {"rot": 90, "axis": [0, 1]}     # panel turned 90° CCW: bias edge on the left, Side 2 end up
UP_RIGHT = {"rot": -90, "axis": [0, -1]}  # panel turned 90° CW: bias edge on the right, Side 2 end down
UPRIGHT = {"rot": 0, "axis": [1, 0]}      # as the 1-up


def P(cx, cy, how):
    return {"cx": round(cx, 2), "cy": round(cy, 2), "gap": 0.0, "vertical": False, **how}


# STRYKER (mass 1): 5 columns x 3 rows, columns alternate, bias edges outward per pair
cols = [(54.2, 360.9), (360.9, 667.5), (666.0, 972.7), (972.7, 1279.3), (1278.3, 1584.9)]
rows = [(265.1, 881.0), (880.0, 1495.9), (1494.9, 2110.8)]
stryker = [P((a + b) / 2, (c + d) / 2, UP_LEFT if i % 2 == 0 else UP_RIGHT)
           for (c, d) in rows for i, (a, b) in enumerate(cols)]


def pair(x0, x1, y0, y1):
    xm = (x0 + x1) / 2
    return [P((x0 + xm) / 2, (y0 + y1) / 2, UP_LEFT), P((xm + x1) / 2, (y0 + y1) / 2, UP_RIGHT)]


body = ["side1", "side2"]
pages = {
    "3": {"artboard": "STRYKER", "machine": "STRYKER", "sides": body, "positions": stryker, "page": [1656.0, 2376.0]},
    "4": {"artboard": "DBG JAVELIN AUTO 2 pcs", "machine": "DBG", "sides": body,
          "positions": pair(269.4, 882.6, 537.2, 1153.1), "page": [1152.0, 1656.0]},
    "5": {"artboard": "DBG JAVELIN AUTO 3 pcs", "machine": "DBG", "sides": body,
          "positions": [P(576.0, (a + b) / 2, UPRIGHT) for a, b in ((232.4, 539.1), (539.1, 845.2), (845.2, 1151.85))],
          "page": [1152.0, 1656.0]},
    "6": {"artboard": "DISCO", "machine": "DISCO", "sides": body,
          "positions": pair(269.4, 882.6, 520.0, 1135.9), "page": [1152.0, 1656.0]},
    "7": {"artboard": "DISCO Bottom", "machine": "DISCO", "sides": ["bottom"],
          "positions": [P(486.0, 828.0, UPRIGHT), P(666.0, 828.0, UPRIGHT)], "page": [1152.0, 1656.0]},
    "8": {"artboard": "DBC", "machine": "DBC", "sides": body,
          "positions": pair(125.4, 738.6, 196.0, 811.9), "page": [864.0, 1008.0]},
    "9": {"artboard": "DBC Bottom", "machine": "DBC", "sides": ["bottom"],
          "positions": [P(342.0, 504.0, UPRIGHT), P(522.0, 504.0, UPRIGHT)], "page": [864.0, 1008.0]},
}
for v in pages.values():
    v["rotation"] = 0

spec = {
    "_scope": "0799-3m Liam Can Insulator (neoprene panel + bottom circle, colored bias on top).",
    "_template_file": "0799-3m.pdf: pages 1-2 = guides built from the panel and bottom 1-ups (1 = one side, Center; "
                      "2 = two sides, Side 1 / Side 2); pages 3-9 = '0799 - Neo - Mass Export' artboards 01-07.",
    "_measured_by": "tools/make_0799_template.py: 1-up vectors; sheet crop-mark corners, registration targets and the bottoms' quarter notches.",
    "_unverified": "Never checked against a printed sheet: which end of a turned panel is Side 1 (taken as the 1-up turned, "
                   "not mirrored), and that the art lands in the imprint on the first STRYKER, DISCO and DBC sheets.",
    "_sides_note": "Body sheets carry the panel (Side 1 + Side 2, or Center alone); Bottom sheets the circles, and only a job with a bottom gets them.",
    "_one_side_note": "One side prints at the panel's centre, opposite the seam ('d_one'); two sides at -d / +d.",
    "template": "0799 - Liam Can Insulator",
    "product": "0799-3m",
    "products": ["0799-3m"],
    "guide_pages": guide,
    "offsets": {"side_w": IMP, "side_h": IMP, "circle_d": CD_IMP,
                "d_side1": -D, "d_side2": D, "d_one": 0.0},
    "side2_turn": 0,
    "press_pages": pages,
    "proof_cover": [0, 0, 0, 0],
    "info_panel": {"x": 40, "y_top": SHIFT_INFO_TOP, "w": 620, "scale": 1.3},
    "die_fill": [[round(PX, 2), PY, PW, PH], {"circle": [CX, CY, CD_DIE / 2]}],
    "die_bands": [{"rect": [round(PX, 2), round(PY + 280.97, 2), PW, 25.17], "component": "bias"}],
    "die_regions": {k: {"rects": [
        {"slot": "side1", "label": "Panel", "x0": round(PX - 6, 2), "x1": round(PX + PW + 6, 2),
         "y0": round(PY - 6, 2), "y1": round(PY + PH + 6, 2)},
        {"slot": "bottom", "label": "Bottom", "circle": True, "x0": CX - 92, "x1": CX + 92,
         "y0": CY - 92, "y1": CY + 92}]} for k in ("1", "2")},
    "flat_proof": {"always_show": ["side1", "bottom"]},
}
json.dump(spec, open(HERE / "press" / "press_spec_0799-3m.json", "w"), indent=1)
print("ok", len(out.pages), "pages")
