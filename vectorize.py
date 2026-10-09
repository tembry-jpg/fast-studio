"""
vectorize.py — turn a raster upload into vector artwork fit for screen print.

╔══════════════════════════════════════════════════════════════════════════╗
║  WHAT THIS IS FOR                                                        ║
║                                                                          ║
║  Screen print needs vector: the press images a stencil, and a stencil    ║
║  cut from pixels carries the pixels' stair-stepped edges onto the        ║
║  garment. Customers send PNGs anyway. Tracing turns the one case that    ║
║  can be recovered — a flat-colour mark on a plain ground — into real     ║
║  outlines, and refuses the cases that cannot.                            ║
║                                                                          ║
║  It is NOT a general raster-to-vector converter. A photograph, a         ║
║  gradient or a soft-edged mark has no correct tracing, and the gates     ║
║  below exist to turn those away rather than produce something that       ║
║  looks plausible on screen and prints badly.                             ║
╚══════════════════════════════════════════════════════════════════════════╝

The traced PDF carries each colour in the SOURCE file's own colour, not in a
separation. That is deliberate: everything downstream — dropping the inks the
customer switched off, flattening what remains to one spot — already knows how
to work on a customer's vector file, and emitting one means none of it needs a
special case for traced art. A traced upload and an uploaded PDF are the same
kind of thing by the time they reach the press layout.

Measured behaviour, on a real one-colour logo printed at 4" (see the numbers
in the gates below for where these turn into thresholds):

    upload    effective dpi   paths   disagreement with the source
      128 px        32          32          6.64 %
      200 px        50          32          3.43 %
      300 px        75          32          2.23 %
      640 px       160          32          1.32 %
     2000 px       500          32          1.10 %

The path count is the striking part: the shape is recovered correctly even
from a thumbnail. Low resolution does not produce obvious garbage, it produces
something softly wrong — which is the more dangerous failure, because it looks
fine in a preview and mushy on press. Hence a hard floor rather than a warning.
"""

import logging
from pathlib import Path

import numpy as np
from PIL import Image

log = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Gates
# ─────────────────────────────────────────────────────────────────────────────
#
# Every threshold here is a measurement, not a preference. Change one only
# against a printed sheet.
#
# Two different numbers per measurement, and they do different jobs. The
# *_GOOD values are what the art would ideally be and are used only to work
# out the advice — "print it this wide and it's clean". The *_MENTION values
# are the ones that decide whether the customer is told anything at all.
#
# They were the same number to begin with, and that is what made the notice
# fire on jobs that print perfectly well. Screen printing is a process with
# gain in it: a little fill on a fine serif is normal, expected, and not what
# anyone means by a bad print. Warning at the ideal treats the ordinary as a
# defect, and a notice that fires on ordinary work teaches people to click
# past it — which is exactly when it stops protecting the one job that
# really is too fine to hold.

# Resolution, as dots per inch AT THE SIZE THE CUSTOMER PLACED THE ART — not
# the file's own dpi tag, which is decoration and frequently wrong.
#
# These used to be borrowed from ordinary place-a-raster-in-a-layout advice
# (150 good, 75 floor), and that advice does not apply here. Nothing raster
# reaches the press: the image is traced to outlines first and the OUTLINES
# are scaled. There is no resampling at print time and no pixel to soften.
#
# What effective dpi actually predicts is how faithfully the trace follows
# the original, and that was measured rather than assumed — the same logo
# rendered at ten resolutions, traced, and compared against the true vector:
#
#     boundary error (mils)  ≈  160 / effective dpi
#
# Ink gain on a screen is 2–8 mil and registration tolerance is about 31 mil
# (1/32"), so the trace only becomes the worst thing on the sheet below about
# 40 dpi. At the old 150 the error is one mil — an order of magnitude inside
# the noise of the process, which is why that gate fired on work that prints
# perfectly.
#
# The failure that does matter is not wobble but LOSS: below roughly 50 dpi
# whole features start disappearing from the mask before potrace ever sees
# them. On the test logo, 21 distinct shapes survive at 53 dpi, 19 at 40, and
# 16 at 27. That is what these numbers are now set against, and it is also
# why the message talks about detail going missing rather than edges
# softening.
DPI_GOOD = 80.0        # advice only: "under this width it's clean"
DPI_MENTION = 50.0     # below here features begin to drop out
DPI_FLOOR = 30.0       # below here the trace has lost real parts of the mark

