"""0799-3m Liam photo mockups from Numo's layers (2026-10-08), 1350 px, two sets:

  static/assets/0799-3m     TWO sides: two insulators, both fronts (Side 1 left,
                            Side 2 right) + the bottom circle
  static/assets/0799-3m-1s  ONE side: the front (Side 1, left) and the back with
                            the side seam (right) + the bottom circle

Each set's layers: background (cans on transparency -> laid on the photo's own
cream), body colour mask, bias mask, stitching mask, two textures (a soft
overlay wash and an opaque grey shading). Masks are rewritten white-on-black
with matching alpha, which is what the configurator's mask loader reads.
Print areas (art_zone_*) are derived: each printed insulator's face = the body
mask on that side minus the bias; the bottom = the inner 1.8" of the 2.5" disc.

    python3 tools/make_0799_photo_assets.py  BG BODY BIAS STITCH TEX_DARK TEX_LIGHT  ONE_SIDE(0|1)
"""
import json, sys
from pathlib import Path
import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent.parent
bg_f, body_f, bias_f, st_f, dark_f, light_f, one = sys.argv[1:8]
one = one == "1"
OUT = HERE / "static" / "assets" / ("0799-3m-1s" if one else "0799-3m")
OUT.mkdir(parents=True, exist_ok=True)
S = 1350
CREAM = (243, 230, 214)


def rgba(f):
    im = Image.open(f).convert("RGBA")
    assert im.size == (S, S), (f, im.size)
    return np.array(im)


def mask_png(alpha, name):
    a = alpha.astype(np.uint8)
    Image.fromarray(np.dstack([a, a, a, a]), "RGBA").save(OUT / f"{name}.png")


bg = Image.new("RGBA", (S, S), CREAM + (255,))
bg.alpha_composite(Image.open(bg_f).convert("RGBA"))
bg.convert("RGB").save(OUT / "background.png")

body = rgba(body_f)[..., 3].astype(np.int32)
bias = rgba(bias_f)[..., 3].astype(np.int32)
mask_png(body, "neoprene_mask")
mask_png(bias, "bias_mask")
mask_png(rgba(st_f)[..., 3], "stitching_mask")
Image.open(dark_f).convert("RGBA").save(OUT / "texture_overlay.png")
Image.open(light_f).convert("RGBA").save(OUT / "texture_screen.png")

# ── print areas ─────────────────────────────────────────────────────────────
ys, xs = np.nonzero(body > 128)
# the bottom disc: the body below the insulators (a gap of empty rows between)
rows = (body > 128).any(axis=1)
gap = next(y for y in range(ys.min() + 300, S) if not rows[y])
disc_top = next(y for y in range(gap, S) if rows[y])
face = np.where(bias > 64, 0, body)
face[gap:] = 0
mid = S // 2
zones = {}
left, right = face.copy(), face.copy()
left[:, mid:] = 0
right[:, :mid] = 0


def to_face(m):
    """The 3" x 3" imprint as the camera sees it on one insulator's face.

    Height: the visible body is the panel below the bias (the 1-up's grey top
    band, 25.17 pt, is where the bias goes) = 280.97 pt; the imprint is 216 pt
    of it, centred 153.07 pt up from the bottom edge = 12.58 pt above the
    visible middle. Width: 3" of the 8.35" circumference
    wraps 129 deg, which the camera sees as sin(64.7 deg) = 0.904 of the
    insulator's width (measured at mid-height: the mask flares at the bias).
    The configurator reads the wrap back from this shape."""
    import math
    y_, x_ = np.nonzero(m > 128)
    yc = (y_.min() + y_.max()) // 2
    band = (m[yc - 20:yc + 20] > 128).any(axis=0)
    xs_ = np.nonzero(band)[0]
    fx0, fx1 = xs_.min(), xs_.max()
    col = (m[:, (fx0 + fx1) // 2] > 128)
    fy = np.nonzero(col)[0]
    fy0, fy1 = fy.min(), fy.max()
    k = (fy1 - fy0 + 1) / 280.97                       # px per pt, vertically
    cyy = (fy0 + fy1) / 2 - 12.58 * k
    h = 216.0 * k
    w = (fx1 - fx0 + 1) * math.sin(3.0 / 8.35 * math.pi)
    cxx = (fx0 + fx1) / 2
    out = np.zeros_like(m)
    out[int(round(cyy - h / 2)):int(round(cyy + h / 2)), int(round(cxx - w / 2)):int(round(cxx + w / 2))] = 255
    return np.minimum(out, m)


left, right = to_face(left), to_face(right)
mask_png(left, "art_zone_side1")
if not one:
    mask_png(right, "art_zone_side2")
d = body.copy(); d[:disc_top] = 0
dy, dx = np.nonzero(d > 128)
cx, cy = (dx.min() + dx.max()) / 2, (dy.min() + dy.max()) / 2
r = (dx.max() - dx.min() + 1) / 2 * (1.8 / 2.5)
yy, xx = np.mgrid[0:S, 0:S]
disc = (((xx - cx) ** 2 + (yy - cy) ** 2) <= r * r) * 255
mask_png(disc, "art_zone_bottom")
for n, m in (("side1", left), ("side2", right if not one else None), ("bottom", disc)):
    if m is None:
        continue
    y_, x_ = np.nonzero(m > 128)
    zones[n] = [int(x_.min()), int(y_.min()), int(x_.max() - x_.min() + 1), int(y_.max() - y_.min() + 1)]

ex = {
    "background": {"file": "background.png", "blend": "normal"},
    "neoprene_mask": {"file": "neoprene_mask.png", "role": "color_mask"},
    "bias_mask": {"file": "bias_mask.png", "role": "trim_mask"},
    "art_zone_side1": {"file": "art_zone_side1.png", "role": "art_clip"},
    "art_zone_bottom": {"file": "art_zone_bottom.png", "role": "art_clip"},
    "stitching_mask": {"file": "stitching_mask.png", "role": "color_mask"},
    "texture_overlay": {"file": "texture_overlay.png", "blend": "overlay"},
    "texture_screen": {"file": "texture_screen.png", "blend": "soft-light"},
}
if not one:
    ex["art_zone_side2"] = {"file": "art_zone_side2.png", "role": "art_clip"}
json.dump({"product": "0799-3m", "width": S, "height": S,
           "_about": ("Numo's 0799 Liam photo layers (2026-10-08), " +
                      ("ONE side: Side 1 front (left), the back with the seam (right)." if one else
                       "TWO sides: Side 1 (left) and Side 2 (right), both fronts.")) +
                     " Built by tools/make_0799_photo_assets.py.",
           "exports": ex}, open(OUT / "manifest.json", "w"), indent=1)
if not one:
    th = Image.open(OUT / "background.png").resize((400, 400), Image.LANCZOS)
    th.save(OUT / "thumbnail.png")
print(OUT.name, json.dumps(zones))
