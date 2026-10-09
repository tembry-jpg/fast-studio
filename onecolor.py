"""
onecolor.py — reduce multi-colour vector art to one screen-print ink.

Every painted shape in the artwork gets one of three treatments:

    print     prints in the job's ink
    knockout  a hole cut through the ink; the product shows through
    remove    as if it were never drawn (whatever is underneath shows)

Knock out and remove look the same on a shape standing on its own and very
different on a shape drawn on top of other artwork: the square in the middle of
a four-colour X is the textbook case. Remove it and the arms under it close the
gap; knock it out and the X keeps its centre.

The work is split so the configurator can offer an easy button, a preview, and
a click-to-edit fallback:

    analyze()  numbers the shapes, renders an ID map (each shape in its own
               colour, anti-aliasing off, so a pixel says which shape is on top
               there), and proposes a treatment for each shape
    apply()    writes a new one-colour PDF from a set of treatments: ink shapes
               in black, knockouts in white, removed shapes not painted. The
               press build already turns black into 100 % and white into 0 % of
               the one screen, so nothing downstream needs to know this ran.

The automatic proposal is deliberately simple and says why:
  * white, in art that also has colour, is a knockout (it was drawn to be
    background showing through);
  * a coloured shape mostly surrounded by artwork of OTHER colours is detail
    inside a mark — the centre of the X, lettering on a badge — and is knocked
    out, which is what keeps it legible in one ink;
  * everything else prints.
"""

import hashlib
import re
import subprocess
from pathlib import Path

import numpy as np
import pikepdf
from PIL import Image

DPI = 150                    # same as the upload preview, so pixels line up
WHITE_MIN = 0.92             # lightness at/above which a colour is "white"
DETAIL_FRAC = 0.5            # share of a shape's outline touching other colours
RING_PX = 3

_FILL_OPS = {"f", "F", "f*", "B", "B*", "b", "b*"}
_STROKE_ONLY = {"S", "s"}
_TEXT_OPS = {"Tj", "TJ", "'", '"'}
_COLOR_OPS = {"g", "G", "rg", "RG", "k", "K", "cs", "CS", "sc", "SC", "scn", "SCN"}
_PATH_START = {"m", "re"}


# ── colours ────────────────────────────────────────────────────────────────

def _cs_info(res, name):
    """(family, extra) for a colour space name: gray/rgb/cmyk/tint/pattern."""
    n = str(name)
    direct = {"/DeviceGray": "gray", "/G": "gray", "/DeviceRGB": "rgb",
              "/RGB": "rgb", "/DeviceCMYK": "cmyk", "/CMYK": "cmyk",
              "/Pattern": "pattern"}
    if n in direct:
        return direct[n], None
    try:
        cs = res.ColorSpace[name]
    except Exception:
        return "rgb", None
    return _cs_obj_info(cs)


def _cs_obj_info(cs):
    if isinstance(cs, pikepdf.Name):
        return _cs_info(None, cs)
    try:
        head = str(cs[0])
    except Exception:
        return "rgb", None
    if head == "/ICCBased":
        n = int(cs[1].get("/N", 3))
        return {1: "gray", 3: "rgb", 4: "cmyk"}.get(n, "rgb"), None
    if head in ("/Separation", "/DeviceN"):
        return "tint", cs
    if head == "/Indexed":
        return "indexed", cs
    if head == "/Pattern":
        return "pattern", None
    if head == "/CalGray":
        return "gray", None
    return "rgb", None


_PMS_CACHE = {}


# A spot colour the designer NAMED white ("WHITE", "White Ink", "White
# Underbase") is a white ink they want printed, not background. It is given
# this stand-in colour — just below the white threshold, so it isn't treated
# as a knockout — and the separation step labels it "White".
WHITE_INK_RGB = (233 / 255.0, 233 / 255.0, 234 / 255.0)
WHITE_INK_HEX = "#E9E9EA"


def _named_spot_rgb(name):
    """Screen colour of a named spot ink: PANTONE names from the library."""
    n = (name or "").strip()
    if n.lower() in ("all", "registration"):
        return (0.0, 0.0, 0.0)
    if re.search(r"\bwhite\b", n, re.I):
        return WHITE_INK_RGB
    if not _PMS_CACHE:
        try:
            from pantone_rgb import PANTONE_RGB as lib
        except Exception:
            try:
                from engine import PANTONE_RGB as lib
            except Exception:
                lib = {}
        for k, v in lib.items():
            _PMS_CACHE[k.lower()] = v
        _PMS_CACHE.setdefault("__loaded__", "")
    key = n.lower()
    hx = _PMS_CACHE.get(key) or _PMS_CACHE.get(key.replace("pms ", "pantone "))
    if not hx and not key.startswith("pantone"):
        hx = _PMS_CACHE.get("pantone " + key)
    if not hx:
        return None
    h = hx.lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4))


def _lab_to_rgb(L, a, b, white=(0.9642, 1.0, 0.8249)):
    """CIE Lab (D50 by default, as Illustrator writes it) to sRGB 0..1."""
    fy = (L + 16) / 116.0
    fx = fy + a / 500.0
    fz = fy - b / 200.0
    def finv(t):
        return t ** 3 if t ** 3 > 0.008856 else (t - 16 / 116.0) / 7.787
    X, Y, Z = white[0] * finv(fx), white[1] * finv(fy), white[2] * finv(fz)
    # Bradford D50 -> D65, then XYZ -> linear sRGB.
    X2 = 0.9555766 * X - 0.0230393 * Y + 0.0631636 * Z
    Y2 = -0.0282895 * X + 1.0099416 * Y + 0.0210077 * Z
    Z2 = 0.0122982 * X - 0.0204830 * Y + 1.3299098 * Z
    r = 3.2404542 * X2 - 1.5371385 * Y2 - 0.4985314 * Z2
    g = -0.9692660 * X2 + 1.8760108 * Y2 + 0.0415560 * Z2
    bl = 0.0556434 * X2 - 0.2040259 * Y2 + 1.0572252 * Z2
    def gam(c):
        c = max(0.0, min(1.0, c))
        return 12.92 * c if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055
    return (gam(r), gam(g), gam(bl))


