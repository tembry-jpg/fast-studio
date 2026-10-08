"""
porous.py — print limits on open-weave bodies (burlap).

Burlap is an open weave: between the threads there are holes, and ink laid
over a hole has nothing to sit on. A line thinner than about one thread pitch
can cross a hole and come out broken; small lettering is made of exactly those
lines. Ink also wicks along the threads, so tight gaps (inside small letters,
between close lines) fill in.

So on these products the artwork is measured at its printed size, vector as
well as raster — the ordinary checks only look at raster art, because on
neoprene a vector line holds at any size the press can image. Here it doesn't.

The limits live on the product (products.py, "porous"), in points at printed
size, so production can tune them per material without touching this file:

    line_pt        finest line that prints solid; thinner is mentioned
    line_floor_pt  below this a line is likely to break up, said more firmly
    gap_pt         tightest gap that stays open
    pattern_ppi    pixels per inch of the body tile, so proofs show the weave
                   at its real size

The customer sentence carries no measurements (the house rule for these
notes); the figures travel with the job onto the proof for production.
"""
import shutil
import subprocess
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image

import vectorize as V

VECTOR_EXTS = {".pdf", ".ai"}
RENDER_PPI = 300          # px per printed inch the measurement is made at


def limits(product_id):
    """The product's porous-body limits, or None for an ordinary body."""
    try:
        from products import PRODUCTS
        lim = (PRODUCTS.get(product_id or "") or {}).get("porous")
        return dict(lim) if lim else None
    except Exception:
        return None


def _render(path, dpi):
    """A vector file's first page as RGBA (transparent background)."""
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "r"
        subprocess.run(["pdftocairo", "-png", "-transp", "-singlefile", "-r", str(int(dpi)),
                        "-f", "1", "-l", "1", str(path), str(out)],
                       check=True, capture_output=True, timeout=60)
        return Image.open(str(out) + ".png").convert("RGBA")


def vector_mask(path, printed_w_in):
    """Which pixels carry ink, at RENDER_PPI of the PRINTED size, as (mask, ppi)."""
    p = Path(path)
    if p.suffix.lower() not in VECTOR_EXTS or not shutil.which("pdftocairo"):
        return None, None
    # A first pass finds how wide the artwork is in the file; the second
    # renders it so the printed width comes out at RENDER_PPI.
    probe = _render(p, 72)
    a = np.asarray(probe)[:, :, 3] > 8
    if not a.any():
        return None, None
    xs = np.nonzero(a.any(axis=0))[0]
    art_w_pt = max(1.0, float(xs[-1] - xs[0] + 1))
    dpi = RENDER_PPI * printed_w_in / (art_w_pt / 72.0)
    dpi = max(36, min(dpi, 2400))
    img = _render(p, dpi)
    alpha = np.asarray(img)[:, :, 3]
    mask = alpha > 128
    ys, xs = np.nonzero(mask)
    if not len(xs):
        return None, None
    mask = mask[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    ppi = mask.shape[1] / max(printed_w_in, 1e-6)
    return mask, ppi


def assess(mask, ppi, printed_w_in, lim, zone_w_in=None):
    """
    The open-weave verdict for art measured at printed size.

    Returns {"verdict", "notes", "thinnest_stroke_pt", "thinnest_gap_pt",
    "porous": True}. Warnings only: whether to print it is the customer's call,
    which the export's acknowledgement records.
    """
    line_pt = float(lim.get("line_pt", 4.0))
    floor_pt = float(lim.get("line_floor_pt", 2.5))
    gap_pt = float(lim.get("gap_pt", 3.0))
    cap = max(line_pt, gap_pt) + 1.0
    st = V._thinnest(mask, ppi, cap_pt=cap)
    filled = V.fill_holes(mask)
    # Gaps taper to a point wherever two strokes meet (an A, a V); the tip
    # always reads near zero, so the gap is read further up its width.
    gp = V._thinnest(filled & ~mask, ppi, pct=50.0, cap_pt=cap)
    name = lim.get("name") or "This material"
    out = {"verdict": "ok", "notes": [], "porous": True,
           "thinnest_stroke_pt": None if st is None else round(st, 2),
           "thinnest_gap_pt": None if gp is None else round(gp, 2)}
    thin = st is not None and st < line_pt
    tight = gp is not None and gp < gap_pt
    nap = lim.get("kind") == "nap"
    if thin and nap:
        out["verdict"] = "warn"
        need = printed_w_in * line_pt / st
        fits = zone_w_in is None or need <= zone_w_in + 1e-6
        out["notes"].append(
            f"{name} has a rough nap, so the finest lines and smallest lettering in this "
            "artwork may print slightly broken or uneven. "
            + (f"Printing it {need:.1f}\" wide or larger, or bolder artwork, keeps them crisp."
               if fits else "Bolder artwork — thicker lines and larger lettering — prints best on it."))
    elif thin:
        out["verdict"] = "warn"
        need = printed_w_in * line_pt / st
        fits = zone_w_in is None or need <= zone_w_in + 1e-6
        strong = st < floor_pt
        out["notes"].append(
            f"{name} is an open weave, and the finest lines and smallest lettering in "
            f"this artwork are thinner than the gaps between its threads, so they "
            + ("will likely fall into the holes and print broken or patchy. "
               if strong else "can fall into the holes and print broken or patchy. ")
            + (f"Printing it {need:.1f}\" wide or larger, or bolder artwork, keeps them solid."
               if fits else
               "Bolder artwork — thicker lines and larger lettering — prints best on it."))
    if tight and nap:
        out["verdict"] = "warn"
        out["notes"].append(
            f"Ink can spread a little on {name.lower()}'s nap, so the tightest gaps in this "
            "artwork — inside small letters and between close lines — may fill in.")
    elif tight:
        out["verdict"] = "warn"
        out["notes"].append(
            f"Ink spreads along {name.lower()}'s threads, so the tightest gaps in this "
            "artwork — inside small letters and between close lines — may fill in.")
    return out


def check(path, printed_w_in, product_id, zone_w_in=None, mask=None):
    """Measure art (vector, or a raster mask given) against the product's limits."""
    lim = limits(product_id)
    if not lim:
        return None
    if mask is None:
        mask, ppi = vector_mask(path, printed_w_in)
    else:
        ppi = mask.shape[1] / max(printed_w_in, 1e-6)
    if mask is None:
        return None
    return assess(mask, ppi, printed_w_in, lim, zone_w_in)


def hole_mask(tile_rgb, strength=1.0):
    """
    Where the weave's holes are in a body tile, 0..1 per pixel.

    The holes photograph as the darkest pixels relative to their surroundings
    (shadow between the threads), so this is local darkness: how far each pixel
    sits below the local mean, scaled so the open holes reach 1.
    """
    from PIL import ImageFilter
    g = Image.fromarray(tile_rgb).convert("L")
    L = np.asarray(g).astype(np.float32)
    rad = max(2, int(min(L.shape) / 40))
    M = np.asarray(g.filter(ImageFilter.GaussianBlur(rad))).astype(np.float32)
    d = (M - L) / 255.0
    # About 15 % of a burlap tile reads as hole at these settings, which is
    # in line with the open area of a typical hessian weave.
    h = np.clip((d - 0.03) / 0.08, 0, 1) * strength
    return h