# The thinnest the press will hold. STROKE_GOOD_PT is comfortable on a coarse
# mesh over neoprene; STROKE_MENTION_PT is where fine detail starts closing
# up enough to be worth a word; below STROKE_FLOOR_PT a positive line really
# can drop out rather than merely thin.
#
# Gaps get their own floor, and a lower one, because they fail the other way:
# a gap does not disappear, it fills, and a filled counter in a small letter
# is a cosmetic loss rather than a lost mark.
STROKE_GOOD_PT = 0.75
STROKE_MENTION_PT = 0.55
STROKE_FLOOR_PT = 0.40
GAP_MENTION_PT = 0.45

# Colours a raster upload may be traced into. The press ceiling is higher
# (MAX_SPOT_INKS), but tracing hits its own limit first: every boundary
# between two traced colours is a seam, and the blend pixels along it belong
# to neither shape. Two colours is the case that works cleanly; three is
# allowed with a warning; past that the traps start eating thin features in
# whichever colour loses.
TRACE_COLORS_GOOD = 2
TRACE_COLORS_MAX = 3

# Spread applied to each colour mask before tracing a multi-colour job.
#
# Measured on a three-colour logo: untrapped, the seams between traced
# colours leave bare garment over 0.13–0.20% of the art, the widest gap 6.7
# mil from a 150 dpi upload and 3.3 mil from 300. One pixel of spread closes
# every one of them to zero, at a cost of 0.25–0.55% spill past the outer
# edge. That is an ordinary trap value — 2 to 8 mil is normal on press — and
# it is applied automatically because no customer should have to know the
# word "trap" to get a printable file.
TRAP_PX = 1

RASTER_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tiff", ".tif", ".webp"}


def is_raster(filename):
    return Path(filename).suffix.lower() in RASTER_EXTS


def available():
    """Whether tracing can run at all in this process."""
    try:
        import potrace  # noqa: F401
        return True
    except Exception:
        return False


# ─────────────────────────────────────────────────────────────────────────────
# Masks
# ─────────────────────────────────────────────────────────────────────────────

def _rgba(path_or_img):
    img = (path_or_img if isinstance(path_or_img, Image.Image)
           else Image.open(path_or_img))
    return np.asarray(img.convert("RGBA")).astype(int)


def ink_mask(path_or_img, ink=None, bg=(255, 255, 255), tol=90):
    """
    Which pixels carry ink.

    Transparency decides wherever the file has it — an alpha channel is the
    artist saying outright what is artwork and what is not, and no colour
    guess beats that. Failing that, ink is whatever is not the background
    colour, which is what a one-colour logo on white amounts to, and which
    keeps the counters: the holes inside the letters are the same white as
    the page, so they fall out on their own.

    With `ink`, only pixels near that colour count. That is the form used
    once the customer's reduction has decided which colours print.
    """
    a = _rgba(path_or_img)
    rgb, alpha = a[:, :, :3], a[:, :, 3]
    if (alpha < 250).any():
        base = alpha > 128
        if ink is None:
            return base
        return base & (np.abs(rgb - np.array(ink)).max(axis=2) <= tol)
    if ink is not None:
        return np.abs(rgb - np.array(ink)).max(axis=2) <= tol
    return np.abs(rgb - np.array(bg)).max(axis=2) > tol


def knockout_background(path_or_img, out_png, bg=(255, 255, 255), tol=90):
    """
    The image with everything that is not artwork made transparent.

    A one-colour product recolours the art to the chosen ink, and it does that
    to every pixel that is not transparent. A JPEG or a flattened PNG carries
    its background as opaque white, so without this the recolour fills the
    whole rectangle and the preview shows a solid block of ink where the logo
    should be — which is also, accurately, what would print.

    Run at upload so the preview, the colour separation and the trace are all
    looking at the same artwork. The mask is the one `trace` uses, so what the
    customer sees is what the press gets.
    """
    img = (path_or_img if isinstance(path_or_img, Image.Image)
           else Image.open(path_or_img)).convert("RGBA")
    a = np.asarray(img).copy()
    if (a[:, :, 3] < 250).any():
        # Already has transparency — the artist said what is artwork.
        img.save(str(out_png), "PNG")
        return str(out_png), False
    keep = ink_mask(img, bg=bg, tol=tol)
    a[:, :, 3] = np.where(keep, 255, 0).astype(np.uint8)
    Image.fromarray(a, "RGBA").save(str(out_png), "PNG")
    return str(out_png), True


