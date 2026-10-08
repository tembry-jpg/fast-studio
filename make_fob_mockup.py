"""
make_fob_mockup.py — the Key Fob (0635-3m) mockup layers from the Photoshop
exports, plus the band geometry the configurator warps the art onto.

The photo shows two fobs: the top one ring-left (Side 1 face up), the bottom
one turned over, ring-right (Side 2 face up). Each visible face is a curved
band running from the stitched end (the slit next to the ring) to the fold.

Inputs (1350 x 1350 PNG with transparency, in this order):
  photo   the fob photo on transparency (rings, tab, shadows)
  face    the outer face (colour fabric) mask
  inside  the inside of the loop (back fabric) mask
  edge    the cut edge (foam) mask
  tex1    texture overlay (opaque mid-grey: the weave and shading)
  tex2    texture screen  (soft highlights)
  shadow  optional: black shadow on transparency, drawn as is over the
          colours and textures (darkens without shifting the hue)

    python3 tools/make_fob_mockup.py photo.png face.png inside.png edge.png overlay.png screen.png
"""
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent.parent
OUT = HERE / "static" / "assets" / "0635-3m"
CREAM = (251, 238, 222)          # the 0070-3m backdrop

# Where each visible face starts and ends (canvas px), read off the face mask:
# the stitched end (by the slit) and the fold end, top and bottom corners.
# Listed in reading order, so u=0 is the left of the art.
FACES = {
    # top fob, ring left: stitched end left, fold right
    "side1": {"rows": (400, 615), "top": (446, 1152), "bot": (456, 1194),
              "start": ((441, 447), (455, 600)), "end": ((1152, 453), (1194, 607))},
    # bottom fob, ring right, turned over: fold left, stitched end right
    "side2": {"rows": (660, 880), "top": (209, 911), "bot": (157, 896),
              "start": ((209, 700), (157, 858)), "end": ((912, 721), (896, 870))},
}
N = 48


def _alpha(path):
    return np.asarray(Image.open(path).convert("RGBA"))[:, :, 3]


def _white(alpha):
    a = np.zeros(alpha.shape + (4,), np.uint8)
    a[:, :, :3] = 255
    a[:, :, 3] = alpha
    return Image.fromarray(a, "RGBA")


def _edge(mask, rows, xr, which):
    """The face's top or bottom outline between two x's, as (x, y) points."""
    y0, y1 = rows
    pts = []
    for x in range(xr[0], xr[1] + 1):
        ys = np.nonzero(mask[y0:y1, x])[0]
        if len(ys):
            pts.append((x, y0 + (ys.min() if which == "top" else ys.max())))
    return np.array(pts, float)


def _resample(pts, a, b, n):
    """n points along a polyline from a to b, evenly by arc length."""
    p = np.vstack([a, pts, b])
    d = np.r_[0, np.cumsum(np.hypot(*np.diff(p, axis=0).T))]
    t = np.linspace(0, d[-1], n)
    return np.c_[np.interp(t, d, p[:, 0]), np.interp(t, d, p[:, 1])]


def _hit(p, d, poly):
    """Where the ray p + s*d (s > 0) first crosses the polyline, or None."""
    best = None
    for a, b in zip(poly[:-1], poly[1:]):
        e = b - a
        den = d[0] * e[1] - d[1] * e[0]
        if abs(den) < 1e-9:
            continue
        w = a - p
        s_ = (w[0] * e[1] - w[1] * e[0]) / den
        t_ = (w[0] * d[1] - w[1] * d[0]) / den
        if s_ > 0 and -1e-6 <= t_ <= 1 + 1e-6 and (best is None or s_ < best):
            best = s_
    return None if best is None else p + best * d