def _tint_rgb(cs, vals):
    """
    Screen colour of a Separation/DeviceN tint.

    A named PANTONE is looked up by name — that is the colour it prints — and
    the tint mixed toward white. Otherwise the tint function is evaluated into
    its alternate space, Lab included (Illustrator writes PANTONE swatches with
    a Lab alternate; read as RGB those came out white, and the spot inks of a
    logo silently turned into knockouts).
    """
    t = max(vals) if vals else 1.0
    try:
        if str(cs[0]) == "/Separation":
            named = _named_spot_rgb(str(cs[1]).lstrip("/"))
            if named == WHITE_INK_RGB:
                return named if t > 0.05 else (1.0, 1.0, 1.0)
            if named is not None:
                return tuple(1 - t * (1 - c) for c in named)
    except Exception:
        pass
    try:
        alt = cs[2]
        fn = cs[3]
        c0 = [float(v) for v in fn.get("/C0", [0] * 4)]
        c1 = [float(v) for v in fn.get("/C1", [1] * 4)]
        comp = [a + (b - a) * t for a, b in zip(c0, c1)]
        if isinstance(alt, pikepdf.Array) and str(alt[0]) == "/Lab" and len(comp) >= 3:
            wp = alt[1].get("/WhitePoint") if len(alt) > 1 else None
            white = tuple(float(v) for v in wp) if wp is not None else (0.9642, 1.0, 0.8249)
            return _lab_to_rgb(comp[0], comp[1], comp[2], white)
        alt_fam, _ = _cs_obj_info(alt)
        return _to_rgb(alt_fam, comp)
    except Exception:
        return (1 - t, 1 - t, 1 - t)


def _to_rgb(fam, v):
    if fam == "gray" and v:
        return (v[0], v[0], v[0])
    if fam == "rgb" and len(v) >= 3:
        return tuple(v[:3])
    if fam == "cmyk" and len(v) >= 4:
        c, m, y, k = v[:4]
        return (1 - min(1, c + k), 1 - min(1, m + k), 1 - min(1, y + k))
    return (0.0, 0.0, 0.0)


def _hex(rgb):
    return "#%02X%02X%02X" % tuple(max(0, min(255, round(c * 255))) for c in rgb)


def _is_white(rgb):
    return rgb is not None and min(rgb) >= WHITE_MIN


# ── the walker ─────────────────────────────────────────────────────────────

def _rewrite(pdf, handler):
    """
    Walk page 1 and every form it uses, numbering each painted shape.

    All colour operators are dropped; `handler(idx, rgb, kind)` returns
    (ops_before, paint_op_or_None, ops_after) for each shape, where ops are
    (operands, operator) pairs. A None paint op means "do not paint". Colour
    goes in front of the path, because colour operators are not allowed inside
    a path under construction.
    """
    counter = [0]
    seen = set()

    def walk(obj, res, is_page):
        ops = list(pikepdf.parse_content_stream(obj))
        out = []
        fill = [("gray", None), [0.0]]
        stroke = [("gray", None), [0.0]]
        path_at = None

        def rgb_of(state):
            (fam, extra), vals = state
            if fam == "tint":
                return _tint_rgb(extra, vals)
            if fam in ("pattern", "indexed"):
                return None
            return _to_rgb(fam, vals)

        stack = []
        for operands, op in ops:
            s = str(op)
            # Colour is part of the graphics state: q saves it, Q restores it.
            # Without this a colour set inside q…Q leaked onto every shape
            # painted after the Q.
            if s == "q":
                stack.append(([fill[0], list(fill[1])], [stroke[0], list(stroke[1])]))
            elif s == "Q" and stack:
                f0, s0 = stack.pop()
                fill[0], fill[1] = f0[0], f0[1]
                stroke[0], stroke[1] = s0[0], s0[1]
            if s in _COLOR_OPS:
                tgt = stroke if s in ("G", "RG", "K", "CS", "SC", "SCN") else fill
                nums = [float(x) for x in operands if not isinstance(x, pikepdf.Name)]
                if s in ("cs", "CS"):
                    tgt[0] = _cs_info(res, operands[0]); tgt[1] = [0.0]
                elif s in ("g", "G"):
                    tgt[0] = ("gray", None); tgt[1] = nums
                elif s in ("rg", "RG"):
                    tgt[0] = ("rgb", None); tgt[1] = nums
                elif s in ("k", "K"):
                    tgt[0] = ("cmyk", None); tgt[1] = nums
                else:
                    tgt[1] = nums
                continue
            if s in _PATH_START and path_at is None:
                path_at = len(out)
            if s == "n":
                path_at = None
                out.append((operands, op))
                continue
            if s in _FILL_OPS or s in _STROKE_ONLY:
                idx = counter[0]; counter[0] += 1
                rgb = rgb_of(stroke if s in _STROKE_ONLY else fill)
                before, paint, after = handler(idx, rgb, "path")
                at = path_at if path_at is not None else len(out)
                out[at:at] = before
                out.append(([], pikepdf.Operator(paint)) if paint else ([], pikepdf.Operator("n")))
                out.extend(after)
                path_at = None
                continue
            if s in _TEXT_OPS:
                idx = counter[0]; counter[0] += 1
                before, paint, after = handler(idx, rgb_of(fill), "text")
                out.extend(before)
                out.append((operands, op))
                out.extend(after)
                continue
            if s == "Do":
                try:
                    x = res.XObject[operands[0]]
                except Exception:
                    x = None
                if x is not None and x.get("/Subtype") == "/Form" and x.objgen not in seen:
                    seen.add(x.objgen)
                    walk(x, x.get("/Resources", res), False)
            out.append((operands, op))

        data = pikepdf.unparse_content_stream(out)
        if is_page:
            obj.Contents = pdf.make_stream(data)
        else:
            obj.write(data)

    page = pdf.pages[0]
    walk(page.obj, page.obj.get("/Resources") or page.Resources, True)
    return counter[0]


