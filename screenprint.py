"""
screenprint.py — artwork validation for the This Is Fast / -3M one-color
screen-print workflow.

The goal is to catch, at upload time, the artwork problems that would otherwise
reach the art department and require a manual rebuild:

    * raster artwork submitted for a screen-print job
    * "vector" files that are really just a JPG in a PDF/AI wrapper
    * artwork sitting on an opaque white/colored background rectangle
    * multi-color artwork submitted for a one-color process

Design rule: only enforce what can be detected reliably. Anything ambiguous is
returned as a warning (shown to the customer, does not block the upload) rather
than an error. Requirements that cannot be measured reliably — 12 pt minimum
type, >1 pt strokes — are communicated in the UI instead of guessed at here.

Only stdlib + Pillow + pdfrw are used, all already project dependencies.
"""

from pathlib import Path
import re
import xml.etree.ElementTree as ET

from PIL import Image

# ── tuning ──────────────────────────────────────────────────────────────────
# Flip to False if multi-color detection ever rejects production-ready art in
# the field; the finding then downgrades to a warning instead of a hard block.
BLOCK_MULTICOLOR = True

# A color cluster must cover at least this share of the artwork's solid pixels
# before it counts as a real ink (filters anti-aliasing and stray artifacts).
MIN_CLUSTER_SHARE = 0.015

# Max per-channel distance for two sampled colors to be treated as one ink.
CLUSTER_DISTANCE = 40

# Alpha at or above this is a "solid" pixel — edge anti-aliasing is excluded.
SOLID_ALPHA = 200

# Artwork whose pixels are this opaque across the whole canvas is treated as
# sitting on a background rather than being genuinely full-bleed.
BACKGROUND_COVERAGE = 0.97

# ── multi-color spot jobs ───────────────────────────────────────────────────
# The press runs at most this many spot screens. This is a physical limit of
# the printing method, not a preference — art needing more than this cannot be
# produced as drawn.
MAX_SPOT_INKS = 5

# One-color products used to refuse multi-color artwork outright. With this on,
# the upload is accepted instead and the customer is handed a tool to reduce it
# to a single ink, behind a warning that recoloring in a vector program first is
# the safer route. Set False to go back to refusing it at upload.
ALLOW_MULTICOLOR_REDUCTION = True

# Two detected inks this close in CIEDE2000 are the same ink as far as the
# press is concerned, so art that exceeds MAX_SPOT_INKS only because of
# near-duplicate colors (tints, anti-aliasing survivors, two almost-identical
# blues) is merged down automatically instead of being flagged. Raise this to
# merge more aggressively, lower it to flag more art for human review.
#
# ~12 is about where two solids stop reading as different colors side by side.
# Beyond that the merge starts changing how the artwork actually looks.
MERGE_DELTA_E = 12.0

RASTER_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".gif", ".tiff", ".tif", ".webp", ".heic"}
VECTOR_EXTS = {".svg", ".pdf", ".ai", ".eps"}


class ArtworkReport:
    """Outcome of validating one uploaded file."""

    def __init__(self):
        self.errors = []      # blocking — upload is refused
        self.warnings = []    # informational — upload proceeds
        self.facts = {}       # detected properties, for logging / job record

    def fail(self, code, message, detail=None):
        self.errors.append({"code": code, "message": message, "detail": detail or ""})

    def warn(self, code, message, detail=None):
        self.warnings.append({"code": code, "message": message, "detail": detail or ""})

    @property
    def ok(self):
        return not self.errors

    def as_dict(self):
        return {
            "ok": self.ok,
            "errors": self.errors,
            "warnings": self.warnings,
            "facts": self.facts,
        }


# ─────────────────────────────────────────────────────────────────────────────
# File-type gate
# ─────────────────────────────────────────────────────────────────────────────

def check_extension(filename, report):
    """Reject raster formats outright. Returns the lowercased extension."""
    ext = Path(filename).suffix.lower()

    if ext in RASTER_EXTS:
        report.fail(
            "raster_file",
            "Artwork cannot be uploaded because this product requires one-color "
            "vector artwork. Please upload compatible vector artwork and try again.",
            f"{ext.upper().lstrip('.')} is a pixel-based format. Accepted vector "
            f"formats: AI, EPS, PDF, SVG.",
        )
    elif ext not in VECTOR_EXTS:
        report.fail(
            "unsupported_file",
            "Artwork cannot be uploaded because this product requires one-color "
            "vector artwork. Please upload compatible vector artwork and try again.",
            f"'{ext or 'this file type'}' is not supported. Accepted vector "
            f"formats: AI, EPS, PDF, SVG.",
        )
    return ext


# ─────────────────────────────────────────────────────────────────────────────
# SVG inspection
# ─────────────────────────────────────────────────────────────────────────────

_SVG_SHAPES = {
    "path", "rect", "circle", "ellipse", "polygon", "polyline", "line", "text", "use",
}


def _strip_ns(tag):
    return tag.split("}", 1)[-1] if "}" in tag else tag


def inspect_svg(path, report):
    """Look for embedded rasters and real vector geometry inside an SVG."""
    try:
        tree = ET.parse(str(path))
    except Exception as e:
        report.warn("svg_unreadable", "Artwork could not be fully inspected.", str(e))
        return

    root = tree.getroot()
    shape_count = 0
    embedded_images = 0

    for el in root.iter():
        tag = _strip_ns(el.tag)
        if tag == "image":
            embedded_images += 1
        elif tag in _SVG_SHAPES:
            shape_count += 1

    report.facts["svg_shapes"] = shape_count
    report.facts["svg_embedded_images"] = embedded_images

    if embedded_images and shape_count == 0:
        report.fail(
            "embedded_raster",
            "Artwork cannot be uploaded because this file contains a placed image "
            "rather than vector artwork. Please upload true one-color vector "
            "artwork and try again.",
            "The SVG contains only an embedded image, not vector paths.",
        )
    elif embedded_images:
        report.fail(
            "embedded_raster_mixed",
            "Artwork cannot be uploaded because it contains a placed image. "
            "Screen-print artwork must be entirely vector — please remove or "
            "recreate the placed image as vector artwork.",
            f"Found {embedded_images} embedded image(s) alongside vector artwork.",
        )
    elif shape_count == 0:
        report.fail(
            "no_vector_geometry",
            "Artwork cannot be uploaded because no vector artwork was found in "
            "this file. Please upload compatible vector artwork and try again.",
            "No drawable vector elements were found in the SVG.",
        )