def flat_share(path_or_img, ink_rgbs, bg=(255, 255, 255), tol=48.0, max_dim=400):
    """
    How much of the artwork is actually its inks: the share of non-background
    pixels within `tol` (RGB distance) of one of `ink_rgbs`.

    A flat-colour logo scores high even with soft edges — only the thin blend
    along each boundary misses. A photo or a gradient scores low however few
    inks it was squeezed into, and that is the case tracing must turn away:
    it would trace, and print as a posterised mess.
    """
    img = (path_or_img if isinstance(path_or_img, Image.Image)
           else Image.open(path_or_img)).convert("RGBA")
    if max(img.size) > max_dim:
        k = max_dim / max(img.size)
        img = img.resize((max(1, int(img.width * k)), max(1, int(img.height * k))), Image.NEAREST)
    a = np.asarray(img).astype(np.float32)
    rgb, alpha = a[..., :3], a[..., 3]
    art = alpha > 128
    if bg is not None:
        art &= np.linalg.norm(rgb - np.array(bg, np.float32), axis=2) > tol
    if not art.any() or not ink_rgbs:
        return 0.0
    px = rgb[art]
    pal = np.array(ink_rgbs, np.float32)
    d = np.linalg.norm(px[:, None, :] - pal[None, :, :], axis=2).min(axis=1)
    return float((d <= tol).mean())


def drop_blend_inks(inks, bg=(255, 255, 255), tol=18.0):
    """
    Remove "inks" that are only the blend along an edge.

    Anti-aliased artwork has a ring of in-between pixels wherever two colours
    meet — navy lettering on white leaves a band of greyish navy — and thin
    type has enough edge for that band to count as a colour of its own. A
    colour lying on the straight line between two others (or between one and
    the background), away from both ends, is that band, not an ink.

    inks: [{"hex", "share", ...}] biggest first. Returns the kept list.
    """
    def rgb(h):
        h = h.lstrip("#"); return np.array([int(h[i:i + 2], 16) for i in (0, 2, 4)], np.float32)
    pts = [rgb(i["hex"]) for i in inks]
    anchors = pts + [np.array(bg, np.float32)]
    kept = []
    for k, c in enumerate(pts):
        blend = False
        for a in range(len(anchors)):
            for b in range(a + 1, len(anchors)):
                if a == k or b == k:
                    continue
                A, B = anchors[a], anchors[b]
                AB = B - A
                L = float(AB @ AB)
                if L < 1:
                    continue
                t = float((c - A) @ AB) / L
                if 0.12 < t < 0.88 and np.linalg.norm(A + t * AB - c) <= tol:
                    # only a blend if it is the smaller of the two it sits between
                    if inks[k].get("share", 0) < max(
                            (inks[a].get("share", 1) if a < len(inks) else 1),
                            (inks[b].get("share", 1) if b < len(inks) else 1)):
                        blend = True
                        break
            if blend:
                break
        if not blend:
            kept.append(inks[k])
    total = sum(i.get("share", 0) for i in kept) or 1
    for i in kept:
        i["share"] = round(i.get("share", 0) / total, 3)
    return kept


def masks_for_inks(path_or_img, inks, bg=(255, 255, 255)):
    """
    One mask per kept ink, by nearest colour.

    Nearest-colour rather than per-ink tolerance, so every artwork pixel lands
    in exactly one mask. Tolerances leave the blend pixels along a boundary
    belonging to no ink at all, which is the seam this module traps against —
    better not to create more of them than the raster already has.

    `inks` is a list of (name, (r, g, b)). Background is a colour like any
    other here and simply gets no mask of its own.
    """
    a = _rgba(path_or_img)
    rgb, alpha = a[:, :, :3], a[:, :, 3]
    pal = np.array([c for _, c in inks] + [list(bg)])
    d = np.linalg.norm(rgb[:, :, None, :] - pal[None, None, :, :], axis=3)
    idx = d.argmin(axis=2)
    opaque = alpha > 128 if (alpha < 250).any() else np.ones(idx.shape, bool)
    return {name: (idx == i) & opaque for i, (name, _) in enumerate(inks)}