def _col(rgb):
    r, g, b = rgb
    return [([r, g, b], pikepdf.Operator("rg")), ([r, g, b], pikepdf.Operator("RG"))]


def _id_rgb(idx):
    i = idx + 1
    return (1 / 255, ((i >> 8) & 255) / 255, (i & 255) / 255)


# ── rendering ──────────────────────────────────────────────────────────────

def _render(pdf_path, out_png, transparent=False, antialias=True):
    args = ["pdftocairo", "-png", "-singlefile", "-r", str(DPI)]
    if transparent:
        args.append("-transp")
    if not antialias:
        args += ["-antialias", "none"]
    stem = str(out_png)[:-4]
    subprocess.run(args + [str(pdf_path), stem], check=True,
                   capture_output=True, timeout=120)
    return Path(out_png)


def visible_box(png_path, alpha_min=8):
    """Tight box around visible pixels, as the upload preview crops."""
    a = np.asarray(Image.open(png_path).convert("RGBA"))[..., 3]
    ys, xs = np.nonzero(a > alpha_min)
    if not len(xs):
        return (0, 0, a.shape[1], a.shape[0])
    return (int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1)


def _dilate(mask, r):
    out = mask.copy()
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            if dx == 0 and dy == 0:
                continue
            sh = np.zeros_like(mask)
            ys = slice(max(dy, 0), mask.shape[0] + min(dy, 0))
            yd = slice(max(-dy, 0), mask.shape[0] + min(-dy, 0))
            xs = slice(max(dx, 0), mask.shape[1] + min(dx, 0))
            xd = slice(max(-dx, 0), mask.shape[1] + min(-dx, 0))
            sh[ys, xs] = mask[yd, xd]
            out |= sh
    return out


# ── public ─────────────────────────────────────────────────────────────────

def analyze(pdf_path, work_dir):
    """
    Number the shapes, render the ID map and the colour preview on the same
    pixel grid (cropped to the art, as the upload preview is), and propose a
    treatment for each shape.
    """
    work = Path(work_dir); work.mkdir(parents=True, exist_ok=True)
    tag = hashlib.sha1(Path(pdf_path).read_bytes()).hexdigest()[:12]

    shapes = []
    paint_ops = []
    _learn_paint_ops(pikepdf.open(str(pdf_path)), paint_ops)
    pdf = pikepdf.open(str(pdf_path))

    def record_keep(idx, rgb, kind):
        shapes.append({"i": idx, "rgb": rgb, "kind": kind})
        orig = paint_ops[idx] if idx < len(paint_ops) else "f"
        return _col(_id_rgb(idx)), (orig if kind == "path" else None), []

    n = _rewrite(pdf, record_keep)
    id_pdf = work / f"{tag}.ids.pdf"
    pdf.save(str(id_pdf))
    id_png = _render(id_pdf, work / f"{tag}.ids.png", transparent=False, antialias=False)
    col_png = _render(pdf_path, work / f"{tag}.color.png", transparent=True)

    box = Image.open(col_png).convert("RGBA").getchannel("A").getbbox() \
        or (0, 0) + Image.open(col_png).size
    col = Image.open(col_png).convert("RGBA").crop(box)
    ids_rgb = np.asarray(Image.open(id_png).convert("RGB").crop(box)).astype(np.int32)
    ids = np.where(ids_rgb[..., 0] == 1, ids_rgb[..., 1] * 256 + ids_rgb[..., 2], 0) - 1
    ids[ids >= n] = -1                                    # -1 = nothing there

    # Keep only what is visible in the colour render, so anti-aliasing noise at
    # the edges of the aliased map can't claim pixels outside the art.
    alpha = np.asarray(col)[..., 3]
    ids[alpha < 8] = -1

    white = {s["i"]: _is_white(s["rgb"]) for s in shapes}
    hexes = {s["i"]: (_hex(s["rgb"]) if s["rgb"] is not None else "#777777") for s in shapes}
    any_colour = any(not w for w in white.values())
    colour_px = None
    if any_colour:
        col_ids = [j for j, w in white.items() if not w]
        colour_px = np.isin(ids, col_ids)

    for s in shapes:
        i = s["i"]
        mask = ids == i
        area = int(mask.sum())
        s["area"] = area
        s["hex"] = hexes[i]
        s.pop("rgb", None)
        if area == 0:
            s["auto"], s["why"] = "print", "hidden under other artwork"
            continue
        if white[i]:
            s["auto"], s["why"] = (("knockout", "white inside colour") if any_colour
                                   else ("print", "white-only artwork"))
            if any_colour:
                s["white_role"] = _white_role(mask, ids, white, colour_px)
            continue
        ys, xs = np.nonzero(mask)
        y0, y1 = max(ys.min() - RING_PX - 1, 0), ys.max() + RING_PX + 2
        x0, x1 = max(xs.min() - RING_PX - 1, 0), xs.max() + RING_PX + 2
        m = mask[y0:y1, x0:x1]
        ring = _dilate(m, RING_PX) & ~m
        rid = ids[y0:y1, x0:x1][ring]
        if not len(rid):
            s["auto"], s["why"] = "print", ""
            continue
        other = np.array([(j >= 0 and hexes.get(j) != hexes[i] and not white.get(j, False))
                          for j in rid.tolist()])
        frac = float(other.mean())
        s["detail"] = round(frac, 2)
        if frac >= DETAIL_FRAC:
            s["auto"], s["why"] = "knockout", "sits inside artwork of other colors"
        else:
            s["auto"], s["why"] = "print", ""

    # Never knock everything out: a traced JPG's colour fringe can make every
    # colour look like detail inside another, and then nothing prints. The
    # colour with the most area prints; any part can still be changed.
    painted = [s for s in shapes if s["area"] > 0]
    if painted and not any(s["auto"] == "print" for s in painted):
        area_by = {}
        for s in painted:
            area_by[s["hex"]] = area_by.get(s["hex"], 0) + s["area"]
        main = max(area_by, key=area_by.get)
        for s in painted:
            if s["hex"] == main:
                s["auto"], s["why"] = "print", "the main colour"

    # The ID map is shipped as an image the browser can read pixel-exact.
    idmap = np.zeros(ids.shape + (3,), np.uint8)
    v = ids + 1
    idmap[..., 1] = (v >> 8) & 255
    idmap[..., 2] = v & 255
    idmap_png = work / f"{tag}.idmap.png"
    Image.fromarray(idmap, "RGB").save(idmap_png)
    colour_png = work / f"{tag}.colour.png"
    col.save(colour_png)

    groups = {}
    for s in shapes:
        if s["area"] == 0:
            continue
        g = groups.setdefault(s["hex"], {"hex": s["hex"], "shapes": [], "area": 0})
        g["shapes"].append(s["i"]); g["area"] += s["area"]
    return {"shapes": shapes,
            "groups": sorted(groups.values(), key=lambda g: -g["area"]),
            "idmap_png": str(idmap_png), "colour_png": str(colour_png),
            "width": col.width, "height": col.height, "count": n,
            "box": [int(box[0]), int(box[1])], "dpi": DPI}