def bands(face_alpha):
    """
    Each face as N cross-lines from its top edge to its bottom edge.

    The cross-lines turn smoothly from the slant of the stitched end to the
    slant of the fold end, so art and background lines run parallel to the
    stitching where they meet it. Pairing the top and bottom edges by their
    own lengths instead let the cross-lines wobble wherever the traced bottom
    edge was rough — on Side 2 they leaned against the stitching by the slit.
    """
    m = face_alpha > 128
    out = {}
    for sid, f in FACES.items():
        top = _resample(_edge(m, f["rows"], f["top"], "top"), f["start"][0], f["end"][0], N)
        raw = _edge(m, f["rows"], f["bot"], "bottom")
        # A running median smooths the traced bottom edge (the slit and the
        # fabric's ragged edge make single-pixel spikes).
        ys = raw[:, 1].copy()
        k = 7
        for i in range(len(ys)):
            ys[i] = np.median(raw[max(0, i - k):i + k + 1, 1])
        bot_line = np.vstack([np.array(f["start"][1], float), np.c_[raw[:, 0], ys],
                              np.array(f["end"][1], float)])
        sd = np.subtract(f["start"][1], f["start"][0]).astype(float)
        ed = np.subtract(f["end"][1], f["end"][0]).astype(float)
        sd /= np.hypot(*sd); ed /= np.hypot(*ed)
        # Extend the bottom line a little past both ends so end rays still hit it.
        ext = np.vstack([bot_line[0] - (bot_line[1] - bot_line[0]) * 20, bot_line,
                         bot_line[-1] + (bot_line[-1] - bot_line[-2]) * 20])
        bot = []
        for i, tp in enumerate(top):
            u = i / (N - 1)
            d = sd * (1 - u) + ed * u
            d /= np.hypot(*d)
            q = _hit(tp, d, ext)
            bot.append(q if q is not None else tp + d * np.hypot(*np.subtract(f["start"][1], f["start"][0])))
        bot[0], bot[-1] = np.array(f["start"][1], float), np.array(f["end"][1], float)
        out[sid] = {"top": top.round(1).tolist(), "bot": np.array(bot).round(1).tolist()}
    return out


def build(photo, face, inside, edge, tex1, tex2, shadow=None):
    OUT.mkdir(parents=True, exist_ok=True)
    bg = Image.new("RGBA", (1350, 1350), CREAM + (255,))
    bg.alpha_composite(Image.open(photo).convert("RGBA"))
    bg.convert("RGB").save(OUT / "background.png", optimize=True)
    fa = _alpha(face)
    _white(fa).save(OUT / "neoprene_mask.png", optimize=True)
    _white(_alpha(inside)).save(OUT / "back_mask.png", optimize=True)
    _white(_alpha(edge)).save(OUT / "foam_mask.png", optimize=True)
    Image.open(tex1).convert("RGBA").save(OUT / "texture_overlay.png", optimize=True)
    Image.open(tex2).convert("RGBA").save(OUT / "texture_screen.png", optimize=True)
    for f in ("footer_bg.png",):
        src = HERE / "static" / "assets" / "0070-3m" / f
        if src.exists():
            (OUT / f).write_bytes(src.read_bytes())
    manifest = {
        "product": "0635-3m", "width": 1350, "height": 1350,
        "exports": {
            "background": {"file": "background.png", "blend": "normal"},
            "neoprene_mask": {"file": "neoprene_mask.png", "role": "color_mask"},
            "back_mask": {"file": "back_mask.png", "role": "back_mask"},
            "foam_mask": {"file": "foam_mask.png", "role": "foam_mask"},
            "texture_overlay": {"file": "texture_overlay.png", "blend": "overlay"},
            "texture_screen": {"file": "texture_screen.png", "blend": "screen"},
            "footer_bg": {"file": "footer_bg.png", "blend": "normal", "opacity": 0.8},
        },
    }
    if shadow:
        Image.open(shadow).convert("RGBA").save(OUT / "inside_shadow.png", optimize=True)
        manifest["exports"]["inside_shadow"] = {"file": "inside_shadow.png", "role": "shadow", "strength": 2}
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=1) + "\n")
    b = bands(fa)
    (OUT / "bands.json").write_text(json.dumps(b) + "\n")
    return b


if __name__ == "__main__":
    b = build(*sys.argv[1:8])
    for sid, v in b.items():
        print(sid, "top", v["top"][0], "→", v["top"][-1], " bot", v["bot"][0], "→", v["bot"][-1])
