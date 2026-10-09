"""Spring Camo and Fall Camo stock backgrounds for every 4CP item.

Source: Numo's "fall and spring camo" PDF (press/tif/fall_and_spring_camo.pdf):
page 1 = Spring Camo (the one with green), page 3 = Fall Camo (more orange);
page 2 is empty. Both were drawn for the 0070 panel (316.8 x 783.1 pt).

Each item's stockbackgrounds folder gets the two as JPGs. Where the folder
already has backgrounds they are made the same size as those (the upload
check compares against them); elsewhere they are the item's printed shape at
the same density as the 0070-3w set (4.53 px per pt). The camo is cropped to
fill, from the middle; the 0635's long strip takes it turned on its side so
the pattern keeps its size.

    python3 tools/make_camo_backgrounds.py
"""
from pathlib import Path
from PIL import Image
from pdf2image import convert_from_path

HERE = Path(__file__).resolve().parent.parent
SRC = HERE / "press" / "tif" / "fall_and_spring_camo.pdf"
CAMOS = {"Spring Camo.jpg": 1, "Fall Camo.jpg": 3}
DENSITY = 1433 / 316.373                  # px per pt of the 0070-3w set

import sys
sys.path.insert(0, str(HERE))
from products import PRODUCTS

ITEMS = [pid for pid, p in PRODUCTS.items() if p.get("is_4cp") and not p.get("twin_of")
         and (p.get("asset_id") or pid) == pid]

pages = {name: convert_from_path(str(SRC), dpi=600, first_page=n, last_page=n)[0].convert("RGB")
         for name, n in CAMOS.items()}


def cover(img, w, h):
    s = max(w / img.width, h / img.height)
    r = img.resize((max(w, round(img.width * s)), max(h, round(img.height * s))), Image.LANCZOS)
    x, y = (r.width - w) // 2, (r.height - h) // 2
    return r.crop((x, y, x + w, y + h))


for pid in ITEMS:
    p = PRODUCTS[pid]
    folder = HERE / "static" / "assets" / pid / "stockbackgrounds"
    existing = sorted(f for f in folder.glob("*.jp*g") if f.name not in CAMOS) if folder.exists() else []
    if existing:
        with Image.open(existing[0]) as im:
            w, h = im.size
    else:
        w, h = round(p["page_w"] * DENSITY), round(p["page_h"] * DENSITY)
    folder.mkdir(parents=True, exist_ok=True)
    for name, page in pages.items():
        src = page.rotate(90, expand=True) if w > h else page
        cover(src, w, h).save(folder / name, quality=90)
    print(pid, w, h, "existing set" if existing else "new set")
