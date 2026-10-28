"""
Waterslide decal plates, screen printed (Numo, 2026-10-13).

A waterslide decal is screened onto decal paper in layers, then a clear cover
coat over everything; in the shop it is soaked, slid off the paper and laid on
the item face up. So the FIRST layer printed is the one against the item:

    1  White back   the art's shape, pulled in a little (the choke) so no
                    white peeks out past the colour edges. On clear glass it
                    is what makes the colours opaque instead of see-through.
    2… one plate per ink (the PMS screens), in the order given
    N  Cover coat   the art's shape grown by a margin (the spread), holes
                    filled - the clear film that carries the decal.

Every plate is right-reading, 1:1, black on white (a film positive), all the
same page size with the same registration targets, so the screens line up.

How: the job's art is separated by ink at its print size (onecolor.separate,
the same as every screen-printed item), Ghostscript renders each separation as
its own plate image (tiffsep), and each plate - and the white and cover coat
made from their union - is traced back to vector (vectorize, potrace) at
`dpi` (1200: a hundredth of a millimetre-ish; 6 pt type keeps its shape).

    make_plates([(slot_label, separated_pdf), ...], ink_names, out_dir, prefix,
                opts=None, info=None)
        -> {"plates": [{"name", "file", "order"}], "proof": path, "notes": [...]}

opts (PRODUCTS[...]["decal"] overrides the defaults below).
"""
import subprocess
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image

DEFAULTS = {
    "dpi": 1200,              # plates traced at this resolution
    "white_back": True,       # print a white back (first, against the item)
    "white_choke_pt": 0.5,    # how far the white is pulled in from the art's edge
    "white_fine_full": True,  # art too fine to choke keeps a full-size white back
    "cover_spread_in": 0.0625,  # cover coat past the art's edge (1/16")
    "cover_fill_holes": True, # cover coat one solid shape (no holes in letters)
    "margin_in": 0.75,        # page edge to art, room for the targets
    "gap_in": 0.5,            # between locations on one sheet
    "mirror": False,          # right-reading
}


# ── masks ──────────────────────────────────────────────────────────────────

def _shift_or(m, dy, dx):
    o = np.zeros_like(m)
    h, w = m.shape
    ys, yd = (slice(0, h - dy), slice(dy, h)) if dy >= 0 else (slice(-dy, h), slice(0, h + dy))
    xs, xd = (slice(0, w - dx), slice(dx, w)) if dx >= 0 else (slice(-dx, w), slice(0, w + dx))
    o[yd, xd] = m[ys, xs]
    return o


def grow(mask, r):
    """Mask grown by about `r` px all round - an octagon, alternating 4- and
    8-neighbour steps (round enough for a margin; no scipy needed)."""
    m = mask.copy()
    k = int(round(r))
    for i in range(k):
        n = m.copy()
        n |= _shift_or(m, 1, 0); n |= _shift_or(m, -1, 0)
        n |= _shift_or(m, 0, 1); n |= _shift_or(m, 0, -1)
        if i % 2:
            n |= _shift_or(m, 1, 1); n |= _shift_or(m, 1, -1)
            n |= _shift_or(m, -1, 1); n |= _shift_or(m, -1, -1)
        m = n
    return m


def shrink(mask, r):
    return ~grow(~mask, r)


def _fill_holes_fast(mask):
    """Holes filled: background pixels not connected to the border become ink.
    Iterative propagation from the border through background, 4-connected."""
    bg = ~mask
    reach = np.zeros_like(mask)
    reach[0, :] = bg[0, :]; reach[-1, :] = bg[-1, :]
    reach[:, 0] = bg[:, 0]; reach[:, -1] = bg[:, -1]
    while True:
        # Sweep along rows and columns with cumulative logic: a run of
        # background touching a reached pixel is reached.
        prev = reach.sum()
        for axis in (0, 1):
            for flip in (False, True):
                r = np.flip(reach, axis) if flip else reach
                b = np.flip(bg, axis) if flip else bg
                # propagate along axis: reached[i] |= reached[i-1] & bg[i]
                r = r.copy()
                if axis == 0:
                    for i in range(1, r.shape[0]):
                        r[i] |= r[i - 1] & b[i]
                else:
                    for i in range(1, r.shape[1]):
                        r[:, i] |= r[:, i - 1] & b[:, i]
                reach = np.flip(r, axis) if flip else r
        if reach.sum() == prev:
            break
    return ~reach


# ── separation → plate images ──────────────────────────────────────────────

def _render_separations(sep_pdf, dpi, work):
    """{spot name: ink mask} for every named spot in the file (tiffsep)."""
    out = Path(work) / "s.tif"
    subprocess.run(["gs", "-q", "-dNOPAUSE", "-dBATCH", "-dSAFER", "-sDEVICE=tiffsep",
                    f"-r{dpi}", "-dFirstPage=1", "-dLastPage=1",
                    f"-sOutputFile={out}", str(sep_pdf)], check=True, timeout=600)
    masks = {}
    for f in Path(work).glob("s(*).tif"):
        name = f.name[2:-5]
        if name in ("Cyan", "Magenta", "Yellow", "Black"):
            continue
        a = np.asarray(Image.open(f))
        masks[name] = a < 128          # tiffsep: 0 = full ink
    return masks


