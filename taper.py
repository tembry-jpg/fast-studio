"""
Glass art for direct screen print on a tapered glass.

IN USE: widen_pdf (at the end) - the art made a set amount wider, height
unchanged, every row the same (PRODUCTS[...]["glass_widen"]). Numo's press
tilts the glass so the screen follows the taper; the art is printed flat and
not bent (Numo, 2026-10-13).

AVAILABLE, OFF: warp_pdf below, the row-by-row taper fix. press_layout uses it
only for an item with PRODUCTS[...]["glass_taper_fix"] = True (none now).

Taper correction for direct screen print on a tapered glass.

The press rolls the glass under a flat screen moving at one speed. The glass
is wider at the top of the print than at the bottom, so the screen and the
glass surface only move together at one diameter, D_match. Art at any other
height prints stretched by D(depth) / D_match: wider above that diameter,
narrower below. Pre-warping each row of the art by the inverse,

    s(depth) = D_match / D(depth)

puts it on the glass at its true size, row by row.

D_match is a property of the press, not the glass. It comes from Numo's own
practice (the 9613 setup guide): art centred on the template's centre line
prints right when it is made 5 % wider. On the 9613 that line is 2.5" below
the Lip Line, where the glass is 2.941" across, so

    D_match = 1.05 x 2.941 = 3.088"

From there everything is the glass's own geometry: a straight taper from the
mouth to the base. Rows below the centre line get more than 5 %, rows above
it less (up to the 3.088" diameter, where the correction is zero).

    warp_pdf(src, dst, glass, center_depth_in)
        src's art, centred on its own box, assumed to print with its centre
        center_depth_in below the Lip Line. Vector paths only: text is
        outlined first; a placed image is left unwarped (reported).

Unverified: the 5 % comes from the guide, not a measured glass. Change
CALIBRATION (or a glass's own "match_d") when production measures one.
"""
import shutil
import tempfile
from pathlib import Path

import pikepdf

# 9613 Mixing Glass 16oz Clear (Numo, 2026-10-12). "lip_to_rim": how far the
# template's Lip Line sits below the glass's rim (taken as 0 until measured).
GLASSES = {
    "9613": {"height": 5.75, "d_top": 3.375, "d_bottom": 2.375, "lip_to_rim": 0.0},
}
# Numo's practice: centred art (2.5" below the Lip Line) + 5 % width.
CALIBRATION = {"depth": 2.5, "stretch": 1.05}


def diameter(glass, depth_in):
    """Glass diameter `depth_in` below the Lip Line (straight taper)."""
    d = depth_in + glass.get("lip_to_rim", 0.0)
    return glass["d_top"] - (glass["d_top"] - glass["d_bottom"]) * d / glass["height"]


def match_diameter(glass):
    if glass.get("match_d"):
        return glass["match_d"]
    return CALIBRATION["stretch"] * diameter(glass, CALIBRATION["depth"])


def stretch(glass, depth_in):
    """How much wider to make the art at this depth so it prints true."""
    return match_diameter(glass) / diameter(glass, depth_in)


# ── vector warp ──────────────────────────────────────────────────────────────

_PATH_OPS = {"m": 1, "l": 1, "c": 3, "v": 2, "y": 2}


def _mul(a, b):
    """Affine matrices [a b c d e f], a then b."""
    return [a[0] * b[0] + a[1] * b[2], a[0] * b[1] + a[1] * b[3],
            a[2] * b[0] + a[3] * b[2], a[2] * b[1] + a[3] * b[3],
            a[4] * b[0] + a[5] * b[2] + b[4], a[4] * b[1] + a[5] * b[3] + b[5]]


def _inv(m):
    a, b, c, d, e, f = m
    det = a * d - b * c
    return [d / det, -b / det, -c / det, a / det, (c * f - d * e) / det, (b * e - a * f) / det]


def _apply(m, x, y):
    return m[0] * x + m[2] * y + m[4], m[1] * x + m[3] * y + m[5]


