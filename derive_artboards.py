"""
derive_artboards.py — name every press sheet, and record it in its spec.

Run once per template, by hand, when adding or re-measuring a product. It is a
developer tool and is excluded from the deploy; the names it writes are what
the app actually uses.

The naming rule, as the press floor states it:

    23" x 33"  ->  STRYKER          16" x 23"  ->  DISCO
    12" x 14"  ->  DBC

    a STRYKER sheet printing two different sides at once takes the suffix
    "2 Sides Diff"; otherwise "1 Side"

    any sheet carrying the half-moon arcs that align the bottom imprint takes
    a further "- BTM"

Two of those three come off the file without judgement. The page size is the
page size. The arcs are found by the same detector that located the imprint
positions in the first place — a sheet with no arcs yields no positions, so
"did this page have arcs" is already answered by the measuring pass.

The third needs a decision, and the geometry makes it: on a sheet printing two
different sides, both panels of one koozie straddle the sheet's centre line, so
every position sits on that centre. On a one-side sheet the positions are
packed into columns off-centre instead. That is checked here rather than
assumed, and the result is written into the spec where a human can correct it.

Verified against Numo's own internal file for the 1080, where all eight names
come out identical to the artboards in that file.
"""

import json
import re
import sys
from pathlib import Path

from pdfrw import PdfReader

HERE = Path(__file__).parent.resolve()

SIZE_PREFIX = {(23, 33): "STRYKER", (16, 23): "DISCO", (12, 14): "DBC"}

# How close to the sheet's centre line a position must sit to count as centred.
# The measured positions scatter by a few points; 25 pt is a third of an inch,
# far tighter than the gap between a centred layout and a columned one.
CENTRE_TOL_PT = 25.0


def page_sizes(template_pdf):
    out = {}
    for i, p in enumerate(PdfReader(str(template_pdf)).pages, 1):
        mb = [float(v) for v in p.MediaBox]
        out[i] = (mb[2] - mb[0], mb[3] - mb[1])
    return out


def arcs_by_page(template_pdf, pages, sizes):
    """
    Which sheets carry the half-moon arcs, measured not assumed.

    press_positions() locates a position by finding the two arcs that face each
    other across the bottom circle, so a sheet without them yields nothing.
    That makes the position detector a direct test for the marks themselves.
    """
    import measure_press_template as M
    out = {}
    for pn in pages:
        w, h = sizes[pn]
        try:
            out[pn] = len(M.press_positions(str(template_pdf), pn, w, h, dpi=100)) > 0
        except Exception as e:
            print(f"  ! page {pn}: arc detection failed ({e}); assuming none")
            out[pn] = False
    return out


def name_for(size_pt, positions, has_arcs, offsets=None):
    """
    The sheet's name.

    Both suffixes describe features of a koozie, and neither is applied to a
    product that does not have them. A flat product prints one panel from one
    side and has no bottom disc, so its positions sitting on the sheet's centre
    line means only that they are centred — not that two different sides are
    being printed at once — and whatever marks the arc detector found on it are
    not bottom-alignment half-moons. Without these guards the tote's single
    front-panel sheet comes out called "STRYKER 2 Sides Diff - BTM", which
    describes a koozie and would send the wrong file to the floor.
    """
    offsets = offsets or {}
    w_in = round(size_pt[0] / 72)
    h_in = round(size_pt[1] / 72)
    prefix = SIZE_PREFIX.get((w_in, h_in))
    if not prefix:
        return None
    name = prefix

    two_sided_product = (abs(float(offsets.get("d_side1") or 0)) > 1
                         and abs(float(offsets.get("d_side2") or 0)) > 1)
    has_bottom = float(offsets.get("circle_d") or 0) > 1

    if prefix == "STRYKER" and two_sided_product:
        centre = size_pt[0] / 2.0
        centred = sum(1 for p in positions
                      if abs(p["cx"] - centre) <= CENTRE_TOL_PT)
        name += " 2 Sides Diff" if (positions and centred == len(positions)) \
            else " 1 Side"
    if has_arcs and has_bottom:
        name += " - BTM"
    return name