def _drop_unused_spots(page):
    """
    Remove the art's own spot colour spaces that nothing paints with any more.
    After separation every shape is in a NumoSp ink, but the file still lists
    the spots it came with (the designer's PANTONE 485 C on art the order
    prints in 185 C), and a RIP can show each listed spot as a plate.
    Only Separation / DeviceN entries, patterns and shadings not named in
    their own content stream go.
    """
    seen = set()

    def walk(holder):
        res = holder.get("/Resources")
        if res is None:
            return
        try:
            if isinstance(holder.get("/Contents"), pikepdf.Array):
                body = b"\n".join(c.read_bytes() for c in holder.Contents)
            elif "/Contents" in holder:
                body = holder.Contents.read_bytes()
            else:
                body = holder.read_bytes()
        except Exception:
            return
        cs = res.get("/ColorSpace")
        if cs is not None:
            for k in list(cs.keys()):
                if k.startswith("/NumoSp"):
                    continue
                v = cs[k]
                if isinstance(v, pikepdf.Array) and len(v) and str(v[0]) in ("/Separation", "/DeviceN") \
                        and not re.search(re.escape(k.encode()) + rb"(?![A-Za-z0-9#._-])", body):
                    del cs[k]
        # Patterns and shadings nothing paints with (an Illustrator file's
        # pattern swatches) carry their own spot colours.
        for kind in ("/Pattern", "/Shading"):
            d = res.get(kind)
            if d is None:
                continue
            for k in list(d.keys()):
                if not re.search(re.escape(k.encode()) + rb"(?![A-Za-z0-9#._-])", body):
                    del d[k]
        for _, x in (res.get("/XObject") or {}).items():
            if x.get("/Subtype") == "/Form" and x.objgen not in seen:
                seen.add(x.objgen)
                walk(x)
    walk(page)


def _white_role(mask, ids, white, colour_px):
    """
    What a white (non-spot) shape in art that also has colour is for:

      "knockout"  it sits inside the coloured art (a letter's counter, a white
                  stripe through a red logo) or behind it (a white box the logo
                  was drawn on): the product shows through.
      "ink"       it stands on its own on the artboard (white lettering next to
                  red lettering): it prints in White ink.

    Its outline is read the same way as a coloured detail's: mostly touching
    coloured shapes means inside them. A white whose box holds most of the
    coloured art is the background it was drawn on.
    """
    if not mask.any():
        return "knockout"
    ys, xs = np.nonzero(mask)
    y0, y1 = max(ys.min() - RING_PX - 1, 0), ys.max() + RING_PX + 2
    x0, x1 = max(xs.min() - RING_PX - 1, 0), xs.max() + RING_PX + 2
    m = mask[y0:y1, x0:x1]
    ring = _dilate(m, RING_PX) & ~m
    near = ids[y0:y1, x0:x1][ring]
    if len(near):
        touching = colour_px[y0:y1, x0:x1][ring]
        if float(touching.mean()) >= DETAIL_FRAC:
            return "knockout"
    total = int(colour_px.sum())
    if total:
        inside = int(colour_px[ys.min():ys.max() + 1, xs.min():xs.max() + 1].sum())
        if inside >= 0.5 * total:
            return "knockout"
    return "ink"


def white_ink_knockouts(pdf_path, work_dir=None):
    """
    Walker indices of the white shapes that are knockouts, in art where some
    white stands on its own and prints as White ink (see _white_role).
    """
    import tempfile
    an = analyze(pdf_path, Path(work_dir or tempfile.gettempdir()) / "numo_white")
    return {s["i"] for s in an["shapes"] if s.get("white_role") == "knockout"}


def _learn_paint_ops(pdf, out):
    """The original paint operator of every shape, in walker order."""
    def learn(idx, rgb, kind):
        return [], None, []
    # A private walk that records operators instead of rewriting.
    seen = set()

    def walk(obj, res):
        for operands, op in pikepdf.parse_content_stream(obj):
            s = str(op)
            if s in _FILL_OPS or s in _STROKE_ONLY:
                out.append(s)
            elif s in _TEXT_OPS:
                out.append(s)
            elif s == "Do":
                try:
                    x = res.XObject[operands[0]]
                except Exception:
                    continue
                if x.get("/Subtype") == "/Form" and x.objgen not in seen:
                    seen.add(x.objgen)
                    walk(x, x.get("/Resources", res))
    page = pdf.pages[0]
    walk(page.obj, page.obj.get("/Resources") or page.Resources)