class _Warper:
    def __init__(self, pdf, fn):
        self.pdf, self.fn = pdf, fn
        self.images = 0
        self.done = {}

    def point(self, ctm, inv, x, y):
        px, py = _apply(ctm, x, y)
        wx, wy = self.fn(px, py)
        return _apply(inv, wx, wy)

    def stream(self, owner, ctm0):
        """Rewrite `owner`'s content with every path point warped in page space."""
        ops = pikepdf.parse_content_stream(owner)
        out = []
        stack = []
        ctm = list(ctm0)
        inv = _inv(ctm)
        res = owner.get("/Resources") if hasattr(owner, "get") else None
        xobjs = (res.get("/XObject") if res is not None else None) or {}
        for operands, op in ops:
            o = str(op)
            if o == "q":
                stack.append(ctm)
            elif o == "Q":
                ctm = stack.pop() if stack else ctm
                inv = _inv(ctm)
            elif o == "cm":
                ctm = _mul([float(v) for v in operands], ctm)
                inv = _inv(ctm)
            elif o in _PATH_OPS:
                v = [float(x) for x in operands]
                nv = []
                for i in range(0, len(v), 2):
                    nv += self.point(ctm, inv, v[i], v[i + 1])
                operands = [round(x, 4) for x in nv]
            elif o == "re":
                x, y, w, h = [float(x) for x in operands]
                pts = [(x, y), (x + w, y), (x + w, y + h), (x, y + h)]
                wp = [self.point(ctm, inv, *p) for p in pts]
                out.append(([round(c, 4) for c in wp[0]], pikepdf.Operator("m")))
                for p in wp[1:]:
                    out.append(([round(c, 4) for c in p], pikepdf.Operator("l")))
                out.append(([], pikepdf.Operator("h")))
                continue
            elif o == "Do":
                name = str(operands[0])
                xo = xobjs.get(name)
                if xo is not None and str(xo.get("/Subtype")) == "/Form":
                    m = [float(v) for v in xo.get("/Matrix", [1, 0, 0, 1, 0, 0])]
                    self.form(xo, _mul(m, ctm))
                elif xo is not None:
                    self.images += 1
            elif o in ("Tj", "TJ", "'", '"'):
                raise ValueError("text in the art - outline it first")
            out.append((operands, op))
        data = pikepdf.unparse_content_stream(out)
        if isinstance(owner, pikepdf.Page):
            owner.Contents = self.pdf.make_stream(data)
        else:
            owner.write(data)

    def form(self, xo, ctm):
        key = xo.objgen
        if key in self.done and self.done[key] != ctm:
            raise ValueError("a form drawn twice at different places")
        self.done[key] = ctm
        # The warp can push art past the form's box: open it up.
        xo.BBox = pikepdf.Array([-1e5, -1e5, 1e5, 1e5])
        self.stream(xo, ctm)


def _has_text(path):
    try:
        import text_outline
        return bool(text_outline.fonts(path))
    except ImportError:
        # Without text_outline.py: any font in the file means live text.
        import subprocess
        out = subprocess.run(["pdffonts", str(path)], capture_output=True, text=True).stdout
        return len(out.strip().splitlines()) > 2


def _outline(src, dst):
    """Text to outlines (text_outline.py, or Ghostscript directly without it)."""
    try:
        import text_outline
        if text_outline.outline(src, dst):
            return True
    except ImportError:
        pass
    # Ghostscript directly (text_outline also insists the result renders
    # identically, which tiny hinting differences can fail).
    if True:
        import subprocess
        r = subprocess.run(["gs", "-q", "-dNOPAUSE", "-dBATCH", "-dSAFER", "-dNoOutputFonts",
                            "-sDEVICE=pdfwrite", f"-sOutputFile={dst}", str(src)],
                           capture_output=True, timeout=180)
        return r.returncode == 0 and Path(dst).is_file()