def clear_spot_near_slug(template_pdf, page, cap, page_h_pt, name_pt=(180, 34),
                         dpi=150):
    """
    Where on this sheet the name can be printed without landing on anything.

    Measured against ink rather than against text. Part of what the templates
    put in the slug is outlined vector rather than live text — pdftotext cannot
    see the product name on some sheets at all — so a placement worked out from
    word boxes lands cleanly on one sheet and straight through the product name
    on the next. Rendering the page and looking for empty pixels does not care
    how the text was made.

    Steps outward from the ink caption in the direction its own text reads as
    "down", and returns the first position where a name-sized box is empty.
    Returns (x_pt, y_pt, rot) in PDF space, or None if nothing clear is found.

    The box it looks for is deliberately taller than the text that goes in it.
    A box just big enough finds the gap BETWEEN two lines of the slug — empty,
    technically, and the name then prints jammed against the product name above
    it. Asking for room on both sides pushes the search past the whole block.
    """
    from pdf2image import convert_from_path
    import numpy as np

    img = convert_from_path(str(template_pdf), dpi=dpi,
                            first_page=page, last_page=page)[0].convert("L")
    # 150 dpi, and a threshold that counts light grey as ink. At 50 dpi the
    # thin type in these slugs renders at about grey 216 — lighter than any
    # sensible ink threshold — so the scan could not see the product name it
    # was supposed to step past, and placed the sheet name on top of it.
    ink = np.asarray(img) < 245
    s = dpi / 72.0
    H, W = ink.shape

    # The caption's centre, in PDF space (pdftotext measures from the top).
    cx = (cap["x0"] + cap["x1"]) / 2
    cy = page_h_pt - (cap["y0"] + cap["y1"]) / 2
    across = (cap["y1"] - cap["y0"]) if cap["orient"] in (0, 180) \
        else (cap["x1"] - cap["x0"])

    # "Down" in the caption's own reading direction, as a PDF-space vector.
    dirs = {0: (0, -1), 180: (0, 1), 90: (1, 0), 270: (-1, 0)}
    dx, dy = dirs.get(cap["orient"], (0, -1))
    nw, nh = name_pt
    if cap["orient"] in (90, 270):
        nw, nh = nh, nw

    step = 4.0
    for k in range(1, 120):
        off = across / 2 + 8 + k * step
        px, py = cx + dx * off, cy + dy * off
        x0 = int((px - nw / 2) * s); x1 = int((px + nw / 2) * s)
        y0 = int((page_h_pt - py - nh / 2) * s)
        y1 = int((page_h_pt - py + nh / 2) * s)
        if x0 < 0 or y0 < 0 or x1 >= W or y1 >= H:
            break
        if not ink[y0:y1, x0:x1].any():
            return round(px, 2), round(py, 2), cap["orient"]
    return None


def derive(spec_path, template_pdf, write=False):
    spec = json.loads(Path(spec_path).read_text())
    pages = sorted(int(p) for p in spec.get("press_pages", {}))
    if not pages:
        print(f"{Path(spec_path).name}: no press pages")
        return
    sizes = page_sizes(template_pdf)
    arcs = arcs_by_page(template_pdf, pages, sizes)

    import press_layout as PL
    # The ink caption ("SPOT COLOR") anchors the search for clear space.
    # find_spot_color_labels became find_template_labels, which returns every
    # caption on the sheet; the spot one is the one this needs.
    caps = PL.find_template_labels(str(template_pdf), max(pages))
    spots = {}
    for pn in pages:
        cap = (caps.get(pn) or caps.get(str(pn)) or {}).get("spot")
        if cap:
            spot = clear_spot_near_slug(template_pdf, pn, cap, sizes[pn][1])
            if spot:
                spots[pn] = spot

    print(f"\n=== {spec.get('product')}")
    unknown = []
    for pn in pages:
        pg = spec["press_pages"][str(pn)]
        nm = name_for(sizes[pn], pg.get("positions") or [], arcs[pn],
                      offsets=spec.get("offsets"))
        w_in, h_in = round(sizes[pn][0] / 72), round(sizes[pn][1] / 72)
        if nm is None:
            unknown.append(pn)
            nm = f"SHEET {w_in}x{h_in}"
        spot = spots.get(pn)
        print(f"  p{pn:<3} {w_in:>2}x{h_in:<2}  {nm:<34} "
              f"{'name at %.0f,%.0f rot %d' % spot if spot else 'NO CLEAR SPOT'}")
        if write:
            # The name itself is only recorded if the spec has none: these are
            # read off Numo's production files, and a derived guess must never
            # quietly replace one that was.
            pg.setdefault("artboard", nm)
            # Typed or derived, every name follows the machine / - BTM rule;
            # the layout is kept beside it for choosing sheets.
            pg.setdefault("_artboard_as_drawn", pg["artboard"])
            pg["machine"], pg["layout"] = parse_name(pg["_artboard_as_drawn"])
            pg["artboard"] = normalize_name(pg["artboard"], bool(arcs[pn]))
            if spot:
                pg["name_at"] = list(spot)
    if unknown:
        print(f"  ! pages {unknown} are a size the rule does not name")
    if write:
        Path(spec_path).write_text(json.dumps(spec, indent=1) + "\n")
        print(f"  written to {Path(spec_path).name}")