# ─────────────────────────────────────────────────────────────────────────────
# PDF / AI inspection
# ─────────────────────────────────────────────────────────────────────────────

def inspect_pdf(path, report):
    """
    Detect PDF/AI files whose page content is a single placed raster image.

    Modern .ai files are PDF-compatible, so the same inspection covers both.
    """
    try:
        import logging
        from pdfrw import PdfReader
        # pdfrw logs a warning for every filter chain it can't decompress; that
        # is expected here and would otherwise flood the production logs.
        logging.getLogger("pdfrw").setLevel(logging.ERROR)
    except Exception:
        return  # pdfrw unavailable — the pixel-level checks still apply

    try:
        # decompress so the content stream can be scanned for drawing operators
        pdf = PdfReader(str(path), decompress=True)
    except Exception as e:
        report.warn("pdf_unreadable", "Artwork could not be fully inspected.", str(e))
        return

    if not pdf.pages:
        report.fail(
            "empty_file",
            "Artwork cannot be uploaded because the file appears to be empty. "
            "Please upload compatible vector artwork and try again.",
            "No pages found in the document.",
        )
        return

    page = pdf.pages[0]
    image_xobjects = 0
    form_xobjects = 0
    image_dims = []
    try:
        res = page.Resources or {}
        xobjects = (res.XObject or {}) if res else {}
        for _, xo in (xobjects.items() if xobjects else []):
            subtype = str(getattr(xo, "Subtype", "") or "")
            if "Image" in subtype:
                image_xobjects += 1
                try:
                    image_dims.append(f"{int(xo.Width)}×{int(xo.Height)}px")
                except Exception:
                    pass
            elif "Form" in subtype:
                form_xobjects += 1
    except Exception:
        return

    report.facts["pdf_image_xobjects"] = image_xobjects
    report.facts["pdf_form_xobjects"] = form_xobjects

    if not image_xobjects:
        return

    # Any raster inside the file is a production problem for screen print,
    # whether the file is a pure wrapper or vector art with a placed image.
    has_vector_ops = _pdf_has_vector_operators(page)
    report.facts["pdf_vector_operators"] = has_vector_ops

    if has_vector_ops:
        detail = (f"Found {image_xobjects} placed image(s) "
                  f"({', '.join(image_dims)}) alongside vector artwork."
                  if image_dims else
                  f"Found {image_xobjects} placed image(s) alongside vector artwork.")
    else:
        detail = ("The page contains a placed image and no vector paths — this is "
                  "usually a JPG or PNG saved into a PDF/AI wrapper.")
        if image_dims:
            detail += f" Image size: {', '.join(image_dims)}."

    report.fail(
        "embedded_raster",
        "Artwork cannot be uploaded because this file contains a placed image "
        "rather than one-color vector artwork. Please upload true vector artwork "
        "and try again.",
        detail,
    )


# Path-construction and painting operators that indicate real vector geometry.
_VECTOR_OP_RE = re.compile(
    rb"(?:^|[\s\]])(?:re|[ml]|c|v|y|h)[\s]+(?:[\d.\-]+[\s]+)*?(?:f\*?|B\*?|b\*?|S|s|n)[\s]",
    re.M,
)
_SIMPLE_OPS_RE = re.compile(rb"[\s](?:f\*?|B\*?|b\*?|S|s)[\s]")


def _pdf_has_vector_operators(page):
    """True when the page's content stream draws vector paths or text."""
    try:
        contents = page.Contents
        if contents is None:
            return False
        streams = contents if isinstance(contents, list) else [contents]
        blob = b""
        for st in streams:
            try:
                blob += st.stream.encode("latin-1") if isinstance(st.stream, str) else (st.stream or b"")
            except Exception:
                continue
        if not blob:
            return False
        # Text-showing operators also count as vector content.
        if re.search(rb"[\s](?:Tj|TJ|'|\")[\s]", blob):
            return True
        if _VECTOR_OP_RE.search(blob):
            return True
        return bool(_SIMPLE_OPS_RE.search(blob))
    except Exception:
        return False


# ─────────────────────────────────────────────────────────────────────────────
# EPS inspection
# ─────────────────────────────────────────────────────────────────────────────

def inspect_eps(path, report):
    """Detect EPS files that are just a wrapper around a raster image."""
    try:
        with open(path, "rb") as fp:
            head = fp.read(2_000_000)
    except Exception:
        return

    has_image_op = re.search(rb"\b(?:colorimage|imagemask|\bimage\b)\s", head) is not None
    has_paths = re.search(rb"\b(?:curveto|lineto|rlineto|moveto)\b", head) is not None

    report.facts["eps_image_operator"] = has_image_op
    report.facts["eps_path_operators"] = has_paths

    if has_image_op and not has_paths:
        report.fail(
            "embedded_raster",
            "Artwork cannot be uploaded because this file contains a placed image "
            "rather than vector artwork. Please upload true one-color vector "
            "artwork and try again.",
            "The EPS contains raster image data with no vector paths.",
        )


# ─────────────────────────────────────────────────────────────────────────────
# Pixel-level checks, run against the rasterized preview
# ─────────────────────────────────────────────────────────────────────────────