def apply(pdf_path, decisions, auto, out_pdf):
    """
    Write the one-colour PDF: ink shapes black, knockouts white, removed
    shapes not painted. `decisions` overrides `auto` per shape index.
    """
    probe = pikepdf.open(str(pdf_path))
    paint_ops = []
    _learn_paint_ops(probe, paint_ops)
    pdf = pikepdf.open(str(pdf_path))

    def handle(idx, rgb, kind):
        d = decisions.get(str(idx)) or decisions.get(idx) or auto.get(idx, "print")
        orig = paint_ops[idx] if idx < len(paint_ops) else "f"
        if d == "remove":
            if kind == "text":
                return ([([3], pikepdf.Operator("Tr"))], None, [([0], pikepdf.Operator("Tr"))])
            return [], None, []
        col = (1.0, 1.0, 1.0) if d == "knockout" else (0.0, 0.0, 0.0)
        return _col(col), (orig if kind == "path" else None), []

    _rewrite(pdf, handle)
    pdf.save(str(out_pdf))
    return str(out_pdf)


def _mul(m, n):
    """PDF matrices [a b c d e f]: m then n."""
    a, b, c, d, e, f = m
    A, B, C, D, E, F = n
    return [a * A + b * C, a * B + b * D, c * A + d * C, c * B + d * D,
            e * A + f * C + E, e * B + f * D + F]


def _page_path(ops, ctm):
    """A path's construction ops, moved into page space."""
    a, b, c, d, e, f = ctm

    def pt(x, y):
        return [a * x + c * y + e, b * x + d * y + f]
    out = []
    for operands, op in ops:
        o = str(op)
        v = [float(x) for x in operands]
        if o in ("m", "l"):
            out.append((pt(*v), pikepdf.Operator(o)))
        elif o == "c":
            out.append((pt(v[0], v[1]) + pt(v[2], v[3]) + pt(v[4], v[5]), op))
        elif o in ("v", "y"):
            out.append((pt(v[0], v[1]) + pt(v[2], v[3]), op))
        elif o == "re":
            x, y, w, h = v
            out += [(pt(x, y), pikepdf.Operator("m")), (pt(x + w, y), pikepdf.Operator("l")),
                    (pt(x + w, y + h), pikepdf.Operator("l")), (pt(x, y + h), pikepdf.Operator("l")),
                    ([], pikepdf.Operator("h"))]
        elif o == "h":
            out.append(([], op))
    return out


def _fill_ops(mask, rgb, grid, page):
    """A filled area (True pixels on the editor's grid) as a vector shape in
    page space: traced like an image, a pixel wider all round so it meets the
    shapes around it without a hairline."""
    import vectorize
    m = vectorize.dilate(np.asarray(mask, dtype=bool), 1)
    curves = vectorize._trace_curves(m, turdsize=0)
    bx, by, dpi = float(grid["box"][0]), float(grid["box"][1]), float(grid.get("dpi") or DPI)
    cb = [float(v) for v in (page.obj.get("/CropBox") or page.obj.get("/MediaBox"))]
    k = 72.0 / dpi

    def pt(p):
        return [cb[0] + (bx + p.x) * k, cb[3] - (by + p.y) * k]
    ops = [([], pikepdf.Operator("q"))] + _col(rgb)
    for cv in curves:
        ops.append((pt(cv.start_point), pikepdf.Operator("m")))
        for sg in cv.segments:
            if sg.is_corner:
                ops.append((pt(sg.c), pikepdf.Operator("l")))
                ops.append((pt(sg.end_point), pikepdf.Operator("l")))
            else:
                ops.append((pt(sg.c1) + pt(sg.c2) + pt(sg.end_point), pikepdf.Operator("c")))
        ops.append(([], pikepdf.Operator("h")))
    ops += [([], pikepdf.Operator("f*")), ([], pikepdf.Operator("Q"))]
    return ops if curves else []