def parse_name(name):
    """
    Split a sheet name into (machine, layout).

    layout is "1side", "2diff" or None for a machine with one layout. Reads
    every spelling the templates have used: "STRYKER 1 side", "STRYKER 2 Sides
    Diff", "DBG 2 Side and Bottom", "STRYKER 1 Side copy", "... - BTM".
    """
    n = re.sub(r"\s+copy\b", "", name or "", flags=re.I).strip()
    n = re.sub(r"\s*-\s*BTM\s*$", "", n, flags=re.I).strip()
    layout = None
    m = re.search(r"\b([12])\s+Sides?\b.*$", n, re.I)
    if m:
        layout = "2diff" if m.group(1) == "2" else "1side"
        n = n[:m.start()].strip()
    return n, layout


def normalize_name(name, has_arcs):
    """
    The floor's naming rule: the machine, and "- BTM" on the sheet carrying the
    half-moon arcs that line up the bottom imprint. Nothing else — which layout
    a sheet is (1 side / 2 sides different) is recorded separately and used to
    choose the sheet, not printed in its name.
    """
    machine, _ = parse_name(name)
    return f"{machine} - BTM" if has_arcs else machine


def enforce_btm(spec_path, template_pdf, write=False):
    """Apply normalize_name to every press sheet. Flat goods (no bottom) are skipped."""
    spec = json.loads(Path(spec_path).read_text())
    if not float((spec.get("offsets") or {}).get("circle_d") or 0):
        print(f"{spec.get('product')}: no bottom circle — BTM rule does not apply")
        return
    pages = sorted(int(p) for p in spec.get("press_pages", {}))
    arcs = arcs_by_page(template_pdf, pages, page_sizes(template_pdf))
    print(f"\n=== {spec.get('product')}")
    for pn in pages:
        pg = spec["press_pages"][str(pn)]
        old = pg.get("_artboard_as_drawn") or pg.get("artboard") or ""
        machine, layout = parse_name(old)
        new = normalize_name(old, bool(arcs[pn]))
        if write:
            pg["_artboard_as_drawn"] = old
            pg["machine"] = machine
            pg["layout"] = layout
        print(f"  p{pn:<3} {old:<38} -> {new:<16} layout={layout}")
        if write:
            pg["artboard"] = new
    if write:
        Path(spec_path).write_text(json.dumps(spec, indent=1) + "\n")


if __name__ == "__main__":
    import press_layout as PL
    write = "--write" in sys.argv
    want = [a for a in sys.argv[1:] if not a.startswith("-")]
    for pid, cfg in PL.PRESS_TEMPLATES.items():
        if want and pid not in want:
            continue
        if not PL.has_press_template(pid):
            continue
        spec = Path(cfg["spec"])
        if str(spec) in {str(Path(c["spec"])) for p, c in PL.PRESS_TEMPLATES.items()
                         if p != pid and list(PL.PRESS_TEMPLATES).index(p) <
                         list(PL.PRESS_TEMPLATES).index(pid)}:
            continue            # twins sharing one spec: derive it once
        if "--btm" in sys.argv:
            enforce_btm(spec, cfg["template"], write=write)
        else:
            derive(spec, cfg["template"], write=write)
    if not write:
        print("\n(dry run — pass --write to record these in the specs)")