# ─────────────────────────────────────────────────────────────────────────────
# Measuring — the gates, before any tracing happens
# ─────────────────────────────────────────────────────────────────────────────

def _shift(a, dy, dx, fill=0):
    """`a` moved by (dy, dx), vacated edges filled — a roll that does not wrap."""
    out = np.full_like(a, fill)
    ys = slice(max(dy, 0), a.shape[0] + min(dy, 0))
    xs = slice(max(dx, 0), a.shape[1] + min(dx, 0))
    ys2 = slice(max(-dy, 0), a.shape[0] + min(-dy, 0))
    xs2 = slice(max(-dx, 0), a.shape[1] + min(-dx, 0))
    out[ys, xs] = a[ys2, xs2]
    return out


_NEIGH8 = [(dy, dx) for dy in (-1, 0, 1) for dx in (-1, 0, 1) if (dy, dx) != (0, 0)]


def erode(mask):
    """One 3x3 erosion. Off-image counts as empty, so edges erode inward."""
    out = mask.copy()
    for dy, dx in _NEIGH8:
        out &= _shift(mask, dy, dx, False)
    return out


_NEIGH4 = [(-1, 0), (1, 0), (0, -1), (0, 1)]


def dilate(mask, iterations=1, diagonal=False):
    """
    One or more dilations.

    Four-connected by default — a cross, not a square — which is what the trap
    measurement was made with. Growing corners as well would spread a diagonal
    edge by √2 px instead of 1 and put more ink down than the 0.25–0.55% spill
    that figure assumes.
    """
    neigh = _NEIGH8 if diagonal else _NEIGH4
    out = mask
    for _ in range(max(0, iterations)):
        grown = out.copy()
        for dy, dx in neigh:
            grown |= _shift(out, dy, dx, False)
        out = grown
    return out


def fill_holes(mask):
    """
    `mask` with enclosed gaps filled — the silhouette of the artwork.

    Grows the outside inward from the image border until it stops, which
    reaches every empty pixel connected to the edge. What is left empty is
    enclosed, and those are the gaps that can close up on press.
    """
    empty = ~mask
    outside = np.zeros_like(mask)
    outside[0, :] |= empty[0, :]
    outside[-1, :] |= empty[-1, :]
    outside[:, 0] |= empty[:, 0]
    outside[:, -1] |= empty[:, -1]
    while True:
        grown = dilate(outside) & empty
        if grown.sum() == outside.sum():
            break
        outside = grown
    return mask | (empty & ~outside)


def _thinnest(mask, px_per_inch, pct=2.0, cap_pt=4.0):
    """
    The narrowest run of True in `mask`, in points, or None if everything is
    comfortably thicker than `cap_pt`.

    Counts how many 3x3 erosions each pixel survives, which is its distance to
    the nearest empty pixel; the ridge of that field is the local half-width of
    whatever it sits inside. A low percentile of the ridge finds the thinnest
    real stroke while ignoring the single-pixel tips where every shape tapers
    to nothing and which would otherwise report zero for all artwork.

    Capped deliberately, for two reasons. It keeps the cost proportional to how
    thin the art is rather than how large the file is — a solid disc is
    hundreds of pixels deep at its centre and none of that depth matters. And
    the gate only needs to know whether anything is TOO THIN; the exact width
    of a thick stroke is not a number anyone acts on.

    Erosion distance rather than a true Euclidean transform: it reads a
    diagonal stroke slightly narrower than it is, which errs toward warning
    about art that would have been fine rather than passing art that will not
    print. For a gate that is the right direction to be wrong in.
    """
    if not mask.any():
        return None
    cap = max(1, int(np.ceil(cap_pt / 72.0 * px_per_inch / 2)))
    d = np.zeros(mask.shape, np.int32)
    cur = mask
    for _ in range(cap):
        cur = erode(cur)
        if not cur.any():
            break
        d += cur
    d += mask                      # every ink pixel is at least 1 deep

    ridge = d.copy()
    for dy, dx in _NEIGH8:
        ridge = np.maximum(ridge, _shift(d, dy, dx, 0))
    # Everything that hit the cap is one flat plateau, and every pixel of it
    # counts as a local maximum — on a mark with any solid area that is tens
    # of thousands of pixels, all at the same value, and they drown the
    # percentile so completely that a hairline reads as a thick stroke. They
    # are saturated rather than measured, so they are dropped: what remains is
    # the strokes the cap was wide enough to resolve, which are exactly the
    # ones thin enough to matter.
    saturated = d.max() if d.size else 0
    peaks = d[(d >= ridge) & mask & (d < max(saturated, 2))]
    peaks = peaks[peaks > 0]
    if not peaks.size:
        return None                     # nothing thinner than the cap
    return float(np.percentile(peaks, pct)) * 2 / px_per_inch * 72.0


