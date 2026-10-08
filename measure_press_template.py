"""
measure_press_template.py — derive a press spec from a This Is Fast template.

press_layout.py needs a JSON spec per product: where the imprint zones sit on
the guide pages, and where every koozie lands on each press sheet. Those come
from the template artwork itself, which draws them in fixed colors:

    #D81E33 / #D81E3B   die cut
    #5DC8DC / #62C9D9   maximum imprint area
    #775DA8             seam line
    #EB8E9D             orientation arrows

So the measuring is a color pass over a high-resolution render. Nothing here is
specific to one product — run it against a template and it reports that
product's geometry.

Verify against 0070-3m-24HR-1c, whose spec was measured by hand and has been to
press, before trusting the numbers for anything new.

    python3 measure_press_template.py <template.pdf> [--dpi 300]
"""

import sys
from collections import defaultdict

from PIL import Image
from pdf2image import convert_from_path

DIE_RGB    = [(0xD8, 0x1E, 0x33), (0xD8, 0x1E, 0x3B)]
IMPRINT_RGB = [(0x5D, 0xC8, 0xDC), (0x62, 0xC9, 0xD9), (0x60, 0xD9, 0xCB)]
TOL = 42


def _mask_points(img, targets, tol=TOL):
    """Pixels close to any target color, as a set of (x, y)."""
    import numpy as np
    a = np.asarray(img.convert("RGB")).astype(np.int16)
    hit = np.zeros(a.shape[:2], bool)
    for t in targets:
        hit |= (np.abs(a - np.array(t, dtype=np.int16)) <= tol).all(axis=2)
    ys, xs = np.nonzero(hit)
    return set(zip(xs.tolist(), ys.tolist()))


def _split(vals, gap):
    """Group sorted values into runs separated by more than `gap`."""
    vals = sorted(vals)
    if not vals:
        return []
    groups, cur = [], [vals[0]]
    for v in vals[1:]:
        if v - cur[-1] > gap:
            groups.append(cur); cur = [v]
        else:
            cur.append(v)
    groups.append(cur)
    return groups


def artwork_region(pts, scale, page_w_px):
    """
    The x-range holding the die artwork, excluding everything to its left.

    These guides put a legend and a notes panel down the left, both drawn in
    the same colors as the geometry — the notes panel's border is a longer run
    of teal than the imprint rectangle itself, so "the widest cluster" picks
    the wrong one. The artwork is always the rightmost column, which is the
    property that actually holds across the template family.
    """
    xs = [x for x, _ in pts]
    if not xs:
        return (0, page_w_px)
    groups = [g for g in _split(set(xs), gap=int(30 * scale)) if len(g) > 8 * scale]
    if not groups:
        return (min(xs), max(xs))
    best = max(groups, key=lambda g: max(g))
    return (min(best), max(best))