def _curves(mask):
    import vectorize
    if not mask.any():
        return []
    return vectorize._trace_curves(mask, turdsize=2, alphamax=1.0, opttolerance=0.2)


def _draw(c, curves, x0, y0, px_pt, h_px, mirror_w=None):
    """Curves (pixel space, y down) onto the canvas, art's top-left at (x0, y0 + h)."""
    if not curves:
        return
    def P(pt):
        x = pt.x * px_pt
        if mirror_w is not None:
            x = mirror_w - x
        return x0 + x, y0 + (h_px - pt.y) * px_pt
    p = c.beginPath()
    for cv in curves:
        p.moveTo(*P(cv.start_point))
        for s in cv.segments:
            if s.is_corner:
                p.lineTo(*P(s.c)); p.lineTo(*P(s.end_point))
            else:
                p.curveTo(*P(s.c1), *P(s.c2), *P(s.end_point))
        p.close()
    c.drawPath(p, fill=1, stroke=0, fillMode=0)


def _fit_text(c, x, y, width, text, size, font="Helvetica"):
    """One line of text, made smaller until it fits `width`."""
    while size > 4 and c.stringWidth(text, font, size) > width:
        size -= 0.5
    c.setFont(font, size)
    c.drawString(x, y, text)


def _target(c, x, y, r=9):
    c.setLineWidth(0.5)
    c.circle(x, y, r * 0.6, fill=0, stroke=1)
    c.line(x - r, y, x + r, y)
    c.line(x, y - r, x, y + r)


# ── the plates ─────────────────────────────────────────────────────────────