def measure(mask, printed_w_in, printed_h_in=None):
    """
    The numbers the gates are decided on, for art placed at a given size.

    Cheap on purpose: no tracing happens here. The configurator re-checks on
    every resize, and the answer has to arrive while the customer is still
    dragging the handle.
    """
    h, w = mask.shape
    printed_h_in = printed_h_in or (printed_w_in * h / w)
    ppi_x = w / max(printed_w_in, 1e-6)
    ppi_y = h / max(printed_h_in, 1e-6)
    ppi = (ppi_x + ppi_y) / 2

    stroke = _thinnest(mask, ppi)
    # Gaps are measured only where they are enclosed by artwork; the open page
    # around the mark is not a gap that can close.
    filled = fill_holes(mask)
    gap = _thinnest(filled & ~mask, ppi)

    return {
        "effective_dpi": round(ppi, 1),
        "thinnest_stroke_pt": None if stroke is None else round(stroke, 2),
        "thinnest_gap_pt": None if gap is None else round(gap, 2),
        "ink_fraction": round(float(mask.mean()), 4),
    }


def assess(mask, printed_w_in, printed_h_in=None, n_colors=1):
    """
    Whether this art can be traced for press, and what to tell the customer.

    Returns a dict with `verdict` in {"ok", "warn", "refuse"} and a list of
    plain-sentence `notes`.

    At most ONE note about print quality, deliberately. The measurements
    behind it are all still in the returned dict — the thinnest stroke, the
    tightest gap, the effective resolution — and production can read them
    there. But the customer is not a prepress operator, and handing them six
    findings about one logo reads as a catalogue of everything wrong with
    their artwork. Screen printing has gain in it; a little fill on fine
    detail is the process working normally, not a fault. So the notice says
    the one thing a customer can act on, in one sentence, and says nothing at
    all until the art is genuinely fine enough to be worth mentioning.

    The lever named depends on which measurements are marginal, because they
    do not share a fix: thin detail wants the art printed larger, low
    resolution wants it printed smaller, and art that is short on both at
    once cannot be solved by resizing in either direction — only by better
    artwork. Advising "print it larger" on a job that is also low-resolution
    would trade one problem for the other.
    """
    m = measure(mask, printed_w_in, printed_h_in)
    notes, verdict = [], "ok"

    def worse(v):
        nonlocal verdict
        order = {"ok": 0, "warn": 1, "refuse": 2}
        if order[v] > order[verdict]:
            verdict = v

    dpi = m["effective_dpi"]
    st = m["thinnest_stroke_pt"]
    gp = m["thinnest_gap_pt"]

    # Where the art would have to sit for each measurement to be comfortable.
    # Both are in inches of printed width, so they can be compared directly —
    # and when the smaller of them is below the larger, no size works.
    max_w = mask.shape[1] / DPI_GOOD if dpi else None
    min_w = (printed_w_in * STROKE_GOOD_PT / st
             if st and st > 0 else None)

    coarse = dpi is not None and dpi < DPI_MENTION
    very_coarse = dpi is not None and dpi < DPI_FLOOR
    fine = ((st is not None and st < STROKE_MENTION_PT)
            or (gp is not None and gp < GAP_MENTION_PT))
    very_fine = st is not None and st < STROKE_FLOOR_PT

    if (coarse or very_coarse) and (fine or very_fine):
        # Resizing cannot fix both: wider thickens the detail but thins the
        # resolution, narrower does the reverse.
        worse("refuse" if (very_coarse or very_fine) else "warn")
        notes.append(
            "Because of the size of this imprint and the fine detail in the "
            "artwork, some of that detail may fill in on press. This image "
            f"is also only working out to {dpi:.0f} DPI at this size, so "
            "printing it larger would start losing detail instead of saving "
            "it — vector artwork (AI, EPS, PDF or SVG) is the one thing that "
            "holds both.")
    elif very_fine:
        worse("warn")
        notes.append(
            "Because of the size of this imprint and the fine detail in the "
            "artwork, some of that detail may fill in or break up on press. "
            + (f"Printing it {min_w:.1f}\" wide or larger keeps it open."
               if min_w else "Printing it larger keeps it open."))
    elif fine:
        worse("warn")
        notes.append(
            "Because of the size of this imprint and the fine detail in the "
            "artwork, some of that detail may fill in slightly on press. "
            "That is normal for screen printing and usually reads fine"
            + (f"; printing it {min_w:.1f}\" wide or larger keeps it fully "
               "open." if min_w else "."))
    elif very_coarse:
        worse("refuse")
        notes.append(
            f"This image is only {mask.shape[1]}px wide and you've placed it "
            f"at {printed_w_in:.2f}\", which works out to {dpi:.0f} DPI. "
            "There isn't enough in the file to follow at that size, so the "
            "finer parts of the mark won't make it through. Place it under "
            f"{max_w:.1f}\" wide, or send vector artwork (AI, EPS, PDF or "
            "SVG).")
    elif coarse:
        worse("warn")
        notes.append(
            f"At {printed_w_in:.2f}\" wide this image works out to "
            f"{dpi:.0f} DPI. It converts to vector and prints at a clean "
            "edge, but the file has little enough in it that the smallest "
            f"details may not survive the conversion. Under {max_w:.1f}\" "
            "wide they all come through, and vector artwork comes through at "
            "any size.")

    # Colours are a capability limit rather than a print-quality risk, so
    # this one is said separately and only when the limit is actually
    # exceeded. Three traced colours used to earn a warning of their own;
    # they no longer do, because TRAP_PX closes those seams automatically and
    # the warning was describing work the code had already done.
    if n_colors > TRACE_COLORS_MAX:
        worse("refuse")
        notes.append(
            f"This artwork has {n_colors} colours. We can trace up to "
            f"{TRACE_COLORS_MAX} from an image — past that the colours start "
            f"interfering with each other at their edges. Reduce it in the "
            f"colour panel, or send vector artwork.")

    m["verdict"] = verdict
    m["notes"] = notes
    return m