def cut(pdf_path, remove, out_pdf, recolor=None, knock=None, fills=None, grid=None):
    """
    The artwork with some shapes taken out and everything else exactly as it
    was (its colours, spots and strokes untouched). `remove` holds shape
    numbers as analyze() counts them; `recolor` maps shape numbers to an
    (r, g, b) they are painted in instead; `knock` shapes become holes through
    all the art (the page is clipped to everything outside them, so nothing
    under them prints either - no white paint is involved); `fills` are
    (mask, (r, g, b)) areas on the editor's grid (`grid`: {"box", "dpi"} from
    analyze) added as new shapes after everything else, so every existing
    shape keeps its number. Returns (shapes in the file, shapes that could
    not be recoloured).
    """
    remove = {int(i) for i in remove}
    recolor = {int(k): v for k, v in (recolor or {}).items()}
    knock = {int(i) for i in (knock or [])} - remove
    holes = []                                   # knocked-out outlines, page space
    skipped = []
    pdf = pikepdf.open(str(pdf_path))
    counter = [0]
    seen = set()

    def walk(obj, res, is_page, ctm0):
        out = []
        path_at, clips = None, False
        ctm, stack = list(ctm0), []
        for operands, op in pikepdf.parse_content_stream(obj):
            s = str(op)
            if s == "q":
                stack.append(list(ctm))
            elif s == "Q" and stack:
                ctm = stack.pop()
            elif s == "cm" and len(operands) == 6:
                ctm = _mul([float(x) for x in operands], ctm)
            if s in _PATH_START and path_at is None:
                path_at = len(out)
            if s in ("W", "W*"):
                clips = True
            if s == "n":
                path_at, clips = None, False
            if s in _FILL_OPS or s in _STROKE_ONLY:
                idx = counter[0]; counter[0] += 1
                at = path_at if path_at is not None else len(out)
                path_at, was_clip, clips = None, clips, False
                if idx in knock:
                    if s in _FILL_OPS and not was_clip:
                        holes.extend(_page_path(out[at:], ctm))
                    out.append(([], pikepdf.Operator("n")))
                elif idx in remove:
                    # "n" ends the path without painting it; a clip set with it stays.
                    out.append(([], pikepdf.Operator("n")))
                elif idx in recolor and not was_clip:
                    # Its own colour, inside q...Q so the shapes after it keep theirs.
                    out[at:at] = [([], pikepdf.Operator("q"))] + _col(recolor[idx])
                    out.append((operands, op))
                    out.append(([], pikepdf.Operator("Q")))
                else:
                    if idx in recolor:
                        skipped.append(idx)
                    out.append((operands, op))
                continue
            if s in _TEXT_OPS:
                idx = counter[0]; counter[0] += 1
                if idx in recolor and idx not in remove:
                    skipped.append(idx)          # live text: outlined on upload, so rare
                if idx in remove or idx in knock:
                    out += [([3], pikepdf.Operator("Tr")), (operands, op), ([0], pikepdf.Operator("Tr"))]
                else:
                    out.append((operands, op))
                continue
            if s == "Do":
                try:
                    x = res.XObject[operands[0]]
                except Exception:
                    x = None
                if x is not None and x.get("/Subtype") == "/Form" and x.objgen not in seen:
                    seen.add(x.objgen)
                    fm = [float(v) for v in (x.get("/Matrix") or [1, 0, 0, 1, 0, 0])]
                    walk(x, x.get("/Resources", res), False, _mul(fm, ctm))
            out.append((operands, op))
        if is_page and fills and grid:
            # The page's own content in q...Q so the fills are drawn in page
            # space whatever transform the content leaves set.
            add = []
            for mask, rgb in fills:
                add += _fill_ops(mask, rgb, grid, page)
            if add:
                out = [([], pikepdf.Operator("q"))] + out + [([], pikepdf.Operator("Q"))] + add
        if is_page and holes:
            # Everything on the page is clipped to the area outside the holes:
            # a big box plus the outlines, even-odd, so a letter's counter
            # (an outline inside an outline) stays part of the letter.
            x0, y0, x1, y1 = [float(v) for v in (obj.get("/MediaBox") or [0, 0, 612, 792])]
            big = [([x0 - 5000, y0 - 5000, (x1 - x0) + 10000, (y1 - y0) + 10000], pikepdf.Operator("re"))]
            out = ([([], pikepdf.Operator("q"))] + big + holes
                   + [([], pikepdf.Operator("W*")), ([], pikepdf.Operator("n"))] + out
                   + [([], pikepdf.Operator("Q"))])
        data = pikepdf.unparse_content_stream(out)
        if is_page:
            obj.Contents = pdf.make_stream(data)
        else:
            obj.write(data)

    page = pdf.pages[0]
    walk(page.obj, page.obj.get("/Resources") or page.Resources, True, [1, 0, 0, 1, 0, 0])
    pdf.save(str(out_pdf))
    return counter[0], skipped


def split_parts(pdf_path, out_pdf):
    """
    A traced image draws each colour as one path of many outlines, so the
    whole colour is one shape: a lasso round one word picked every word in
    that colour. Here each outline becomes its own shape, with the holes
    inside it (the counter of an O) kept with it, so every letter, star and
    facet can be picked on its own. It looks exactly the same. Page content
    only (the tracer writes no forms). Returns how many shapes it wrote.
    """
    def pts_of(sub):
        out = []
        for operands, op in sub:
            o = str(op)
            if o in ("m", "l"):
                out.append((float(operands[0]), float(operands[1])))
            elif o == "c":
                out.append((float(operands[4]), float(operands[5])))
            elif o in ("v", "y"):
                out.append((float(operands[2]), float(operands[3])))
        return out

    def inside(pt, poly):
        x, y = pt; n = len(poly); hit = False
        j = n - 1
        for i in range(n):
            xi, yi = poly[i]; xj, yj = poly[j]
            if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / ((yj - yi) or 1e-12) + xi:
                hit = not hit
            j = i
        return hit

    def regroup(subs, paint):
        polys = [pts_of(sb) for sb in subs]
        boxes = []
        for pl in polys:
            if pl:
                xs = [p[0] for p in pl]; ys = [p[1] for p in pl]
                boxes.append((min(xs), min(ys), max(xs), max(ys)))
            else:
                boxes.append((0, 0, 0, 0))
        area = [(b[2] - b[0]) * (b[3] - b[1]) for b in boxes]
        parent = [-1] * len(subs)
        for i, pl in enumerate(polys):
            if not pl:
                continue
            best = -1
            for j, pj in enumerate(polys):
                if j == i or not pj or area[j] <= area[i]:
                    continue
                bj, bi = boxes[j], boxes[i]
                if bi[0] < bj[0] or bi[1] < bj[1] or bi[2] > bj[2] or bi[3] > bj[3]:
                    continue
                if inside(pl[0], pj) and (best < 0 or area[j] < area[best]):
                    best = j
            parent[i] = best
        depth = []
        for i in range(len(subs)):
            d, k = 0, parent[i]
            while k >= 0 and d < 64:
                d += 1; k = parent[k]
            depth.append(d)
        groups = {}
        for i in range(len(subs)):
            root = i if depth[i] % 2 == 0 else parent[i]
            groups.setdefault(root, []).append(i)
        out = []
        for root in sorted(groups):
            for i in groups[root]:
                out += subs[i]
            out.append(([], paint))
        return out, len(groups)

    pdf = pikepdf.open(str(pdf_path))
    page = pdf.pages[0]
    out, subs, cur, n = [], [], None, 0
    for operands, op in pikepdf.parse_content_stream(page):
        o = str(op)
        if o == "m":
            if cur:
                subs.append(cur)
            cur = [(operands, op)]
        elif o in ("l", "c", "v", "y") and cur is not None:
            cur.append((operands, op))
        elif o == "h" and cur is not None:
            cur.append((operands, op)); subs.append(cur); cur = None
        elif o in ("f", "f*", "F") and (subs or cur):
            if cur:
                subs.append(cur); cur = None
            ops, k = regroup(subs, op)
            out += ops; n += k; subs = []
        else:
            if cur:
                subs.append(cur); cur = None
            if subs:                       # a path that isn't a plain fill: as it was
                for sb in subs:
                    out += sb
                subs = []
            out.append((operands, op))
    page.obj.Contents = pdf.make_stream(pikepdf.unparse_content_stream(out))
    pdf.save(str(out_pdf))
    return n


