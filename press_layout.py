"""
press_layout.py — impose configurator artwork onto a This Is Fast press template.

╔══════════════════════════════════════════════════════════════════════════╗
║  SCOPE: the This Is Fast twins listed in PRESS_TEMPLATES — four koozies  ║
║  and the Main Squeeze Tote.                                              ║
║                                                                          ║
║  Nothing here is general. Every product has its own die, imprint sizes,  ║
║  seam positions and sheet layouts, and each is described by its own      ║
║  press_spec_<product>.json. A product absent from PRESS_TEMPLATES has no ║
║  press file and the configurator hides the option rather than guessing.  ║
║  Pointing a spec at another product's template places art in the wrong   ║
║  places, so build() refuses when the two disagree.                       ║
║                                                                          ║
║  Only 0070-3m-24HR-1c has been to press. The three other koozies were    ║
║  measured by measure_press_template.py, which reproduces all 48 of the   ║
║  0070's hand-measured positions to within 0.72 pt — good evidence, not a ║
║  proof. The tote was measured separately (see below). Check a printed    ║
║  sheet before any of them runs a live job.                               ║
║                                                                          ║
║  To add a product: measure its template, write press_spec_<product>.json,║
║  add it here, and run unmatched_guide_colors() — templates are separate  ║
║  exports and their guide colours drift, which is invisible until it      ║
║  reaches a proof.                                                        ║
╚══════════════════════════════════════════════════════════════════════════╝

Produces one PDF containing:

  * a customer proof page, in the selected PMS ink, chosen automatically from
    how many sides the job actually prints (1 Side and Bottom vs 2 Sides and
    Bottom), carrying an ink/item information panel
  * every press sheet, in registration black, with the artwork imposed at all
    koozie positions found on the sheet

The template's geometry lives in a JSON spec beside this file.

On the koozies, positions are anchored to the bottom-circle die arcs, whose
centre coincides with the bottom imprint circle — so a position is located by
its arc pair, and the two side imprints sit at fixed offsets along the koozie's
axis. The tote has no such arcs; its template draws a magenta crosshair at the
dead centre of each imprint instead, which is read directly and is the better
arrangement of the two. A spec records the result either way, so nothing
downstream has to know which method produced it.

Colour follows the template's own ART REQUIREMENTS:
  - press sheets use /Separation /All  (registration black)
  - the customer proof uses the named PMS separation so it reads as the job
    will actually print
"""

import json
import logging
from datetime import date
from pathlib import Path

from pdfrw import PdfReader, PdfWriter, PageMerge
from pdfrw.buildxobj import pagexobj
from pdfrw.toreportlab import makerl
from reportlab.pdfgen import canvas as rlcanvas
from reportlab.lib.colors import CMYKColorSep, Color

import re

from screenprint import (ink_bbox_points, recolor_form_to_spot,
                         drop_white_knockouts,
                         hex_to_cmyk, decode_stream, _tokenize as _tokens)

logging.getLogger("pdfrw").setLevel(logging.ERROR)

ALL_SLOTS = ("side1", "bottom", "side2")

# Bump this whenever the proof page changes. It is reported by
# /api/press-available/<product_id> so you can confirm from a browser which
# build of this file the running server actually loaded — a stale process or a
# stale __pycache__ is otherwise invisible and looks like "the old file".
VERSION = "2026-09-30j  4CP can 2X2; art sizes Side 1, Side 2, Bottom"

HERE = Path(__file__).parent.resolve()
PRESS_DIR = HERE / "press"

# Products that have a measured press template. A product absent from here has
# no press file — the configurator hides the option rather than guessing.
PRESS_TEMPLATES = {
    "0070-3m-24HR-1c": {
        "template": PRESS_DIR / "0070-3m-24HR-1c.pdf",
        "spec":     PRESS_DIR / "press_spec_0070-3m.json",
        "stitched": True,
    },
    # Kolder Kaddy Slim Can. Its template is the first to draw the die arcs on
    # only one sheet of each pair; the arc-less sheets take their partner's
    # positions, recorded in the spec under _arcless_pages_filled so the
    # pairing can be checked rather than taken on trust. Sewn, and the first
    # product whose seams are measured rather than assumed.
    "1080-3m-24HR-1c": {
        "template": PRESS_DIR / "1080-3m-24HR-1c.pdf",
        "spec":     PRESS_DIR / "press_spec_1080-3m-24HR-1c.json",
        "stitched": True,
    },
    # Kolder Kaddy Slim Can, 12 oz. Scuba foam, bonded — no thread to draw.
    # Same paired-sheet template as the 1080.
    "0472-24HR-1c": {
        "template": PRESS_DIR / "0472-24HR-1c.pdf",
        "spec":     PRESS_DIR / "press_spec_0472-24HR-1c.json",
        "stitched": False,
    },
    # Pocket Coolie. Scuba foam, bonded rather than sewn — no thread to draw.
    "9100-24HR-1c": {
        "template": PRESS_DIR / "9100-24HR-1c.pdf",
        "spec":     PRESS_DIR / "press_spec_9100-24HR-1c.json",
        "stitched": False,
    },
    # All three of the above were measured by measure_press_template.py rather than
    # by hand. That pass reproduces every one of the 0070's 48 hand-measured
    # positions to within 0.72 pt, but none of them has been to press —
    # check a printed sheet before any of them runs a live job.

    # Main Squeeze Tote, one side. The first flat product here, and the first
    # whose press sheet carries magenta crosshairs at the dead centre of each
    # imprint — so its positions are read rather than fitted from die arcs.
    # Cotton canvas, no thread to draw, no bottom imprint.
    #
    # The natural and dyed-canvas item numbers are the same bag on the same
    # die, and the vendor's two templates were measured as identical — die,
    # imprint rectangles and both crosshairs agree to a hundredth of a point.
    # So they share one spec, which names both under "products". They do NOT
    # share a template: each carries its own item number in its title, and the
    # press room reads that off the sheet.
    # The standard items print on the same dies as their This Is Fast twins,
    # so they share the template and its measured spec. What differs is the
    # colour: up to five inks, each kept as its own named PANTONE screen.
    "0070-3m": {"template": PRESS_DIR / "0070-3m-24HR-1c.pdf",
                "spec": PRESS_DIR / "press_spec_0070-3m.json", "stitched": True},
    "1080-3m": {"template": PRESS_DIR / "1080-3m-24HR-1c.pdf",
                "spec": PRESS_DIR / "press_spec_1080-3m-24HR-1c.json", "stitched": True},
    # Metallic neoprene (products.METALLIC_TWINS): the 3m's die and template.
    "0070-3l": {"template": PRESS_DIR / "0070-3m-24HR-1c.pdf",
                "spec": PRESS_DIR / "press_spec_0070-3m.json", "stitched": True},
    "1080-3l": {"template": PRESS_DIR / "1080-3m-24HR-1c.pdf",
                "spec": PRESS_DIR / "press_spec_1080-3m-24HR-1c.json", "stitched": True},
    # Denim neoprene: its own (bigger) cut and sheets, the 3m's imprint areas.
    "0070-3u": {"template": PRESS_DIR / "0070-3u-24HR-1c.pdf",
                "spec": PRESS_DIR / "press_spec_0070-3u.json", "stitched": True},
    # Burlap neoprene: its own cut and sheets, the 3m's imprint areas.
    "0070-3b": {"template": PRESS_DIR / "0070-3b-24HR-1c.pdf",
                "spec": PRESS_DIR / "press_spec_0070-3b.json", "stitched": True},
    # The slim can in denim and burlap: own cuts and sheets, the 1080-3m's imprint areas.
    "1080-3u": {"template": PRESS_DIR / "1080-3u-24HR-1c.pdf",
                "spec": PRESS_DIR / "press_spec_1080-3u.json", "stitched": True},
    "1080-3b": {"template": PRESS_DIR / "1080-3b-24HR-1c.pdf",
                "spec": PRESS_DIR / "press_spec_1080-3b.json", "stitched": True},
    # Suede (Smoke): own cuts and sheets; the 1080's has a DBG sheet too.
    "0070-3s": {"template": PRESS_DIR / "0070-3s-24HR-1c.pdf",
                "spec": PRESS_DIR / "press_spec_0070-3s.json", "stitched": True},
    "1080-3s": {"template": PRESS_DIR / "1080-3s-24HR-1c.pdf",
                "spec": PRESS_DIR / "press_spec_1080-3s.json", "stitched": True},
    # Key Fob: a strip folded over its middle (tools/make_strip_template.py).
    "0635-3m": {"template": PRESS_DIR / "0635-3m-24HR-1c.pdf",
                "spec": PRESS_DIR / "press_spec_0635-3m.json", "stitched": True},
    # MMKK (magnetic Kolder Kaddy): the 0070-3m's cut, its own sheets.
    "0262-3m": {"template": PRESS_DIR / "0262-3m-24HR-1c.pdf",
                "spec": PRESS_DIR / "press_spec_0262-3m.json", "stitched": True},
    # Heathered neoprene (products.HEATHERED_TWINS): the 3m's die and template.
    "0070-3h": {"template": PRESS_DIR / "0070-3m-24HR-1c.pdf",
                "spec": PRESS_DIR / "press_spec_0070-3m.json", "stitched": True},
    "1080-3h": {"template": PRESS_DIR / "1080-3m-24HR-1c.pdf",
                "spec": PRESS_DIR / "press_spec_1080-3m-24HR-1c.json", "stitched": True},
    "0472":    {"template": PRESS_DIR / "0472-24HR-1c.pdf",
                "spec": PRESS_DIR / "press_spec_0472-24HR-1c.json", "stitched": False},
    "9100":    {"template": PRESS_DIR / "9100-24HR-1c.pdf",
                "spec": PRESS_DIR / "press_spec_9100-24HR-1c.json", "stitched": False},
    "5001-TIF-7-1C": {
        "template": PRESS_DIR / "5001-TIF-7-1C.pdf",
        "spec":     PRESS_DIR / "press_spec_5001-TIF-7-1C.json",
        "stitched": False,
    },
    # Horizontal Bank Bag 10.5" x 5.5" (9210-02), expanded vinyl and laminated
    # nylon: one die, one template, separate Front and Back sheets.
    "9210-02-EV-1C": {"template": PRESS_DIR / "9210-02-1C.pdf",
                      "spec": PRESS_DIR / "press_spec_9210-02.json", "stitched": False},
    "9210-02-LN-1C": {"template": PRESS_DIR / "9210-02-1C.pdf",
                      "spec": PRESS_DIR / "press_spec_9210-02.json", "stitched": False},
    # Liam Can Insulator (0799): one long panel sewn to a bottom circle, colored
    # bias on top. Panels lie on their side on most sheets; the bottoms print
    # on sheets of their own.
    "0799-3m": {"template": PRESS_DIR / "0799-3m.pdf",
                "spec": PRESS_DIR / "press_spec_0799-3m.json", "stitched": False},
    "5001-TIF-CC-1C": {
        "template": PRESS_DIR / "5001-TIF-CC-1C.pdf",
        "spec":     PRESS_DIR / "press_spec_5001-TIF-7-1C.json",
        "stitched": False,
    },
}

# On rotated press positions, which way along the sheet Side 1 sits.
# Flip to -1 if a printed sheet shows Side 1 and Side 2 swapped.
ROTATED_SIDE1_DIR = 1

# Components that are not the product's body. Everything else a job carries is
# the body in whatever the product is made of, so the die gets filled on the
# proof without this file having to know the material's name.
_NON_BODY_COMPONENTS = {"stitching"}


def _body_pattern_path(comp):
    """The local tile of a printed body material (camo), from the component's
    `pattern` url. Only files under static/assets/ are accepted."""
    url = (comp or {}).get("pattern") or ""
    if not url.startswith("/static/assets/") or ".." in url:
        return None
    p = (HERE / url.lstrip("/")).resolve()
    return p if p.is_file() and str(p).startswith(str(HERE / "static" / "assets")) else None


