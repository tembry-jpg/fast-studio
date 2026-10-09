"""Mockup assets for the 5010 Daily Grind tote (static/assets/5010-10, shared
by 5010-10, 5010-cc and their This Is Fast twins).

Numo's four layers (2400 x 2400, 2026-10-09), passed as a folder holding:
  background.png       the bags' photo with soft shadows on a transparent
                       backdrop - flattened here onto the configurator's cream
  canvas_mask.png      the bags' silhouette (any colour; only alpha is used)
  texture_overlay.png  weave texture, overlay blend
  texture_screen.png   shading, soft-light blend
Right bag = Side 1 (Front), left bag = Side 2 (Back).

Also writes template_guide.png: page 1 of press/5010-TIF-1C.pdf (the TIF
template) cropped to the die, 2400 px tall.

    python3 tools/make_5010_assets.py <layers folder>
"""
import json
import shutil
import sys
from pathlib import Path
from PIL import Image
from pdf2image import convert_from_path

HERE = Path(__file__).resolve().parent.parent
SRC = Path(sys.argv[1])
OUT = HERE / "static" / "assets" / "5010-10"
OUT.mkdir(parents=True, exist_ok=True)
CREAM = (251, 238, 222)            # the 5001-7 tote's backdrop

bg = Image.open(SRC / "background.png").convert("RGBA")
flat = Image.new("RGBA", bg.size, CREAM + (255,))
flat.alpha_composite(bg)
a = Image.open(SRC / "canvas_mask.png").convert("RGBA").split()[3]
# Under the bags the colour mask paints solid canvas, so the photo there is
# never seen: flattened to one grey it costs almost nothing to download
# (5.3 MB -> 1.3 MB). Edges, where the mask is partial, keep the photo.
solid = a.point(lambda v: 255 if v >= 254 else 0)
flat.paste((127, 121, 114, 255), (0, 0), solid)
flat.convert("RGB").save(OUT / "background.png", optimize=True)

white = Image.new("L", a.size, 255)
Image.merge("RGBA", (white, white, white, a)).save(OUT / "canvas_mask.png", optimize=True)
# Grey layers: stored grey + alpha (LA), a third of the RGBA size.
for name in ("texture_overlay.png", "texture_screen.png"):
    Image.open(SRC / name).convert("RGBA").convert("LA").save(OUT / name, optimize=True)

# Template guide: the die on the TIF template, [573.5, 74.4, 1797.5, 2522.3] pt.
X0, Y0, X1, Y1 = 573.5, 74.4, 1797.5, 2522.3
PAGE_H = 3315.31
dpi = 2400 / (Y1 - Y0) * 72
pg = convert_from_path(str(HERE / "press" / "5010-TIF-1C.pdf"), dpi=dpi,
                       first_page=1, last_page=1)[0].convert("RGB")
k = dpi / 72
guide = pg.crop((round(X0 * k), round((PAGE_H - Y1) * k), round(X1 * k), round((PAGE_H - Y0) * k)))
guide.save(OUT / "template_guide.png", optimize=True)

json.dump({
    "product": "5010-10", "width": 2400, "height": 2400,
    "_about": "Numo's 5010 Daily Grind photo layers (2026-10-09): right bag = Side 1 (Front), left bag = Side 2 (Back). Built by tools/make_5010_assets.py.",
    "default_art": [],
    "exports": {
        "background": {"file": "background.png", "blend": "normal"},
        "canvas_mask": {"file": "canvas_mask.png", "role": "color_mask"},
        "texture_overlay": {"file": "texture_overlay.png", "blend": "overlay"},
        # The shading photo (wrinkles, weave) is a mid-grey layer: soft-light
        # left the bag looking flat, so it goes on in hard-light at 60 %, which
        # brings the canvas out on dark colours without dirtying Natural.
        "texture_screen": {"file": "texture_screen.png", "blend": "hard-light", "opacity": 0.6},
    }}, open(OUT / "manifest.json", "w"), indent=1)

# Thumbnails: the lineup photos (static/tif/soon/), one per item.
photos = HERE / "static" / "tif" / "soon"
for pid, photo in (("5010-10", "daily-grind-natural.jpg"), ("5010-cc", "daily-grind-colored.jpg"),
                   ("5010-TIF-10-1C", "daily-grind-natural.jpg"),
                   ("5010-TIF-CC-1C", "daily-grind-colored.jpg")):
    d = HERE / "static" / "assets" / pid
    d.mkdir(parents=True, exist_ok=True)
    Image.open(photos / photo).convert("RGB").save(d / "thumbnail.png")
print("ok", guide.size)