# ─────────────────────────────────────────────────────────────────────────────
# Tracing
# ─────────────────────────────────────────────────────────────────────────────

def _fast_bm_to_pathlist(bm, turdsize=2, turnpolicy=None):
    """potracer's bm_to_pathlist, with the same result, found faster.

    The library finds each next outline by searching the WHOLE bitmap
    (np.nonzero) for its last row that still has a pixel: once per outline,
    so a traced JPG with hundreds of outlines read millions of pixels hundreds
    of times - most of a ten-second trace. That row only ever moves down the
    bitmap (each outline found is cleared from it, and an outline never
    reaches above the row it was found in), so the search here carries on
    from where the last one stopped. Same row, same pixel, same order, so
    the same outlines.
    """
    import sys
    P = sys.modules["potrace.potrace"]
    if turnpolicy is None:
        turnpolicy = P.POTRACE_TURNPOLICY_MINORITY
    plist = []
    original = bm.copy()
    y = bm.shape[0] - 1
    while True:
        while y >= 0 and not bm[y].any():
            y -= 1
        if y < 0:
            break
        x = int(np.argmax(bm[y]))           # first set pixel in the row
        sign = original[y][x]
        path = P.findpath(bm, x, y + 1, sign, turnpolicy)
        if path is None:
            raise ValueError
        P.xor_path(bm, path)
        if path.area > turdsize:
            plist.append(path)
    return plist


def _speed_up_potrace():
    import sys
    P = sys.modules.get("potrace.potrace")
    if P is not None and getattr(P, "bm_to_pathlist", None) is not _fast_bm_to_pathlist:
        P.bm_to_pathlist = _fast_bm_to_pathlist


