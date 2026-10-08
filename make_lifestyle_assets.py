"""A lifestyle photo for the configurator's "Lifestyle" view (0070-3m first).

Numo's layered lifestyle shot -> a mockup asset set the configurator renders
exactly like its product mockup: the photo, the body and stitching colour
masks, the shading, and the print area on the insulator's face.

    python3 tools/make_lifestyle_assets.py OUT_ID PRODUCT_ID PHOTO BODY STITCH SHADE SHADE_SOFT RIM EDGES [PLACE]

PHOTO        the whole photo (the insulator in it is recoloured)
BODY         the insulator's body (any colour, on transparency)
STITCH       the seam stitching (on transparency)
SHADE        the opaque grey shading of the body       -> overlay
SHADE_SOFT   the light grey shading layer               -> multiply
RIM          the dark line inside the top edge          -> drawn on top
EDGES        the white edge highlights                  -> drawn on top

PLACE (optional): a JSON file of the print area as Numo's placement shot
shows it, in the photo's pixels (see the code for its fields). From the can's silhouette these give how far round the can
the imprint wraps and how far it is turned from the camera (the 0070-3m's is
turned 16 degrees to the right: its centre line sits right of the can's
middle and its right edge almost on the silhouette).

Without PLACE, the print area: the product mockup's Side 1 print area, taken as a share of
its can body (width, top, height), laid on the photo's body the same way and
centred across the face the photo shows. The art is clipped to the body, so it never runs off the insulator.
"""
import json, sys
from pathlib import Path
import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent.parent
out_id, pid, photo, body_f, st_f, sh_f, soft_f, rim_f, edge_f = sys.argv[1:10]
place = sys.argv[10] if len(sys.argv) > 10 else None
src_w = Image.open(photo).size[0]
OUT = HERE / "static" / "assets" / out_id
OUT.mkdir(parents=True, exist_ok=True)
S = 1350
CONTRAST = float(__import__("os").environ.get("LIFE_CONTRAST", "2.0"))


def load(f):
    im = Image.open(f).convert("RGBA")
    return im.resize((S, S), Image.LANCZOS) if im.size != (S, S) else im


def mask_png(alpha, name):
    a = np.clip(alpha, 0, 255).astype(np.uint8)
    Image.fromarray(np.dstack([a, a, a, a]), "RGBA").save(OUT / f"{name}.png")


load(photo).convert("RGB").save(OUT / "background.jpg", quality=90)
body = np.asarray(load(body_f))[..., 3].astype(np.int32)
mask_png(body, "neoprene_mask")
mask_png(np.asarray(load(st_f))[..., 3], "stitching_mask")
mask_png(body, "art_zone_side1")          # the art is clipped to the face
mask_png(body, "art_zone_side2")          # (whichever side is shown)
# The photo's shading, with its contrast raised about its middle grey: the
# body colour is laid on flat, and overlaid at the layer's own contrast a
# saturated colour came out with no light on it at all.
sh = np.asarray(load(sh_f)).astype(np.float32)
mid = np.median(sh[..., 0][sh[..., 3] > 128])
g = np.clip(128 + (sh[..., 0] - mid) * CONTRAST, 0, 255)
Image.fromarray(np.dstack([g, g, g, sh[..., 3]]).astype(np.uint8), "RGBA").save(OUT / "texture_overlay.png")
load(soft_f).save(OUT / "texture_screen.png")
load(rim_f).save(OUT / "rim.png")
load(edge_f).save(OUT / "edges.png")


