"""Assets for the 0799-3m Liam Can Insulator: template_guide.png (the panel and
bottom 1-ups as laid out on the press template's guide page) and a PLACEHOLDER
flat mockup (panel + bottom circle, bias band on top) until Numo's photo layers
arrive. Prints the template zones and proof bounds products.py uses.

    python3 tools/make_0799_assets.py
"""
import json
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter
from pdf2image import convert_from_path

HERE = Path(__file__).resolve().parent.parent
OUT = HERE / "static" / "assets" / "0799-3m"
OUT.mkdir(parents=True, exist_ok=True)
spec = json.load(open(HERE / "press" / "press_spec_0799-3m.json"))

# ── template guide: guide page 2, cropped to the drawing ────────────────────
GX0, GX1, GY0, GY1 = 30.0, 670.0, 600.0, 1140.0      # pt, y up
K = 2.5                                               # px per pt
page = convert_from_path(str(HERE / "press" / "0799-3m.pdf"), dpi=int(72 * K), first_page=2, last_page=2)[0]
PAGE_H = 1180.0
guide = page.crop((int(GX0 * K), int((PAGE_H - GY1) * K), int(GX1 * K), int((PAGE_H - GY0) * K))).convert("RGB")
guide.save(OUT / "template_guide.png")
gw, gh = guide.size


def frac(z):
    x0, y_top = z["left"], z["top"]
    return {"x": round((x0 - GX0) / (GX1 - GX0), 4), "y": round((GY1 - y_top) / (GY1 - GY0), 4),
            "w": round(z["w"] / (GX1 - GX0), 4), "h": round(z["h"] / (GY1 - GY0), 4)}


g1, g2 = spec["guide_pages"]["1"]["zones"], spec["guide_pages"]["2"]["zones"]
tz = {"side1": {**frac(g2["side1"]), "l": "Side 1"},
      "bottom": {**frac(g2["bottom"]), "l": "Bottom"},
      "side2": {**frac(g2["side2"]), "l": "Side 2"}}
one = {**frac(g1["side1"]), "l": "Side 1"}

# The photo mockups (tools/make_0799_photo_assets.py) replace the placeholder;
# once they are in, only the template guide is rebuilt here.
if "photo layers" in (OUT / "manifest.json").read_text() if (OUT / "manifest.json").exists() else False:
    print(json.dumps({"template_zones": tz, "one_side_zone": one}, indent=1))
    raise SystemExit
# ── placeholder mockup (1350 px), flat ──────────────────────────────────────
S = 1350
PW, PH, BIAS, SEW = 614.875, 306.14, 25.17, 18.64
k = S * 0.86 / PW
px0, py0 = (S - PW * k) / 2, 190.0
cd = 180.0 * k
ccx, ccy = S / 2, py0 + PH * k + 70 + cd / 2

bg = Image.new("RGB", (S, S), (243, 236, 226))
sh = Image.new("L", (S, S), 0)
ds = ImageDraw.Draw(sh)
ds.rectangle((px0 + 10, py0 + 16, px0 + PW * k + 10, py0 + PH * k + 16), fill=90)
ds.ellipse((ccx - cd / 2 + 10, ccy - cd / 2 + 16, ccx + cd / 2 + 10, ccy + cd / 2 + 16), fill=90)
sh = sh.filter(ImageFilter.GaussianBlur(18))
bg.paste((200, 190, 178), (0, 0), sh)
# the body in mid grey (the colour mask tints it), seam lines at each end
body = ImageDraw.Draw(bg)
body.rectangle((px0, py0, px0 + PW * k, py0 + PH * k), fill=(170, 170, 170))
body.ellipse((ccx - cd / 2, ccy - cd / 2, ccx + cd / 2, ccy + cd / 2), fill=(170, 170, 170))
bg.save(OUT / "background.png")

mask = Image.new("L", (S, S), 0)
dm = ImageDraw.Draw(mask)
dm.rectangle((px0, py0 + BIAS * k, px0 + PW * k, py0 + PH * k), fill=255)
dm.ellipse((ccx - cd / 2, ccy - cd / 2, ccx + cd / 2, ccy + cd / 2), fill=255)
Image.merge("RGBA", (mask, mask, mask, mask)).save(OUT / "neoprene_mask.png")

bias = Image.new("L", (S, S), 0)
ImageDraw.Draw(bias).rectangle((px0, py0, px0 + PW * k, py0 + BIAS * k), fill=255)
Image.merge("RGBA", (bias, bias, bias, bias)).save(OUT / "bias_mask.png")

# seams: the side seam allowance at each end and the sewing band, faint
shade = Image.new("RGBA", (S, S), (0, 0, 0, 0))
dsh = ImageDraw.Draw(shade)
for x in (px0 + 6.68 * k, px0 + (PW - 6.68) * k):
    dsh.line((x, py0 + BIAS * k, x, py0 + PH * k), fill=(0, 0, 0, 70), width=3)
dsh.line((px0, py0 + (PH - SEW) * k, px0 + PW * k, py0 + (PH - SEW) * k), fill=(0, 0, 0, 55), width=2)
dsh.line((px0, py0 + BIAS * k, px0 + PW * k, py0 + BIAS * k), fill=(0, 0, 0, 45), width=2)
shade.save(OUT / "shading.png")

foot = Image.new("RGBA", (S, 160), (243, 236, 226, 0))
foot.save(OUT / "footer_bg.png")
th = bg.copy()
th.paste((150, 150, 150), (0, 0), mask)
th.paste((40, 40, 40), (0, 0), bias)
th.resize((400, 400), Image.LANCZOS).save(OUT / "thumbnail.png")


def pb(x_center_pt, size_pt):
    return {"x": round(px0 + (x_center_pt - size_pt / 2) * k), "y": round(py0 + (PH - 153.07 - size_pt / 2) * k),
            "w": round(size_pt * k), "h": round(size_pt * k)}


bounds = {"side1": pb(154.44, 216.0), "side2": pb(460.44, 216.0),
          "bottom": {"x": round(ccx - 64.8 * k), "y": round(ccy - 64.8 * k), "w": round(129.6 * k), "h": round(129.6 * k)}}
one_b = pb(307.44, 216.0)

json.dump({
    "product": "0799-3m", "width": S, "height": S,
    "_about": "PLACEHOLDER (tools/make_0799_assets.py): the panel and bottom drawn flat, bias band on top, "
              "until Numo's photo layers arrive.",
    "exports": {
        "background": {"file": "background.png", "blend": "normal"},
        "neoprene_mask": {"file": "neoprene_mask.png", "role": "color_mask"},
        "bias_mask": {"file": "bias_mask.png", "role": "trim_mask"},
        "shading": {"file": "shading.png", "role": "shadow"},
        "footer_bg": {"file": "footer_bg.png", "blend": "normal"},
    }}, open(OUT / "manifest.json", "w"), indent=1)

print(json.dumps({"template_zones": tz, "one_side_zone": one, "proof_bounds": bounds,
                  "one_side_bounds": one_b, "guide_px": [gw, gh]}, indent=1))