def _trace_curves(mask, turdsize=2, alphamax=1.0, opttolerance=0.2):
    """
    Outlines for one mask.

    Two things here are measured rather than assumed, and both fail by
    producing a plausible-looking wrong file rather than an error:

      * the bitmap must be boolean. potracer compares raw values against its
        blacklevel, so a 0/1 uint8 array reads as one flat field and comes
        back as a single rectangle the size of the page.

      * it must be INVERTED. potracer traces the False region, so passing the
        ink mask straight in fills the background and knocks out the
        artwork — and the result still looks like the logo at a glance,
        because every shape is correct. It is the ink and the paper that have
        swapped.
    """
    import potrace
    _speed_up_potrace()
    bmp = potrace.Bitmap(~mask.astype(bool))
    return bmp.trace(turdsize=turdsize, alphamax=alphamax,
                     opticurve=True, opttolerance=opttolerance).curves


def _emit(c, curves, sx, sy, pt_h):
    """Draw one colour's curves onto a reportlab canvas as a single path."""
    p = c.beginPath()
    for curve in curves:
        sp = curve.start_point
        p.moveTo(sp.x * sx, pt_h - sp.y * sy)
        for seg in curve.segments:
            if seg.is_corner:
                p.lineTo(seg.c.x * sx, pt_h - seg.c.y * sy)
                p.lineTo(seg.end_point.x * sx, pt_h - seg.end_point.y * sy)
            else:
                p.curveTo(seg.c1.x * sx, pt_h - seg.c1.y * sy,
                          seg.c2.x * sx, pt_h - seg.c2.y * sy,
                          seg.end_point.x * sx, pt_h - seg.end_point.y * sy)
        p.close()
    # Even-odd, so counters stay open instead of filling solid — the holes in
    # an O or an A are nested curves, and a nonzero rule fills them in.
    c.drawPath(p, fill=1, stroke=0, fillMode=0)


def trace(path_or_img, out_pdf, colors=None, bg=(255, 255, 255),
          printed_w_in=None, trap_px=TRAP_PX):
    """
    Trace a raster image to a one-page vector PDF.

    colors : [(name, (r, g, b))] — the inks to keep, each traced separately
             and filled in its own source colour. None traces everything that
             is not background as a single shape, which is the one-colour
             case.
    printed_w_in : the size the art will print at. The page is made that size
             so the vector carries its intended scale, the way an uploaded
             PDF does. Without it the page is the pixel grid at 72 dpi.

    Returns a dict describing what was produced, or raises if potrace is not
    installed.
    """
    from reportlab.pdfgen import canvas as rlcanvas

    img = (path_or_img if isinstance(path_or_img, Image.Image)
           else Image.open(path_or_img))
    if colors:
        masks = masks_for_inks(img, colors, bg=bg)
        order = [n for n, _ in colors]
        fills = dict(colors)
    else:
        masks = {"ink": ink_mask(img, bg=bg)}
        order, fills = ["ink"], {"ink": (0, 0, 0)}

    a = _rgba(img)
    h, w = a.shape[:2]
    pt_w = (printed_w_in * 72.0) if printed_w_in else w
    pt_h = pt_w * h / w
    sx, sy = pt_w / w, pt_h / h

    c = rlcanvas.Canvas(str(out_pdf), pagesize=(pt_w, pt_h))
    counts = {}
    # Largest area first, so a colour that sits behind another is laid down
    # first and the one in front covers its trap rather than the other way
    # round. Without this the spread from a background colour prints over the
    # detail sitting on top of it.
    painted = [n for n in sorted(order, key=lambda n: -int(masks[n].sum()))
               if masks[n].any()]
    for i, name in enumerate(painted):
        m = masks[name]
        # Trap every layer except the topmost. A lower colour spreads so the
        # one painted over it covers the seam; the top layer has nothing above
        # it to hide a spread, so trapping it would only grow the mark.
        if trap_px and i < len(painted) - 1:
            m = dilate(m, iterations=trap_px)
        curves = _trace_curves(m)
        r, g, b = fills[name]
        c.setFillColorRGB(r / 255.0, g / 255.0, b / 255.0)
        _emit(c, curves, sx, sy, pt_h)
        counts[name] = len(curves)
    c.save()

    return {
        "out": str(out_pdf),
        "paths": counts,
        "total_paths": sum(counts.values()),
        "page_pt": [pt_w, pt_h],
        "source_px": [w, h],
        "trapped": bool(trap_px and len(order) > 1),
    }