def warp_pdf(src, dst, glass, center_depth_in, about_x=None, about_y=None, scale=1.0):
    """
    Pre-warp one-colour vector art for the taper. The art's box centre prints
    `center_depth_in` below the Lip Line; rows are stretched about `about_x`
    (default the box's centre) by stretch(depth). `scale`: points on the
    glass per unit of the art (the art is placed at that scale); `about_y`:
    the height in the art that prints at center_depth_in (default the box's
    centre). Returns {"images": n,
    "stretch_top", "stretch_center", "stretch_bottom"}.
    """
    src, dst = Path(src), Path(dst)
    work = src
    tmp = None
    if _has_text(src):
        tmp = Path(tempfile.mkdtemp())
        o = tmp / "outlined.pdf"
        if not _outline(src, o):
            raise ValueError("couldn't outline the text in the art")
        work = o
    with pikepdf.open(str(work)) as pdf:
        pg = pdf.pages[0]
        x0, y0, x1, y1 = [float(v) for v in pg.mediabox]
        cx = (x0 + x1) / 2 if about_x is None else about_x
        cy = (y0 + y1) / 2 if about_y is None else about_y

        def fn(x, y):
            depth = center_depth_in - (y - cy) * scale / 72.0
            return cx + (x - cx) * stretch(glass, depth), y

        w = _Warper(pdf, fn)
        w.stream(pg, [1, 0, 0, 1, 0, 0])
        # The page grows sideways by the largest stretch.
        smax = max(stretch(glass, center_depth_in - (yy - cy) * scale / 72.0) for yy in (y0, y1))
        half = max(cx - x0, x1 - cx) * smax
        pg.MediaBox = pikepdf.Array([cx - half, y0, cx + half, y1])
        for k in ("/CropBox", "/TrimBox", "/ArtBox", "/BleedBox"):
            if k in pg.obj:
                del pg.obj[k]
        pdf.save(str(dst))
    if tmp:
        shutil.rmtree(tmp, ignore_errors=True)
    return {"images": w.images,
            "stretch_top": round(stretch(glass, center_depth_in - (y1 - cy) * scale / 72.0), 4),
            "stretch_center": round(stretch(glass, center_depth_in), 4),
            "stretch_bottom": round(stretch(glass, center_depth_in - (y0 - cy) * scale / 72.0), 4)}


if __name__ == "__main__":
    g = GLASSES["9613"]
    print(f"match diameter {match_diameter(g):.3f}\"")
    for d in (1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0):
        print(f'  {d:.1f}" below Lip Line: glass {diameter(g, d):.3f}"  stretch {100 * (stretch(g, d) - 1):+.1f}%')


# ── Uniform widening (what the press actually wants) ────────────────────────
#
# Numo prints tapered glass flat on a rotary press with the glass tilted so
# its top edge runs level under the screen: the press follows the taper, and
# the art must NOT be bent for it (warp_pdf above stays for reference only).
# What it does want is the art made a little wider - same height - so it
# reads at its true shape where the glass curves away from the eye. How much
# is set per item (PRODUCTS[...]["glass_widen"]: 0.05 = 5 %).

def widen_pdf(src, dst, factor, about_x=None):
    """`src` stretched sideways by `factor` (1.05 = 5 % wider) about its box
    centre (or about_x), height unchanged. Text is outlined first."""
    src, dst = Path(src), Path(dst)
    work, tmp = src, None
    if _has_text(src):
        tmp = Path(tempfile.mkdtemp())
        o = tmp / "outlined.pdf"
        if not _outline(src, o):
            raise ValueError("couldn't outline the text in the art")
        work = o
    with pikepdf.open(str(work)) as pdf:
        pg = pdf.pages[0]
        x0, y0, x1, y1 = [float(v) for v in pg.mediabox]
        cx = (x0 + x1) / 2 if about_x is None else about_x
        w = _Warper(pdf, lambda x, y: (cx + (x - cx) * factor, y))
        w.stream(pg, [1, 0, 0, 1, 0, 0])
        half = max(cx - x0, x1 - cx) * factor
        pg.MediaBox = pikepdf.Array([cx - half, y0, cx + half, y1])
        for k in ("/CropBox", "/TrimBox", "/ArtBox", "/BleedBox"):
            if k in pg.obj:
                del pg.obj[k]
        pdf.save(str(dst))
    if tmp:
        shutil.rmtree(tmp, ignore_errors=True)
    return {"images": w.images}