def _fill_body_pattern(img, body_hex, tile_path, tile_px, porous_inset_px=None, porous_strength=1.0):
    """
    Swap the body's flat fill for its printed pattern.

    The die is filled in the pattern's average color, which no renderer can
    confuse with anything else on the page, so every pixel of exactly that
    color is body. Those take the tile, repeated at tile_px across; the art,
    printed over the body, keeps its own pixels.
    """
    import numpy as np
    from PIL import Image
    rgb = _hex_to_rgb01(body_hex)
    if not rgb:
        return img
    want = np.array([round(v * 255) for v in rgb])
    a = np.asarray(img.convert("RGB")).astype(np.int16)
    mask = (np.abs(a - want).max(axis=2) <= 3)
    if not mask.any():
        return img
    tile = Image.open(tile_path).convert("RGB")
    tile_px = max(16, int(tile_px))
    tile = tile.resize((tile_px, max(1, round(tile.height * tile_px / tile.width))), Image.LANCZOS)
    # Mirrored in a 2x2 block so neighbouring tiles meet edge to matching
    # edge; the camo art isn't drawn to repeat, and plain tiling shows seams.
    t = np.asarray(tile)

    def _mirror(t):
        return np.concatenate([np.concatenate([t, t[:, ::-1]], axis=1),
                               np.concatenate([t[::-1], t[::-1, ::-1]], axis=1)], axis=0)
    block = _mirror(t)
    h, w = mask.shape
    reps = (-(-h // block.shape[0]), -(-w // block.shape[1]), 1)
    pat = np.tile(block, reps)[:h, :w]
    holes = None
    if porous_inset_px:
        # The holes are read off the tile at its own resolution, where the
        # weave is crisp, then laid out exactly like the tile.
        try:
            from porous import hole_mask
            src = Image.open(tile_path).convert("RGB")
            hm = Image.fromarray((hole_mask(np.asarray(src), porous_strength) * 255).astype(np.uint8))
            hm = np.asarray(hm.resize(tile.size, Image.LANCZOS)).astype(np.float32) / 255.0
            holes = np.tile(_mirror(hm), (reps[0], reps[1]))[:h, :w]
        except Exception as e:
            print(f"⚠️ weave holes not read: {e}")
    out = a.astype(np.uint8)
    out[mask] = pat[mask]
    # An open weave (burlap): ink over a hole has nothing to sit on, so the
    # art shows the weave through it — thin lines come out broken on the proof
    # the way they will on the product. Only well inside the die, so the
    # stitching along the edges stays whole.
    if porous_inset_px and holes is not None:
        try:
            from scipy import ndimage
            die = ndimage.binary_fill_holes(mask)
            inner = ndimage.distance_transform_edt(die) > porous_inset_px
            art = inner & ~mask
            if art.any():
                h = holes[..., None]
                mix = (pat.astype(np.float32) * h + a.astype(np.float32) * (1 - h))
                out[art] = mix[art].round().clip(0, 255).astype(np.uint8)
        except Exception as e:
            print(f"⚠️ weave not applied to the flat lay: {e}")
    return Image.fromarray(out)


def paste_sewn_on(img, slot_id, ppi, product_id):
    """Draw what's sewn on after printing (the MMKK's magnet) onto one flat
    panel: the products' "sewn_on" entries for this slot, at their real size,
    offset from the panel's centre. Returns the image (unchanged if none)."""
    try:
        from products import PRODUCTS
        prod = product_id if isinstance(product_id, dict) else (PRODUCTS.get(product_id or "") or {})
        items = [o for o in (prod.get("sewn_on") or []) if o.get("slot") == slot_id]
        if not items:
            return img
        from PIL import Image
        base = img.convert("RGBA")
        for o in items:
            src = HERE / o["file"]
            if not src.exists():
                continue
            m = Image.open(src).convert("RGBA")
            w, h = max(1, int(o["w_in"] * ppi)), max(1, int(o["h_in"] * ppi))
            m = m.resize((w, h), Image.LANCZOS)
            cx = base.width / 2 + o.get("dx_in", 0) * ppi
            cy = base.height / 2 + o.get("dy_in", 0) * ppi
            base.alpha_composite(m, (int(cx - w / 2), int(cy - h / 2)))
        return base if img.mode == "RGBA" else base.convert(img.mode)
    except Exception as e:
        print(f"⚠️ sewn-on parts not drawn: {e}")
        return img


def has_press_template(product_id):
    cfg = PRESS_TEMPLATES.get(product_id)
    return bool(cfg and Path(cfg["template"]).exists() and Path(cfg["spec"]).exists())


def press_template_status(product_id):
    """
    Why a product has no press file — "ok", "unregistered", or what is missing.

    These two cases look identical from the outside and are opposites. A
    product with no entry above is *meant* to have no press file, and the
    export quietly falling back to a print PDF is correct. A product that IS
    registered but whose files did not arrive is a deployment that went wrong,
    and the same quiet fallback hides it: the export simply comes back without
    a press file and without a 2X2, which reads as "the code is broken" rather
    than as "one PDF is missing". Reported through /api/press-available so the
    difference can be seen from a browser instead of guessed at.
    """
    cfg = PRESS_TEMPLATES.get(product_id)
    if not cfg:
        return "unregistered"
    missing = [str(Path(cfg[k]).name) for k in ("template", "spec")
               if not Path(cfg[k]).exists()]
    return "ok" if not missing else "missing: " + ", ".join(missing)


def missing_press_files():
    """Every registered product whose template or spec is not on disk."""
    return {pid: press_template_status(pid) for pid in PRESS_TEMPLATES
            if press_template_status(pid) != "ok"}


def art_as_pdf(path, work_dir=None):
    """
    The imposition places artwork as vector, so the source has to be a PDF.

    AI is already PDF-compatible. SVG is converted. EPS goes through Ghostscript
    when it is available; if it is not, the caller is told rather than being
    handed a rasterized substitute.
    """
    path = Path(path)
    ext = path.suffix.lower()
    if ext in (".pdf", ".ai"):
        return str(path)
    out = Path(work_dir or path.parent) / (path.stem + ".press.pdf")
    if ext == ".svg":
        import cairosvg
        cairosvg.svg2pdf(url=str(path), write_to=str(out))
        return str(out)
    if ext == ".eps":
        import shutil as _sh, subprocess
        gs = _sh.which("gs") or _sh.which("ghostscript")
        if not gs:
            raise ValueError(
                "EPS artwork needs Ghostscript on the server to build a press "
                "file. Re-upload the artwork as PDF or AI.")
        # -dEPSCrop keeps the page at the EPS BoundingBox. Without it Ghostscript
        # writes the art into the corner of a letter-size page, which survives
        # here only because Artwork measures the ink rather than the MediaBox —
        # a fragile thing to depend on.
        subprocess.run([gs, "-dNOPAUSE", "-dBATCH", "-dEPSCrop",
                        "-sDEVICE=pdfwrite",
                        f"-sOutputFile={out}", str(path)], check=True,
                       capture_output=True, timeout=120)
        return str(out)
    raise ValueError(f"Cannot build a press file from {ext or 'this file type'}.")


# ─────────────────────────────────────────────────────────────────────────────
# Colour
# ─────────────────────────────────────────────────────────────────────────────

def registration_black():
    """/Separation /All — prints on every plate, which is what the template asks for."""
    return CMYKColorSep(1, 1, 1, 1, spotName="All", density=1)


# ── One colour, everywhere, on the press sheets ─────────────────────────────
# A press sheet is a single screen. Everything on it — the imposed art, the
# vendor's die arcs and sheet labels, the NSO and PMS captions we stamp — has
# to come out on ONE separation, or the RIP splits the sheet across plates and
# half of it never reaches the screen. The art is already drawn in /All, but
# the vendor template paints its own furniture in DeviceGray and RGB, and
# reportlab's caption text is RGB.
#
# So after the sheets are assembled, every colour operator on every page and
# in every nested form is rewritten to /Separation /All: anything that puts
# down ink becomes 100 %, anything white becomes 0 % (a knockout — no ink,
# same as white was). No tints: the floor burns a solid screen.
REG_CS_NAME = "/NumoReg"
_WHITE_MIN = 0.95          # lightness at/above which a colour counts as white


def _lightness(space, vals):
    """0 = full ink, 1 = paper, for a colour in the given family."""
    if not vals:
        return 0.0
    if space == "gray":
        return vals[0]
    if space == "rgb":
        return min(vals[:3])
    if space == "cmyk":
        return 1.0 - max(vals[:4])
    # a separation / DeviceN tint: 0 = no ink
    return 1.0 - max(vals)


def _space_family(cs_obj):
    import pikepdf
    if cs_obj is None:
        return "gray"
    if isinstance(cs_obj, pikepdf.Name):
        n = str(cs_obj)
        return {"/DeviceGray": "gray", "/G": "gray", "/DeviceRGB": "rgb",
                "/RGB": "rgb", "/DeviceCMYK": "cmyk", "/CMYK": "cmyk",
                "/Pattern": "pattern"}.get(n, "tint")
    if isinstance(cs_obj, pikepdf.Array) and len(cs_obj):
        head = str(cs_obj[0])
        if head in ("/Separation", "/DeviceN"):
            return "tint"
        if head == "/ICCBased":
            n = int(cs_obj[1].get("/N", 3))
            return {1: "gray", 3: "rgb", 4: "cmyk"}.get(n, "rgb")
        if head in ("/CalRGB", "/Lab"):
            return "rgb"
        if head == "/CalGray":
            return "gray"
        if head == "/Indexed":
            return "indexed"
        if head == "/Pattern":
            return "pattern"
    return "tint"


def force_registration(pdf_path, keep_spots=None):
    """
    Rewrite every colour in a press PDF to /Separation /All.

    Returns a report dict; `problems` lists anything that could not be
    converted (images, shadings, patterns) so the caller can refuse to ship it.

    keep_spots: names of Separations to leave exactly as they are — the inks
    of a multi-colour job. Their art keeps its PANTONE names so the RIP makes a
    screen per ink; everything else (template furniture, captions, knockouts)
    still becomes /All so it lands on every one of those screens.
    """
    keep = {str(n).lstrip("/") for n in (keep_spots or [])}
    import pikepdf

    pdf = pikepdf.open(str(pdf_path), allow_overwriting_input=True)
    reg = illustrator_registration(pdf)
    reg_name = pikepdf.Name(REG_CS_NAME)
    report = {"rewritten": 0, "problems": []}
    done = set()

    def _add_cs(res):
        if "/ColorSpace" not in res:
            res.ColorSpace = pikepdf.Dictionary()
        res.ColorSpace[reg_name] = reg

    def _set(fill, tint):
        return [([reg_name], pikepdf.Operator("cs" if fill else "CS")),
                ([tint], pikepdf.Operator("scn" if fill else "SCN"))]

    def _walk(owner, res, is_page):
        if res is None:
            res = pikepdf.Dictionary()
            owner.Resources = res
        _add_cs(res)
        cspaces = res.get("/ColorSpace", {})
        ops = pikepdf.parse_content_stream(owner)
        out = []
        if is_page:
            # Without this, anything drawn before its first colour operator
            # is DeviceGray black by default.
            out += _set(True, 1) + _set(False, 1)
        fam = {"fill": "gray", "stroke": "gray"}
        for operands, op in ops:
            o = str(op)
            if o in ("g", "G", "rg", "RG", "k", "K"):
                space = {"g": "gray", "rg": "rgb", "k": "cmyk"}[o.lower()]
                vals = [float(v) for v in operands]
                tint = 0 if _lightness(space, vals) >= _WHITE_MIN else 1
                out += _set(o.islower(), tint)
                fam["fill" if o.islower() else "stroke"] = "reg"
                report["rewritten"] += 1
                continue
            if o in ("cs", "CS"):
                name = operands[0]
                cs_obj = name if str(name).startswith("/Device") or str(name) == "/Pattern" \
                    else cspaces.get(name)
                f = _space_family(cs_obj)
                if (keep and isinstance(cs_obj, pikepdf.Array) and len(cs_obj) > 1
                        and str(cs_obj[0]) == "/Separation"
                        and str(cs_obj[1]).lstrip("/") in keep):
                    fam["fill" if o == "cs" else "stroke"] = "keep"
                    out.append((operands, op))
                    continue
                fam["fill" if o == "cs" else "stroke"] = f
                if f == "pattern":
                    report["problems"].append("pattern fill")
                    out.append((operands, op))
                else:
                    out.append(([reg_name], op))
                continue
            if o in ("sc", "scn", "SC", "SCN"):
                key = "fill" if o in ("sc", "scn") else "stroke"
                f = fam[key]
                if f in ("pattern", "keep"):
                    out.append((operands, op))
                    continue
                vals = [float(v) for v in operands if not isinstance(v, pikepdf.Name)]
                if f == "reg":
                    # Already set to /NumoReg by us, or a previous tint of it
                    light = 1.0 - (vals[0] if vals else 1.0)
                elif f == "indexed":
                    light = 0.0
                else:
                    light = _lightness(f, vals)
                tint = 0 if light >= _WHITE_MIN else 1
                out.append(([tint], pikepdf.Operator("scn" if key == "fill" else "SCN")))
                report["rewritten"] += 1
                continue
            if o == "sh":
                report["problems"].append("shading")
            if o == "INLINE IMAGE":
                report["problems"].append("inline image")
            if o == "Do":
                xobjs = res.get("/XObject", {})
                x = xobjs.get(operands[0])
                if x is not None:
                    if x.get("/Subtype") == "/Image":
                        if not x.get("/ImageMask"):
                            report["problems"].append("placed image")
                    elif x.objgen not in done:
                        done.add(x.objgen)
                        _walk(x, x.get("/Resources"), False)
            out.append((operands, op))
        data = pikepdf.unparse_content_stream(out)
        if is_page:
            owner.Contents = pdf.make_stream(data)
        else:
            owner.write(data)

    for page in pdf.pages:
        res = page.obj.get("/Resources")
        if res is None:
            res = getattr(page, "resources", None)   # inherited from /Pages
            if res is not None:
                page.obj.Resources = res
        _walk(page.obj, res, True)
    # Every /All on the sheet is then the one Illustrator definition: the
    # template's own furniture brought in its own (one with an RGB fallback),
    # and anything reportlab wrote. Two definitions under one name is what
    # makes Illustrator open the black as a spot swatch called Registration
    # instead of its [Registration] swatch.
    report["registration_unified"] = unify_registration(pdf, reg)
    pdf.save(str(pdf_path))
    report["problems"] = sorted(set(report["problems"]))
    return report


# Illustrator's own [Registration], exactly as Illustrator writes it into a PDF:
# /Separation /All, CMYK alternate, a PostScript (type 4) tint transform that
# puts 100 % on every plate. Opened in Illustrator this IS the [Registration]
# swatch, not a spot colour of that name.
_AI_REG_FN = b"{dup 1.0 mul exch dup 1.0 mul exch dup 1.0 mul exch 1.0 mul}"


def illustrator_registration(pdf):
    import pikepdf
    fn = pdf.make_stream(_AI_REG_FN)
    fn.FunctionType = 4
    fn.Domain = pikepdf.Array([0, 1])
    fn.Range = pikepdf.Array([0, 1, 0, 1, 0, 1, 0, 1])
    return pdf.make_indirect(pikepdf.Array([
        pikepdf.Name.Separation, pikepdf.Name.All, pikepdf.Name.DeviceCMYK, fn]))


def unify_registration(pdf, reg):
    """Point every /Separation /All colour space, on every page and in every
    nested form, at `reg`. Returns how many entries were replaced."""
    import pikepdf
    seen, n = set(), 0

    def walk(res):
        nonlocal n
        if res is None:
            return
        cs = res.get("/ColorSpace")
        if cs is not None:
            for k in list(cs.keys()):
                v = cs[k]
                if isinstance(v, pikepdf.Array) and len(v) >= 2 and str(v[0]) == "/Separation" \
                        and str(v[1]) == "/All" and v.objgen != reg.objgen:
                    cs[k] = reg
                    n += 1
        for _, x in (res.get("/XObject") or {}).items():
            if x.get("/Subtype") == "/Form" and x.objgen not in seen:
                seen.add(x.objgen)
                walk(x.get("/Resources"))
        for _, pat in (res.get("/Pattern") or {}).items():
            if pat.objgen not in seen:
                seen.add(pat.objgen)
                walk(pat.get("/Resources"))
    for page in pdf.pages:
        walk(page.obj.get("/Resources"))
    return n


def pms_spot(pms_name, pms_hex):
    """The selected PMS as a named separation, for the customer proof."""
    if not pms_name:
        return Color(0, 0, 0)
    cy, ma, ye, k = hex_to_cmyk(pms_hex or "#000000")
    return CMYKColorSep(cy, ma, ye, k, spotName=pms_name, density=1)


# ─────────────────────────────────────────────────────────────────────────────
# Placement
# ─────────────────────────────────────────────────────────────────────────────

def nominal_zone_pts(product_id, slot_id, w, h):
    """
    The imprint area a slot's art is fitted into, in points.

    One figure for every view: the slot's stated size ("3.5\" W × 3.5\" H",
    "1.625\" diameter") is what the configurator measures the art against, so
    the proof table and the press sheets fit to it too. The template's boxes,
    measured off the PDF, carry their stroke and drawing slop — 252 x 252.72
    on the 9100, 216 x 324.72 on the 0472 — and fitting to those printed art
    0.01" past the stated maximum while the configurator said it fit exactly.
    Falls back to the measured box when the product states no size.
    """
    try:
        from products import PRODUCTS
        import re as _re
        p = PRODUCTS.get(product_id or "") or {}
        s = next((x for x in p.get("art_slots") or [] if x.get("id") == slot_id), None)
        nums = [float(v) for v in _re.findall(r'([\d.]+)"', (s or {}).get("size", ""))]
        if nums:
            iw = nums[0]
            ih = nums[1] if len(nums) > 1 else nums[0]
            return iw * 72.0, ih * 72.0
    except Exception:
        pass
    return w, h


class Artwork:
    """The customer's vector art, measured once and reused for every imprint."""

    def __init__(self, path, hidden_rgbs=None):
        self.path = str(path)
        # Source colours the customer switched off while reducing the art to
        # one ink. They are removed from the form before anything else touches
        # it — see _form_for. Measuring happens on the whole file either way:
        # a hidden colour that sat at the edge of the art would otherwise
        # change the ink bounds between the preview and the press sheet.
        self.hidden_rgbs = list(hidden_rgbs or [])
        box = [float(v) for v in PdfReader(self.path).pages[0].MediaBox]
        ink = ink_bbox_points(self.path, tuple(box)) or tuple(box)
        self.x0, self.y0, self.x1, self.y1 = ink
        self.w, self.h = self.x1 - self.x0, self.y1 - self.y0

    def _fit_scale(self, zone_w, zone_h, scale_mult=1.0, circular=False, art_rot=0.0):
        """
        The factor that fits this art inside a zone, proportions kept.

        A circular zone is given as a diameter in zone_w, and needs different
        arithmetic: fitting the art to the square around the circle lets its
        corners escape the circle entirely. For the bottom imprint that put a
        near-square logo 41% over the printable area, 0.39" past the edge on
        every corner — visible on the press sheets as artwork bursting through
        the die arcs, and invisible on the flat proof, which masks the bottom
        to a circle and so quietly cropped the evidence.

        The largest rectangle of a given shape that fits in a circle is the one
        whose diagonal is the diameter, so scale by the art's diagonal rather
        than by its longest side.
        """
        if circular:
            diagonal = (self.w ** 2 + self.h ** 2) ** 0.5
            return (zone_w / diagonal) * scale_mult
        # Never past the imprint area: the art's box, turned by the customer's
        # rotation (degrees), is held inside the zone whatever scale arrives.
        import math
        c, n = abs(math.cos(math.radians(art_rot or 0.0))), abs(math.sin(math.radians(art_rot or 0.0)))
        bw, bh = self.w * c + self.h * n, self.w * n + self.h * c
        return min(min(zone_w / self.w, zone_h / self.h) * scale_mult, zone_w / bw, zone_h / bh)

    def fitted_size(self, zone_w, zone_h, scale_mult=1.0, circular=False, art_rot=0.0):
        """
        The size this art actually prints at in a zone, in points.

        The imprint zone is the largest area the art may occupy, not the size
        of the imprint: art is scaled to fit inside it with its proportions
        kept, so one dimension lands short of the zone unless the art happens
        to match the zone's aspect ratio exactly. Reporting the zone instead
        tells a customer their 2.6"-tall mark is 4.6" tall, which is the number
        they would measure against on the sample.

        Shares _fit_scale() with draw() on purpose: the figure printed on the
        proof has to be the figure the press actually lays down, and two copies
        of the same formula are two things to keep in step.
        """
        s = self._fit_scale(zone_w, zone_h, scale_mult, circular, art_rot)
        return self.w * s, self.h * s

    def draw(self, c, cx, cy, zone_w, zone_h, rot_deg, scale_mult=1.0,
             circular=False, off_x=0.0, off_y=0.0, art_rot=0.0, paint=None):
        """
        Draw the art in a zone, at the size and place the customer put it.

        off_x/off_y are fractions of the zone, the same units the configurator
        nudges art in, so they survive the difference between the guide image
        it works in and the press template's points. Positive off_y moves the
        art down, matching the browser.

        art_rot is the customer's own rotation of the mark inside the slot,
        which is not the same thing as rot_deg — that one is the slot's place
        on the die, and on a tote's back panel it is 180° whatever the
        customer did.
        """
        s = self._fit_scale(zone_w, zone_h, scale_mult, circular, art_rot)
        dw, dh = self.w * s, self.h * s
        c.saveState()
        c.translate(cx, cy)
        c.rotate(rot_deg)
        # Inside the rotated frame, so a nudge follows the art rather than the
        # sheet — on a 180° panel, "right" on screen is right on the panel.
        c.translate(off_x * zone_w, -off_y * zone_h)
        if art_rot:
            c.rotate(art_rot)
        c.translate(-dw / 2, -dh / 2)
        c.scale(s, s)
        c.translate(-self.x0, -self.y0)
        c.doForm(makerl(c, self._form_for(c, paint)))
        c.restoreState()

    def _form_for(self, c, paint=None):
        """
        The prepared art form for this canvas, built once and reused.

        A sheet carries the same mark at every koozie position — up to 48 of
        them — and this used to re-read the source PDF and embed a fresh copy
        for each one. The art is vector, so every copy is the full file: a
        400 KB logo became roughly 59 MB of press PDF, which is slow to build,
        slow to download and the reason a single export could hold the server
        long enough to time out. Embedding it once per page and referencing it
        from each position produces the same printed result from a fraction of
        the bytes.

        The cache is per canvas, not per Artwork, and that matters: the form
        has had its own colours stripped so it inherits whatever separation is
        set when it is drawn, and the proof canvas paints in the customer's PMS
        while the press canvases paint in registration black. One form shared
        across both would take whichever colour was set first. Each page gets
        its own canvas here, so keying on the canvas keeps them apart, and only
        the current canvas's form is held so a long run does not accumulate
        them.
        """
        # `paint` is (ink_rgb, knockout_rgb) for this canvas. With it, white in
        # the art is a real knockout painted in knockout_rgb; without it the
        # old behaviour stands (every colour flattened to the current fill).
        key = (id(c), paint)
        if getattr(self, "_form_key", None) != key:
            xo = pagexobj(PdfReader(self.path).pages[0])
            # Colours the customer switched off while reducing the art come
            # out first, before the flatten below makes every remaining colour
            # indistinguishable from them.
            #
            # Hiding an ink in the browser only repaints a canvas; the press
            # file places the original vector. Without this the ink they were
            # shown as removed comes back — and because the flatten turns it
            # into the job's one colour, a badge whose background the customer
            # dropped arrives at the press as a solid disc with the lettering
            # swallowed. The print PDF has always done this; the press path
            # did not, which is how a one-colour job could preview correctly
            # and still image as a filled blob.
            if self.hidden_rgbs:
                from screenprint import drop_colors_from_form
                if not drop_colors_from_form(xo, self.hidden_rgbs):
                    print(f"⚠️ Hidden colours could NOT be removed from "
                          f"{self.path} — its content stream could not be "
                          f"rewritten. The press file still carries them.")
            if paint == "keep":
                pass        # already separated into named inks; leave them be
            elif paint:
                # One ink, with white kept as a hole rather than removed.
                # Removing a white shape that sits on a fill uncovers the
                # fill, so white lettering on a banner printed solid.
                from screenprint import paint_ink_and_knockouts
                if not paint_ink_and_knockouts(xo, paint[0], paint[1]):
                    drop_white_knockouts(xo)
                    recolor_form_to_spot(xo)
            else:
                drop_white_knockouts(xo)
                recolor_form_to_spot(xo)
            self._form_key, self._form = key, xo
        return self._form


def _pair_box(words, first, second):
    """
    The box around two adjacent words, and which way they read.

    Matching is case-insensitive: the templates are not consistent. Most set
    the ink placeholder as "SPOT COLOR", the 9100 as "Spot Color" — and
    matching only the shouted version meant that template never had its
    caption replaced at all, so every 9100 press sheet went out still reading
    "Spot Color" instead of the ink the customer chose. The same is true of
    "NSO NUMBER" against the 9100's "NSO Number".
    """
    a = [w for w in words if w[0].upper() == first]
    b = [w for w in words if w[0].upper() == second]
    if not a or not b:
        return None
    s, cw = a[0], b[0]
    dx = abs((s[1] + s[3]) / 2 - (cw[1] + cw[3]) / 2)
    dy = abs((s[2] + s[4]) / 2 - (cw[2] + cw[4]) / 2)
    if dx > dy:
        orient = 0 if s[1] < cw[1] else 180
    else:
        orient = 90 if s[2] > cw[2] else 270
    return dict(x0=min(s[1], cw[1]), y0=min(s[2], cw[2]),
                x1=max(s[3], cw[3]), y1=max(s[4], cw[4]), orient=orient)


def find_template_labels(template_pdf, page_count):
    """
    Locate the placeholder captions on each press sheet.

    Returns {page_number: {"spot": box, "nso": box}} with each box in
    pdftotext's top-left origin and its rotation in degrees (0, 90, 180 or
    270 — the sheets are laid out in all of them). A caption the template
    does not carry is simply absent.

    Both are found in one pass. pdftotext is a subprocess per page and these
    templates run to twelve pages, so reading the words once and matching two
    pairs against them costs half what two passes would.
    """
    import subprocess, re
    out = {}
    for pn in range(1, page_count + 1):
        try:
            xml = subprocess.run(
                ["pdftotext", "-f", str(pn), "-l", str(pn), "-bbox", str(template_pdf), "-"],
                capture_output=True, text=True, timeout=60).stdout
        except Exception:
            continue
        words = [(m.group(5), float(m.group(1)), float(m.group(2)),
                  float(m.group(3)), float(m.group(4)))
                 for m in re.finditer(
                     r'<word xMin="([\d.]+)" yMin="([\d.]+)" xMax="([\d.]+)" '
                     r'yMax="([\d.]+)">([^<]*)</word>', xml)]
        found = {}
        for key, (w1, w2) in (("spot", ("SPOT", "COLOR")),
                              ("nso", ("NSO", "NUMBER"))):
            box = _pair_box(words, w1, w2)
            if box:
                found[key] = box
        if found:
            out[pn] = found
    return out


def _stamp_material_tag(c, box, page_h, product):
    """The product's "press_tag" (e.g. "EV") in bold, just right of the NSO
    caption, in registration black so it is on every screen."""
    try:
        from products import PRODUCTS as _P
        tag = ((_P.get(product or "") or {}).get("press_tag") or "").strip()
    except Exception:
        tag = ""
    if not tag or not box:
        return
    x = box["x1"] + 18
    y = page_h - (box["y0"] + box["y1"]) / 2
    c.saveState()
    c.setFillColor(registration_black())
    c.setFont("Helvetica-Bold", 26)
    if box.get("orient") in (0, None):
        c.drawString(x, y - 9, tag)
    else:
        c.translate((box["x0"] + box["x1"]) / 2, y)
        c.rotate(box["orient"])
        c.drawString((box["x1"] - box["x0"]) / 2 + 18, -9, tag)
    c.restoreState()


def _stamp_caption(c, box, page_h, text, runs=None):
    """
    Print `text` over one of the template's placeholder captions.

    The placeholder is covered rather than removed — it is the vendor's own
    page content and editing their stream to delete two words is far more
    fragile than painting over the box pdftotext just measured.
    """
    if not box or not (text or runs):
        return
    pms_name = str(text or "")
    pad = 3.0
    x0, x1 = box["x0"] - pad, box["x1"] + pad
    # pdftotext measures from the top; the canvas measures from the bottom.
    y0, y1 = page_h - box["y1"] - pad, page_h - box["y0"] + pad
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    bw, bh = x1 - x0, y1 - y0

    c.saveState()
    c.setFillColor(Color(1, 1, 1))
    c.rect(x0, y0, bw, bh, fill=1, stroke=0)          # cover the placeholder
    c.translate(cx, cy)
    c.rotate(box["orient"])
    along = bw if box["orient"] in (0, 180) else bh   # text runs along this edge
    size = 22.0
    if runs:
        # A multi-colour job: every ink's name is printed IN that ink, so each
        # screen carries only its own name ("186 C" on the 186 screen) instead
        # of the whole list landing on every screen in registration.
        gap = "   "
        def width(sz):
            return sum(c.stringWidth(t, "Helvetica", sz) for t, _ in runs) \
                + c.stringWidth(gap, "Helvetica", sz) * (len(runs) - 1)
        while size > 6 and width(size) > along - 4:
            size -= 0.5
        c.setFont("Helvetica", size)
        x = -width(size) / 2
        for k, (t, col) in enumerate(runs):
            c.setFillColor(col)
            c.drawString(x, -size * 0.34, t)
            x += c.stringWidth(t + (gap if k < len(runs) - 1 else ""), "Helvetica", size)
        c.restoreState()
        return
    while size > 6 and c.stringWidth(pms_name, "Helvetica", size) > along - 4:
        size -= 0.5
    c.setFillColor(Color(0, 0, 0))
    c.setFont("Helvetica", size)
    c.drawCentredString(0, -size * 0.34, pms_name)
    c.restoreState()


# ── Recolouring the template's own strokes ──────────────────────────────────
# The guide page draws the die cut in red and the seam lines in purple. On the
# customer proof those become the actual neoprene and stitching colours, so the
# proof reads as the finished product. Only STROKE operators are remapped —
# fills are left alone so the legend text and orientation arrows keep their
# meaning.

DIE_CUT_RGB = [(0.847, 0.118, 0.2), (0.847, 0.118, 0.231), (0.847, 0.118, 0.224)]
SEAM_RGB    = [(0.431, 0.302, 0.624), (0.467, 0.365, 0.659)]

_RG_RE = re.compile(rb"([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+RG")


def _hex_list_to_rgb(hexes):
    """#rrggbb strings to 0-255 triples, skipping anything malformed."""
    out = []
    for h in (hexes or []):
        s = str(h).strip().lstrip("#")
        if len(s) != 6:
            continue
        try:
            out.append(tuple(int(s[i:i + 2], 16) for i in (0, 2, 4)))
        except ValueError:
            continue
    return out


def _machine_of(name):
    """The press name out of a sheet name, for specs without a "machine" field."""
    n = re.sub(r"\s*-\s*BTM\s*$", "", name or "", flags=re.I).strip()
    n = re.sub(r"\s+copy\b", "", n, flags=re.I)
    return re.sub(r"\s+[12]\s+Sides?\b.*$", "", n, flags=re.I).strip()


def _hex_to_rgb01(hexv):
    h = (hexv or "").lstrip("#")
    if len(h) != 6:
        return None
    try:
        return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    except ValueError:
        return None


def remap_stroke_colors(page, mapping, tol=0.02):
    """
    Rewrite the page's stroke colours in place.

    mapping: [([(r,g,b), …] targets, (r,g,b) replacement), …]
    Returns True when the content stream was rewritten.
    """
    contents = page.Contents
    if contents is None or isinstance(contents, list):
        return False                     # multi-stream pages are left alone
    data = decode_stream(contents)
    if not data:
        return False

    def sub(m):
        try:
            rgb = tuple(float(m.group(i)) for i in (1, 2, 3))
        except ValueError:
            return m.group(0)
        for targets, repl in mapping:
            if any(all(abs(rgb[i] - t[i]) <= tol for i in range(3)) for t in targets):
                return f"{repl[0]:.4f} {repl[1]:.4f} {repl[2]:.4f} RG".encode()
        return m.group(0)

    out, n = _RG_RE.subn(sub, data)
    if not n:
        return False
    contents.stream = out.decode("latin-1")
    contents.Filter = None
    contents.DecodeParms = None
    return True


# ── Stripping the guide page down to a product preview ──────────────────────
# The proof shows the product, not the instruction sheet: imprint guides,
# orientation arrows, zone labels and the colour legend all come out, leaving
# the die cut, the stitching and the artwork.

# The guide colours, as each template actually writes them.
#
# The same element is not the same value in every template — these are separate
# exports, and the shades drift. The 0472 draws its imprint dashes at
# (0.459, 0.804, 0.867), a full 0.075 from the value the others use, and its
# die red at 0.231 where the 0070's is 0.2: a difference of 0.031 against a
# tolerance of 0.03, which missed by a thousandth and left every guide line on
# the customer's proof.
#
# Adding a product means checking for shades not listed here.
# unmatched_guide_colors() reports them, so a new template is a one-line check
# rather than a hunt through a content stream.
SUPPRESS_STROKE = [
    (0.365, 0.784, 0.863),   # maximum imprint area dashes
    (0.384, 0.788, 0.851),   # legend swatch (imprint area)
    (0.459, 0.804, 0.867),   # imprint area dashes — 0472
    (0.431, 0.302, 0.624),   # seam lines — redrawn as zig-zag stitching
    (0.467, 0.365, 0.659),   # legend swatch (seam)
    (0.847, 0.118, 0.231),   # legend swatch (die cut)
    (0.745, 0.129, 0.196),   # labels / arrows — 0472
    (0.929, 0.110, 0.306),   # orientation arrow + "Side 1 (Front)" — tote
]
SUPPRESS_FILL = [
    (0.384, 0.788, 0.851),   # zone labels + legend text (imprint area)
    (0.459, 0.804, 0.867),   # zone labels — 0472
    (0.467, 0.365, 0.659),   # legend text (seam)
    (0.847, 0.118, 0.231),   # orientation arrows, "ART", legend text (die cut)
    (0.745, 0.129, 0.196),   # orientation arrows, "ART" — 0472
    (0.929, 0.098, 0.255),   # orientation arrows, "ART", legend text — tote
]

_PAINT_OPS = {b"f", b"F", b"f*", b"S", b"s", b"B", b"B*", b"b", b"b*"}
_TEXT_OPS = {b"Tj", b"TJ", b"'", b'"'}
_NUM = re.compile(rb"^[+-]?(\d+\.?\d*|\.\d+)$")


def _near(rgb, targets, tol=0.02):
    return any(all(abs(rgb[i] - t[i]) <= tol for i in range(3)) for t in targets)


def _suppress_stream(obj, tol=0.02, fills=None, strokes=None):
    """
    Apply suppression to one content stream object.

    The colour lists default to the guide families, which is what every guide
    page wants. They are arguments so a press sheet can suppress its own marks
    without borrowing the guide's list — a press sheet has no guide furniture
    on it, and running the guide colours over it would be looking for things
    that are not there.
    """
    fills = SUPPRESS_FILL if fills is None else fills
    strokes = SUPPRESS_STROKE if strokes is None else strokes
    data = decode_stream(obj)
    if not data:
        return False
    out, pend = [], []
    fill = stroke = None
    changed = False
    for tok, is_op in _tokens(data):
        if not is_op:
            pend.append(tok)
            continue
        if tok in (b"rg", b"RG") and len(pend) >= 3:
            try:
                rgb = tuple(float(pend[-3 + i]) for i in range(3))
                if tok == b"rg":
                    fill = rgb
                else:
                    stroke = rgb
            except ValueError:
                pass
        elif tok in _TEXT_OPS:
            # Zone labels ("Side 1", "ART") are text, not paths.
            if fill and _near(fill, fills, tol):
                pend = []
                changed = True
                continue
        elif tok in _PAINT_OPS:
            drop = ((tok in (b"f", b"F", b"f*") and fill and _near(fill, fills, tol))
                    or (tok in (b"S", b"s") and stroke and _near(stroke, strokes, tol))
                    or (tok in (b"B", b"B*", b"b", b"b*") and (
                        (fill and _near(fill, fills, tol)) or
                        (stroke and _near(stroke, strokes, tol)))))
            if drop:
                out.extend(pend); pend = []
                out.append(b"n")
                changed = True
                continue
        out.extend(pend); pend = []
        out.append(tok)
    out.extend(pend)
    if not changed:
        return False
    obj.stream = b" ".join(out).decode("latin-1")
    obj.Filter = None
    obj.DecodeParms = None
    return True


_GUIDE_COLOR_FAMILIES = SUPPRESS_FILL + SUPPRESS_STROKE + [(0.847, 0.118, 0.2)]


# Marks drawn on a press sheet for us to measure against, not for the press to
# image. The tote's crosshairs are the case: the vendor put a magenta cross at
# the dead centre of each imprint so the positions could be read off the sheet
# instead of fitted from die outlines, which is how the koozies had to be done.
#
# Their job is finished the moment the spec records those centres. Left in the
# output they would burn onto the screen, so they come off every press sheet
# this file produces — which also means the numbers in the spec are now the
# only record of where they were. Do not re-derive them from an exported file.
REGISTRATION_MARK_RGB = [
    (1.0, 0.0, 1.0),   # magenta imprint-centre crosshairs — tote
]


def drop_registration_marks(page, tol=0.02):
    """Discard the measuring marks, keeping everything else the sheet draws."""
    contents = page.Contents
    if contents is None or isinstance(contents, list):
        return False
    return _suppress_stream(contents, tol,
                            fills=REGISTRATION_MARK_RGB,
                            strokes=REGISTRATION_MARK_RGB)


def unmatched_guide_colors(template_pdf, guide_page=2, tol=0.03):
    """
    Saturated colours on a guide page that no suppression rule covers.

    Run this when adding a product. Anything it lists is guide furniture that
    will survive onto the customer's proof, or a die outline that will not be
    filled — both of which look like the imposition is broken rather than like
    a colour value being a few thousandths off.
    """
    page = PdfReader(str(template_pdf)).pages[guide_page - 1]
    c = page.Contents
    if c is None or isinstance(c, list):
        return []
    data = decode_stream(c)
    if not data:
        return []
    known = _GUIDE_COLOR_FAMILIES + [tuple(
        float(v) for v in op.split()[:3]) for op in DIE_STROKE_REDS]
    seen, out = set(), []
    for m in _COL_RE.finditer(data):
        rgb = tuple(round(float(m.group(i)), 3) for i in (1, 2, 3))
        if max(rgb) - min(rgb) <= 0.15 or rgb in seen:
            continue                      # greys and near-blacks are content
        seen.add(rgb)
        if not _near(rgb, known, tol):
            out.append(rgb)
    return out
_COL_RE = re.compile(rb"([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+(?:rg|RG)")
_DO_RE = re.compile(rb"/([A-Za-z0-9_.]+)\s+Do")


def _own_xobjects(obj):
    """The XObject resources a stream's own `/Name Do` calls resolve against."""
    try:
        res = obj.Resources
        return dict((res.XObject or {}).items()) if res and res.XObject else {}
    except Exception:
        return {}


def _form_is_guide(obj, depth=0, tol=0.03, seen=None):
    """True when a form draws only guide artwork (arrows, labels, guide lines).

    Nested `Do` calls are resolved against the form's *own* resources, not the
    page's: the same name (/Fm4) means different objects at different depths.
    """
    if depth > 6:
        return False
    seen = seen if seen is not None else set()
    if id(obj) in seen:
        return False
    seen = seen | {id(obj)}
    data = decode_stream(obj)
    if not data:
        return False
    cols = []
    for m in _COL_RE.finditer(data):
        try:
            cols.append(tuple(float(m.group(i)) for i in (1, 2, 3)))
        except ValueError:
            pass
    xobjs = _own_xobjects(obj)
    nested = [xobjs.get("/" + n.decode()) for n in _DO_RE.findall(data)]
    if any(n is None for n in nested):        # unresolved name: don't guess
        return False
    if not cols and not nested:
        return False
    if cols and not all(_near(cl, _GUIDE_COLOR_FAMILIES, tol) for cl in cols):
        return False
    if nested:
        return all(_form_is_guide(n, depth + 1, tol, seen) for n in nested)
    return bool(cols)


def _drop_guide_forms(obj, tol=0.03, contents=None):
    """Remove `Do` calls for forms that contain nothing but guide artwork.

    `obj` supplies the resources; `contents` is the stream to rewrite (the page's
    Contents for a page, the form itself for a form).
    """
    contents = contents if contents is not None else obj
    if contents is None or isinstance(contents, list):
        return False
    data = decode_stream(contents)
    if not data:
        return False
    xobjs = _own_xobjects(obj)
    if not xobjs:
        return False
    guide_names = {str(k) for k, v in xobjs.items()
                   if "Form" in str(getattr(v, "Subtype", "") or "")
                   and _form_is_guide(v, tol=tol)}
    if not guide_names:
        return False

    def sub(m):
        return b"" if ("/" + m.group(1).decode()) in guide_names else m.group(0)

    out, n = _DO_RE.subn(sub, data)
    if out == data or not n:
        return False
    contents.stream = out.decode("latin-1")
    contents.Filter = None
    contents.DecodeParms = None
    return True


def strip_illustrator_private_data(page):
    """
    Remove the Illustrator private data the template carries on every page.

    An Illustrator-authored PDF stores a second, complete copy of the document
    in /PieceInfo /Illustrator /Private. Illustrator treats that copy as the
    real file: opening the PDF rebuilds the document from it and ignores the
    page content entirely. Every other PDF reader does the opposite and renders
    the page content.

    That split is invisible until it bites. The imposed artwork is drawn into
    the page content, so the export looks right in Preview, Acrobat and the
    browser — and opens in Illustrator as the bare template with no artwork on
    it, which is exactly where a press operator would look.

    Dropping /PieceInfo leaves Illustrator with only the page content, which is
    the copy that has the artwork on it. The cost is that Illustrator's own
    artboard names live in the discarded data, so the artboards come back
    numbered rather than named. Named artboards are worth less than artwork
    that is actually there.

    /Thumb goes with it: it is the template's pre-imposition preview, and file
    browsers would otherwise show a thumbnail with no artwork on it.
    """
    for key in ("/PieceInfo", "/Thumb", "/LastModified"):
        if page[key] is not None:
            del page[key]
    return page


def suppress_guides_deep(page, tol=0.02):
    """Suppress guide artwork on the page and through the whole form tree.

    Form XObjects nest, and each level resolves `/Name Do` against its own
    resources, so a single pass over the page's resource dictionary misses the
    arrows and labels that live two levels down. This walks the tree.
    """
    contents = page.Contents
    if contents is None or isinstance(contents, list):
        return False
    changed = _drop_guide_forms(page, tol=0.03, contents=contents)
    changed |= _suppress_stream(contents, tol)

    seen = set()

    def walk(obj, depth=0):
        nonlocal changed
        if depth > 6 or id(obj) in seen:
            return
        seen.add(id(obj))
        changed |= _drop_guide_forms(obj, tol=0.03)
        changed |= _suppress_stream(obj, tol)
        for _, child in _own_xobjects(obj).items():
            if "Form" in str(getattr(child, "Subtype", "") or ""):
                walk(child, depth + 1)

    for _, o in _own_xobjects(page).items():
        if "Form" in str(getattr(o, "Subtype", "") or ""):
            walk(o)
    return changed


def suppress_guides(page, tol=0.02):
    """
    Turn the guide artwork into no-op paints, keeping the paths intact.

    Walks the content stream tracking the current fill and stroke colour; when a
    path is about to be painted in one of the guide colours, the paint operator
    becomes `n` so the path is discarded instead of drawn.
    """
    contents = page.Contents
    if contents is None or isinstance(contents, list):
        return False
    data = decode_stream(contents)
    if not data:
        return False

    out = []
    pend = []
    fill = stroke = None
    changed = False
    for tok, is_op in _tokens(data):
        if not is_op:
            pend.append(tok)
            continue
        if tok in (b"rg", b"RG") and len(pend) >= 3:
            try:
                rgb = tuple(float(pend[-3 + i]) for i in range(3))
                if tok == b"rg":
                    fill = rgb
                else:
                    stroke = rgb
            except ValueError:
                pass
        elif tok in _PAINT_OPS:
            drop = ((tok in (b"f", b"F", b"f*") and fill and _near(fill, SUPPRESS_FILL, tol))
                    or (tok in (b"S", b"s") and stroke and _near(stroke, SUPPRESS_STROKE, tol))
                    or (tok in (b"B", b"B*", b"b", b"b*") and (
                        (fill and _near(fill, SUPPRESS_FILL, tol)) or
                        (stroke and _near(stroke, SUPPRESS_STROKE, tol)))))
            if drop:
                out.extend(pend); pend = []
                out.append(b"n")
                changed = True
                continue
        out.extend(pend); pend = []
        out.append(tok)
    out.extend(pend)
    if not changed:
        return False
    contents.stream = b" ".join(out).decode("latin-1")
    contents.Filter = None
    contents.DecodeParms = None
    return True


# Where the seam runs on this template, and how the zig-zag is drawn over it.
SEAM_X = (509.91, 774.83)
SEAM_BANDS = ((555.0, 849.5), (94.0, 388.3))
ZIGZAG_AMPLITUDE = 2.6
ZIGZAG_PITCH = 7.0


def draw_straight_seams(c, hexv, bands, xs):
    """A straight running stitch: short dashes along each seam."""
    rgb = _hex_to_rgb01(hexv)
    if not rgb:
        return
    c.saveState()
    c.setStrokeColor(Color(*rgb))
    c.setLineWidth(1.2)
    c.setLineCap(1)
    c.setDash(4, 3)
    for x, (y0, y1) in zip(xs, bands):
        c.line(x, y0, x, y1)
    c.restoreState()


def draw_zigzag_seams(c, hexv, bands=SEAM_BANDS, xs=SEAM_X):
    """Draw the seam as zig-zag stitching, the way the factory sews it."""
    rgb = _hex_to_rgb01(hexv)
    if not rgb:
        return
    c.saveState()
    c.setStrokeColor(Color(*rgb))
    c.setLineWidth(1.1)
    c.setLineCap(1)
    c.setLineJoin(1)
    for x in xs:
        for y0, y1 in bands:
            p = c.beginPath()
            y = y0
            side = -1
            p.moveTo(x + ZIGZAG_AMPLITUDE * side, y)
            while y < y1:
                y = min(y + ZIGZAG_PITCH, y1)
                side = -side
                p.lineTo(x + ZIGZAG_AMPLITUDE * side, y)
            c.drawPath(p, stroke=1, fill=0)
    c.restoreState()


# The die-cut outline is stroked in this exact red, distinct from the red used
# by the legend text and swatch — so it can be targeted precisely.
# Reds a die outline is drawn in. Which one a template uses varies, and one of
# them doubles as the legend swatch colour, so colour alone cannot identify the
# die — _find_die_stroke picks by path size instead.
DIE_STROKE_REDS = [
    b"0.847 0.118 0.2 RG",
    b"0.847 0.118 0.231 RG",
]
DIE_STROKE_OP = DIE_STROKE_REDS[0]     # kept for callers that reference it


def _find_die_stroke(data):
    """
    Where the die outline's stroke colour is set, and which op set it.

    The die is the largest stroked path on the page by a wide margin — several
    hundred bytes of path against fifty or so for a legend swatch. Taking the
    first red instead picks whichever the template happens to write earliest,
    which on some templates is a legend swatch: the fill then lands on a
    10-point dash in the margin and the product itself stays empty.
    """
    best = None
    for op in DIE_STROKE_REDS:
        start = 0
        while True:
            i = data.find(op, start)
            if i < 0:
                break
            start = i + 1
            m = re.compile(rb"\sS\s").search(data, i + len(op))
            if not m:
                continue
            size = m.start() - (i + len(op))
            if best is None or size > best[2]:
                best = (i, op, size)
    return (best[0], best[1]) if best else None


def fill_die_cut(page, rgb):
    """
    Paint the die-cut shape solid in the product's colour so the proof reads as
    the finished item rather than as a line drawing.

    The template strokes the die AFTER the seam and imprint guides, so filling
    it in place would bury them. Instead the same path is re-emitted as a fill
    at the very start of the content stream — underneath everything — and the
    original red stroke is turned into a no-op paint.
    """
    contents = page.Contents
    if contents is None or isinstance(contents, list):
        return False
    data = decode_stream(contents)
    if not data:
        return False
    hit = _find_die_stroke(data)
    if hit is None:
        return False
    i, op = hit
    m = re.compile(rb"\sS\s").search(data, i)
    if not m:
        return False
    j = m.start()
    body = data[i + len(op):j]                 # dash reset, q, cm, path ops
    rg = f"{rgb[0]:.4f} {rgb[1]:.4f} {rgb[2]:.4f} rg".encode()

    # Filled where the path already is, rather than copied to the top of the
    # stream. Relocating it was a way to get the fill underneath the guides,
    # but suppress_guides_deep() has already removed those by the time this
    # runs — and the copy only lands correctly if the path carries its own
    # transform. On a template that strokes the die at the very end of its
    # content stream, after transforms set further up, the fill is emitted
    # against a different coordinate system and disappears off the page: the
    # proof comes out as an unfilled outline with no product colour at all.
    out = data[:i] + rg + body + b"\nf\n" + data[m.end():]

    contents.stream = out.decode("latin-1")
    contents.Filter = None
    contents.DecodeParms = None
    return True


def _swatch(c, x, y, hexv, size=9.5):
    """Small colour chip drawn beside a component row."""
    try:
        h = (hexv or "").lstrip("#")
        r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    except Exception:
        return False
    c.setFillColor(Color(r, g, b))
    c.setStrokeColor(Color(0.72, 0.72, 0.72))
    c.setLineWidth(0.5)
    c.rect(x, y, size, size, fill=1, stroke=1)
    return True


def _info_panel(c, x, y_top, w, rows, scale=1.0):
    """
    The job specification block on the customer proof.

    rows is a list of (label, value, hex_or_None); a hex draws a colour chip
    beside the value so the build reads at a glance.
    """
    c.setFillColor(Color(0.42, 0.42, 0.42))
    c.setFont("Helvetica-Bold", 9 * scale)
    c.drawString(x, y_top, "THIS CONFIGURATION")
    c.setStrokeColor(Color(0.80, 0.80, 0.80))
    c.setLineWidth(0.6)
    c.line(x, y_top - 8 * scale, x + w, y_top - 8 * scale)

    ty = y_top - 25 * scale
    for label, value, hexv in rows:
        c.setFillColor(Color(0.55, 0.55, 0.55))
        c.setFont("Helvetica", 7.5 * scale)
        c.drawString(x, ty, label)
        vx = x + 118 * scale
        if hexv and _swatch(c, vx, ty - 1.5 * scale, hexv, size=9.5 * scale):
            vx += 15 * scale
        c.setFillColor(Color(0.15, 0.15, 0.15))
        c.setFont("Helvetica-Bold", 9.5 * scale)
        c.drawString(vx, ty, str(value))
        ty -= 17 * scale
    return ty


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

def _stamp_sheet_name(c, spot, name):
    """
    Print which sheet this is, in its own job slug.

    The name goes here rather than on the artboard because an artboard name
    cannot survive this export: Illustrator keeps those in its private copy of
    the document, which every page has stripped so the imposed artwork is
    visible at all, and the PDF format has nothing that carries one. Printed
    into the slug it survives any conversion, and it lands next to the NSO
    number the production artist is about to write in — which is the moment
    someone needs to know which sheet they are looking at.

    The position is measured once per template by derive_artboards.py, which
    renders the sheet and finds empty space beside the slug. It is measured
    rather than offset from the caption because part of what the templates put
    in that block is outlined vector rather than live text — on some sheets
    pdftotext cannot see the product name at all — so an offset that clears the
    block on one sheet prints straight through it on the next. The rotation
    comes with it, so the name reads the right way up on sheets the template
    set sideways or inverted.
    """
    if not name or not spot:
        return
    x, y, rot = spot[0], spot[1], spot[2]
    c.saveState()
    c.translate(x, y)
    c.rotate(rot)
    c.setFillColor(Color(0, 0, 0))
    c.setFont("Helvetica-Bold", 12)
    c.drawCentredString(0, 0, name)
    c.restoreState()


def _set_page_labels(writer, names):
    """
    Name the pages of the output PDF.

    This is NOT the same thing as naming Illustrator artboards, and it is worth
    being clear about why, because the two look alike from the outside.
    Illustrator keeps artboard names in its own private copy of the document,
    which this file strips from every page — stripping it is what makes the
    imposed artwork visible in Illustrator at all, and the names go with it.
    Nothing in the PDF specification carries an artboard name.

    Page labels are what a PDF does have. They show in a reader's page-number
    box and in tools that split by label, and they cost nothing. The names that
    actually matter for the press room are the per-sheet filenames the export
    writes, which do not depend on any application reading them back.
    """
    from pdfrw import PdfDict, PdfName, PdfString
    nums = []
    for i, entry in enumerate(names):
        nm = entry.get("name") if isinstance(entry, dict) else entry
        if not nm:
            continue
        nums.extend([i, PdfDict(P=PdfString.encode(nm))])
    if not nums:
        return
    writer.trailer.Root.PageLabels = PdfDict(Nums=nums)


def sheet_filename(prefix, name, page_no):
    """
    What one press sheet is called on disk.

    The NSO number, then the sheet name exactly as the floor says it —
    "NSO-104882 - STRYKER - BTM 2 Sides Same.pdf". No sheet number: a job gets
    one sheet per machine, so the name alone says which it is.
    """
    safe = re.sub(r'[^A-Za-z0-9 ._-]', '', str(name or "sheet")).strip()
    safe = re.sub(r'\s+', ' ', safe)
    return f"{prefix} - {safe}.pdf"


def split_sheets(built_pdf, out_dir, prefix, page_names):
    """
    One PDF per press sheet, named for the sheet.

    The point of this is the press room's mass export: opening the master and
    exporting artboards gets you files called Artboard 1..N, because the names
    Illustrator would use were stripped along with its private data. Writing
    the files here skips that round trip entirely and names them correctly the
    first time.

    The proof page is not split out; it is the customer's, not the floor's.
    """
    src = PdfReader(str(built_pdf))
    out = []
    for page, entry in zip(src.pages, page_names):
        entry = entry if isinstance(entry, dict) else {"name": entry, "page": 0}
        name = entry.get("name")
        if name == "Proof":
            continue
        # A sheet whose artboard name was never recorded still has to come out
        # as a file. Dropping it would lose a screen from the job silently,
        # which is the one failure the press room cannot see.
        if not name:
            name = f"Sheet {entry.get('page') or 0:02d}"
        dest = Path(out_dir) / sheet_filename(prefix, name, entry.get("page") or 0)
        # Two sheets with one name would overwrite each other; never lose one.
        n = 2
        while dest in out:
            dest = dest.with_name(f"{dest.stem} ({n}).pdf"); n += 1
        w = PdfWriter(str(dest), trailer=None)
        w.addpage(page)
        _set_page_labels(w, [entry])
        w.write()
        out.append(dest)
    return out


def _wrap_text(c, text, font, size, width):
    """Break `text` into lines that fit `width` at this font and size."""
    words, lines, cur = str(text).split(), [], ""
    for w in words:
        trial = f"{cur} {w}".strip()
        if cur and c.stringWidth(trial, font, size) > width:
            lines.append(cur)
            cur = w
        else:
            cur = trial
    if cur:
        lines.append(cur)
    return lines


def _risk_line(r):
    """One finding as the proof prints it.

    The configurator sends these as finished sentences. A caller that has the
    structured finding instead gets the same line built here, rather than
    str() printing a dict onto a customer's proof.
    """
    if isinstance(r, dict):
        return ": ".join(p for p in (r.get("label") or r.get("slot"),
                                     r.get("note") or r.get("message")) if p)
    return str(r)


def _accepted_risks_height(c, risks, w, scale=1.0):
    """How tall _accepted_risks_note will draw, so callers can place it.

    Wraps with the same font and width the drawing does; anything else and
    the block would overrun whatever was reserved for it.
    """
    if not risks:
        return 0.0
    size = 7.5 * scale
    h = 13 * scale
    for r in risks:
        h += 10 * scale * len(_wrap_text(c, f"— {_risk_line(r)}",
                                         "Helvetica", size, w)) + 2 * scale
    return h


def _accepted_risks_note(c, x, y_top, w, risks, scale=1.0):
    """
    The print-quality findings the customer accepted, printed on the proof.

    Set apart from the configuration block above it and headed plainly, so
    nobody reads it as a specification. It is a record of a decision: these
    are the things the configurator flagged and the customer chose to print
    regardless.
    """
    if not risks:
        return y_top
    size = 7.5 * scale
    c.setFillColor(Color(0.62, 0.36, 0.26))
    c.setFont("Helvetica-Bold", 8 * scale)
    c.drawString(x, y_top, "ACCEPTED BY CUSTOMER")
    y = y_top - 13 * scale
    c.setFont("Helvetica", size)
    for r in risks:
        for line in _wrap_text(c, f"— {_risk_line(r)}", "Helvetica", size, w):
            c.drawString(x, y, line)
            y -= 10 * scale
        y -= 2 * scale
    return y


# ─────────────────────────────────────────────────────────────────────────────
# The customer proof
# ─────────────────────────────────────────────────────────────────────────────
#
# Page one of every press file. It is drawn here rather than printed over the
# vendor's guide page, which is what it used to be, and that change is what
# lets it carry Numo's own layout and none of the vendor's branding.
#
# The vendor guide is still built — the flat lay comes off it, because those
# die shapes are measured geometry and redrawing them here would be a second
# approximation of the same thing — but it is used as a source and never
# reaches the output.

PROOF_W, PROOF_H = 612.0, 792.0        # US Letter portrait, so it prints as-is
PROOF_MARGIN = 34.0

_INK = Color(0.13, 0.13, 0.13)
_MUTED = Color(0.45, 0.45, 0.45)
_RULE = Color(0.85, 0.85, 0.85)


def _field(c, x, y, label, value, size=9.0, label_w=78.0, swatch_hex=None):
    """One `Label: value` line, with an optional colour chip before the value."""
    c.setFillColor(_MUTED)
    ls = size                                   # a long label ("Heathered Neoprene") fits its column
    while ls > 6 and c.stringWidth(str(label), "Helvetica", ls) > label_w - 4:
        ls -= 0.25
    c.setFont("Helvetica", ls)
    c.drawString(x, y, label)
    vx = x + label_w
    if swatch_hex and _swatch(c, vx, y - 1.0, swatch_hex, size=size * 0.95):
        vx += size * 1.45
    c.setFillColor(_INK)
    c.setFont("Helvetica-Bold", size)
    c.drawString(vx, y, str(value if value not in (None, "") else "—"))
    return y - (size + 4.0)


def _imprint_inks(inks):
    """Every ink that prints on the job, once each, in screen order: [{name, hex}]."""
    if not inks:
        return []
    lists = inks.values() if isinstance(inks, dict) else [inks]
    out, seen = [], set()
    for lst in lists:
        for i in lst or []:
            if i.get("hidden"):
                continue
            nm = i.get("pms") or i.get("hex") or ""
            if nm in seen:
                continue
            seen.add(nm)
            out.append({"name": nm.replace("PANTONE ", ""),
                        "hex": i.get("pms_hex") or i.get("hex") or "#000000"})
    return out


def _ink_field(c, x, y, label, inks, right, size=9.0, label_w=78.0):
    """The Imprint line for a multi-color job: a chip in front of every ink."""
    c.setFillColor(_MUTED)
    c.setFont("Helvetica", size)
    c.drawString(x, y, label)
    x0 = x + label_w
    vx = x0
    for ink in inks:
        text = ink["name"]
        w = size * 1.45 + c.stringWidth(text, "Helvetica-Bold", size) + 10
        if vx > x0 and vx + w > right:
            vx = x0
            y -= size + 4.0
        _swatch(c, vx, y - 1.0, ink["hex"], size=size * 0.95)
        c.setFillColor(_INK)
        c.setFont("Helvetica-Bold", size)
        c.drawString(vx + size * 1.45, y, text)
        vx += w
    return y - (size + 4.0)


def _proof_swatch_grid(c, x, y_bottom, w, colors, chip=12.0, gap=3.5):
    """
    The product's available colourways, as chips.

    Laid out upward from `y_bottom` rather than downward from a heading,
    because the number of rows depends on how many colours the material comes
    in — 58 for neoprene, 17 for dyed canvas — and a grid that grows downward
    from a fixed point runs off the foot of the page on the long palettes.
    Returns the y of the heading, so whatever sits above it can stop there.
    """
    if not colors:
        return y_bottom
    per_row = max(1, int((w + gap) // (chip + gap)))
    rows = -(-len(colors) // per_row)
    y = y_bottom + (rows - 1) * (chip + gap)
    head_y = y + chip + 6
    c.setFillColor(_MUTED)
    c.setFont("Helvetica", 8.5)
    c.drawString(x, head_y, "Available Product Colors")
    cx = x
    for i, col in enumerate(colors):
        if i and i % per_row == 0:
            cx = x
            y -= chip + gap
        _swatch(c, cx, y, col.get("hex") or "#FFFFFF", size=chip)
        cx += chip + gap
    return head_y


def _proof_sidecars(out_pdf, meta, flat_png, mockup_img):
    """What a proof page was drawn from, kept beside it: an export with color
    variants puts every variant of an item on one page (build_proof_page_multi)."""
    import shutil as _sh
    try:
        Path(f"{out_pdf}.meta.json").write_text(json.dumps(meta, default=str))
        if flat_png and Path(flat_png).exists():
            _sh.copy2(str(flat_png), f"{out_pdf}.flat.png")
            if Path(f"{flat_png}.vec.json").exists():
                _sh.copy2(f"{flat_png}.vec.json", f"{out_pdf}.flat.png.vec.json")
        if mockup_img and Path(mockup_img).exists():
            _sh.copy2(str(mockup_img), f"{out_pdf}.mock.img")
    except Exception as e:
        print(f"⚠️ proof sidecars not kept: {e}")


def draw_flat_vectors(c, flat_png, X, Y, W, H):
    """Over a 4CP flat lay drawn at (X, Y, W, H): each panel again, as the print
    file's own vector, so the proof carries the same named spot colours as the
    production file (in the colours the picker shows). The picture stays under
    it — for anything that can't be drawn this way, and as the fallback."""
    side = Path(f"{flat_png}.vec.json")
    if not side.exists():
        return
    try:
        d = json.loads(side.read_text())
        if not Path(d["pdf"]).exists():
            return
        from pdfrw import PdfReader as _R
        from pdfrw.buildxobj import pagexobj
        from pdfrw.toreportlab import makerl
        page = _R(d["pdf"]).pages[0]
        xo = pagexobj(page)
        ph = float(page.MediaBox[3]) - float(page.MediaBox[1])
        s = W / float(d["png"][0])
        top = Y + H
        for p in d["panels"]:
            px, py, pw_, ph_ = p["at"]
            x0, y0, x1, y1 = p["box"]                 # points, from the page's top-left
            f = (pw_ / p["w"]) * (p["w"] / max(1e-6, (x1 - x0) if p["rot"] in (0, 180) else (y1 - y0)))
            k = f * s                                  # print-file points -> proof points
            left, bottom = X + px * s, top - (py + ph_) * s
            w_, h_ = pw_ * s, ph_ * s
            c.saveState()
            path = c.beginPath()
            if p.get("circle"):
                ins = p.get("inset", 0) * w_
                path.ellipse(left + ins, bottom + ins, w_ - 2 * ins, h_ - 2 * ins)
            else:
                path.rect(left, bottom, w_, h_)
            c.clipPath(path, stroke=0, fill=0)
            if p["rot"] == 180:
                c.translate(left + w_, bottom + h_)
                c.rotate(180)
            else:
                c.translate(left, bottom)
            c.scale(k, k)
            c.translate(-x0, -(ph - y1))
            c.doForm(makerl(c, xo))
            c.restoreState()
    except Exception as e:
        print(f"⚠️ Flat lay vector overlay skipped: {e}")


def build_proof_page_multi(out_pdf, metas, flats, mockup_img=None):
    """
    One proof page for every color variant of an item (one order line each):
    the job's details once at the top, then a block per variant — its colors,
    imprint and quantity beside its flat lay.
    """
    from reportlab.lib.utils import ImageReader
    c = rlcanvas.Canvas(str(out_pdf), pagesize=(PROOF_W, PROOF_H))
    m0 = metas[0]
    x = PROOF_MARGIN
    y = PROOF_H - PROOF_MARGIN
    text_right = PROOF_W - PROOF_MARGIN
    mock_bottom = PROOF_H
    if mockup_img and Path(mockup_img).exists():
        try:
            im = ImageReader(str(mockup_img))
            iw, ih = im.getSize()
            box = 150.0
            sc = min(box / iw, box / ih)
            mw, mh = iw * sc, ih * sc
            mx, my = PROOF_W - PROOF_MARGIN - mw, PROOF_H - PROOF_MARGIN - mh
            c.drawImage(im, mx, my, mw, mh, mask="auto")
            c.setStrokeColor(_RULE); c.setLineWidth(0.6)
            c.rect(mx, my, mw, mh, fill=0, stroke=1)
            text_right, mock_bottom = mx - 16, my
        except Exception as e:
            print(f"⚠️ Mockup could not be placed on the proof: {e}")
    c.setFillColor(_INK); c.setFont("Helvetica", 17)
    c.drawString(x, y - 13, "DIGITAL PROOF")
    y -= 30
    c.setFillColor(_RULE); c.rect(x, y + 6, text_right - x, 0.8, fill=1, stroke=0)
    y -= 6
    nso = m0.get("order_id")
    if nso and m0.get("revision"):
        nso = f'{nso}   ·   Rev {m0["revision"]}'
    y = _field(c, x, y, "NSO#", nso)
    if m0.get("customer"):
        y = _field(c, x, y, "Customer", m0.get("customer"))
    if m0.get("artist"):
        y = _field(c, x, y, "Artist", m0.get("artist"))
    y = _field(c, x, y, "Item#", m0.get("item"))
    y = _field(c, x, y, "Description", m0.get("label"))
    y = _field(c, x, y, "Colors", f"{len(metas)} on this order")
    _ord = {"side 1": 0, "side 2": 1, "bottom": 2}
    sizes = sorted(m0.get("art_sizes") or [], key=lambda z: _ord.get(str(z.get("label") or "").lower(), 3))
    c.setFillColor(_MUTED); c.setFont("Helvetica", 9)
    c.drawString(x, y, "Art Size"); y -= 13
    for sz in sizes:
        y = _field(c, x + 14, y, sz.get("label") or "", sz.get("size"), label_w=64.0)
    y -= 4
    for label, text in (("Info", None), ("Artist Note", m0.get("artist_note"))):
        c.setFillColor(_MUTED); c.setFont("Helvetica", 9)
        c.drawString(x, y, label)
        if text:
            c.setFillColor(_INK); c.setFont("Helvetica", 9)
            c.drawString(x + 78, y, str(text)[:90])
        c.setStrokeColor(_RULE); c.setLineWidth(0.7)
        c.line(x + 78, y - 2, max(x + 200, text_right), y - 2)
        y -= 17
    y = min(y, mock_bottom - 10)
    w = PROOF_W - 2 * PROOF_MARGIN
    head_y = _proof_swatch_grid(c, x, PROOF_MARGIN + 14, w, m0.get("product_colors"))
    floor_y = head_y + 14
    # ── A block per variant ────────────────────────────────────────────────
    n = len(metas)
    block_h = (y - floor_y) / n
    col_w = 190.0
    for k, (mt, fl) in enumerate(zip(metas, flats)):
        top = y - k * block_h
        c.setStrokeColor(_RULE); c.setLineWidth(0.7)
        c.line(x, top, x + w, top)
        fy = top - 15
        c.setFillColor(_INK); c.setFont("Helvetica-Bold", 10.5)
        body = mt.get("item_color") or {}
        c.drawString(x, fy, f"{k + 1}.  {body.get('name') or 'Color ' + str(k + 1)}"
                     + (f"   ·   line {mt['line_no']}" if mt.get("line_no") else ""))
        fy -= 16
        fy = _field(c, x, fy, body.get("label") or "Item Color", body.get("name"), swatch_hex=body.get("hex"))
        for extra in mt.get("components_extra") or []:
            fy = _field(c, x, fy, extra.get("label") or "", extra.get("name"), swatch_hex=extra.get("hex"))
        inks_list = mt.get("imprint_inks") or []
        ink = mt.get("imprint") or {}
        if len(inks_list) > 1:
            fy = _ink_field(c, x, fy, "Imprint", inks_list, x + col_w)
        else:
            fy = _field(c, x, fy, "Imprint", ink.get("name"), swatch_hex=ink.get("hex"))
        if mt.get("quantity"):
            fy = _field(c, x, fy, "Quantity", f'{int(mt["quantity"]):,}')
        if fl and Path(fl).exists():
            try:
                # Trimmed to the item, so each lay fills its block.
                from PIL import Image as _Im, ImageChops as _IC
                pim = _Im.open(str(fl)).convert("RGB")
                bb = _IC.difference(pim, _Im.new("RGB", pim.size, (255, 255, 255))).convert("L").point(
                    lambda v: 255 if v > 12 else 0).getbbox()
                if bb:
                    mpx = int(0.02 * max(pim.size))
                    pim = pim.crop((max(0, bb[0] - mpx), max(0, bb[1] - mpx),
                                    min(pim.width, bb[2] + mpx), min(pim.height, bb[3] + mpx)))
                im = ImageReader(pim)
                iw, ih = im.getSize()
                aw, ah = w - col_w - 8, block_h - 10
                sc = min(aw / iw, ah / ih)
                fw, fh = iw * sc, ih * sc
                c.drawImage(im, x + col_w + 8 + (aw - fw) / 2, top - 5 - ah + (ah - fh) / 2, fw, fh, mask="auto")
                # The vector panels, placed as the whole lay would be (it was trimmed).
                _W0, _H0 = _Im.open(str(fl)).size
                _cx0, _cy0 = ((max(0, bb[0] - mpx), max(0, bb[1] - mpx)) if bb else (0, 0))
                _X, _Yt = x + col_w + 8 + (aw - fw) / 2 - _cx0 * sc, top - 5 - ah + (ah - fh) / 2 + fh + _cy0 * sc
                draw_flat_vectors(c, fl, _X, _Yt - _H0 * sc, _W0 * sc, _H0 * sc)
            except Exception as e:
                print(f"⚠️ Flat lay could not be placed on the proof: {e}")
    c.setFillColor(_MUTED); c.setFont("Helvetica", 7.5)
    c.drawString(x, PROOF_MARGIN - 4, f"Generated {date.today().isoformat()}"
                 + (f"   ·   {m0.get('footer')}" if m0.get("footer") else ""))
    c.save()
    return str(out_pdf)


def build_proof_page(out_pdf, meta, flat_png=None, mockup_img=None):
    _proof_sidecars(out_pdf, meta, flat_png, mockup_img)
    return _build_proof_page(out_pdf, meta, flat_png, mockup_img)


def _build_proof_page(out_pdf, meta, flat_png=None, mockup_img=None):
    """
    Draw the customer proof.

    Everything on it comes from the job: what was ordered, what colour the
    product is, which ink, how big the art prints in each location, and what
    the customer was warned about and accepted. The fields the production
    artist fills in by hand — the NSO number, their own notes — are ruled but
    left empty, because this sheet is checked and annotated before it goes to
    production.
    """
    c = rlcanvas.Canvas(str(out_pdf), pagesize=(PROOF_W, PROOF_H))
    x = PROOF_MARGIN
    y = PROOF_H - PROOF_MARGIN

    # ── The mockup, top right ───────────────────────────────────────────────
    # The customer's own render, so the sheet opens with the thing they
    # approved rather than a stock photo of a blank product. Placed first
    # because the header rules beside it have to stop where it starts — the
    # renders carry their own background, and a rule run to the margin
    # disappears under it.
    text_right = PROOF_W - PROOF_MARGIN
    mock_bottom = PROOF_H
    if mockup_img and Path(mockup_img).exists():
        try:
            from reportlab.lib.utils import ImageReader
            im = ImageReader(str(mockup_img))
            iw, ih = im.getSize()
            box = 186.0
            s = min(box / iw, box / ih)
            mw, mh = iw * s, ih * s
            mx = PROOF_W - PROOF_MARGIN - mw
            my = PROOF_H - PROOF_MARGIN - mh
            c.drawImage(im, mx, my, mw, mh, mask="auto")
            c.setStrokeColor(_RULE)
            c.setLineWidth(0.6)
            c.rect(mx, my, mw, mh, fill=0, stroke=1)
            text_right = mx - 16
            mock_bottom = my
        except Exception as e:
            print(f"⚠️ Mockup could not be placed on the proof: {e}")

    # ── Title and the job, top left ─────────────────────────────────────────
    c.setFillColor(_INK)
    c.setFont("Helvetica", 17)
    c.drawString(x, y - 13, "DIGITAL PROOF")
    y -= 30

    c.setFillColor(_RULE)
    c.rect(x, y + 6, text_right - x, 0.8, fill=1, stroke=0)
    y -= 6

    body = meta.get("item_color") or {}
    ink = meta.get("imprint") or {}
    nso = meta.get("order_id")
    if nso and meta.get("revision"):
        nso = f'{nso}   ·   Rev {meta["revision"]}'
    y = _field(c, x, y, "NSO#", nso)
    # Only when there is one. Nothing in the configurator collects it today,
    # and a row reading "—" on every proof looks like something was missed.
    if meta.get("customer"):
        y = _field(c, x, y, "Customer", meta.get("customer"))
    if meta.get("artist"):
        y = _field(c, x, y, "Artist", meta.get("artist"))
    y = _field(c, x, y, "Item#", meta.get("item"))
    y = _field(c, x, y, "Description", meta.get("label"))
    if meta.get("quantity"):
        y = _field(c, x, y, "Quantity", f'{int(meta["quantity"]):,}')
    y = _field(c, x, y, body.get("label") or "Item Color", body.get("name"),
               swatch_hex=body.get("hex"))
    for extra in meta.get("components_extra") or []:
        y = _field(c, x, y, extra.get("label") or "", extra.get("name"),
                   swatch_hex=extra.get("hex"))
    inks_list = meta.get("imprint_inks") or []
    if len(inks_list) > 1:
        y = _ink_field(c, x, y, "Imprint", inks_list, text_right)
    else:
        y = _field(c, x, y, "Imprint", ink.get("name"), swatch_hex=ink.get("hex"))

    # Side 1, Side 2, then Bottom, whatever order the locations were placed in.
    _ord = {"side 1": 0, "side 2": 1, "bottom": 2}
    sizes = sorted(meta.get("art_sizes") or [],
                   key=lambda z: _ord.get(str(z.get("label") or "").lower(), 3))
    c.setFillColor(_MUTED)
    c.setFont("Helvetica", 9)
    c.drawString(x, y, "Art Size")
    y -= 13
    for s in sizes:
        y = _field(c, x + 14, y, s.get("label") or "", s.get("size"),
                   label_w=64.0)
    if not sizes:
        y -= 4

    # ── Notes the artist fills in ───────────────────────────────────────────
    # Ruled and left empty on purpose: this sheet is checked and annotated by
    # hand before it goes to the floor.
    y -= 4
    # In artist mode the note typed at export is set on its line; the line is
    # still ruled so it can be added to by hand.
    for label, text in (("Info", None), ("Artist Note", meta.get("artist_note"))):
        c.setFillColor(_MUTED)
        c.setFont("Helvetica", 9)
        c.drawString(x, y, label)
        if text:
            c.setFillColor(_INK)
            size = 9.0
            room = max(x + 200, text_right) - (x + 78)
            while size > 7 and c.stringWidth(text, "Helvetica", size) > room:
                size -= 0.25
            while len(text) > 4 and c.stringWidth(text, "Helvetica", size) > room:
                text = text[:-2].rstrip() + "…"
            c.setFont("Helvetica", size)
            c.drawString(x + 78, y, text)
        c.setStrokeColor(_RULE)
        c.setLineWidth(0.7)
        c.line(x + 78, y - 2, max(x + 200, text_right), y - 2)
        y -= 17

    # The flat lay runs the full width of the sheet, so it has to clear the
    # mockup as well as the field column. On a job with few fields — one
    # imprint, one component — the column ends above the image, and without
    # this the lay's white background takes a bite out of its bottom corner.
    y = min(y, mock_bottom - 10)

    # ── The foot of the page, laid out upward ───────────────────────────────
    # Colourways first, then the accepted findings above them, because both
    # blocks are as tall as their content — 58 neoprene chips or 17 canvas
    # ones, one finding or six — and only the flat lay in the middle can give
    # the space up. Anchoring them to fixed heights instead put the chips
    # through the footer on the long palettes.
    w = PROOF_W - 2 * PROOF_MARGIN
    risks = meta.get("accepted_risks") or []
    head_y = _proof_swatch_grid(c, x, PROOF_MARGIN + 14, w,
                                meta.get("product_colors"))
    floor_y = head_y + 18
    if risks:
        risk_h = _accepted_risks_height(c, risks, w, scale=0.95)
        _accepted_risks_note(c, x, floor_y + risk_h, w, risks, scale=0.95)
        floor_y += risk_h + 10

    # ── The flat lay, in whatever is left ───────────────────────────────────
    # The same front/back/bottom view the 2X2 gives, which reads as the
    # product rather than as a die diagram. Centred in the gap so a short
    # palette does not leave a band of white across the middle of the sheet.
    if flat_png and Path(flat_png).exists():
        try:
            from reportlab.lib.utils import ImageReader
            im = ImageReader(str(flat_png))
            iw, ih = im.getSize()
            avail_h = max(80.0, y - floor_y - 8)
            s = min(w / iw, avail_h / ih)
            fw, fh = iw * s, ih * s
            c.drawImage(im, (PROOF_W - fw) / 2,
                        floor_y + (avail_h - fh) / 2, fw, fh, mask="auto")
            draw_flat_vectors(c, flat_png, (PROOF_W - fw) / 2, floor_y + (avail_h - fh) / 2, fw, fh)
        except Exception as e:
            print(f"⚠️ Flat lay could not be placed on the proof: {e}")

    c.setFillColor(_MUTED)
    c.setFont("Helvetica", 7.5)
    c.drawString(x, PROOF_MARGIN - 4,
                 f"Generated {date.today().isoformat()}"
                 + (f"   ·   {meta.get('footer')}" if meta.get("footer") else ""))
    c.save()
    return str(out_pdf)


def _pick_proof_page(spec, two_sided):
    """
    Which guide page to use as the customer proof.

    Chosen by what each guide page says it shows, not by page number. The page
    numbers were assumed to be 1 for the one-side guide and 2 for the two-side
    one, which held for the first two products and is not a property of the
    format — a template carrying its guides in the other order, or only one of
    them, would send a two-sided job to a page that is a press sheet.
    """
    guides = spec.get("guide_pages") or {}
    fallback = None
    for pn in sorted(guides, key=int):
        sides = guides[pn].get("sides") or []
        if ("side2" in sides) == bool(two_sided):
            return int(pn)
        if fallback is None:
            fallback = int(pn)
    return fallback or 1


def build(template_pdf, spec_path, art_pdf, out_path,
          slots=("side1", "bottom", "side2"),
          pms_name="PANTONE Black C", pms_hex="#2C2927",
          item=None, order_id=None, include_press_sheets=True, product=None,
          components=None, hidden_colors=None, placement=None,
          accepted_risks=None, proof_extra=None, mockup_img=None,
          proof_path=None, sides=None, inks=None, caption_names=None):
    """
    Impose `art_pdf` onto `template_pdf`.

    slots     : which imprint locations the job actually prints. Whether the
                proof uses the 1-side or the 2-side guide page follows from
                this.
    hidden_colors : source colours the customer switched off while reducing
                the art to one ink, as #rrggbb strings.
    placement : per slot, how the customer sized and placed the mark —
                {"sc": float, "ox": fraction of zone width,
                 "oy": fraction of zone height, "rot": radians, clockwise}.
                An absent slot falls back to the art filling its zone, which
                is what every job did before placement was carried through.
    proof_extra : the things only the configurator knows — the product's
                catalogue name and the colourways it is offered in.
    mockup_img : the customer's own render, shrunk into the proof's corner.

    Page one is Numo's own proof sheet, drawn here rather than overprinted
    onto the vendor's guide page. The guide page is still built — it is the
    source the flat lay is cropped from, and its die shapes are measured
    geometry — but it is used and discarded, so none of the vendor's
    instruction furniture or branding reaches the customer.
    """
    placement = placement or {}
    spec = json.loads(Path(spec_path).read_text())
    # A spec is calibrated to a die, not to a catalogue number, and refuses to
    # impose artwork using any other product's geometry. Usually that is one
    # product, but the tote ships the same bag in undyed and dyed canvas under
    # two item numbers: same die, same template, same imposition, different
    # price. Such a spec lists every product it covers in "products", and the
    # single "product" key stays as the one it was measured from.
    if product and (spec.get("products") or spec.get("product")):
        allowed = spec.get("products") or [spec["product"]]
        if product not in allowed:
            raise ValueError(
                f"spec {Path(spec_path).name} is calibrated for "
                f"{', '.join(map(repr, allowed))}, not {product!r}. "
                f"Each die needs its own measured spec.")
    slots = [s for s in ALL_SLOTS if s in slots]
    # One artwork per imprint location. `art_pdf` is either a single file used
    # everywhere, or {slot: file} when the customer put different art in
    # different locations. It used to be one file only, so a job that started
    # with the same art everywhere and then replaced Side 2 still imposed the
    # original on Side 2 — the preview and the press file disagreed.
    hidden_rgbs = _hex_list_to_rgb(hidden_colors)
    if isinstance(art_pdf, dict):
        missing = [sl for sl in slots if not art_pdf.get(sl)]
        if missing:
            raise ValueError("No artwork for " + ", ".join(missing))
        _by_file = {}
        arts = {}
        for sl in slots:
            f = str(art_pdf[sl])
            if f not in _by_file:          # same file in several places: measure once
                _by_file[f] = Artwork(f, hidden_rgbs=hidden_rgbs)
            arts[sl] = _by_file[f]
    else:
        _one = Artwork(art_pdf, hidden_rgbs=hidden_rgbs)
        arts = {sl: _one for sl in ALL_SLOTS}

    # A multi-colour job: each ink keeps its PANTONE name as its own
    # Separation on the press sheets, and shows in its own colour on the proof.
    # The art is written twice from the same shapes — once per purpose — so
    # the two can't drift apart.
    screens = None
    arts_press = arts_proof = None
    # One colour: the art goes on its PMS as a named Separation too, its own
    # screen, rather than in registration black. Everything else on the sheet
    # (marks, die, captions' furniture) stays [Registration] so it lands on it.
    # Every colour in the (already one-colour) art is that ink; white is a
    # knockout; colours switched off while reducing stay off.
    one_ink = False
    if not inks and pms_name:
        one_ink = True
        inks = [{"hex": "#000000", "sources": [], "pms": pms_name,
                 "pms_hex": pms_hex or "#000000", "hidden": False}]
        for h in (hidden_colors or []):
            inks.append({"hex": h, "sources": [h], "pms": None, "pms_hex": h, "hidden": True})
    if inks:
        import onecolor
        comps = list(components or [])
        body_c = next((cp for cp in comps if (cp.get("label") or "").lower()
                       not in _NON_BODY_COMPONENTS), None)
        body_rgb0 = _hex_to_rgb01(body_c.get("hex")) if body_c else None
        work = Path(out_path).parent
        # inks is one list for the whole job, or {slot: list} when each
        # location has its own colors (two white logos, one printed red and one
        # blue). Every location is separated with its own list; the press
        # sheets carry the union of their screens.
        by_src, arts_press, arts_proof, screens = {}, {}, {}, []
        for sl in slots:
            src = str(art_pdf[sl]) if isinstance(art_pdf, dict) else str(art_pdf)
            sl_inks = (inks.get(sl) or []) if isinstance(inks, dict) else inks
            key = (src, json.dumps(sl_inks, sort_keys=True))
            if key not in by_src:
                n = len(by_src)
                stem = Path(src).stem
                pp = work / f"{stem}.sep{n}-press.pdf"
                pr = work / f"{stem}.sep{n}-proof.pdf"
                # Traced images: disjoint, trapped inks -> overprint (see separate()).
                got = onecolor.separate(src, sl_inks, pp, "press",
                                        overprint=src.endswith(".traced.pdf"),
                                        white_is_knockout=one_ink)
                for nm in got or []:
                    if nm not in screens:
                        screens.append(nm)
                onecolor.separate(src, sl_inks, pr, "proof",
                                  knockout_rgb=tuple(body_rgb0 or (1, 1, 1)),
                                  white_is_knockout=one_ink)
                by_src[key] = (Artwork(str(pp)), Artwork(str(pr)))
            arts_press[sl], arts_proof[sl] = by_src[key]

    def place(slot_id):
        """How this slot's mark is sized and nudged, with safe defaults."""
        p = placement.get(slot_id) or {}
        try:
            # The configurator sends its rotation as it holds it: radians,
            # clockwise on screen. ReportLab turns counter-clockwise in
            # degrees. (Read as degrees, a quarter turn came out as 1.6°.)
            import math as _m
            return (float(p.get("sc", 1.0) or 1.0),
                    float(p.get("ox", 0.0) or 0.0),
                    float(p.get("oy", 0.0) or 0.0),
                    -_m.degrees(float(p.get("rot", 0.0) or 0.0)))
        except (TypeError, ValueError):
            return 1.0, 0.0, 0.0, 0.0
    # Multi-colour: the ink caption is written one name per ink, each in its
    # own separation, so a screen shows only its own ink's name.
    spot_runs = None
    if inks:
        spot_runs = []
        seen_nm = set()
        for lst in (inks.values() if isinstance(inks, dict) else [inks]):
            for i in lst or []:
                nm = i.get("pms") or i.get("hex")
                if i.get("hidden") or not nm or nm in seen_nm:
                    continue
                seen_nm.add(nm)
                if onecolor.is_white_ink(i):
                    # Prints white; shown light pink on screen (onecolor.WHITE_SPOT_PREVIEW_CMYK).
                    spot = CMYKColorSep(*onecolor.WHITE_SPOT_PREVIEW_CMYK, spotName=nm, density=1)
                else:
                    spot = pms_spot(nm, i.get("pms_hex") or i.get("hex"))
                # A screen shared by several colourways of the same art carries
                # every colourway's PMS for it, comma separated (caption_names).
                spot_runs.append(((caption_names or {}).get(nm) or nm.replace("PANTONE ", ""), spot))
        spot_runs = spot_runs or None
    two_sided = "side2" in slots
    proof_page = _pick_proof_page(spec, two_sided)
    item = item or spec.get("product", "")

    src = PdfReader(str(template_pdf))
    # Where the template prints "SPOT COLOR", print the ink actually chosen.
    captions = find_template_labels(template_pdf, len(src.pages))
    off = spec["offsets"]
    d1, d2 = off["d_side1"], off["d_side2"]
    sw, sh, cd = off["side_w"], off["side_h"], off["circle_d"]

    pages = []
    # What each output page is, in the same order as `pages`. The proof and the
    # press sheets come out of one loop and some template pages are dropped, so
    # the output index is not the template index — and the sheet names are
    # recorded against the template's numbering.
    page_names = []
    # The guide page never joins `pages`; it is held here as the flat lay's
    # source and the imprint sizes measured off it are carried alongside.
    guide_page_obj = None
    art_sizes = []
    proof_pdf = None
    # Which press sheets this job gets. Sheets come in pairs carrying the
    # same art: the "- BTM" one has the half-moon arcs that line up the bottom
    # imprint. A job printing a bottom gets the BTM sheets; a job without one
    # gets their plain partners. A template with no partner of the needed kind
    # (every sheet has arcs, or none do) exports what it has rather than
    # nothing, and says so.
    sheet_note = None
    press_names = {pn: (v.get("artboard") or "") for pn, v in spec["press_pages"].items()}
    is_btm = {pn: bool(re.search(r"-\s*BTM\s*$", nm, re.I)) for pn, nm in press_names.items()}
    want_btm = "bottom" in slots
    # Templates without "- BTM" pairs (the 0799: the bottoms print on sheets of
    # their own, "sides": ["bottom"]) take every sheet; "sides" then decides.
    chosen = ({pn for pn, b in is_btm.items() if b == want_btm} if any(is_btm.values())
              else set(press_names))
    # Sheets that each print one panel (the 9210-02 bank bag: a Front sheet
    # and a Back sheet) say which in "sides"; a job without that side doesn't
    # get the sheet.
    chosen = {pn for pn in chosen
              if not spec["press_pages"][pn].get("sides")
              or set(spec["press_pages"][pn]["sides"]) & set(slots)}
    if not chosen:
        chosen = set(press_names)
        if any(is_btm.values()):
            sheet_note = ("no plain sheets in this template, so the - BTM sheets were used"
                          if not want_btm else
                          "no - BTM sheets in this template, so the plain sheets were used")


    # How many sides this job prints, and whether they match:
    #   "1side"  one side (Side 1 or Side 2 alone)
    #   "2same"  both sides, same art at the same size and place
    #   "2diff"  both sides, different art
    # It picks the layout on machines that have two — the 1080 and 0472 each
    # have a STRYKER laid out for one side and one for two — and it goes on
    # every sheet's name, so the floor knows what they are running.
    has1, has2 = "side1" in slots, "side2" in slots
    sides = sides or ("2diff" if (has1 and has2) else ("1side" if (has1 or has2) else None))
    SIDES_LABEL = {"1side": "1 Side", "2same": "2 Sides Same", "2diff": "2 Sides Different"}
    want_layout = "1side" if sides in (None, "1side") else "2diff"
    by_machine = {}
    for pn in sorted(chosen, key=int):
        pg = spec["press_pages"][pn]
        by_machine.setdefault(pg.get("machine") or _machine_of(press_names[pn]), []).append(pn)
    picked = set()
    for machine, pns in by_machine.items():
        layouts = {pn: spec["press_pages"][pn].get("layout") for pn in pns}
        if len({layouts[pn] for pn in pns}) <= 1:
            picked.update(pns)                 # one layout: every sheet of it
            continue
        hit = [pn for pn in pns if layouts[pn] == want_layout] or pns
        picked.update(hit)
    chosen = picked

    def sheet_label(press):
        base = press.get("artboard") or ""
        tag = SIDES_LABEL.get(sides)
        return f"{base} {tag}".strip() if tag else base

    for pn in range(1, len(src.pages) + 1):
        page = src.pages[pn - 1]
        mb = [float(v) for v in page.MediaBox]
        pw, ph = mb[2] - mb[0], mb[3] - mb[1]

        guide = spec["guide_pages"].get(str(pn))
        press = spec["press_pages"].get(str(pn))

        # Only the matching guide page is kept; the other is dropped so the
        # customer is never handed a proof for a layout they didn't buy.
        if guide and pn != proof_page:
            continue
        if press and str(pn) not in chosen:
            continue
        if press and not include_press_sheets:
            continue
        if not guide and not press:
            pages.append(page)
            page_names.append(None)
            continue

        ov = f"{out_path}.ov{pn}.pdf"
        c = rlcanvas.Canvas(ov, pagesize=(pw, ph))

        if guide:
            # Die cut -> neoprene colour, seam lines -> stitching colour.
            comp_by_label = {(cp.get("label") or "").lower(): cp
                             for cp in (components or [])}
            stitch = comp_by_label.get("stitching")
            # The body is whatever the product is made of, and the client names
            # it after the material — "Neoprene", "Scuba Foam", "Canvas".
            # Matching those by name meant each new material silently produced
            # a proof with the die left unfilled, so match by exclusion: every
            # component is body except the thread.
            body = next((cp for lbl, cp in comp_by_label.items()
                         if lbl not in _NON_BODY_COMPONENTS), None)
            mapping = []
            body_rgb = _hex_to_rgb01(body.get("hex")) if body else None
            stitch_rgb = _hex_to_rgb01(stitch.get("hex")) if stitch else None
            # Strip the instruction-sheet furniture, then rebuild the page as
            # a product preview: die cut filled in the material colour with
            # zig-zag stitching over it.
            # Die first, then the guides.
            #
            # One template draws its die in the same red the others use for the
            # legend swatch, which suppression removes — so with suppression
            # first, the die is already gone by the time fill_die_cut looks for
            # it and the proof shows no product at all. Filling first turns
            # that path into a neoprene-coloured fill, which no guide rule
            # matches, and suppression then clears the furniture around it.
            if body_rgb:
                fill_die_cut(page, body_rgb)
            suppress_guides_deep(page)

            # Some templates stroke the die at the very start of the content
            # stream rather than the end — the tote's does, 4 KB into 65 KB —
            # and everything the template paints afterwards then lands on top
            # of the in-place fill, including its own panel blocks. The proof
            # comes out with a white front panel and a grey back one, which
            # reads as the product having no colour at all.
            #
            # Where the die is a plain rectangle the spec gives it outright and
            # the overlay paints it here, above the template's blocks and below
            # the artwork. That is exact and does not care what order the
            # template writes its stream in. A die that is not a rectangle has
            # no die_fill and keeps fill_die_cut above.
            if body_rgb and spec.get("die_fill"):
                c.saveState()
                c.setFillColor(Color(*body_rgb))
                c.setStrokeColor(Color(*[min(1.0, v * 0.86) for v in body_rgb]))
                c.setLineWidth(0.75)
                for rect in spec["die_fill"]:
                    if isinstance(rect, dict) and rect.get("circle"):
                        c.circle(*rect["circle"], fill=1, stroke=1)
                    else:
                        c.rect(*rect, fill=1, stroke=1)
                # Bands in a component's own colour (the 0799's bias binding).
                for band in spec.get("die_bands") or []:
                    want = (band.get("component") or "").lower()
                    cp = next((x for x in (components or [])
                               if (x.get("label") or "").lower() == want), None)
                    rgb = _hex_to_rgb01(cp.get("hex")) if cp else None
                    if rgb:
                        c.setFillColor(Color(*rgb))
                        c.rect(*band["rect"], fill=1, stroke=0)
                        c.setFillColor(Color(*body_rgb))
                # The fold the bag is sewn along, drawn so the proof reads as
                # one flat body rather than two loose panels.
                for y in spec.get("die_folds") or []:
                    c.line(spec["die_fill"][0][0], y,
                           spec["die_fill"][0][0] + spec["die_fill"][0][2], y)
                c.restoreState()

            # The ink in its exact screen colour, not as a CMYK-alternate
            # separation. This page is never shipped — it is rendered once to
            # make the proof's flat lay — and rendering a separation goes
            # through its rough CMYK alternate, which a renderer then converts
            # the way a press would print it: saturated inks come back muddy
            # (347 C's #009A44 rendered as #006D61, Black C as a warm brown),
            # so the digital proof disagreed with the virtual beside it.
            ink_rgb = _hex_to_rgb01(pms_hex) or (0, 0, 0)
            c.setFillColor(Color(*ink_rgb))
            c.setStrokeColor(Color(*ink_rgb))
            zones = guide["zones"]
            for name in slots:
                z = zones.get(name)
                if not z:
                    continue
                rot = (spec.get("side2_turn", 180) % 360) if name == "side2" else 0
                sc, ox, oy, arot = place(name)
                zw_, zh_ = nominal_zone_pts(product, name, z["w"], z["h"])
                # The bottom imprint is a circle, not a square.
                if arts_proof:
                    arts_proof[name].draw(c, z["cx"], z["cy"], zw_, zh_, rot,
                                          scale_mult=sc, circular=(name == "bottom"),
                                          off_x=ox, off_y=oy, art_rot=arot, paint="keep")
                else:
                    arts[name].draw(c, z["cx"], z["cy"], zw_, zh_, rot,
                             scale_mult=sc, circular=(name == "bottom"),
                             off_x=ox, off_y=oy, art_rot=arot,
                             paint=(tuple(ink_rgb), tuple(body_rgb or (1, 1, 1))))
            # Cover the legend and the step-1 instruction, which described
            # elements this proof no longer shows.
            #
            # Per product, because the guides do not share a layout. They look
            # alike, but the blocks sit at different heights and the pages are
            # not even the same size, so one rectangle cannot serve both:
            # the Kolder Kaddy's values land on the Pocket Coolie low enough to
            # bury its ART REQUIREMENTS box and clip the top off its notes
            # panel, while leaving the step-1 text they were meant to hide in
            # plain view. Re-anchoring to the top of the page does not fix it
            # either — the offset between the two layouts is not the page
            # height difference.
            #
            # Measure the block positions when adding a product and record them
            # here; the default is the Kolder Kaddy's, which has been to press.
            cover = spec.get("proof_cover") or [16, 228, 462, 418]
            c.setFillColor(Color(1, 1, 1))
            c.rect(*cover, fill=1, stroke=0)

            # Only products that are actually sewn get stitching drawn. The
            # seam positions in SEAM_BANDS/SEAM_X are calibrated to the Kolder
            # Kaddy; drawing them on a bonded product would put thread on a
            # proof for a product that has none, in places its die does not
            # even have seams.
            if stitch_rgb and PRESS_TEMPLATES.get(product or "", {}).get("stitched", True):
                # Seam positions come from the spec where the product has them
                # measured. The constants are the Kolder Kaddy's: on a slim can
                # they would run thread down the middle of the panel rather
                # than along its edges.
                seams = spec.get("seams") or {}
                if seams.get("style") == "straight":
                    # A straight running stitch (the key fob's ends), not zig-zag.
                    draw_straight_seams(c, stitch.get("hex"), seams.get("bands") or [],
                                        seams.get("xs") or [])
                else:
                    draw_zigzag_seams(c, stitch.get("hex"),
                                      bands=seams.get("bands") or SEAM_BANDS,
                                      xs=seams.get("xs") or SEAM_X)
            # Fold lines (the key fob folds in half): a soft crease in the body colour.
            if body_rgb and spec.get("fold_lines"):
                c.saveState()
                c.setStrokeColor(Color(*[v * 0.8 for v in body_rgb]))
                c.setLineWidth(0.8)
                for x0_, y0_, x1_, y1_ in spec["fold_lines"]:
                    c.line(x0_, y0_, x1_, y1_)
                c.restoreState()

            rows = []
            if order_id:
                rows.append(("ORDER", order_id, None))
            rows.append(("ITEM", item, None))
            rows.append(("SCREEN PRINT INK", pms_name or "—", pms_hex))
            # Product options as configured — neoprene, stitching, and whatever
            # else the product carries.
            for comp in (components or []):
                rows.append((comp.get("label", "").upper(),
                             comp.get("name", "—"), comp.get("hex")))
            # The size this customer's art actually prints at in each location,
            # not the maximum imprint area it was fitted into. The area is a
            # property of the product and is the same on every job; what the
            # customer and the press both need is the size of this imprint.
            for sl in ALL_SLOTS:
                if sl not in slots:
                    continue
                z = guide["zones"].get(sl)
                if not z:
                    continue
                label = {"side1": "SIDE 1 IMPRINT", "side2": "SIDE 2 IMPRINT",
                         "bottom": "BOTTOM IMPRINT"}[sl]
                aw, ah = arts[sl].fitted_size(*nominal_zone_pts(product, sl, z["w"], z["h"]),
                                         scale_mult=place(sl)[0],
                                         circular=(sl == "bottom"), art_rot=place(sl)[3])
                rows.append((label, f'{aw/72:.2f}" W x {ah/72:.2f}" H', None))
                art_sizes.append({
                    "label": label.title().replace(" Imprint", ""),
                    "size": f'{aw/72:.2f}" W x {ah/72:.2f}" H'})
            rows.append(("ARTWORK", "One-color vector", None))
            rows.append(("GENERATED", date.today().isoformat(), None))
            # Placed per product, for the same reason proof_cover is: the
            # guide pages are not even the same size, so one set of
            # coordinates cannot serve them all. The default is the Kolder
            # Kaddy's, which has been to press.
            ip = spec.get("info_panel") or {}
            bottom = _info_panel(c, ip.get("x", 46), ip.get("y_top", 600),
                                 ip.get("w", 430), rows,
                                 scale=ip.get("scale", 1.5))
            # What the customer was warned about and chose to print anyway.
            #
            # On the proof rather than only in the configurator, because by
            # the time this file reaches the floor the conversation that
            # produced it is over. Without it the artist checking the job
            # finds the thin stroke themselves, cannot tell whether anyone
            # knows, and either prints something that will break up or stops
            # a job the customer already accepted.
            _accepted_risks_note(c, ip.get("x", 46), bottom - 14 * ip.get("scale", 1.5),
                                 ip.get("w", 430), accepted_risks,
                                 scale=ip.get("scale", 1.5))
        else:
            # The crosshairs have done their job in the spec; they must not
            # reach a screen. Removed from the page rather than painted over,
            # so nothing is left underneath for a separation to pick up.
            drop_registration_marks(page)
            if pn in captions:
                _stamp_caption(c, captions[pn].get("spot"), ph, pms_name,
                               runs=spot_runs)
                # The sales order number, over the vendor's "NSO NUMBER"
                # placeholder. Left alone when the job has no number yet, so
                # the sheet still says what the artist should write in.
                _stamp_caption(c, captions[pn].get("nso"), ph, order_id)
                # The material, burned into the screen beside the order number
                # (the 9210-02 bank bag: "EV" expanded vinyl, "LN" laminated
                # nylon — one template, so production can't tell from the
                # sheet which goods to pull).
                _stamp_material_tag(c, captions[pn].get("nso"), ph, product)
                _stamp_sheet_name(c, press.get("name_at"),
                                  sheet_label(press))
            c.setFillColor(registration_black())
            c.setStrokeColor(registration_black())
            # Which way a rotated position turns. The koozie sheets turn
            # clockwise, which is what -90 is and what every spec without this
            # key keeps getting. The tote's sheet is the first to turn the
            # other way: its only orientation cue is the "…- Front / NSO
            # NUMBER / SPOT COLOR" label the vendor set along the left edge,
            # and that label reads bottom-to-top, so the art is set to read
            # the same way up as the sheet that carries it.
            #
            # This is a half-and-half call that the template cannot settle —
            # the sheet is symmetric about both crosshairs — so it is a spec
            # value to flip rather than a constant to hunt for, and it is one
            # of the two things to confirm on the first printed sheet.
            rot_deg = press.get("rotation", -90)
            # One side alone prints where the template says one side goes (the
            # 0799: the panel's centre, opposite the seam) — d_one — instead of
            # at its two-side spot.
            one_side = ("d_one" in off) and (("side1" in slots) != ("side2" in slots))
            pd1 = off["d_one"] if one_side else d1
            pd2 = off["d_one"] if one_side else d2
            for p in press["positions"]:
                cx, cy = p["cx"], p["cy"]
                # A position may carry its own turn and its own Side 1 → Side 2
                # direction (the 0799's panels lie on their side, alternately
                # one way and the other).
                if p.get("axis"):
                    ux, uy = p["axis"]
                else:
                    ux, uy = (0, 1) if p["vertical"] else (ROTATED_SIDE1_DIR, 0)
                base = p["rot"] if "rot" in p else (0 if p["vertical"] else rot_deg)
                targets = {
                    "side1":  ((cx + ux * pd1, cy + uy * pd1), base,       (sw, sh)),
                    "bottom": ((cx, cy),                     base,       (cd, cd)),
                    # Side 2 is printed head-down on dies that fold back on
                    # themselves (koozies); a strip that folds over its middle
                    # (the key fob) prints both halves the same way up.
                    "side2":  ((cx + ux * pd2, cy + uy * pd2), base + spec.get("side2_turn", 180), (sw, sh)),
                }
                only = press.get("sides")
                for name in slots:
                    if only and name not in only:
                        continue
                    (px, py), rot, (zw, zh) = targets[name]
                    zw, zh = nominal_zone_pts(product, name, zw, zh)
                    if 0 <= px <= pw and 0 <= py <= ph:
                        sc, ox, oy, arot = place(name)
                        # The bottom position prints inside the die circle.
                        (arts_press or arts)[name].draw(c, px, py, zw, zh, rot,
                                 scale_mult=sc, circular=(name == "bottom"),
                                 off_x=ox, off_y=oy, art_rot=arot,
                                 # black = ink, white = hole; the registration
                                 # pass makes them 100 % and 0 % of the screen
                                 paint=("keep" if arts_press else ((0.0, 0.0, 0.0), (1.0, 1.0, 1.0))))
        c.save()
        PageMerge(page).add(PdfReader(ov).pages[0]).render()
        Path(ov).unlink(missing_ok=True)
        if guide:
            # Held back, not shipped. Numo's own proof replaces it below and
            # this page is only the shape the flat lay is cut from.
            guide_page_obj = page
            continue
        pages.append(page)
        # Numbered by the TEMPLATE's page, not this file's. The export keeps
        # only one of the two guide pages, so output indices shift by one on a
        # 1-side job and not on a 2-side one — and the floor's sheet numbers
        # would move with them. The template's numbering is fixed, and is what
        # Numo's own internal files are numbered by.
        page_names.append({"page": pn,
                           "name": sheet_label(press) or None})

    # ── Page one: Numo's proof ──────────────────────────────────────────────
    flat_png = None
    two_png = None
    if guide_page_obj is not None:
        tmp_guide = Path(f"{out_path}.guide.pdf")
        tmp_flat = Path(f"{out_path}.2X2.png")
        try:
            gw = PdfWriter(str(tmp_guide), trailer=None)
            gw.addpage(guide_page_obj)
            gw.write()
            _bc = next((cp for cp in (components or [])
                        if (cp.get("label") or "").lower() not in _NON_BODY_COMPONENTS), None)
            _bp = _body_pattern_path(_bc)
            try:
                from products import PRODUCTS as _P
                _por = (_P.get(product or "") or {}).get("porous")
            except Exception:
                _por = None
            flat_png = build_flat_proof(tmp_guide, spec, tmp_flat,
                                        proof_page=proof_page,
                                        body_pattern=(_bc["hex"], _bp, _por) if _bp else None,
                                        product=product)
            # The 2X2 for production shows both sides even when one is blank.
            try:
                two_png = build_flat_proof(tmp_guide, spec, Path(f"{out_path}.2X2all.png"),
                                           proof_page=proof_page,
                                           body_pattern=(_bc["hex"], _bp, _por) if _bp else None, show_all=True,
                                           product=product)
            except Exception as e:
                print(f"⚠️ 2X2 lay (both sides) could not be rendered: {e}")
        except Exception as e:
            print(f"⚠️ Flat lay could not be rendered: {e}")
        finally:
            tmp_guide.unlink(missing_ok=True)

        extra = proof_extra or {}
        comps = list(components or [])
        body_comp = next((cp for cp in comps
                          if (cp.get("label") or "").lower()
                          not in _NON_BODY_COMPONENTS), None)
        meta = {
            "order_id": order_id,
            "item": item,
            "label": extra.get("label"),
            "customer": extra.get("customer"),
            "artist": extra.get("artist"),
            "artist_note": extra.get("artist_note"),
            "revision": extra.get("revision"),
            "quantity": extra.get("quantity"),
            "item_color": ({"label": body_comp.get("label"),
                            "name": body_comp.get("name"),
                            "hex": body_comp.get("hex")} if body_comp else {}),
            "components_extra": [cp for cp in comps if cp is not body_comp],
            "imprint": {"name": pms_name, "hex": pms_hex},
            "imprint_inks": _imprint_inks(inks),
            "art_sizes": art_sizes,
            "accepted_risks": accepted_risks,
            "product_colors": extra.get("product_colors"),
            "footer": extra.get("footer"),
        }
        # A file of its own, not page one of the press document.
        #
        # They are read by different people for different reasons: the proof
        # is what the customer approves, the press file is what the floor
        # burns screens from. Bound together, the artist scrolls past a
        # customer document to reach their first screen and the salesperson
        # sends a press file to a customer to show them one page of it.
        try:
            proof_pdf = build_proof_page(proof_path or f"{out_path}.proof.pdf",
                                         meta, flat_png=flat_png,
                                         mockup_img=mockup_img)
        except Exception as e:
            print(f"⚠️ Proof page could not be built: {e}")

    for page in pages:
        strip_illustrator_private_data(page)
    writer = PdfWriter(str(out_path), trailer=None)
    writer.addpages(pages)
    _set_page_labels(writer, page_names)
    writer.write()
    # One screen, one colour: nothing leaves here in anything but /All.
    reg = force_registration(out_path, keep_spots=screens)
    if reg["problems"]:
        raise ValueError("Press file has content that cannot be forced to "
                         "registration black: " + ", ".join(reg["problems"]))
    # Opens clean in Illustrator: no placeholder text or cover boxes under the
    # captions, no empty guide groups, no clip group around every placement.
    # Kept only if the sheets render the same (press_tidy).
    try:
        import press_tidy
        t = press_tidy.tidy(out_path)
        if t.get("skipped"):
            print(f"⚠️ press file not tidied: {t['skipped']}")
    except Exception as e:
        print(f"⚠️ press file not tidied: {e}")
    return dict(out=str(out_path), proof_page=proof_page,
                two_sided=two_sided, slots=slots, pages=len(pages),
                page_names=page_names, flat_proof=(two_png or flat_png),
                sheet_note=sheet_note, screens=screens,
                proof=proof_pdf)


def build_for_job(product_id, art_path, slots, pms_name, pms_hex,
                  out_path, order_id=None, item=None, components=None,
                  hidden_colors=None, placement=None, accepted_risks=None,
                  proof_extra=None, mockup_img=None, proof_path=None,
                  sides=None, inks=None, include_press_sheets=True, caption_names=None):
    """
    Build the press file for a configurator job.

    Returns None when the product has no measured template, so callers can
    simply skip the press file rather than special-casing each product.
    """
    if not has_press_template(product_id):
        return None
    cfg = PRESS_TEMPLATES[product_id]
    work = Path(out_path).parent
    if isinstance(art_path, dict):
        # Convert each distinct file once; locations sharing art share the PDF.
        conv = {}
        pdf_art = {}
        for sl, ap in art_path.items():
            if ap not in conv:
                conv[ap] = art_as_pdf(ap, work_dir=work)
            pdf_art[sl] = conv[ap]
    else:
        pdf_art = art_as_pdf(art_path, work_dir=work)
    return build(cfg["template"], cfg["spec"], pdf_art, out_path,
                 slots=slots, pms_name=pms_name, pms_hex=pms_hex,
                 item=item or product_id, order_id=order_id,
                 product=product_id, components=components,
                 hidden_colors=hidden_colors, placement=placement,
                 accepted_risks=accepted_risks, proof_extra=proof_extra,
                 mockup_img=mockup_img, proof_path=proof_path,
                 sides=sides, inks=inks, include_press_sheets=include_press_sheets,
                 caption_names=caption_names)


if __name__ == "__main__":
    import sys
    slots = sys.argv[1].split(",") if len(sys.argv) > 1 else ["side1", "bottom", "side2"]
    pms = sys.argv[2] if len(sys.argv) > 2 else "PANTONE 286 C"
    hexv = sys.argv[3] if len(sys.argv) > 3 else "#0033A0"
    out = sys.argv[4] if len(sys.argv) > 4 else "/tmp/production.pdf"
    art = sys.argv[5] if len(sys.argv) > 5 else "/tmp/numo-logo.pdf"
    print(build_for_job("0070-3m-24HR-1c", art, slots, pms, hexv, out,
                        order_id="DEMO-1001",
                        components=[{"label": "Neoprene", "name": "Red", "hex": "#AE0D2E"},
                                    {"label": "Stitching", "name": "Yellow", "hex": "#FEDD00"}]))


# ─────────────────────────────────────────────────────────────────────────────
# Flat proof
# ─────────────────────────────────────────────────────────────────────────────

FLAT_BG = (255, 255, 255)

# A tote's handles, as the flat proof draws them: two tabs rising from the top
# edge of each panel, in the body's own colour. Simplified deliberately — the
# real handles are sewn loops, and drawing them as loops would put a shape on
# the proof that the die does not have and that no measurement backs. The tabs
# say "this edge is the top, and the handles attach about here", which is all
# the proof needs them to say.
#
# Proportions are of the panel, so they hold at any crop size or render dpi.
FLAT_HANDLE_INSET  = 0.19    # from each side edge, as a fraction of panel width
FLAT_HANDLE_WIDTH  = 0.111   # fraction of panel width
FLAT_HANDLE_HEIGHT = 0.114   # fraction of panel height


def _flat_body_color(part):
    """
    The panel's own colour, read off the panel rather than passed in.

    Taken from a patch inside the top edge: inside, because the crop carries
    the thin die outline at its boundary, and the top edge because that is the
    hem — the one band of every panel that no imprint can reach, whatever the
    customer uploaded. The most common colour in the patch wins, so a stray
    speck of ink cannot drag the handles off the body colour.
    """
    from collections import Counter
    w, h = part.size
    patch = part.crop((int(w * 0.04), int(h * 0.02),
                       int(w * 0.96), int(h * 0.06)))
    px = list(patch.getdata())
    return Counter(px).most_common(1)[0][0] if px else FLAT_BG


def _with_handles(part):
    """Grow a panel upward and draw its two handle tabs into the new space."""
    from PIL import Image, ImageDraw
    w, h = part.size
    th = max(1, int(round(h * FLAT_HANDLE_HEIGHT)))
    tw = max(1, int(round(w * FLAT_HANDLE_WIDTH)))
    inset = int(round(w * FLAT_HANDLE_INSET))
    out = Image.new("RGB", (w, h + th), FLAT_BG)
    out.paste(part, (0, th))
    d = ImageDraw.Draw(out)
    body = _flat_body_color(part)
    for x in (inset, w - inset - tw):
        d.rectangle((x, 0, x + tw - 1, th - 1), fill=body)
    return out
FLAT_LABEL = (140, 140, 140)


def _flat_label_font(px):
    """A light, widely-spaced face for the Side 1 / Side 2 / Bottom captions."""
    from PIL import ImageFont
    for name in ("DejaVuSans.ttf", "LiberationSans-Regular.ttf", "Arial.ttf"):
        try:
            return ImageFont.truetype(name, px)
        except Exception:
            continue
    return ImageFont.load_default()


def _flat_strip(img, s, page_h, regions, shown, out_png, size, product, dpi):
    """
    The flat lay for a strip that folds over its middle (the key fob): Side 1
    is the left half, Side 2 the right, both upright. They're long and short,
    so they stack one above the other rather than sitting side by side.
    """
    from PIL import Image, ImageDraw
    x0, x1 = regions["x"]
    y0, y1 = regions["y"]
    xf = regions["fold_x"]

    def crop(a, b):
        return img.crop((int(a * s), int((page_h - y1) * s), int(b * s), int((page_h - y0) * s)))
    pieces = [("Side 1", crop(x0, xf))]
    if "side2" in shown:
        pieces.append(("Side 2", paste_sewn_on(crop(xf, x1), "side2", dpi, product)))
    canvas = Image.new("RGB", (size, size), FLAT_BG)
    d = ImageDraw.Draw(canvas)
    font = _flat_label_font(max(12, size // 46))
    margin, gap, label_gap = int(size * 0.06), int(size * 0.06), int(size * 0.018)
    cap_h = font.size + label_gap
    pw = size - 2 * margin
    k = pw / pieces[0][1].width
    ph = int(pieces[0][1].height * k)
    total = len(pieces) * (ph + cap_h) + gap * (len(pieces) - 1)
    y = max(margin, (size - total) // 2)
    for label, part in pieces:
        canvas.paste(part.resize((pw, ph), Image.LANCZOS), (margin, y))
        tw = d.textlength(label, font=font)
        d.text((margin + (pw - tw) / 2, y + ph + label_gap), label, font=font, fill=FLAT_LABEL)
        y += ph + cap_h + gap
    canvas.save(str(out_png), "PNG", optimize=True)
    return str(out_png)


def build_flat_proof(proof_pdf, spec, out_png, proof_page=1, size=1600, dpi=220,
                     body_pattern=None, show_all=False, product=None):
    """
    A square proof showing the three imprints laid out flat, side by side.

    The shapes are cropped from the rendered proof page rather than redrawn.
    The die outline, the material fill and the stitching are already correct
    there, and every one of them is geometry that was measured once — drawing
    them again from the same numbers would be a second approximation that can
    drift from the first.

    Side 2 is rotated upright. On the die it is printed head-down, because the
    panel folds back on itself, but this proof is for a customer judging their
    artwork rather than for the press.
    """
    from PIL import Image, ImageDraw
    from pdf2image import convert_from_path

    regions = (spec.get("die_regions") or {}).get(str(proof_page))
    if not regions:
        return None
    guide = (spec.get("guide_pages") or {}).get(str(proof_page)) or {}
    zones = guide.get("zones") or {}
    sides = guide.get("sides") or ["side1"]

    page = PdfReader(str(proof_pdf)).pages[0]
    mb = [float(v) for v in page.MediaBox]
    page_h = mb[3] - mb[1]
    img = convert_from_path(str(proof_pdf), dpi=dpi, first_page=1, last_page=1)[0].convert("RGB")
    s = dpi / 72.0

    # A printed body (camo): the die was filled in the pattern's average color,
    # so swap that for the pattern, about one tile across a panel.
    if body_pattern:
        try:
            _x = regions["x"]
            por = body_pattern[2] if len(body_pattern) > 2 else None
            tile_px = (float(_x[1]) - float(_x[0])) * s * 1.3
            if por and por.get("pattern_ppi"):
                # The weave at its real size: holes the size they are.
                from PIL import Image as _I
                tile_px = _I.open(body_pattern[1]).width / float(por["pattern_ppi"]) * 72 * s
            img = _fill_body_pattern(img, body_pattern[0], body_pattern[1], tile_px,
                                     porous_inset_px=(25 * s) if por else None,
                                     porous_strength=float((por or {}).get("texture_strength", 1.0)))
        except Exception as e:
            print(f"⚠️ Body pattern not applied to the flat lay: {e}")

    def crop(x0, x1, y_lo, y_hi, rotate=False):
        box = (int(x0 * s), int((page_h - y_hi) * s), int(x1 * s), int((page_h - y_lo) * s))
        part = img.crop(box)
        return part.rotate(180) if rotate else part

    flat = spec.get("flat_proof") or {}
    shown = set(sides) | set(flat.get("always_show") or [])
    if show_all:
        shown |= {"side1", "side2"}       # the 2X2: both sides, printed or not
    try:                                  # a side with something sewn on is shown too (MMKK magnet)
        from products import PRODUCTS as _P
        shown |= {o.get("slot") for o in ((_P.get(product or "") or {}).get("sewn_on") or [])}
    except Exception:
        pass

    # Panels side by side on the guide (the 9210-02 bank bag's Front and
    # Back): each cropped from its own rectangle, upright, no bottom disc.
    if regions.get("rects"):
        pieces = [(r["label"], crop(r["x0"], r["x1"], r["y0"], r["y1"]))
                  for r in regions["rects"] if r["slot"] in shown and not r.get("circle")]
        # A round piece (the 0799's bottom) goes under the panels as the disc.
        bottom = None
        for r in regions["rects"]:
            if r.get("circle") and r["slot"] in shown:
                part = crop(r["x0"], r["x1"], r["y0"], r["y1"])
                from PIL import ImageDraw as _ID
                mask = Image.new("L", part.size, 0)
                _ID.Draw(mask).ellipse((0, 0, part.size[0] - 1, part.size[1] - 1), fill=255)
                bottom = Image.new("RGB", part.size, FLAT_BG)
                bottom.paste(part, (0, 0), mask)
    else:
        x0, x1 = regions["x"]
        panels = regions["panels"]
        cd = float((spec.get("offsets") or {}).get("circle_d") or 0)
        bz = zones.get("bottom") or {}
        bcx = float(bz.get("cx") or (x0 + x1) / 2)
        bcy = float(regions.get("circle_cy") or bz.get("cy") or 0)

        # Panels run to the circle, not to where they stop being full width. The
        # die narrows into a tab between the two, and a crop that ends at the last
        # full-width row cuts it off — the panels come out as plain rectangles and
        # the proof stops looking like the product.
        #
        # Only where there is a circle to run to. A flat product has no bottom
        # disc and records circle_d as 0, which puts c_top at 0 — and min() then
        # extends Side 1 from its own edge all the way to the foot of the page,
        # so the proof comes out as one panel of artwork above a tall blank
        # rectangle of everything underneath it.
        # Panels the proof shows whether or not this job prints them. A tote has a
        # back whichever imprints were bought, and a proof that shows only the
        # printed front reads as half a bag rather than as a bag with one side
        # blank. Which sides carry ART is still `sides`, and is decided upstream —
        # this only widens what gets drawn.
        if flat.get("layout") == "strip":
            return _flat_strip(img, s, page_h, regions, shown, out_png, size, product, dpi)

        c_top, c_bot = bcy + cd / 2, bcy - cd / 2
        lo1 = min(panels[0][0], c_top) if cd else panels[0][0]
        pieces = [("Side 1", crop(x0, x1, lo1, panels[0][1]))]
        if "side2" in shown and len(panels) > 1:
            hi2 = max(panels[1][1], c_bot) if cd else panels[1][1]
            # Rotated upright: on the die the back panel is printed head-down,
            # because it folds back on itself.
            pieces.append(("Side 2", paste_sewn_on(crop(x0, x1, panels[1][0], hi2, rotate=True),
                                                   "side2", dpi, product)))

        # Handles go on after the rotation, so they rise from what is now the top
        # of each panel rather than from the fold.
        if flat.get("handles"):
            pieces = [(label, _with_handles(part)) for label, part in pieces]

        bottom = crop(bcx - cd / 2, bcx + cd / 2, c_bot, c_top) if cd else None
        if bottom is not None:
            # Masked to a circle. The square crop carries the corners where the
            # tabs meet the disc, which read as a rounded square rather than the
            # round bottom the product actually has.
            from PIL import ImageDraw as _ID
            mask = Image.new("L", bottom.size, 0)
            _ID.Draw(mask).ellipse((0, 0, bottom.size[0] - 1, bottom.size[1] - 1), fill=255)
            disc = Image.new("RGB", bottom.size, FLAT_BG)
            disc.paste(bottom, (0, 0), mask)
            bottom = disc


    # ── compose ──────────────────────────────────────────────────────────────
    canvas = Image.new("RGB", (size, size), FLAT_BG)
    d = ImageDraw.Draw(canvas)
    font = _flat_label_font(max(12, size // 46))
    margin = int(size * 0.045)
    gap = int(size * 0.035)
    label_gap = int(size * 0.018)

    n = len(pieces)
    avail_w = size - 2 * margin - (gap * (n - 1))
    cell_w = avail_w / n
    # Panels get the top ~62% of the square; the circle and captions take the
    # rest. With no circle to place there is nothing below to balance them, so
    # they take more of the square and sit in the middle of it rather than
    # crowding the top edge above a block of empty white.
    cap_h = font.size + label_gap
    panel_h_max = size * (0.60 if bottom is not None else 0.78)
    scale = min(cell_w / pieces[0][1].width, panel_h_max / pieces[0][1].height)
    pw, ph = int(pieces[0][1].width * scale), int(pieces[0][1].height * scale)

    total_w = pw * n + gap * (n - 1)
    x = (size - total_w) // 2
    top = margin if bottom is not None else max(margin, (size - ph - cap_h) // 2)
    for label, part in pieces:
        canvas.paste(part.resize((pw, ph), Image.LANCZOS), (x, top))
        tw = d.textlength(label, font=font)
        d.text((x + (pw - tw) / 2, top + ph + label_gap), label, font=font, fill=FLAT_LABEL)
        x += pw + gap

    if bottom is not None:
        room = size - (top + ph + cap_h + label_gap) - margin
        cd_px = int(min(room - cap_h - label_gap, size * 0.28))
        if cd_px > 20:
            b = bottom.resize((cd_px, cd_px), Image.LANCZOS)
            bx = (size - cd_px) // 2
            by = top + ph + cap_h + label_gap
            canvas.paste(b, (bx, by))
            tw = d.textlength("Bottom", font=font)
            d.text(((size - tw) / 2, by + cd_px + label_gap), "Bottom", font=font, fill=FLAT_LABEL)

    canvas.save(str(out_png), "PNG", optimize=True)
    return str(out_png)