def _cluster_colors(samples):
    """Greedy color clustering. samples: list of (r,g,b). Returns [(rgb, count)]."""
    clusters = []  # [[sum_r, sum_g, sum_b, count, (rep_r,rep_g,rep_b)]]
    for rgb in samples:
        placed = False
        for c in clusters:
            rep = c[4]
            if (abs(rgb[0] - rep[0]) <= CLUSTER_DISTANCE
                    and abs(rgb[1] - rep[1]) <= CLUSTER_DISTANCE
                    and abs(rgb[2] - rep[2]) <= CLUSTER_DISTANCE):
                c[0] += rgb[0]; c[1] += rgb[1]; c[2] += rgb[2]; c[3] += 1
                placed = True
                break
        if not placed:
            clusters.append([rgb[0], rgb[1], rgb[2], 1, rgb])
    out = []
    for c in clusters:
        n = c[3]
        out.append(((c[0] // n, c[1] // n, c[2] // n), n))
    out.sort(key=lambda t: -t[1])
    return out


def _rgb_to_hsv(rgb):
    r, g, b = [v / 255.0 for v in rgb]
    mx, mn = max(r, g, b), min(r, g, b)
    d = mx - mn
    if d == 0:
        h = 0.0
    elif mx == r:
        h = (60 * ((g - b) / d)) % 360
    elif mx == g:
        h = (60 * ((b - r) / d) + 120) % 360
    else:
        h = (60 * ((r - g) / d) + 240) % 360
    s = 0.0 if mx == 0 else d / mx
    return h, s, mx


def _hue_gap(h1, h2):
    d = abs(h1 - h2) % 360
    return min(d, 360 - d)


def inspect_pixels(preview_path, report):
    """
    Inspect the rasterized preview for an opaque background and for multi-color
    artwork. The preview must be rendered with transparency preserved.
    """
    try:
        img = Image.open(str(preview_path)).convert("RGBA")
    except Exception as e:
        report.warn("preview_unreadable", "Artwork could not be fully inspected.", str(e))
        return

    # Downsample large art — this is a statistical check, not a pixel audit.
    max_dim = 400
    if max(img.size) > max_dim:
        ratio = max_dim / max(img.size)
        img = img.resize(
            (max(1, int(img.width * ratio)), max(1, int(img.height * ratio))),
            Image.NEAREST,
        )

    px = img.load()
    w, h = img.size
    total = w * h

    opaque = 0
    solid_samples = []
    for y in range(h):
        for x in range(w):
            r, g, b, a = px[x, y]
            if a >= SOLID_ALPHA:
                opaque += 1
                solid_samples.append((r, g, b))

    coverage = opaque / total if total else 0.0
    report.facts["opaque_coverage"] = round(coverage, 4)

    if not solid_samples:
        report.fail(
            "empty_artwork",
            "Artwork cannot be uploaded because no artwork was detected in the "
            "file. Please check the file and try again.",
            "The artwork rendered as fully transparent.",
        )
        return

    # ── color clusters ──────────────────────────────────────────────────────
    # Quantize before clustering to keep the pass cheap.
    quantized = [(r & 0xF0, g & 0xF0, b & 0xF0) for (r, g, b) in solid_samples]
    clusters = _cluster_colors(quantized)
    significant = [(rgb, n) for rgb, n in clusters
                   if n / len(quantized) >= MIN_CLUSTER_SHARE]
    report.facts["ink_clusters"] = [
        {"hex": "#%02X%02X%02X" % rgb, "share": round(n / len(quantized), 3)}
        for rgb, n in significant[:6]
    ]

    # ── opaque background ───────────────────────────────────────────────────
    # A background is a uniform border enclosing the whole artboard. A solid
    # filled logo also fills its bounding box, so a single flat color is only
    # treated as a background when it is white — otherwise it is left alone
    # rather than risking a reject on production-ready art.
    if coverage >= BACKGROUND_COVERAGE:
        border = []
        for x in range(w):
            border.append(px[x, 0][:3]); border.append(px[x, h - 1][:3])
        for y in range(h):
            border.append(px[0, y][:3]); border.append(px[w - 1, y][:3])
        bclusters = _cluster_colors(border)
        dominant_rgb, dominant_n = bclusters[0]
        if dominant_n / len(border) >= 0.9:
            hexv = "#%02X%02X%02X" % dominant_rgb
            is_white = all(v >= 235 for v in dominant_rgb)
            art_on_top = len(significant) >= 2
            report.facts["background_hex"] = hexv
            if art_on_top or is_white:
                report.fail(
                    "opaque_background",
                    "Artwork cannot be uploaded because it has a "
                    + ("white" if is_white else "solid-color")
                    + " background. Screen-print artwork must have a transparent "
                      "background — the background would otherwise print as part "
                      "of your design. Please remove the background and try again.",
                    f"A solid {hexv} background covers the full artboard.",
                )
                return
            report.warn(
                "flat_artwork",
                "This artwork is a single solid shape with no transparent area. "
                "If it is meant to have a transparent background, please re-save "
                "it without the background.",
                f"The artwork is entirely {hexv} with no transparency.",
            )

    if len(significant) <= 1:
        return

    # More than one ink is still acceptable when the colors are tints of a
    # single ink — screen printers reproduce those as halftones of one screen.
    hsvs = [_rgb_to_hsv(rgb) for rgb, _ in significant]
    chromatic = [hsv for hsv in hsvs if hsv[1] >= 0.15]

    if not chromatic:
        return  # all neutral — black/grey tints of a single ink

    if len(chromatic) == len(hsvs):
        # Every ink shares one hue family: a single colored ink at different
        # tints, which a screen printer reproduces as halftones of one screen.
        base_hue = chromatic[0][0]
        hue_spread = max(_hue_gap(base_hue, hsv[0]) for hsv in chromatic)
        if hue_spread <= 25:
            return
    # A colored ink alongside neutral ink (e.g. a red mark plus black type) is
    # two separate screens, so it falls through and is reported below.

    swatches = ", ".join(f["hex"] for f in report.facts["ink_clusters"][:4])
    message = (
        "Artwork cannot be uploaded because it contains more than one color. "
        "This product prints in a single PMS ink — please supply one-color "
        "vector artwork and try again."
    )
    detail = f"Detected {len(significant)} distinct colors: {swatches}."
    if BLOCK_MULTICOLOR:
        report.fail("multicolor", message, detail)
    else:
        report.warn("multicolor", message, detail)


# ─────────────────────────────────────────────────────────────────────────────
# Multi-color spot separations
# ─────────────────────────────────────────────────────────────────────────────
#
# inspect_pixels() above answers a yes/no question for the one-color program:
# can this art print on a single screen? This answers a different question for
# multi-color spot products — which inks does the art actually use, and can the
# press run them?
#
# It never passes or fails an upload. It reports what it found, merges inks
# that are the same color as far as the press is concerned, and says plainly
# when what remains still exceeds MAX_SPOT_INKS.
#
# The pixel sampling below is deliberately NOT shared with inspect_pixels().
# That function gates the shipping one-color program; keeping the two apart
# means changes here can never alter what it accepts or rejects.


def _delta_e_rgb(rgb1, rgb2):
    """Perceptual distance between two sRGB triples."""
    try:
        from engine import _rgb_to_lab, _delta_e
        return _delta_e(_rgb_to_lab(rgb1), _rgb_to_lab(rgb2))
    except Exception:
        # Fallback if engine's color math is unavailable. Coarser, but it only
        # has to rank pairs against each other.
        rm = (rgb1[0] + rgb2[0]) / 2.0
        dr, dg, db = (rgb1[0] - rgb2[0], rgb1[1] - rgb2[1], rgb1[2] - rgb2[2])
        return (((2 + rm / 256) * dr * dr)
                + 4 * dg * dg
                + ((2 + (255 - rm) / 256) * db * db)) ** 0.5 / 3.0


def _merge_nearest_inks(inks, limit, threshold):
    """
    Merge the closest pairs of inks until at most `limit` remain.

    Only pairs within `threshold` ΔE are merged. Once the closest remaining
    pair is further apart than that, merging would visibly change the artwork,
    so this stops and leaves the caller to flag it rather than quietly
    redrawing the customer's logo.

    inks: [{"rgb": (r,g,b), "count": int, "sources": [hex, ...]}]
    Returns (inks, merges) where merges records what was combined.
    """
    inks = [dict(i) for i in inks]
    merges = []

    while len(inks) > limit:
        best = None
        for a in range(len(inks)):
            for b in range(a + 1, len(inks)):
                de = _delta_e_rgb(inks[a]["rgb"], inks[b]["rgb"])
                if best is None or de < best[0]:
                    best = (de, a, b)

        if best is None or best[0] > threshold:
            break  # nothing left that is safe to combine

        de, a, b = best
        ia, ib = inks[a], inks[b]
        na, nb = ia["count"], ib["count"]
        total = na + nb or 1
        merged_rgb = tuple(
            int(round((ia["rgb"][k] * na + ib["rgb"][k] * nb) / total))
            for k in range(3)
        )
        merges.append({
            "into": "#%02X%02X%02X" % merged_rgb,
            "from": list(ia["sources"]) + list(ib["sources"]),
            "delta_e": round(de, 1),
        })
        inks[a] = {
            "rgb": merged_rgb,
            "count": total,
            "sources": list(ia["sources"]) + list(ib["sources"]),
        }
        inks.pop(b)

    inks.sort(key=lambda i: -i["count"])
    return inks, merges


def _dominant_border_rgb(px, w, h, min_share=0.9):
    """
    The color of the field enclosing the artwork, or None if there isn't one.

    A PDF or AI file has no alpha channel, so anything rasterized from one
    arrives sitting on an opaque artboard — usually white. That field is not an
    ink and must not consume one of the press's screens. A real background
    encloses the art, so it is identified by dominating the border rather than
    by being any particular color, which also catches colored artboards.

    Only solid border pixels count. Art that was supplied with real
    transparency has a transparent border, no dominant color, and nothing is
    excluded.
    """
    border = []
    for x in range(w):
        for y in (0, h - 1):
            r, g, b, a = px[x, y]
            if a >= SOLID_ALPHA:
                border.append((r, g, b))
    for y in range(h):
        for x in (0, w - 1):
            r, g, b, a = px[x, y]
            if a >= SOLID_ALPHA:
                border.append((r, g, b))

    perimeter = 2 * (w + h)
    if not border or len(border) / perimeter < min_share:
        return None  # border is largely transparent — no background field

    clusters = _cluster_colors(border)
    rgb, n = clusters[0]
    return rgb if n / len(border) >= min_share else None


def analyze_separations(preview_path, max_inks=MAX_SPOT_INKS):
    """
    Detect the spot inks in artwork for a multi-color product.

    Returns a dict:
        inks        [{"hex", "share", "sources"}]  final inks, most-used first
        detected    how many distinct inks were found before merging
        max_inks    the press ceiling this was measured against
        merged      [{"into", "from", "delta_e"}]  near-duplicates combined
        over_limit  True when more than max_inks remain after merging
        error       set instead of the above when the preview is unreadable

    over_limit is the caller's cue to flag the art. Everything else is
    printable as returned.
    """
    out = {
        "inks": [],
        "detected": 0,
        "max_inks": max_inks,
        "merged": [],
        "over_limit": False,
        "background_hex": None,
        "error": None,
    }

    try:
        img = Image.open(str(preview_path)).convert("RGBA")
    except Exception as e:
        out["error"] = str(e)
        return out

    max_dim = 400
    if max(img.size) > max_dim:
        ratio = max_dim / max(img.size)
        img = img.resize(
            (max(1, int(img.width * ratio)), max(1, int(img.height * ratio))),
            Image.NEAREST,
        )

    px = img.load()
    w, h = img.size

    # Full-precision samples, unlike inspect_pixels' quantized pass — these
    # colors get matched against the PMS book, so a 16-step quantization error
    # would be enough to land on the wrong chip.
    samples = []
    for y in range(h):
        for x in range(w):
            r, g, b, a = px[x, y]
            if a >= SOLID_ALPHA:
                samples.append((r, g, b))

    if not samples:
        return out

    clusters = _cluster_colors(samples)
    total = len(samples)
    significant = [(rgb, n) for rgb, n in clusters
                   if n / total >= MIN_CLUSTER_SHARE]
    if not significant:
        significant = clusters[:1]

    # Drop the artboard before counting inks. Mirrors inspect_pixels' rule: a
    # single flat color filling its own bounding box is a solid logo, not a
    # background, so the enclosing field is only discarded when there is art on
    # top of it or when it is white.
    bg_rgb = _dominant_border_rgb(px, w, h)
    if bg_rgb is not None:
        is_white = all(v >= 235 for v in bg_rgb)
        art_on_top = len(significant) >= 2
        if is_white or art_on_top:
            kept_sig = [(rgb, n) for rgb, n in significant
                        if max(abs(rgb[k] - bg_rgb[k]) for k in range(3))
                        > CLUSTER_DISTANCE]
            # Never strip the art down to nothing — if the background was the
            # only thing found, it is the artwork.
            if kept_sig:
                out["background_hex"] = "#%02X%02X%02X" % bg_rgb
                significant = kept_sig

    out["detected"] = len(significant)

    inks = [{"rgb": rgb, "count": n, "sources": ["#%02X%02X%02X" % rgb]}
            for rgb, n in significant]

    inks, merges = _merge_nearest_inks(inks, max_inks, MERGE_DELTA_E)
    out["merged"] = merges
    out["over_limit"] = len(inks) > max_inks

    kept = sum(i["count"] for i in inks) or 1
    out["inks"] = [{
        "hex": "#%02X%02X%02X" % i["rgb"],
        "share": round(i["count"] / kept, 3),
        "sources": i["sources"],
    } for i in inks]

    return out


def analyze_vector_separations(pdf_path, max_inks=MAX_SPOT_INKS):
    """
    analyze_separations() for vector artwork, read from the file itself.

    The raster version measures a rendered preview, where the artboard and
    anti-aliasing count as pixels: small inks — the four arms of an X logo at
    9 % each — fall under the minimum share once the white background is in
    the total, and a five-colour logo comes back as one colour. Reading the
    painted shapes gives exact colours and exact areas.

    White in artwork that also has colour: white standing on its own (white
    lettering beside red lettering) is a White ink; white inside or behind the
    coloured art is a knockout (onecolor._white_role, onecolor.separate). This
    holds for plain white, not only a spot named White. Same output shape as
    analyze_separations().
    """
    import onecolor, tempfile
    out = {"inks": [], "detected": 0, "max_inks": max_inks, "merged": [],
           "over_limit": False, "background_hex": None, "error": None,
           "source": "vector"}
    an = onecolor.analyze(pdf_path, Path(tempfile.gettempdir()) / "numo_vsep")
    white_ink_area = sum(s["area"] for s in an["shapes"] if s.get("white_role") == "ink")
    groups = []
    for g in an["groups"]:
        h = g["hex"].lstrip("#")
        rgb = tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
        if all(v >= 235 for v in rgb) and len(an["groups"]) > 1:
            continue
        groups.append({"rgb": rgb, "count": g["area"], "sources": [g["hex"]]})
    if white_ink_area and groups:
        # Every plain white the art uses goes to the one White ink.
        whites = [g["hex"] for g in an["groups"]
                  if all(int(g["hex"][k:k + 2], 16) >= 235 for k in (1, 3, 5))]
        groups.append({"rgb": (255, 255, 255), "count": white_ink_area,
                       "sources": sorted(set(whites)) or ["#FFFFFF"], "white_ink": True})
    if not groups:
        return out
    # Near-identical shades (three navies a designer never meant as three inks)
    # merge first, with no ceiling, so "detected" counts real inks.
    groups, merges = _merge_nearest_inks(groups, 1, MERGE_DELTA_E)
    groups.sort(key=lambda g: -g["count"])
    out["detected"] = len(groups)
    out["merged"] = merges
    out["over_limit"] = len(groups) > max_inks
    total = sum(g["count"] for g in groups) or 1
    out["inks"] = [{"hex": "#%02X%02X%02X" % g["rgb"],
                    "share": round(g["count"] / total, 3),
                    "sources": g["sources"]} for g in groups]
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Ink bounds
# ─────────────────────────────────────────────────────────────────────────────
#
# A PDF/AI page box is the artboard, not the artwork. Illustrator files are
# routinely saved on a letter artboard with the logo sitting in the middle, so
# scaling placed art by the page box makes it land far smaller than the canvas
# preview — which measures the actual ink.
#
# Measuring the ink here, the same way the preview does, keeps the two in step.

_INK_BBOX_CACHE = {}


def ink_bbox_points(pdf_path, page_box, dpi=150):
    """
    The bounding box of the actual artwork on a PDF/AI page, in PDF points.

    page_box : (x0, y0, x1, y1) of the page, in points
    Returns  : (x0, y0, x1, y1) of the ink, or None when it can't be measured
               (the caller then falls back to the page box).
    """
    key = (str(pdf_path), tuple(page_box), dpi)
    if key in _INK_BBOX_CACHE:
        return _INK_BBOX_CACHE[key]

    result = None
    try:
        from pdf2image import convert_from_path
        pages = convert_from_path(
            str(pdf_path), dpi=dpi, first_page=1, last_page=1,
            transparent=True, use_pdftocairo=True, fmt="png",
        )
        if pages:
            im = pages[0].convert("RGBA")
            bbox = im.getchannel("A").getbbox()   # left, top, right, bottom
            if bbox:
                W, H = im.size
                px0, py0, px1, py1 = page_box
                sx = (px1 - px0) / float(W)
                sy = (py1 - py0) / float(H)
                # image origin is top-left, PDF origin is bottom-left
                result = (
                    px0 + bbox[0] * sx,
                    py0 + (H - bbox[3]) * sy,
                    px0 + bbox[2] * sx,
                    py0 + (H - bbox[1]) * sy,
                )
                # Ignore a degenerate measurement and keep the page box.
                if result[2] - result[0] < 1 or result[3] - result[1] < 1:
                    result = None
    except Exception as e:
        print(f"[screenprint] ink bounds unavailable for {pdf_path}: {e}")

    _INK_BBOX_CACHE[key] = result
    return result


# ─────────────────────────────────────────────────────────────────────────────
# Spot color separation
# ─────────────────────────────────────────────────────────────────────────────
#
# A one-color screen-print job should leave the configurator as a single named
# spot separation, not as whatever colors the customer happened to draw in.
#
# The artwork is placed as a form XObject, so rather than rewriting each of its
# color operators we strip colour-setting operators out of its content stream
# entirely. Everything it paints then inherits the graphics state — and the
# caller sets that to the PMS separation before drawing the form. Vector paths,
# text outlines and knockouts are untouched; only the color changes.


def hex_to_cmyk(hex_color):
    """Approximate CMYK for a hex color, used as the separation's alternate space."""
    h = (hex_color or "#000000").lstrip("#")
    if len(h) == 3:
        h = "".join(ch * 2 for ch in h)
    try:
        r, g, b = (int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4))
    except Exception:
        r = g = b = 0.0
    k = 1.0 - max(r, g, b)
    if k >= 1.0:
        return 0.0, 0.0, 0.0, 1.0
    c = (1.0 - r - k) / (1.0 - k)
    m = (1.0 - g - k) / (1.0 - k)
    y = (1.0 - b - k) / (1.0 - k)
    return (round(max(0.0, min(1.0, v)), 4) for v in (c, m, y, k))


# Operators that set a color; their operands are dropped along with them.
_COLOR_OPS = {
    b"rg", b"RG",     # device RGB
    b"g",  b"G",      # device gray
    b"k",  b"K",      # device CMYK
    b"cs", b"CS",     # select color space
    b"sc", b"SC",     # set color
    b"scn", b"SCN",   # set color (with optional pattern name)
}

_DELIMS = b"()<>[]{}/%"


def _tokenize(data):
    """Yield (token_bytes, is_operator) over a PDF content stream."""
    i, n = 0, len(data)
    while i < n:
        ch = data[i:i + 1]
        if ch.isspace():
            i += 1
            continue
        if ch == b"%":                                   # comment
            j = data.find(b"\n", i)
            j = n if j < 0 else j
            yield data[i:j], False
            i = j
            continue
        if ch == b"(":                                   # literal string
            depth, j = 1, i + 1
            while j < n and depth:
                cj = data[j:j + 1]
                if cj == b"\\":
                    j += 2
                    continue
                if cj == b"(":
                    depth += 1
                elif cj == b")":
                    depth -= 1
                j += 1
            yield data[i:j], False
            i = j
            continue
        if ch == b"<" and data[i:i + 2] != b"<<":         # hex string
            j = data.find(b">", i)
            j = n if j < 0 else j + 1
            yield data[i:j], False
            i = j
            continue
        if data[i:i + 2] in (b"<<", b">>"):
            yield data[i:i + 2], False
            i += 2
            continue
        if ch in b"[]{}":
            yield ch, False
            i += 1
            continue
        if ch == b"/":                                   # name
            j = i + 1
            while j < n and not data[j:j + 1].isspace() and data[j:j + 1] not in _DELIMS:
                j += 1
            yield data[i:j], False
            i = j
            continue
        j = i                                            # number or operator
        while j < n and not data[j:j + 1].isspace() and data[j:j + 1] not in _DELIMS:
            j += 1
        tok = data[i:j]
        is_op = not _NUM_RE.match(tok)
        yield tok, is_op
        i = j


_NUM_RE = re.compile(rb"^[+-]?(\d+\.?\d*|\.\d+)$")


def strip_color_operators(data):
    """
    Remove color-setting operators so painted content inherits the current color.

    Inline images (BI … ID … EI) are copied through untouched.
    """
    out = []
    pending = []
    tokens = _tokenize(data)
    for tok, is_op in tokens:
        if not is_op:
            pending.append(tok)
            continue
        if tok == b"BI":
            # copy the inline image verbatim
            out.extend(pending)
            pending = []
            out.append(tok)
            for t2, _ in tokens:
                out.append(t2)
                if t2 == b"EI":
                    break
            continue
        if tok in _COLOR_OPS:
            pending = []          # drop the operator and its operands
            continue
        out.extend(pending)
        pending = []
        out.append(tok)
    out.extend(pending)
    return b" ".join(out)


def _op_color_to_rgb(op, operands):
    """The sRGB triple an operator sets, or None when it isn't a color it defines."""
    try:
        nums = [float(o) for o in operands]
    except (TypeError, ValueError):
        return None
    if op in (b"rg", b"RG") and len(nums) >= 3:
        r, g, b = nums[-3:]
    elif op in (b"g", b"G") and len(nums) >= 1:
        r = g = b = nums[-1]
    elif op in (b"k", b"K") and len(nums) >= 4:
        c, m, y, k = nums[-4:]
        r, g, b = (1 - min(1, c + k)), (1 - min(1, m + k)), (1 - min(1, y + k))
    elif op in (b"sc", b"SC", b"scn", b"SCN"):
        # Untagged component values: 1 = gray, 3 = RGB, 4 = CMYK. A pattern
        # name among the operands makes the color indeterminate, so skip it.
        if len(nums) == 1:
            r = g = b = nums[0]
        elif len(nums) == 3:
            r, g, b = nums
        elif len(nums) == 4:
            c, m, y, k = nums
            r, g, b = (1 - min(1, c + k)), (1 - min(1, m + k)), (1 - min(1, y + k))
        else:
            return None
    else:
        return None
    return tuple(max(0, min(255, int(round(v * 255)))) for v in (r, g, b))


# Painting operators, split by which color they consult.
_FILL_PAINT_OPS   = {b"f", b"F", b"f*", b"B", b"B*", b"b", b"b*"}
_STROKE_PAINT_OPS = {b"S", b"s"}
# Text is painted by its show operators, in the fill colour (live type that was
# never outlined — "SALE" set in white on a banner).
_TEXT_SHOW_OPS = {b"Tj", b"TJ", b"'", b'"'}


def drop_colors_from_form(xobj, hidden_rgbs, tolerance=40):
    """
    Remove artwork drawn in any of `hidden_rgbs` from a placed form XObject.

    This exists because hiding a color in the browser only repaints a canvas.
    The exported PDF places the customer's original vector file, so without
    this the ink they were shown as removed would come back on the press
    sheet — the preview would be lying about what prints, which is the worst
    way for this to fail.

    Paths painted in a hidden color have their painting operator replaced with
    `n` (end path, paint nothing). The path is still constructed, so clipping
    and the graphics stack are untouched; only the ink stops.

    Returns True when the form was rewritten, False when it was left alone —
    the caller should then place it unchanged rather than silently shipping
    artwork that still carries the hidden ink.
    """
    if not hidden_rgbs:
        return False
    try:
        decoded = decode_stream(xobj)
        if decoded is None:
            return False

        def hidden(rgb):
            return rgb is not None and any(
                max(abs(rgb[i] - h[i]) for i in range(3)) <= tolerance
                for h in hidden_rgbs)

        out, pending = [], []
        fill_hidden = stroke_hidden = False
        tokens = _tokenize(decoded)
        for tok, is_op in tokens:
            if not is_op:
                pending.append(tok)
                continue

            if tok == b"BI":                      # inline image — copy verbatim
                out.extend(pending); pending = []
                out.append(tok)
                for t2, _ in tokens:
                    out.append(t2)
                    if t2 == b"EI":
                        break
                continue

            if tok in _COLOR_OPS:
                rgb = _op_color_to_rgb(tok, pending)
                if rgb is not None:
                    if tok in (b"rg", b"g", b"k", b"sc", b"scn"):
                        fill_hidden = hidden(rgb)
                    else:
                        stroke_hidden = hidden(rgb)
            elif (tok in _FILL_PAINT_OPS and fill_hidden) or \
                 (tok in _STROKE_PAINT_OPS and stroke_hidden):
                out.extend(pending); pending = []
                out.append(b"n")                  # end the path without painting
                continue

            out.extend(pending); pending = []
            out.append(tok)

        out.extend(pending)
        rewritten = b" ".join(out)
        if not rewritten.strip():
            return False
        xobj.stream = rewritten.decode("latin-1")
        xobj.Filter = None
        xobj.DecodeParms = None
        return True
    except Exception as e:
        print(f"[screenprint] could not drop hidden colors: {e}")
        return False


def drop_white_knockouts(xobj, threshold=235):
    """
    Turn opaque white shapes into real holes before the art is flattened to one ink.

    Designers routinely punch detail out of a filled shape by drawing it in
    white on top — lettering on a banner, a highlight inside a solid mark —
    rather than subtracting it from the path. On screen it reads correctly
    because white and the fill are different colors.

    recolor_form_to_spot() then strips every color operator so the whole form
    inherits the job's single ink, and those white shapes become the same ink
    as what they were punched out of: the lettering silently fills in and the
    customer gets a solid blob where their design had detail. The preview never
    shows this, because it works from the rasterized PNG where the white pixels
    are their own color and get knocked out as background — so the two disagree
    and only the press file is wrong.

    Dropping them makes white mean what it means on press: no ink, substrate
    shows through.

    Art that paints nothing but white is left alone — that is a design meant to
    print in white on a dark product, not a set of knockouts, and removing it
    would leave an empty screen.

    Returns True when the form was rewritten.
    """
    try:
        decoded = decode_stream(xobj)
        if decoded is None:
            return False

        def is_white(rgb):
            return rgb is not None and all(v >= threshold for v in rgb)

        # Only act when there is non-white artwork for the white to punch out of.
        seen_white = seen_ink = False
        cur = None
        pending = []
        for tok, is_op in _tokenize(decoded):
            if not is_op:
                pending.append(tok)
                continue
            if tok in _COLOR_OPS:
                rgb = _op_color_to_rgb(tok, pending)
                if rgb is not None and tok in (b"rg", b"g", b"k", b"sc", b"scn"):
                    cur = rgb
            elif tok in _FILL_PAINT_OPS and cur is not None:
                if is_white(cur):
                    seen_white = True
                else:
                    seen_ink = True
            pending = []

        if not (seen_white and seen_ink):
            return False

        return drop_colors_from_form(xobj, [(255, 255, 255)],
                                     tolerance=255 - threshold)
    except Exception as e:
        print(f"[screenprint] could not knock out white shapes: {e}")
        return False


def _cs_family(xobj, name):
    """'tint' for Separation/DeviceN spaces, 'pattern', or None for device-like."""
    try:
        res = xobj.Resources or {}
        cs = (res.ColorSpace or {}).get(name) if hasattr(res, "ColorSpace") else None
    except Exception:
        cs = None
    if cs is None:
        n = str(name)
        return "pattern" if n == "/Pattern" else None
    try:
        head = str(cs[0]) if isinstance(cs, (list, tuple)) or hasattr(cs, "__getitem__") else str(cs)
    except Exception:
        head = str(cs)
    if head in ("/Separation", "/DeviceN"):
        return "tint"
    if head == "/Pattern":
        return "pattern"
    return None


def paint_ink_and_knockouts(xobj, ink_rgb, ko_rgb, threshold=235):
    """
    Flatten a placed form to one ink while keeping white as a real knockout.

    Every shape painted in a colour is repainted in `ink_rgb`; every shape
    painted in white (or near it) is repainted in `ko_rgb`. The caller picks
    those per canvas: on a press sheet ink is black and a knockout is white,
    which the registration pass turns into 100 % and 0 % of the one screen —
    a hole cut through whatever the white sits on. On the proof the ink is the
    PMS and a knockout is the product colour, so it reads as the substrate.

    This replaces dropping white shapes. Dropping one that sits on top of a
    fill does not make a hole, it uncovers the fill: white lettering on a
    banner printed as a solid banner.

    Art that is only white is printing white on a dark product, not a set of
    knockouts, so it is all treated as ink. Spot-colour (Separation/DeviceN)
    values are read as tints — 0 is no ink — not as grey levels, or a 100 %
    PMS would count as white.

    Returns True when the form was rewritten.
    """
    try:
        # The art's own groups (form XObjects inside the form) are painted
        # too. Customer files nest art routinely (transparency groups, placed
        # files, art cut from a template), and a group left alone keeps its
        # own colors: the proof then showed black lettering for a white ink.
        # "Both ink and white?" is answered for the whole art, not per group.
        streams, seen = [], set()

        def collect(obj):
            if id(obj) in seen:
                return
            seen.add(id(obj))
            data = decode_stream(obj)
            if data is not None:
                streams.append((obj, list(_tokenize(data))))
            res = obj.Resources or {}
            for _, x in ((res.XObject or {}).items() if res else []):
                try:
                    if x is not None and str(x.Subtype) == "/Form":
                        collect(x)
                except Exception:
                    continue

        collect(xobj)
        if not streams or streams[0][0] is not xobj:
            return False

        def classify(tok, operands, fam):
            """'ink', 'white', or None when the colour can't be read."""
            key = "stroke" if tok in (b"RG", b"G", b"K", b"SC", b"SCN") else "fill"
            if tok in (b"sc", b"scn", b"SC", b"SCN"):
                f = fam[key]
                if f == "pattern":
                    return "ink"
                if f == "tint":
                    try:
                        vals = [float(o) for o in operands]
                    except (TypeError, ValueError):
                        return "ink"
                    return "white" if vals and max(vals) <= 0.02 else "ink"
            rgb = _op_color_to_rgb(tok, operands)
            if rgb is None:
                return "ink"
            return "white" if all(v >= threshold for v in rgb) else "ink"

        # Pass 1: is there both ink and white actually painted, anywhere?
        seen_white = seen_ink = False
        for obj, tokens in streams:
            fam = {"fill": None, "stroke": None}
            cur = "ink"
            pending = []
            for tok, is_op in tokens:
                if not is_op:
                    pending.append(tok); continue
                if tok in (b"cs", b"CS") and pending:
                    fam["fill" if tok == b"cs" else "stroke"] = _cs_family(obj, pending[-1].decode("latin-1"))
                elif tok in _COLOR_OPS and tok not in (b"cs", b"CS") and tok in (b"rg", b"g", b"k", b"sc", b"scn"):
                    cur = classify(tok, pending, fam)
                elif tok in _FILL_PAINT_OPS or tok in _TEXT_SHOW_OPS:
                    seen_white |= cur == "white"; seen_ink |= cur == "ink"
                pending = []
        mixed = seen_white and seen_ink

        def col(rgb, stroke):
            return ("%.4f %.4f %.4f %s" % (*rgb, "RG" if stroke else "rg")).encode()

        # Pass 2: rewrite every stream.
        for obj, tokens in streams:
            fam = {"fill": None, "stroke": None}
            out = [col(ink_rgb, False), col(ink_rgb, True)]   # the default colour is ink
            pending = []
            it = iter(tokens)
            for tok, is_op in it:
                if not is_op:
                    pending.append(tok); continue
                if tok == b"BI":
                    out.extend(pending); pending = []; out.append(tok)
                    for t2, _ in it:
                        out.append(t2)
                        if t2 == b"EI":
                            break
                    continue
                if tok in (b"cs", b"CS"):
                    if pending:
                        fam["fill" if tok == b"cs" else "stroke"] = _cs_family(obj, pending[-1].decode("latin-1"))
                    pending = []
                    continue
                if tok in _COLOR_OPS:
                    stroke = tok in (b"RG", b"G", b"K", b"SC", b"SCN")
                    kind = classify(tok, pending, fam)
                    use = ko_rgb if (mixed and kind == "white") else ink_rgb
                    out.append(col(use, stroke))
                    pending = []
                    continue
                out.extend(pending); pending = []
                out.append(tok)
            out.extend(pending)
            obj.stream = b" ".join(out).decode("latin-1")
            obj.Filter = None
            obj.DecodeParms = None
        return True
    except Exception as e:
        print(f"[screenprint] could not flatten artwork to one ink: {e}")
        return False


def decode_stream(xobj):
    """
    Return a PDF stream's decoded bytes, or None when the filter chain isn't
    one we can undo. pdfrw handles plain Flate; ASCII85-wrapped chains are
    decoded here because Illustrator writes them routinely.
    """
    import zlib
    import base64

    raw = xobj.stream
    if raw is None:
        return None
    if isinstance(raw, str):
        raw = raw.encode("latin-1")

    filt = xobj.Filter
    if not filt:
        return raw
    names = [str(f) for f in (filt if isinstance(filt, list) else [filt])]

    data = raw
    for name in names:
        try:
            if name == "/FlateDecode":
                data = zlib.decompress(data)
            elif name == "/ASCII85Decode":
                d = data.strip()
                if d.startswith(b"<~"):
                    d = d[2:]
                data = base64.a85decode(d, adobe=True, ignorechars=b" \t\r\n\v\f")
            elif name == "/ASCIIHexDecode":
                d = data.split(b">")[0]
                data = bytes.fromhex(re.sub(rb"\s", b"", d).decode("ascii"))
            else:
                return None       # DCT, LZW, RunLength, … — leave it alone
        except Exception:
            return None
    return data


def recolor_form_to_spot(xobj):
    """
    Strip colors from a placed form XObject so it inherits the spot color.

    Returns True when the form was rewritten, False when it was left as-is
    (the caller should then place it unchanged rather than mis-coloring it).
    """
    try:
        decoded = decode_stream(xobj)
        if decoded is None:
            return False
        stripped = strip_color_operators(decoded)
        if not stripped.strip():
            return False
        xobj.stream = stripped.decode("latin-1")
        xobj.Filter = None
        xobj.DecodeParms = None
        return True
    except Exception as e:
        print(f"[screenprint] could not convert artwork to spot color: {e}")
        return False


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

def validate_artwork(original_path, filename, preview_path=None):
    """
    Validate one uploaded artwork file for the one-color screen-print workflow.

    original_path : the uploaded file as saved on disk
    filename      : the customer's original filename (used for the extension)
    preview_path  : the rasterized preview PNG, rendered WITH transparency.
                    Pixel checks are skipped when it is absent.
    """
    report = ArtworkReport()
    ext = check_extension(filename, report)
    if not report.ok:
        return report

    try:
        if ext == ".svg":
            inspect_svg(original_path, report)
        elif ext in {".pdf", ".ai"}:
            inspect_pdf(original_path, report)
        elif ext == ".eps":
            inspect_eps(original_path, report)
    except Exception as e:
        report.warn("inspection_failed", "Artwork could not be fully inspected.", str(e))

    if not report.ok:
        return report

    if preview_path and Path(preview_path).exists():
        try:
            inspect_pixels(preview_path, report)
        except Exception as e:
            report.warn("preview_check_failed",
                        "Artwork could not be fully inspected.", str(e))

    return report