def make_plates(locations, ink_names, out_dir, prefix, opts=None, info=None):
    """
    locations: [(label, separated_pdf)] - each PDF one page, the art at its
               print size, inks as named Separations (onecolor.separate).
    ink_names: the PMS names, in print order (also the colours: info["hex"]).
    info:      {"order": "NSO…", "item": "9613", "hex": {name: "#rrggbb"}}
    """
    o = dict(DEFAULTS, **(opts or {}))
    info = info or {}
    out_dir = Path(out_dir); out_dir.mkdir(parents=True, exist_ok=True)
    dpi = int(o["dpi"]); px_pt = 72.0 / dpi
    notes = []
    locs = []
    with tempfile.TemporaryDirectory() as td:
        for i, (label, pdf) in enumerate(locations):
            w = Path(td) / f"l{i}"; w.mkdir()
            masks = _render_separations(pdf, dpi, w)
            h_px, w_px = next(iter(masks.values())).shape if masks else (1, 1)
            union = np.zeros((h_px, w_px), bool)
            for m in masks.values():
                union |= m
            # Room round the art for the cover coat's spread.
            pad = int(round(o["cover_spread_in"] * dpi)) + 4
            def padded(m):
                return np.pad(m, pad)
            union_p = padded(union)
            loc = {"label": label, "w_px": w_px + 2 * pad, "h_px": h_px + 2 * pad, "curves": {}}
            for n in ink_names:
                if n in masks:
                    loc["curves"][n] = _curves(padded(masks[n]))
            if o["white_back"]:
                choke = o["white_choke_pt"] / 72.0 * dpi
                white = shrink(union_p, choke)
                # Lines thinner than twice the choke lose their white back
                # entirely (they print see-through on clear glass).
                # White thinner than about 0.5 pt won't hold on the screen:
                # only white that survives that counts as backing the art.
                t = 0.25 / 72.0 * dpi
                held = grow(shrink(white, t), t)
                back = grow(held, choke + t + 1.5) & union_p
                fine = union_p & ~back
                lost = fine.sum() / max(1, union_p.sum())
                if o["white_fine_full"]:
                    white = held | fine
                    if lost > 0.005:
                        notes.append(f"{label}: {lost:.0%} of the art is finer than "
                                     f"{2 * o['white_choke_pt']:.2g} pt - its white back is full size "
                                     f"there (not pulled in), so registration has to be tight")
                elif lost > 0.005:
                    notes.append(f"{label}: {lost:.0%} of the art is finer than "
                                 f"{2 * o['white_choke_pt']:.2g} pt and gets no white back "
                                 f"(thin lines and small type print see-through)")
                loc["curves"]["White"] = _curves(white)
            # The cover coat: worked at a quarter of the resolution (a margin
            # doesn't need 1200 dpi) and traced from there.
            q = 4
            hq, wq = union_p.shape[0] // q, union_p.shape[1] // q
            small = union_p[:hq * q, :wq * q].reshape(hq, q, wq, q).any(axis=(1, 3))
            cov = grow(small, o["cover_spread_in"] * dpi / q)
            if o["cover_fill_holes"]:
                cov = _fill_holes_fast(cov)
            import vectorize
            cc = vectorize._trace_curves(cov, turdsize=2, alphamax=1.2, opttolerance=0.4) if cov.any() else []
            loc["cover"] = (cc, q)
            locs.append(loc)

    # One sheet size for every plate.
    margin = o["margin_in"] * 72; gap = o["gap_in"] * 72
    W = sum(l["w_px"] * px_pt for l in locs) + gap * (len(locs) - 1) + 2 * margin
    Hart = max(l["h_px"] * px_pt for l in locs)
    H = Hart + 2 * margin + 18
    xs, x = [], margin
    for l in locs:
        xs.append(x)
        x += l["w_px"] * px_pt + gap
    y0 = margin

    plates = (["White"] if o["white_back"] else []) + list(ink_names) + ["Cover Coat"]
    from reportlab.pdfgen import canvas as rlcanvas
    out = []
    tag = " | ".join(t for t in (info.get("order"), info.get("item")) if t)
    for k, name in enumerate(plates, 1):
        slug = "".join(ch for ch in name.replace("PANTONE", "PMS") if ch.isalnum())
        f = out_dir / f"{prefix}-Decal-{k}-{slug}.pdf"
        c = rlcanvas.Canvas(str(f), pagesize=(W, H))
        c.setFillColorRGB(0, 0, 0); c.setStrokeColorRGB(0, 0, 0)
        for l, lx in zip(locs, xs):
            if name == "Cover Coat":
                cc, q = l["cover"]
                _draw(c, cc, lx, y0, px_pt * q, l["h_px"] / q,
                      mirror_w=(l["w_px"] * px_pt) if o["mirror"] else None)
            else:
                _draw(c, l["curves"].get(name, []), lx, y0, px_pt, l["h_px"],
                      mirror_w=(l["w_px"] * px_pt) if o["mirror"] else None)
        # Registration: the same four targets on every plate.
        for tx, ty in ((margin / 2, H / 2), (W - margin / 2, H / 2),
                       (W / 2, margin / 2), (W / 2, H - margin / 2 - 9)):
            _target(c, tx, ty)
        _fit_text(c, margin, H - 14, W - 2 * margin,
                  f"{tag}  -  DECAL PLATE {k} OF {len(plates)}: {name.upper()}"
                  f"  -  print {k}{'st' if k == 1 else 'nd' if k == 2 else 'rd' if k == 3 else 'th'}", 7)
        if o["mirror"]:
            c.drawRightString(W - margin, H - 14, "MIRRORED")
        c.save()
        out.append({"name": name, "file": str(f), "order": k})

    # The proof: all layers in colour, as they stack on the item.
    proof = out_dir / f"{prefix}-Decal-proof.pdf"
    _proof(proof, locs, xs, y0, W, H, px_pt, ink_names, info, o, tag)
    return {"plates": out, "proof": str(proof), "notes": notes,
            "sheet_in": [round(W / 72, 2), round(H / 72, 2)]}


def _hex01(h):
    h = (h or "#000000").lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))


def _proof(path, locs, xs, y0, W, H, px_pt, ink_names, info, o, tag):
    from reportlab.pdfgen import canvas as rlcanvas
    c = rlcanvas.Canvas(str(path), pagesize=(W, H))
    c.setFillColorRGB(0.55, 0.6, 0.65); c.rect(0, 0, W, H, fill=1, stroke=0)   # stand-in for the glass
    hexes = info.get("hex") or {}
    for l, lx in zip(locs, xs):
        cc, q = l["cover"]
        c.setFillColorRGB(0.85, 0.92, 0.97, alpha=0.55)
        _draw(c, cc, lx, y0, px_pt * q, l["h_px"] / q)
        c.setFillAlpha(1)
        if o["white_back"]:
            c.setFillColorRGB(1, 1, 1)
            _draw(c, l["curves"].get("White", []), lx, y0, px_pt, l["h_px"])
        for n in ink_names:
            c.setFillColorRGB(*_hex01(hexes.get(n)))
            _draw(c, l["curves"].get(n, []), lx, y0, px_pt, l["h_px"])
        c.setFillColorRGB(0.1, 0.1, 0.1); c.setFont("Helvetica", 7)
        c.drawString(lx, y0 - 12, l["label"])
    c.setFillColorRGB(0, 0, 0)
    order = ["White"] if o["white_back"] else []
    order += [n.replace("PANTONE ", "") for n in ink_names] + ["Cover coat"]
    _fit_text(c, xs[0], H - 14, W - 2 * xs[0], f"{tag}  -  DECAL PROOF  -  print order: " + " > ".join(order),
              8, "Helvetica-Bold")
    c.save()