def preview(one_colour_pdf, out_png):
    """
    The one-colour result as an alpha mask the configurator recolours: ink is
    opaque, knockouts and background are transparent.

    Cropped to everything the file paints, knockouts included — the same box
    the press build measures (ink_bbox_points takes the rendered alpha), so the
    art keeps the size and position it has on the press sheet.
    Returns (path, width, height).
    """
    rendered = _render(one_colour_pdf, Path(out_png).with_suffix(".raw.png"), transparent=True)
    raw = Image.open(rendered).convert("RGBA")
    box = raw.getchannel("A").getbbox() or (0, 0) + raw.size
    im = np.asarray(raw.crop(box)).astype(np.float32)
    dark = 1.0 - im[..., :3].mean(axis=2) / 255.0          # white = hole
    a = (im[..., 3] / 255.0) * dark
    out = np.zeros(im.shape[:2] + (4,), np.uint8)
    out[..., 3] = np.clip(a * 255, 0, 255).astype(np.uint8)
    img = Image.fromarray(out, "RGBA")
    img.save(out_png)
    return str(out_png), img.width, img.height


# ── multi-ink separation ───────────────────────────────────────────────────

def _hex_rgb01(h):
    h = (h or "#000000").lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))


# A white ink's spot on the press files. It prints white, but a separation
# whose screen colour is white is invisible on a monitor (white on white), so
# its swatch is a light pink: the spot still reads "White", and the artist
# and the floor can see where it prints.
WHITE_SPOT_PREVIEW_CMYK = [0, 0.25, 0.04, 0]


def is_white_ink(ink):
    """A White ink by name, or an ink whose colour is white."""
    nm = str(ink.get("pms") or "").replace("PANTONE ", "").strip().lower()
    if nm == "white":
        return True
    hx = str(ink.get("pms_hex") or ink.get("hex") or "")
    try:
        return all(v >= 0.96 for v in _hex_rgb01(hx))
    except Exception:
        return False


def _cmyk_of(rgb):
    r, g, b = rgb
    k = 1 - max(r, g, b)
    if k >= 1:
        return [0, 0, 0, 1]
    return [round((1 - r - k) / (1 - k), 4), round((1 - g - k) / (1 - k), 4),
            round((1 - b - k) / (1 - k), 4), round(k, 4)]


