"""
make_body_pattern.py — turn a material photo into a body the configurator
can show: the swatch in the colour picker, the body on the mockup, and the
tile the digital proof and 2X2 are filled with. The same files the camo on
scuba uses (static/assets/<product>/patterns/).

  python tools/make_body_pattern.py --product 0070-3l --name "Gold" \\
      --texture gold-texture.jpg [--proof gold-big-swatch.jpg]

  --texture : a photo of the material (mockup body and picker swatch).
  --body    : a finished body layer for this product's mockup (same size as
              its mask, e.g. 1350 x 1350): used as is; --texture then only
              feeds the swatch (defaults to the middle of Side 1 of --body).
  --proof   : a bigger, flat swatch for the proof / 2X2 fill (defaults to
              --texture).

Writes <slug>_swatch.png (160 px), <slug>_body.png (the material over the
product's body mask, same size as the mask), <slug>_tile.png (proof fill),
and adds or replaces the entry in patterns.json with the material's average
colour as its hex. Run it once per colour and per product (0070-3l, 1080-3l).
"""
import argparse
import json
import re
import sys
from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))


def slug(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def mirrored_cover(tex, w, h):
    """The texture repeated (mirrored, so edges meet) to cover w x h."""
    t = np.asarray(tex.convert("RGB"))
    block = np.concatenate([np.concatenate([t, t[:, ::-1]], axis=1),
                            np.concatenate([t[::-1], t[::-1, ::-1]], axis=1)], axis=0)
    reps = (-(-h // block.shape[0]), -(-w // block.shape[1]), 1)
    return Image.fromarray(np.tile(block, reps)[:h, :w])


def square_crop(im):
    s = min(im.size)
    l, t = (im.width - s) // 2, (im.height - s) // 2
    return im.crop((l, t, l + s, t + s))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--product", required=True)
    ap.add_argument("--name", required=True)
    ap.add_argument("--texture")
    ap.add_argument("--body")
    ap.add_argument("--proof")
    ap.add_argument("--mask", help="body mask (default: the product's neoprene/scuba mask)")
    ap.add_argument("--scale", type=float, default=1.0,
                    help="texture size on the mockup body (1 = as photographed, to the mask's width)")
    a = ap.parse_args()

    from products import PRODUCTS
    p = PRODUCTS.get(a.product)
    if not p:
        sys.exit(f"Unknown product {a.product}")
    asset = HERE / "static" / "assets" / (p.get("asset_id") or a.product)
    out = HERE / "static" / "assets" / (p.get("pattern_dir") or p.get("asset_id") or a.product) / "patterns"
    out.mkdir(parents=True, exist_ok=True)
    mask_path = Path(a.mask) if a.mask else next(
        (asset / n for n in ("neoprene_mask.png", "scuba_mask.png") if (asset / n).exists()), None)
    if not mask_path or not mask_path.exists():
        sys.exit(f"No body mask in {asset}")
    mask = Image.open(mask_path).convert("RGBA")
    if a.body:
        # A finished body layer: kept as drawn, cut to the mask.
        body = Image.open(a.body).convert("RGBA").resize(mask.size, Image.LANCZOS)
        al = np.minimum(np.asarray(body.getchannel("A")), np.asarray(mask.getchannel("A")))
        body.putalpha(Image.fromarray(al.astype("uint8")))
        if a.texture:
            tex = Image.open(a.texture).convert("RGB")
        else:
            # The middle of the first panel: flat material, no edge.
            bb = mask.getchannel("A").getbbox()
            cx = bb[0] + (bb[2] - bb[0]) // 4
            cy = bb[1] + (bb[3] - bb[1]) * 2 // 5
            r = max(40, (bb[2] - bb[0]) // 8)
            tex = body.convert("RGB").crop((cx - r, cy - r, cx + r, cy + r))
    elif a.texture:
        tex = Image.open(a.texture).convert("RGB")
        # The mockup body: the material across the mask, the mask's own alpha.
        k = mask.width / tex.width * a.scale
        tex_s = tex.resize((max(1, round(tex.width * k)), max(1, round(tex.height * k))), Image.LANCZOS)
        body = mirrored_cover(tex_s, mask.width, mask.height).convert("RGBA")
        body.putalpha(mask.getchannel("A"))
    else:
        sys.exit("Pass --texture or --body")
    proof = Image.open(a.proof).convert("RGB") if a.proof else tex
    s = slug(a.name)
    body.save(out / f"{s}_body.png", optimize=True)
    square_crop(tex).resize((160, 160), Image.LANCZOS).save(out / f"{s}_swatch.png", optimize=True)
    tile = square_crop(proof)
    if tile.width > 900:
        tile = tile.resize((900, 900), Image.LANCZOS)
    tile.save(out / f"{s}_tile.png", optimize=True)
    avg = np.asarray(proof.convert("RGB")).reshape(-1, 3).mean(axis=0)
    hexv = "#%02X%02X%02X" % tuple(int(round(v)) for v in avg)

    man = out / "patterns.json"
    items = json.loads(man.read_text()) if man.exists() else []
    items = [i for i in items if i.get("name") != a.name]
    items.append({"name": a.name, "hex": hexv, "swatch": f"{s}_swatch.png",
                  "body": f"{s}_body.png", "tile": f"{s}_tile.png"})
    man.write_text(json.dumps(items, indent=2))
    print(f"{a.product} · {a.name}: {hexv} -> {out}")


if __name__ == "__main__":
    main()