def _stroke_px(pts, x0, y0, y1):
    """
    Thickness of the drawn outline, in pixels.

    Sampled across many rows and taken as the median: these outlines are
    dashed, so any single row may land in a gap, catch a dash end, or pick up
    a neighbouring mark, and one bad sample shifts every measurement that
    depends on it.
    """
    runs = []
    for y in range(y0, y1 + 1, max(1, (y1 - y0) // 60)):
        xs = sorted(x for (x, yy) in pts if yy == y and x0 - 2 <= x <= x0 + 30)
        if not xs or xs[0] > x0 + 2:
            continue                      # dash gap, or not the left edge
        n = 1
        for a, b in zip(xs, xs[1:]):
            if b - a <= 1:
                n += 1
            else:
                break
        runs.append(n)
    if not runs:
        return 1
    runs.sort()
    return runs[len(runs) // 2]


def _regions(pts, size, scale, bridge_pt=3.0, min_px=200):
    """
    Group drawn pixels into the separate shapes they belong to.

    Splitting on vertical gaps alone is not enough: the side panel and the
    bottom circle sit closer together on some products than the dash gaps are
    wide on others, so any single threshold merges two shapes on one template
    while splitting one shape on the next.

    Dilating by a little less than the panel-to-circle gap bridges the dashes
    within a shape without bridging the space between shapes, and the bounding
    box is then taken from the original pixels so the dilation does not inflate
    the measurement.
    """
    import numpy as np
    from scipy import ndimage
    w, h = size
    a = np.zeros((h, w), bool)
    for x, y in pts:
        a[y, x] = True
    r = max(1, int(bridge_pt * scale))
    grown = ndimage.binary_dilation(a, np.ones((2 * r + 1, 2 * r + 1), bool))
    lab, n = ndimage.label(grown)
    out = []
    for sl, i in zip(ndimage.find_objects(lab), range(1, n + 1)):
        own = (lab[sl] == i) & a[sl]
        if own.sum() < min_px:
            continue
        ys, xs = np.nonzero(own)
        out.append({
            "x0": sl[1].start + int(xs.min()), "x1": sl[1].start + int(xs.max()),
            "y0": sl[0].start + int(ys.min()), "y1": sl[0].start + int(ys.max()),
            "pts": {(sl[1].start + int(x), sl[0].start + int(y))
                    for x, y in zip(xs, ys)},
        })
    return out


def _edges(counts, min_len, min_run):
    """Rows (or columns) dense enough to be a drawn edge, grouped into runs."""
    hot = [i for i, n in enumerate(counts) if n >= min_len]
    return [g for g in _split(set(hot), gap=min_run) if g]


def imprint_zones(img, scale, page_h_pt):
    """
    Each maximum-imprint-area rectangle, measured on its stroke centreline.

    Found by projection rather than by connectivity. These outlines are dashed,
    and the dash gaps vary enough between products that no single dilation both
    joins the dashes of one shape and keeps neighbouring shapes apart — it
    fragments the rectangles on one template and merges them on the next.

    A rectangle's horizontal edges are the only rows where drawn pixels span
    most of its width, and its vertical edges the only such columns, whatever
    the dash pattern. Pairing those runs recovers the rectangle directly. The
    bottom circle spans no row densely and simply does not register here, which
    is what die_circle() is for.
    """
    import numpy as np
    pts = _mask_points(img, IMPRINT_RGB)
    if not pts:
        return []
    ax0, ax1 = artwork_region(pts, scale, img.size[0])
    pts = {(x, y) for (x, y) in pts if ax0 - 4 <= x <= ax1 + 4}
    if not pts:
        return []

    w, h = img.size
    rows = np.zeros(h, int)
    cols = np.zeros(w, int)
    for x, y in pts:
        rows[y] += 1
        cols[x] += 1

    span = ax1 - ax0 + 1
    v_edges = _edges(cols, span * 0.35, int(3 * scale))
    if len(v_edges) < 2:
        return []

    # The left and right edges run the full height of each rectangle, so the
    # rectangles are read off those columns. Pairing horizontal edges instead
    # is ambiguous: these zones carry a dashed centre line, which is just as
    # dense as a real edge and silently halves the measured height.
    x0 = sum(v_edges[0]) / len(v_edges[0])
    x1 = sum(v_edges[-1]) / len(v_edges[-1])
    edge_cols = set(range(int(x0) - 1, int(x0) + 2)) | set(range(int(x1) - 1, int(x1) + 2))
    ys = sorted({y for (x, y) in pts if x in edge_cols})
    if not ys:
        return []

    out = []
    for grp in _split(set(ys), gap=int(12 * scale)):
        ya, yb = grp[0], grp[-1]
        zw = (x1 - x0) / scale
        zh = (yb - ya) / scale
        if zw < 20 or zh < 20:
            continue
        cx = (x0 + x1) / 2 / scale
        cy = page_h_pt - (ya + yb) / 2 / scale
        out.append({"cx": cx, "cy": cy, "w": zw, "h": zh,
                    "left": cx - zw / 2, "top": cy + zh / 2})
    out.sort(key=lambda z: -z["cy"])
    return out


def circle_at(img, scale, page_h_pt, cx_pt, cy_pt, max_r_pt, targets=None):
    """
    The bottom imprint circle, measured at a centre supplied by the caller.

    The circle is not found by searching. Projection locates the side
    rectangles but not the circle, and every page-wide search for it lands on
    the legend, which is drawn in these same colors. On guide page 2 the circle
    sits exactly midway between the two side zones, which gives its centre
    without searching at all; page 1 places it the same distance below Side 1.

    The diameter is read across the centre row, where nothing else is in range.
    """
    cx_px = cx_pt * scale
    cy_px = (page_h_pt - cy_pt) * scale
    reach = max_r_pt * scale

    pts = _mask_points(img, targets or IMPRINT_RGB)
    d2 = [(((x - cx_px) ** 2 + (y - cy_px) ** 2) ** 0.5, x)
          for (x, y) in pts
          if abs(x - cx_px) <= reach and abs(y - cy_px) <= reach]
    if len(d2) < 40:
        return None

    # Radius as the median distance from the centre. Every drawn pixel of the
    # circle sits at the same distance from it, so the median is unaffected by
    # the dash gaps that make a single-row span unreliable — the widest row can
    # fall in a gap and report a diameter far too small — and unaffected by a
    # stray mark that a bounding box would follow all the way out.
    dists = sorted(d[0] for d in d2)
    r = dists[len(dists) // 2]
    d = 2 * r / scale
    return {"cx": cx_pt, "cy": cy_pt, "d": d, "w": d, "h": d}


def measure_guide(pdf, page, dpi, page_h_pt):
    img = convert_from_path(pdf, dpi=dpi, first_page=page, last_page=page)[0].convert("RGB")
    scale = dpi / 72.0
    return imprint_zones(img, scale, page_h_pt), img


if __name__ == "__main__":
    pdf = sys.argv[1]
    dpi = int(sys.argv[sys.argv.index("--dpi") + 1]) if "--dpi" in sys.argv else 300
    from pdfrw import PdfReader
    pages = PdfReader(pdf).pages
    for pg in (1, 2):
        mb = [float(v) for v in pages[pg-1].MediaBox]
        h_pt = mb[3] - mb[1]
        zones, circ, _ = measure_guide(pdf, pg, dpi, h_pt)
        print(f"--- guide page {pg}  ({mb[2]-mb[0]:.1f} x {h_pt:.1f} pt) ---")
        for i, z in enumerate(zones):
            print(f"  imprint {i}: cx={z['cx']:.2f} cy={z['cy']:.2f} "
                  f"w={z['w']:.2f} h={z['h']:.2f}")
        if circ:
            print(f"  die circle: cx={circ['cx']:.2f} cy={circ['cy']:.2f} d={circ['d']:.2f}")


# ─────────────────────────────────────────────────────────────────────────────
# Press sheets
# ─────────────────────────────────────────────────────────────────────────────
#
# A press sheet prints no die line. Each koozie position is marked only by the
# pair of arcs where the bottom circle meets the two side panels, so a position
# is located by finding those arcs and taking the point between them.
#
# The sheets also carry registration targets (a circle with a crosshair) and a
# caption block. Both are rejected by shape: an arc is a wide, thin, sparse
# stroke, where a target is small and dense and type is small and clustered.

import numpy as np
from scipy import ndimage


def _components(img, dpi):
    """Dark marks on the sheet, as (x0, y0, x1, y1, pixel_count) in pixels."""
    a = np.asarray(img.convert("L"))
    lab, n = ndimage.label(a < 160)
    out = []
    for sl, i in zip(ndimage.find_objects(lab), range(1, n + 1)):
        ys, xs = sl
        out.append((xs.start, ys.start, xs.stop - 1, ys.stop - 1,
                    int((lab[sl] == i).sum())))
    return out


def press_positions(pdf, page, page_w_pt, page_h_pt, dpi=100, expected_gap=None):
    """
    Every koozie position on one press sheet.

    Returns dicts of {cx, cy, gap, vertical} in PDF points, matching the spec
    format: centre of the pair, distance between the two arcs, and whether the
    pair is separated along the sheet's x axis rather than its y axis.
    """
    img = convert_from_path(pdf, dpi=dpi, first_page=page, last_page=page)[0]
    scale = dpi / 72.0
    comps = _components(img, dpi)
    if not comps:
        return []

    arcs = []
    for x0, y0, x1, y1, n in comps:
        w, h = x1 - x0 + 1, y1 - y0 + 1
        long_side, short_side = max(w, h), min(w, h)
        if long_side < 12 * scale:
            continue                       # type, speckles
        if short_side == 0:
            continue
        if long_side / short_side < 2.2:
            continue                       # registration target — too square
        if n > long_side * short_side * 0.45:
            continue                       # filled mark, not a thin stroke
        arcs.append(((x0 + x1) / 2.0, (y0 + y1) / 2.0, w, h))

    used, positions = set(), []

    # Pair arcs on the die's own arc separation, not on nearest neighbour.
    #
    # The two arcs of a position face each other across the bottom circle at a
    # fixed distance — a property of the die, identical on every sheet. On the
    # sparse pages, where two positions sit far apart, the nearest other arc
    # can belong to the neighbouring position instead of the partner, and
    # nearest-neighbour pairing then invents positions halfway between two real
    # ones. Those are the pairs whose gap comes out wildly off the constant.
    if expected_gap:
        tol = expected_gap * 0.18
        cand = [(i, j) for i in range(len(arcs)) for j in range(i + 1, len(arcs))
                if abs(((arcs[i][0]-arcs[j][0])**2 +
                        (arcs[i][1]-arcs[j][1])**2) ** 0.5 / scale
                       - expected_gap) <= tol]
        cand.sort(key=lambda ij: abs(((arcs[ij[0]][0]-arcs[ij[1]][0])**2 +
                                      (arcs[ij[0]][1]-arcs[ij[1]][1])**2) ** 0.5 / scale
                                     - expected_gap))
        pairs = []
        for i, j in cand:
            if i in used or j in used:
                continue
            used.add(i); used.add(j)
            pairs.append((i, j))
    else:
        pairs = []
        for i in range(len(arcs)):
            if i in used:
                continue
            best, bd = None, None
            for j in range(len(arcs)):
                if j == i or j in used:
                    continue
                d = ((arcs[i][0]-arcs[j][0])**2 + (arcs[i][1]-arcs[j][1])**2) ** 0.5
                if bd is None or d < bd:
                    best, bd = j, d
            if best is None:
                continue
            used.add(i); used.add(best)
            pairs.append((i, best))

    for i, j in pairs:
        a, b = arcs[i], arcs[j]
        d = ((a[0]-b[0])**2 + (a[1]-b[1])**2) ** 0.5
        positions.append({
            "cx": (a[0]+b[0]) / 2 / scale,
            "cy": page_h_pt - (a[1]+b[1]) / 2 / scale,
            "gap": d / scale,
            "vertical": bool(abs(a[0]-b[0]) > abs(a[1]-b[1])),
        })

    positions.sort(key=lambda p: (-p["cy"], p["cx"]))
    return positions


def build_spec(pdf, product_id, template_name, dpi=300, press_dpi=100):
    """
    Measure a whole template into the spec press_layout.py consumes.

    Guide pages carry the imprint zones; every page after them is a press
    sheet. Side zones are told apart by position: the upper is Side 1, the
    lower Side 2, and the small one between them is the bottom circle.
    """
    from pdfrw import PdfReader
    pages = PdfReader(pdf).pages
    box = lambda p: [float(v) for v in pages[p-1].MediaBox]

    spec = {
        "_scope": f"CALIBRATED FOR {product_id} ONLY — do not use for any other product",
        "_template_file": template_name,
        "_measured_by": "measure_press_template.py",
        "template": template_name.rsplit(".", 1)[0],
        "product": product_id,
        "guide_pages": {},
        "offsets": {},
        "press_pages": {},
    }

    zones_by_page = {}
    for pg in (1, 2):
        mb = box(pg); h_pt = mb[3] - mb[1]
        zones, circle, _ = measure_guide(pdf, pg, dpi, h_pt)
        big = sorted([z for z in zones if z["w"] > circle["w"] * 1.3],
                     key=lambda z: -z["cy"])
        names = ["side1", "side2"][:len(big)]
        out = {}
        for name, z in zip(names, big):
            out[name] = {"cx": z["cx"], "cy": z["cy"], "w": z["w"], "h": z["h"],
                         "left": z["cx"] - z["w"] / 2, "top": z["cy"] + z["h"] / 2}
        out["bottom"] = {"cx": circle["cx"], "cy": circle["cy"],
                         "w": circle["w"], "h": circle["h"],
                         "left": circle["cx"] - circle["w"] / 2,
                         "top": circle["cy"] + circle["h"] / 2}
        zones_by_page[pg] = out
        spec["guide_pages"][str(pg)] = {"sides": names, "zones": out}

    g2 = zones_by_page[2]
    spec["offsets"] = {
        "circle_d": g2["bottom"]["w"],
        "side_w":   g2["side1"]["w"],
        "side_h":   g2["side1"]["h"],
        "d_side1":  g2["side1"]["cy"] - g2["bottom"]["cy"],
        "d_side2":  g2["side2"]["cy"] - g2["bottom"]["cy"],
    }

    for pg in range(3, len(pages) + 1):
        mb = box(pg); w_pt, h_pt = mb[2] - mb[0], mb[3] - mb[1]
        spec["press_pages"][str(pg)] = {
            "page": [w_pt, h_pt],
            "positions": press_positions(pdf, pg, w_pt, h_pt, dpi=press_dpi),
        }
    return spec


SEAM_RGB = [(0x77, 0x5D, 0xA8)]


def seam_lines(img, scale, page_h_pt):
    """
    The seam lines on a guide page: their x positions and the bands they run in.

    press_layout draws the seams as zig-zag stitching on the proof. Those
    positions were constants calibrated to one product, which put thread down
    the middle of a narrower product's panel — the seams are drawn on the guide
    in their own color, so every product can carry its own.

    Returns {"xs": [x, ...], "bands": [[y_lo, y_hi], ...]} in PDF points, or
    None when the guide draws no seams (a bonded product has none).
    """
    pts = _mask_points(img, SEAM_RGB)
    if not pts:
        return None
    ax0, ax1 = artwork_region(pts, scale, img.size[0])
    pts = {(x, y) for (x, y) in pts if ax0 - 4 <= x <= ax1 + 4}
    if len(pts) < 100:
        return None

    # Vertical runs: columns carrying a lot of ink are the seam lines.
    from collections import Counter
    cols = Counter(x for x, _ in pts)
    busiest = max(cols.values())
    hot = [x for x, n in cols.items() if n >= busiest * 0.35]
    xs = [sum(g) / len(g) / scale for g in _split(set(hot), gap=int(6 * scale))]

    # Each side panel is one band; the gap between them is the bottom circle.
    ys = sorted({y for _, y in pts})
    # Two bands, one per side panel. Short runs beside the bottom circle also
    # register as seam, so the panels are taken as the two longest rather than
    # by a length threshold, which would need a different value per product.
    bands = []
    for g in _split(set(ys), gap=int(25 * scale)):
        lo = page_h_pt - g[-1] / scale
        hi = page_h_pt - g[0] / scale
        bands.append([round(lo, 2), round(hi, 2)])
    bands.sort(key=lambda b: -(b[1] - b[0]))
    bands = sorted(bands[:2], key=lambda b: -b[0])

    # Clipped to the die panels. The seam colour also marks the guide's own
    # labels and rules, which sit above and below the product, so an unclipped
    # band runs stitching off the end of the panel and the proof shows thread
    # floating in space beside the koozie.
    panels = die_panels(img, scale, page_h_pt)
    if panels and len(panels) == len(bands):
        bands = [[max(b[0], p[0]), min(b[1], p[1])]
                 for b, p in zip(bands, panels)]

    return {"xs": [round(x, 2) for x in xs], "bands": [[round(a, 2), round(b, 2)] for a, b in bands]}


def die_panels(img, scale, page_h_pt):
    """The y extent of each side panel of the die, top panel first."""
    pts = _mask_points(img, DIE_RGB)
    if not pts:
        return None
    ax0, ax1 = artwork_region(pts, scale, img.size[0])
    pts = {(x, y) for (x, y) in pts if ax0 - 4 <= x <= ax1 + 4}
    if not pts:
        return None
    spans = {}
    for x, y in pts:
        lo, hi = spans.get(y, (x, x))
        spans[y] = (min(lo, x), max(hi, x))
    widest = max(hi - lo for lo, hi in spans.values())
    # Panel rows span the full panel width; the circle between them does not.
    wide = {y for y, (lo, hi) in spans.items() if (hi - lo) >= widest * 0.90}
    groups = _split(wide, gap=int(10 * scale))
    groups.sort(key=len, reverse=True)
    out = [[page_h_pt - g[-1] / scale, page_h_pt - g[0] / scale] for g in groups[:2]]
    return sorted(out, key=lambda b: -b[0]) if len(out) == 2 else None


def fill_arcless_pages(pdf, press_pages, dpi=100):
    """
    Give sheets that carry no die arcs the positions of the sheet they pair with.

    Some templates draw the arcs on only one sheet of a pair — both are the same
    physical layout, printed twice — and without this those sheets come out
    blank, so half the run prints nothing.

    The partner is the adjacent sheet of the same size. Matching on registration
    targets instead looks more principled and is not: the dashed rules on these
    sheets break into evenly spaced fragments that are indistinguishable from
    targets by shape, and on some pairs those fragments sit a few points apart,
    so the comparison fails on sheets that are plainly a pair.

    Returns the pages and a list of (page, donor) so the pairing can be checked
    rather than taken on trust.
    """
    filled = []
    for pn, v in press_pages.items():
        if v["positions"]:
            continue
        for cand in (str(int(pn) + 1), str(int(pn) - 1)):
            d = press_pages.get(cand)
            if d and d["positions"] and d["page"] == v["page"]:
                v["positions"] = [dict(p) for p in d["positions"]]
                v["positions_from"] = cand
                filled.append((pn, cand))
                break
    return press_pages, filled


def die_regions(img, scale, page_h_pt):
    """
    Where the die's two side panels and bottom circle sit on a guide page.

    Recorded in the spec so the flat proof can crop those areas straight out of
    a rendered proof page. Cropping gives the real thing — exact die outline,
    material fill and stitching, already correct — where redrawing the shapes
    would be a second approximation of geometry that is measured once already.

    Returns {"x": [x0, x1], "panels": [[lo, hi], [lo, hi]], "circle_cy": y}
    in PDF points, top panel first, or None when the die cannot be read.
    """
    pts = _mask_points(img, DIE_RGB)
    if not pts:
        return None
    ax0, ax1 = artwork_region(pts, scale, img.size[0])
    pts = {(x, y) for (x, y) in pts if ax0 - 4 <= x <= ax1 + 4}
    if not pts:
        return None

    spans = {}
    for x, y in pts:
        lo, hi = spans.get(y, (x, x))
        spans[y] = (min(lo, x), max(hi, x))
    widest = max(hi - lo for lo, hi in spans.values())

    wide = {y for y, (lo, hi) in spans.items() if (hi - lo) >= widest * 0.90}
    groups = _split(wide, gap=int(10 * scale))
    groups.sort(key=len, reverse=True)
    if len(groups) < 2:
        return None
    panels = sorted(
        ([page_h_pt - g[-1] / scale, page_h_pt - g[0] / scale] for g in groups[:2]),
        key=lambda b: -b[0])

    xs = [lo for y, (lo, hi) in spans.items() if y in wide]
    xe = [hi for y, (lo, hi) in spans.items() if y in wide]
    x0, x1 = min(xs) / scale, max(xe) / scale

    # The circle sits between the panels.
    circle_cy = (panels[0][0] + panels[1][1]) / 2
    return {"x": [round(x0, 2), round(x1, 2)],
            "panels": [[round(a, 2), round(b, 2)] for a, b in panels],
            "circle_cy": round(circle_cy, 2)}