def can(m):
    """Left, right, top and bottom of a can body, measured at its middle."""
    ys, xs = np.nonzero(m)
    x0, x1 = xs.min(), xs.max()
    col = m[:, (x0 + x1) // 2]
    yy = np.nonzero(col)[0]
    return x0, x1, yy.min(), yy.max()


# The product mockup's Side 1: the print area as a share of its can.
P = HERE / "static" / "assets" / pid
pb = np.asarray(Image.open(P / "neoprene_mask.png").convert("RGBA"))[..., 3] > 128
pz = np.asarray(Image.open(P / "art_zone_side1.png").convert("RGBA"))[..., 3] > 128
zy, zx = np.nonzero(pz)
left = pb.copy(); left[:, zx.max() + 60:] = False      # the Side 1 can only
bx0, bx1, by0, by1 = can(left)
bw, bh = bx1 - bx0 + 1, by1 - by0 + 1
share = ((zx.min() - bx0) / bw, (zx.max() - zx.min() + 1) / bw,
         (zy.min() - by0) / bh, (zy.max() - zy.min() + 1) / bh)

lx0, lx1, ly0, ly1 = can(body > 128)
lw, lh = lx1 - lx0 + 1, ly1 - ly0 + 1
# Across, the print area is centred on the face the camera sees (the seam is
# at its left edge); down, it keeps the mockup's place on the can.
w = share[1] * lw
b = {"x": int(round((lx0 + lx1) / 2 - w / 2)), "y": int(round(ly0 + share[2] * lh)),
     "w": int(round(share[1] * lw)), "h": int(round(share[3] * lh))}

life = {"bounds": b}
if place:
    # PLACE: a JSON file measured off Numo's placement shot, in the photo's
    # pixels: "left" and "mid" (the print area's left edge and centre line)
    # and "top" / "bottom" ([x, y] points along its top and bottom lines).
    #
    # The camera looks down on the can a little, so a line round the can is
    # an ellipse: at angle a from the camera it sits at  y0 + b*cos(a), lowest
    # at the front. Each line's y0 and b are fitted to its points; the left
    # edge and centre line give the turn (phase) and the half-arc.
    import math
    pl = json.load(open(place))
    k = S / src_w
    full = np.asarray(Image.open(body_f).convert("RGBA"))[..., 3] > 128
    ys_, _ = np.nonzero(full)
    mid = (ys_.min() + ys_.max()) // 2
    sil = [np.nonzero(full[y])[0] for y in range(mid - 200, mid + 201, 50)]
    c0 = float(np.median([r.min() for r in sil])); c1 = float(np.median([r.max() for r in sil]))
    cc, R = (c0 + c1) / 2, (c1 - c0) / 2
    ang = lambda x: math.asin(max(-1, min(1, (x - cc) / R)))
    a1, am = ang(pl["left"]), ang(pl["mid"])
    half = am - a1

    def fit(pts):
        A = np.array([[1, math.cos(ang(x))] for x, _ in pts]); yv = np.array([y for _, y in pts])
        (y0, bb), *_ = np.linalg.lstsq(A, yv, rcond=None)
        return float(y0), float(bb)
    ty0, tb = fit(pl["top"]); by0, bb = fit(pl["bottom"])
    xl, xr = cc + R * math.sin(a1), cc + R * math.sin(min(math.pi / 2, am + half))
    life = {"bounds": {"x": round(xl * k, 1), "y": round((ty0 + tb) * k, 1),
                       "w": round((xr - xl) * k, 1), "h": round((by0 + bb - ty0 - tb) * k, 1)},
            "wrap": round(math.degrees(2 * half), 2), "phase": round(math.degrees(am), 2),
            "can": {"cx": round(cc * k, 2), "r": round(R * k, 2)},
            "top": [round(ty0 * k, 2), round(tb * k, 2)], "bottom": [round(by0 * k, 2), round(bb * k, 2)],
            "_measured": pl.get("_from", "")}
    b = life["bounds"]

json.dump({
    "product": pid, "width": S, "height": S,
    "_about": f"Lifestyle photo for {pid}, built by tools/make_lifestyle_assets.py from Numo's layers.",
    "lifestyle": life,
    "exports": {
        "background": {"file": "background.jpg", "blend": "normal"},
        "neoprene_mask": {"file": "neoprene_mask.png", "role": "color_mask"},
        "art_zone_side1": {"file": "art_zone_side1.png", "role": "art_clip"},
        "art_zone_side2": {"file": "art_zone_side2.png", "role": "art_clip"},
        "stitching_mask": {"file": "stitching_mask.png", "role": "color_mask"},
        "texture_overlay": {"file": "texture_overlay.png", "blend": "overlay"},
        "texture_screen": {"file": "texture_screen.png", "blend": "multiply"},
        "rim": {"file": "rim.png", "role": "overlay_top"},
        "edges": {"file": "edges.png", "role": "overlay_top"},
    }}, open(OUT / "manifest.json", "w"), indent=1)
print(out_id, json.dumps(life))