def separate(pdf_path, inks, out_pdf, mode="press", knockout_rgb=(1, 1, 1),
             overprint=False, knockout_white=True, alternate="cmyk", white_is_knockout=False):
    """
    Write the art with every shape painted in its ink.

    inks: [{"sources": [hex, ...], "pms": "PANTONE 286 C", "pms_hex": "#…",
            "hidden": bool}] — the separation the configurator shows, where
            each ink lists the source colours merged into it.

    mode "press": each ink is a named Separation — /PANTONE 286 C with a
        CMYK alternate — so the RIP gives it its own screen, named for the ink.
        Two source colours assigned the same PMS share one Separation, so they
        are one screen. White (and a hidden white) is painted DeviceGray white:
        a knockout, which the registration pass makes 0 % on every screen.
    mode "proof": the same shapes in each PMS's screen colour, knockouts in
        `knockout_rgb` (the product colour), for the customer proof.

    Hidden colours that aren't white are not painted at all, the same as the
    one-colour tool's Remove. Returns the list of PMS names that print.

    knockout_white=False: full-colour print (4CP), where white paint is not a
    knockout but covers the background. White the art doesn't claim stays
    painted white, a white marked hidden is left out, and an ink with
    "paint_white" is painted solid white.

    alternate "rgb": each named spot's alternate is the ink's screen colour in
    DeviceRGB rather than an approximate CMYK, so anything that renders the
    file (a viewer, the proof, a RIP without the spot in its library) shows
    exactly the colour the configurator's picker shows. 4CP items use it; the
    RIP still matches the Pantone by name.

    overprint: for traced images. Their inks are disjoint masks, each lower one
    spread a little under the next (the trap). With the usual knockout the
    upper ink would cut that spread away and the gap would come back, so the
    inks overprint instead — safe precisely because they never overlap except
    at the trap.
    """
    src_pts = []                                   # (rgb, ink index)
    for i, ink in enumerate(inks):
        for h in (ink.get("sources") or [ink.get("hex")]):
            if h:
                src_pts.append((_hex_rgb01(h), i))

    def nearest(rgb):
        if rgb is None or not src_pts:
            return None, 9
        best = min(src_pts, key=lambda p: sum((a - b) ** 2 for a, b in zip(p[0], rgb)))
        return best[1], sum((a - b) ** 2 for a, b in zip(best[0], rgb)) ** 0.5

    # One Separation per PMS name, in ink order.
    sep_names, sep_of_ink = [], {}
    for i, ink in enumerate(inks):
        if ink.get("hidden") or ink.get("paint_white"):
            continue
        nm = ink.get("pms") or ink.get("hex") or f"Ink {i + 1}"
        if nm not in sep_names:
            sep_names.append(nm)
        sep_of_ink[i] = sep_names.index(nm)

    # Colour in the art itself, whatever Pantones it is printed in: art drawn
    # in gold and peach with white facets keeps its facets open even when
    # every colour is set to White ink (otherwise the white facets were taken
    # for White ink and the diamond printed solid).
    any_colour = white_is_knockout or any(
        not _is_white(_hex_rgb01(ink.get("pms_hex") or ink.get("hex")))
        or not _is_white(_hex_rgb01(ink.get("hex") or ink.get("pms_hex")))
        for ink in inks if not ink.get("hidden"))
    # Art with colour that also prints White ink from plain (non-spot) white:
    # only the white standing on its own is ink; white inside or behind the
    # coloured art stays a knockout.
    white_ko = set()
    if knockout_white and any_colour and any(
            not ink.get("hidden") and any(_is_white(_hex_rgb01(h)) for h in (ink.get("sources") or [ink.get("hex")]) if h)
            for ink in inks):
        try:
            white_ko = white_ink_knockouts(pdf_path)
        except Exception as e:
            print(f"white ink / knockout split failed: {e}")
    probe = pikepdf.open(str(pdf_path))
    paint_ops = []
    _learn_paint_ops(probe, paint_ops)
    pdf = pikepdf.open(str(pdf_path))

    def ko():
        g = knockout_rgb if mode == "proof" else (1.0, 1.0, 1.0)
        return _col(g)

    def handle(idx, rgb, kind):
        orig = paint_ops[idx] if idx < len(paint_ops) else "f"
        paint = orig if kind == "path" else None
        i, dist = nearest(rgb)
        white = _is_white(rgb) if rgb is not None else False
        if white and idx in white_ko:
            return ko(), paint, []
        # White that no ink claims closely is background showing through.
        if white and (i is None or dist > 0.16 or inks[i].get("hidden")) and any_colour:
            if knockout_white:
                return ko(), paint, []
            # Full colour: white nobody claimed stays white, as drawn; a
            # white the customer switched off is left out.
            if i is not None and dist <= 0.16 and inks[i].get("hidden"):
                return [], None, []
            return _col((1.0, 1.0, 1.0)), paint, []
        if i is None:
            i = 0
        ink = inks[i]
        if ink.get("paint_white") and not ink.get("hidden"):
            return _col((1.0, 1.0, 1.0)), paint, []
        if ink.get("hidden"):
            if _is_white(_hex_rgb01(ink.get("hex"))) and knockout_white:
                return ko(), paint, []
            if kind == "text":
                return ([([3], pikepdf.Operator("Tr"))], None, [([0], pikepdf.Operator("Tr"))])
            return [], None, []
        if mode == "proof":
            return _col(_hex_rgb01(ink.get("pms_hex") or ink.get("hex"))), paint, []
        nm = pikepdf.Name(f"/NumoSp{sep_of_ink[i]}")
        return ([([nm], pikepdf.Operator("cs")), ([1], pikepdf.Operator("scn")),
                 ([nm], pikepdf.Operator("CS")), ([1], pikepdf.Operator("SCN"))], paint, [])

    _rewrite(pdf, handle)

    if mode == "press":
        spaces = {}
        for k, nm in enumerate(sep_names):
            ink = next(x for x in inks if (x.get("pms") or x.get("hex")) == nm)
            if alternate == "rgb":
                c1 = [round(v, 4) for v in _hex_rgb01(ink.get("pms_hex") or ink.get("hex"))]
                alt_cs, c0 = pikepdf.Name.DeviceRGB, [1, 1, 1]
            else:
                c1 = (list(WHITE_SPOT_PREVIEW_CMYK) if is_white_ink(ink)
                      else _cmyk_of(_hex_rgb01(ink.get("pms_hex") or ink.get("hex"))))
                alt_cs, c0 = pikepdf.Name.DeviceCMYK, [0, 0, 0, 0]
            spaces[pikepdf.Name(f"/NumoSp{k}")] = pdf.make_indirect(pikepdf.Array([
                pikepdf.Name.Separation, pikepdf.Name("/" + nm), alt_cs,
                pikepdf.Dictionary(FunctionType=2, Domain=[0, 1], C0=c0, C1=c1, N=1)]))
        seen = set()

        def add(res):
            if res is None:
                return
            if "/ColorSpace" not in res:
                res.ColorSpace = pikepdf.Dictionary()
            for k, v in spaces.items():
                res.ColorSpace[k] = v
            for _, x in (res.get("/XObject") or {}).items():
                if x.get("/Subtype") == "/Form" and x.objgen not in seen:
                    seen.add(x.objgen)
                    if "/Resources" not in x:
                        x.Resources = pikepdf.Dictionary()
                    add(x.Resources)
        page = pdf.pages[0]
        if "/Resources" not in page.obj:
            page.obj.Resources = pikepdf.Dictionary()
        add(page.obj.Resources)
        _drop_unused_spots(page.obj)
        if overprint:
            res = page.obj.Resources
            if "/ExtGState" not in res:
                res.ExtGState = pikepdf.Dictionary()
            res.ExtGState[pikepdf.Name("/NumoOP")] = pikepdf.Dictionary(
                Type=pikepdf.Name.ExtGState, OP=True, op=True, OPM=1)
            body = page.obj.Contents.read_bytes() if not isinstance(page.obj.Contents, pikepdf.Array) \
                else b"\n".join(c.read_bytes() for c in page.obj.Contents)
            page.obj.Contents = pdf.make_stream(b"/NumoOP gs\n" + body)
    pdf.save(str(out_pdf))
    return sep_names
