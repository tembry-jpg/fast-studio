"""
This Is Fast: a customer's filled-in art template, opened as a job.

Customers send their art back on our own TIF template: the art sits in the
Side 1 / Side 2 panels and the bottom circle of the die, often over a die
filled in the koozie color, with all of the template's guides still there.
Art is always on page 1; the template on that page varies by item and layout
(1 side / 2 sides).

  1. Which template. Page 1 is compared against the blank guide pages of every
     TIF press template (press/*.pdf, the same guide pages customers get). The
     one sharing the most identical shapes wins — the title text isn't needed.
     The same comparison gives the page's offset from the blank, in case the
     customer's file moved the artboard.
  2. What's theirs. Every shape that matches the blank template is furniture
     (guides, arrows, labels, die line) and is dropped. Of what's left, a fill
     covering the whole die is the koozie color; the rest is art.
  3. Where. Each piece of art goes to the panel or circle its center is in:
     upper panel Side 1, lower panel Side 2 (printed head-down on the die, so
     turned upright here), circle the Bottom.
  4. Each location becomes its own vector PDF, and its size and position in
     the imprint area are measured, so the job opens at the size the customer
     drew it.

The result is a job snapshot in the same shape a digital proof carries, so the
configurator opens it through "Revise from proof" like any other job.
"""
import json
import math
import shutil
import subprocess
import tempfile
from collections import Counter
from pathlib import Path

import pikepdf
from pikepdf import Operator

HERE = Path(__file__).parent.resolve()

_PATH_PAINT = {"f", "f*", "F", "B", "B*", "b", "b*", "S", "s"}
_TEXT_SHOW = {"Tj", "TJ", "'", '"'}


def _mul(a, b):
    return [a[0] * b[0] + a[1] * b[2], a[0] * b[1] + a[1] * b[3],
            a[2] * b[0] + a[3] * b[2], a[2] * b[1] + a[3] * b[3],
            a[4] * b[0] + a[5] * b[2] + b[4], a[4] * b[1] + a[5] * b[3] + b[5]]


def _walk(owner, res, ctm, out, owner_key="page", seen_stack=()):
    """Every painted thing in a content stream, recursing into forms: paths,
    text blocks and images, with the owner stream and op index to find it
    again, its bounding box on the page, and its paint op."""
    try:
        ops = pikepdf.parse_content_stream(owner)
    except Exception:
        return out
    res = res if res is not None else pikepdf.Dictionary()
    stack, gs = [], {"ctm": ctm}
    path = []
    tb = None      # current text block: {"start", "pts", "text"}
    tm = [1, 0, 0, 1, 0, 0]; tlm = [1, 0, 0, 1, 0, 0]; lead = 0.0; fsize = 0.0

    def pt(x, y, m=None):
        m = m or gs["ctm"]
        return (x * m[0] + y * m[2] + m[4], x * m[1] + y * m[3] + m[5])

    for i, (a, o) in enumerate(ops):
        o = str(o)
        try:
            if o == "q":
                stack.append(dict(gs))
            elif o == "Q":
                gs = stack.pop() if stack else gs
            elif o == "cm":
                gs["ctm"] = _mul([float(x) for x in a], gs["ctm"])
            elif o in ("g", "rg", "k", "sc", "scn"):
                # The fill colour, to tell the template's own labels (outlined
                # by the customer's app) from art drawn over them.
                gs["fc"] = (gs.get("cs", ""),) + tuple(round(float(x), 3) for x in a if not isinstance(x, pikepdf.Name))
            elif o == "cs":
                gs["cs"] = str(a[0]) if a else ""
            elif o in ("m", "l"):
                path.append(pt(float(a[0]), float(a[1])))
            elif o == "c":
                path += [pt(float(a[0]), float(a[1])), pt(float(a[2]), float(a[3])), pt(float(a[4]), float(a[5]))]
            elif o in ("v", "y"):
                path += [pt(float(a[0]), float(a[1])), pt(float(a[2]), float(a[3]))]
            elif o == "re":
                x, y, w, h = map(float, a)
                path += [pt(x, y), pt(x + w, y + h), pt(x, y + h), pt(x + w, y)]
            elif o in _PATH_PAINT:
                if path:
                    xs = [p[0] for p in path]; ys = [p[1] for p in path]
                    out.append({"kind": "path", "owner": owner_key, "idx": i, "op": o,
                                "bbox": (min(xs), min(ys), max(xs), max(ys)), "n": len(path), "fc": gs.get("fc")})
                path = []
            elif o == "n":
                path = []
            elif o == "BT":
                tb = {"start": i, "pts": [], "text": ""}
                tm = [1, 0, 0, 1, 0, 0]; tlm = [1, 0, 0, 1, 0, 0]
            elif o == "Tf" and len(a) == 2:
                fsize = float(a[1])
            elif o == "TL":
                lead = float(a[0])
            elif o in ("Td", "TD"):
                tx, ty = float(a[0]), float(a[1])
                if o == "TD":
                    lead = -ty
                tlm = _mul([1, 0, 0, 1, tx, ty], tlm); tm = list(tlm)
            elif o == "Tm":
                tlm = [float(x) for x in a]; tm = list(tlm)
            elif o == "T*":
                tlm = _mul([1, 0, 0, 1, 0, -lead], tlm); tm = list(tlm)
            elif o in _TEXT_SHOW and tb is not None:
                m = _mul(tm, gs["ctm"])
                s = a[-1]
                if isinstance(s, pikepdf.Array):
                    txt = b"".join(bytes(x) for x in s if isinstance(x, pikepdf.String))
                else:
                    txt = bytes(s) if isinstance(s, pikepdf.String) else b""
                tb["text"] += txt.decode("latin-1", "replace")
                w = max(1.0, fsize * 0.55 * max(1, len(txt)))
                tb["pts"] += [pt(0, 0, m), pt(w, fsize, m)]
            elif o == "ET" and tb is not None:
                if tb["pts"]:
                    xs = [p[0] for p in tb["pts"]]; ys = [p[1] for p in tb["pts"]]
                    out.append({"kind": "text", "owner": owner_key, "idx": tb["start"], "end": i,
                                "op": "BT", "text": tb["text"].strip(), "fc": gs.get("fc"),
                                "bbox": (min(xs), min(ys), max(xs), max(ys)), "n": 0})
                tb = None
            elif o == "Do":
                nm = str(a[0])
                x = (res.get("/XObject") or {}).get(nm)
                if x is None:
                    continue
                if x.get("/Subtype") == "/Form":
                    if x.objgen in seen_stack:
                        continue
                    m = _mul([float(v) for v in x.get("/Matrix", [1, 0, 0, 1, 0, 0])], gs["ctm"])
                    _walk(x, x.get("/Resources") or res, m, out, owner_key=f"form:{x.objgen}",
                          seen_stack=seen_stack + (x.objgen,))
                else:
                    c = [pt(0, 0), pt(1, 1), pt(0, 1), pt(1, 0)]
                    xs = [p[0] for p in c]; ys = [p[1] for p in c]
                    out.append({"kind": "image", "owner": owner_key, "idx": i, "op": "Do",
                                "bbox": (min(xs), min(ys), max(xs), max(ys)), "n": 0})
        except Exception:
            continue
    return out


def _page_objects(pdf, page_index=0):
    pg = pdf.pages[page_index]
    return _walk(pg, pg.obj.get("/Resources"), [1, 0, 0, 1, 0, 0], [])


def _size_key(r):
    b = r["bbox"]
    return (r["kind"], round(b[2] - b[0]), round(b[3] - b[1]), r.get("text", "") if r["kind"] == "text" else "")


def _offset(cust, blank):
    """The shift that lines the customer's page up with the blank template:
    the most common displacement between shapes of the same size."""
    by = {}
    for r in blank:
        by.setdefault(_size_key(r), []).append(r["bbox"])
    votes = Counter()
    for r in cust:
        for b in by.get(_size_key(r), [])[:6]:
            votes[(round((r["bbox"][0] - b[0]) * 2) / 2, round((r["bbox"][1] - b[1]) * 2) / 2)] += 1
    if not votes:
        return (0.0, 0.0), 0
    (dx, dy), _ = votes.most_common(1)[0]
    return (dx, dy), votes[(dx, dy)]


def _match_key(r, off=(0, 0)):
    b = r["bbox"]
    k = (r["kind"],) + tuple(round(v) for v in (b[0] - off[0], b[1] - off[1], b[2] - off[0], b[3] - off[1]))
    return k + ((r.get("text", ""),) if r["kind"] == "text" else ())


# This Is Fast items that aren't one-color screen print, so have no press
# template to read the customer's template from: the blank template the
# customer fills in, and where its imprint area is on it (page coordinates,
# PDF points, y up). "rot": how far the art is turned on the template - 90
# means it reads bottom to top, as on the pen, and is turned upright here.
EXTRA_TEMPLATES = {
    # The 24 HR Jotter. The gray area is the Mimaki jig's box, 4.28" x 0.25"
    # (308.16 x 18 pt), drawn up the pen.
    "0837-24HR-IMP": {
        "template": "press/tif/0837-24HR-IMP.pdf",
        "guide_pages": {"1": {"sides": ["side1"], "zones": {
            "side1": {"cx": 475.26, "cy": 475.505, "w": 18.0, "h": 308.16, "rot": 90}}}},
    },
}


def _templates():
    """(pid, template pdf, spec, guide page number) for every TIF item with a
    press template on the server, and the ones in EXTRA_TEMPLATES."""
    import press_layout
    from products import is_screenprint, PRODUCTS
    out = []
    for pid, t in EXTRA_TEMPLATES.items():
        tpl = HERE / t["template"]
        if pid in PRODUCTS and tpl.exists():
            spec = {"product": pid, "guide_pages": t["guide_pages"]}
            for pno in sorted(t["guide_pages"].keys(), key=int):
                out.append((pid, tpl, spec, pno))
    for pid, t in press_layout.PRESS_TEMPLATES.items():
        if pid not in PRODUCTS or not is_screenprint(pid):
            continue
        tpl, spec_path = Path(t["template"]), Path(t["spec"])
        if not tpl.exists() or not spec_path.exists():
            continue
        spec = json.loads(spec_path.read_text())
        for pno in sorted((spec.get("guide_pages") or {}).keys(), key=int):
            out.append((pid, tpl, spec, pno))
    return out


_BLANK_CACHE = {}


def _blank_objects(tpl, pno):
    key = (str(tpl), pno)
    if key not in _BLANK_CACHE:
        with pikepdf.open(str(tpl)) as pdf:
            _BLANK_CACHE[key] = _page_objects(pdf, int(pno) - 1)
    return _BLANK_CACHE[key]


_OWNERS = {}


def _owners():
    """For every template shape (by kind and size): which items' templates
    have it. Most of a TIF template is the same on every item - the legend,
    the arrows, the instructions - so only the shapes one item alone has
    (its die line, its title) can tell the items apart."""
    if not _OWNERS:
        for pid, tpl, spec, pno in _templates():
            for r in _blank_objects(tpl, pno):
                _OWNERS.setdefault(_size_key(r), set()).add(pid)
    return _OWNERS


def identify(pdf_path, page_index=0, hint_pid=None):
    """Which TIF template a page of the file is filled in on: (pid, spec,
    guide page, offset, customer objects, template objects) or None.

    Each template is scored twice: on the shapes only that item's template
    has (its die line - what tells a 0070 from a 1080), and on all its
    shapes. The item-only score decides; the overall one breaks ties and
    must clear the bar. `hint_pid` (the item open in the configurator) wins
    when it matches about as well as the best."""
    with pikepdf.open(str(pdf_path)) as pdf:
        if page_index >= len(pdf.pages):
            return None
        cust = _page_objects(pdf, page_index)
    owners = _owners()
    cands = []
    for pid, tpl, spec, pno in _templates():
        blank = _blank_objects(tpl, pno)
        if not blank:
            continue
        off, _ = _offset(cust, blank)
        bk = {_match_key(r) for r in blank}
        hits = sum(1 for r in cust if _match_key(r, off) in bk)
        score = hits / max(1, len(bk))
        own = {_match_key(r) for r in blank if owners.get(_size_key(r)) == {pid}}
        own_score = (sum(1 for r in cust if _match_key(r, off) in own) / len(own)) if own else 0.0
        cands.append((own_score, score, pid, spec, pno, off, blank))
    cands = [c for c in cands if c[1] >= 0.35]
    if not cands:
        return None
    cands.sort(key=lambda c: (round(c[0], 3), c[1]), reverse=True)
    best = cands[0]
    if hint_pid:
        h = next((c for c in cands if c[2] == hint_pid), None)
        if h and h[0] >= best[0] - 0.1 and h[1] >= best[1] - 0.1:
            best = h
    own_score, score, pid, spec, pno, off, blank = best
    return {"pid": pid, "spec": spec, "page": pno, "offset": off, "score": score,
            "objects": cust, "blank": blank}


def _regions(spec, pno):
    """Imprint regions on the guide page, in template coordinates: rect or
    circle, the zone's center there, and how the art sits (0 or 180)."""
    g = spec["guide_pages"][pno]
    zones = g.get("zones") or {}
    die = (spec.get("die_regions") or {}).get(pno)
    regs = {}
    if die:
        x0, x1 = die["x"]
        (u0, u1), (l0, l1) = die["panels"][0], die["panels"][1]
        cy = die.get("circle_cy")
        cx = (x0 + x1) / 2
        z1 = zones.get("side1") or {}
        regs["side1"] = {"shape": "rect", "box": (x0, u0, x1, u1), "rot": 0,
                         "zone": (z1.get("cx", cx), z1.get("cy", (u0 + u1) / 2))}
        z2 = zones.get("side2")
        if z2:
            zc2 = (z2["cx"], z2["cy"])
        else:       # the 1-side layout: Side 2 mirrors Side 1 through the die centre
            zc2 = (2 * cx - regs["side1"]["zone"][0], 2 * (cy or (u0 + l1) / 2) - regs["side1"]["zone"][1])
        regs["side2"] = {"shape": "rect", "box": (x0, l0, x1, l1), "rot": 180, "zone": zc2}
        d = float((spec.get("offsets") or {}).get("circle_d") or 0)
        zb = zones.get("bottom") or {}
        if d and cy:
            r = d / 2
            regs["bottom"] = {"shape": "circle", "box": (cx - r, cy - r, cx + r, cy + r), "rot": 0,
                              "zone": (zb.get("cx", cx), zb.get("cy", cy)), "r": r}
    else:          # flat items (the tote): the zone itself, with room around it
        for sid, z in zones.items():
            m = 0.08 * max(z["w"], z["h"])
            regs[sid] = {"shape": "rect", "rot": int(z.get("rot") or 0), "zone": (z["cx"], z["cy"]),
                         "box": (z["cx"] - z["w"] / 2 - m, z["cy"] - z["h"] / 2 - m,
                                 z["cx"] + z["w"] / 2 + m, z["cy"] + z["h"] / 2 + m)}
    return regs, die


def _region_of(center, regs):
    x, y = center
    for sid, r in regs.items():
        x0, y0, x1, y1 = r["box"]
        if r["shape"] == "circle":
            cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
            if math.hypot(x - cx, y - cy) <= r["r"] * 1.02:
                return sid
        elif x0 <= x <= x1 and y0 <= y <= y1:
            return sid
    return None


def _rewrite(pdf, keep_fn, page_index=0):
    """Blank out every painted thing keep_fn rejects (paths get 'n', text
    blocks and images are removed). A form used more than once keeps a shape
    if any use keeps it."""
    objs = _page_objects(pdf, page_index)
    drop = {}
    for r in objs:
        k = (r["owner"], r["idx"])
        drop.setdefault(k, [r, True])
        if keep_fn(r):
            drop[k][1] = False
    by_owner = {}
    for (owner, idx), (r, d) in drop.items():
        if d:
            by_owner.setdefault(owner, []).append(r)
    streams = {"page": pdf.pages[page_index]}
    def find_forms(res, seen):
        for _, x in ((res or {}).get("/XObject") or {}).items():
            if x.get("/Subtype") == "/Form" and x.objgen not in seen:
                seen.add(x.objgen)
                streams[f"form:{x.objgen}"] = x
                find_forms(x.get("/Resources"), seen)
    find_forms(pdf.pages[page_index].obj.get("/Resources"), set())
    for owner, recs in by_owner.items():
        st = streams.get(owner)
        if st is None:
            continue
        ops = pikepdf.parse_content_stream(st)
        kill, nop = set(), set()
        for r in recs:
            if r["kind"] == "text":
                kill.update(range(r["idx"], r["end"] + 1))
            elif r["kind"] == "image":
                kill.add(r["idx"])
            else:
                nop.add(r["idx"])
        new = []
        for i, (a, o) in enumerate(ops):
            if i in kill:
                continue
            new.append(([], Operator("n")) if i in nop else (a, o))
        data = pikepdf.unparse_content_stream(new)
        if owner == "page":
            pdf.pages[page_index].obj.Contents = pdf.make_stream(data)
        else:
            st.write(data)


def _crop(src_pdf, box, rot, out_path, page_index=0):
    """A new one-page PDF of `box` (page coordinates) from src_pdf's page 1,
    turned 180 when rot says so (90: art reading bottom to top, turned a
    quarter clockwise), the art upright and at its true size."""
    x0, y0, x1, y1 = box
    w, h = x1 - x0, y1 - y0
    if rot == 90:
        w, h = h, w
    with pikepdf.open(str(src_pdf)) as src:
        new = pikepdf.new()
        form = new.copy_foreign(src.pages[page_index].as_form_xobject())
        page = new.add_blank_page(page_size=(w, h))
        page.obj.Resources = pikepdf.Dictionary(XObject=pikepdf.Dictionary(Fm0=form))
        if rot == 180:
            cm = f"-1 0 0 -1 {x1:.4f} {y1:.4f} cm"
        elif rot == 90:
            # (x, y) -> (y - y0, x1 - x): what read upwards reads left to right.
            cm = f"0 -1 1 0 {-y0:.4f} {x1:.4f} cm"
        else:
            cm = f"1 0 0 1 {-x0:.4f} {-y0:.4f} cm"
        page.obj.Contents = new.make_stream(
            f"q 0 0 {w:.4f} {h:.4f} re W n {cm} /Fm0 Do Q".encode())
        new.save(str(out_path))


def _render_rgba(pdf_path, dpi=72, page=1):
    from PIL import Image
    with tempfile.TemporaryDirectory() as d:
        subprocess.run(["pdftocairo", "-png", "-transp", "-singlefile", "-r", str(dpi),
                        "-f", str(page), "-l", str(page),
                        str(pdf_path), str(Path(d) / "r")], check=True, capture_output=True, timeout=60)
        return Image.open(Path(d) / "r.png").convert("RGBA").copy()


def _main_color(img):
    """The most common opaque color, to the nearest 8 levels."""
    px = [p[:3] for p in img.getdata() if p[3] > 200]
    if not px:
        return None
    c = Counter((r // 8 * 8, g // 8 * 8, b // 8 * 8) for r, g, b in px)
    return "#%02X%02X%02X" % c.most_common(1)[0][0]


PAGES_TO_CHECK = 3     # art is on page 1 or 2; press sheets follow


def extract(pdf_path, work_dir, filename_stem="template", hint_pid=None):
    """Open a filled TIF template as a job snapshot, or None if it isn't one.
    Location art files are written to work_dir. The art is on page 1 or 2
    (some templates have two placement pages before the press sheets): each
    of the first pages is read and the one carrying the most art is used."""
    best, empty_pid = None, None
    for pi in range(PAGES_TO_CHECK):
        try:
            plan = _plan(pdf_path, pi, hint_pid)
        except Exception as e:
            print(f"⚠️ TIF import: page {pi + 1} not read: {e}")
            continue
        if plan is None:
            continue
        if not plan["placed"]:
            empty_pid = empty_pid or plan["pid"]
            continue
        n = sum(len(v) for v in plan["placed"].values())
        if best is None or n > best[0]:
            best = (n, plan)
    if best is None:
        return {"pid": empty_pid, "empty": True} if empty_pid else None
    return _build(best[1], pdf_path, work_dir, filename_stem)


def _plan(pdf_path, page_index, hint_pid=None):
    """Identify one page and sort its art into locations (no files yet)."""
    from products import PRODUCTS
    info = identify(pdf_path, page_index, hint_pid)
    if not info:
        return None
    pid, spec, pno, off = info["pid"], info["spec"], info["page"], info["offset"]
    prod = PRODUCTS[pid]
    regs, die = _regions(spec, pno)
    blank_keys = {_match_key(r) for r in info["blank"]}

    def tcoord(b):        # customer page -> template coordinates
        return (b[0] - off[0], b[1] - off[1], b[2] - off[0], b[3] - off[1])

    # The koozie color: a fill over the whole die.
    body_obj = None
    if die:
        dx0, dx1 = die["x"]
        span_y = die["panels"][0][1] - die["panels"][1][0]
        for r in info["objects"]:
            if r["kind"] != "path" or r["op"] in ("S", "s"):
                continue
            b = tcoord(r["bbox"])
            if (b[2] - b[0]) >= 0.9 * (dx1 - dx0) and (b[3] - b[1]) >= 0.8 * span_y:
                body_obj = (r["owner"], r["idx"])

    # The template's own shapes, a fraction of a point off: the customer's
    # copy of the template is often saved again, which moves everything by
    # a rounding. And its labels ("ART", "Bottom"), which the customer's app
    # may have turned into outlines: shapes inside a label's box, in that
    # label's own colour.
    TOL = 1.2
    grid = {}
    for r in info["blank"]:
        bb = r["bbox"]
        grid.setdefault((r["kind"], round(bb[0] / 4), round(bb[1] / 4)), []).append(bb)
    labels = [r for r in info["blank"] if r["kind"] == "text" and r.get("fc") is not None]

    def near_blank(r):
        b = tcoord(r["bbox"])
        gx, gy = round(b[0] / 4), round(b[1] / 4)
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for bb in grid.get((r["kind"], gx + dx, gy + dy), ()):
                    if all(abs(b[i] - bb[i]) <= TOL for i in range(4)):
                        return True
        return False

    def rgb(fc):
        v = [x for x in (fc or ())[1:] if isinstance(x, float)]
        if len(v) == 4:
            c, m, y, k = v
            return ((1 - c) * (1 - k), (1 - m) * (1 - k), (1 - y) * (1 - k))
        if len(v) == 3:
            return tuple(v)
        if len(v) == 1:
            return (v[0],) * 3
        return None

    # An outlined label is its letters: as many shapes as the word has
    # letters, all inside the label's box, near its colour, spanning most of
    # its width. Art that only overlaps a label is never all inside it.
    label_parts = set()
    for t in labels:
        tb, want = t["bbox"], len((t.get("text") or "").replace(" ", ""))
        if not want:
            continue
        tc = rgb(t["fc"])
        group = []
        for r in info["objects"]:
            if r["kind"] != "path" or r["op"] in ("S", "s"):
                continue
            b = tcoord(r["bbox"])
            if not (b[0] >= tb[0] - 4 and b[1] >= tb[1] - 4 and b[2] <= tb[2] + 4 and b[3] <= tb[3] + 4):
                continue
            rc = rgb(r.get("fc"))
            if tc and rc and sum((p - q) ** 2 for p, q in zip(tc, rc)) ** 0.5 > 0.3:
                continue
            group.append((r, b))
        if want - 1 <= len(group) <= want + 2:
            x0 = min(b[0] for _, b in group); x1 = max(b[2] for _, b in group)
            if (x1 - x0) >= 0.6 * (tb[2] - tb[0]):
                label_parts.update((r["owner"], r["idx"]) for r, _ in group)

    def in_label(r):
        return (r["owner"], r["idx"]) in label_parts

    # Art, by location.
    placed = {}
    for r in info["objects"]:
        if _match_key(r, off) in blank_keys or (r["owner"], r["idx"]) == body_obj:
            continue
        if near_blank(r) or in_label(r):
            continue
        b = tcoord(r["bbox"])
        # Stroke-only straight lines and boxes the customer's app redrew are
        # guides too, even when they no longer match the blank exactly.
        if r["kind"] == "path" and r["op"] in ("S", "s") and r["n"] <= 5:
            continue
        sid = _region_of(((b[0] + b[2]) / 2, (b[1] + b[3]) / 2), regs)
        if sid and any(s["id"] == sid for s in prod["art_slots"]):
            placed.setdefault(sid, set()).add((r["owner"], r["idx"]))
    return {"pid": pid, "spec": spec, "pno": pno, "off": off, "info": info, "prod": prod,
            "regs": regs, "die": die, "body_obj": body_obj, "placed": placed,
            "page_index": page_index}


def _build(plan, pdf_path, work_dir, filename_stem):
    pid, pno, off, info, prod = plan["pid"], plan["pno"], plan["off"], plan["info"], plan["prod"]
    regs, die, body_obj, placed, pi = plan["regs"], plan["die"], plan["body_obj"], plan["placed"], plan["page_index"]
    work = Path(work_dir); work.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix="tifimp_"))
    try:
        slots_out, art, files = {}, [], {}
        from screenprint import ink_bbox_points
        for sid, keep in placed.items():
            reg = regs[sid]
            stripped = tmp / f"{sid}.pdf"
            shutil.copy2(str(pdf_path), str(stripped))
            with pikepdf.open(str(stripped), allow_overwriting_input=True) as pdf:
                _rewrite(pdf, lambda r, keep=keep: (r["owner"], r["idx"]) in keep, pi)
                pdf.save(str(stripped))
            bx = reg["box"]
            box = (bx[0] + off[0], bx[1] + off[1], bx[2] + off[0], bx[3] + off[1])
            out = work / f"{filename_stem}-{sid}.pdf"
            _crop(stripped, box, reg["rot"], out, pi)
            files[sid] = out

        # The same drawing on both sides reads as "same" — the press files
        # then say "2 Sides Same" because it is.
        same = False
        if "side1" in placed and "side2" in placed:
            objs = {(r["owner"], r["idx"]): r for r in info["objects"]}
            def sig(keys):
                return Counter((objs[k]["kind"], round(objs[k]["bbox"][2] - objs[k]["bbox"][0]),
                                round(objs[k]["bbox"][3] - objs[k]["bbox"][1])) for k in keys if k in objs)
            a, b = sig(placed["side1"]), sig(placed["side2"])
            common = sum((a & b).values())
            same = common >= 0.95 * max(sum(a.values()), sum(b.values()), 1)

        # Sizes and positions, in the configurator's own units.
        from PIL import Image
        asset = prod.get("asset_id") or pid
        guide = HERE / "static" / "assets" / asset / "template_guide.png"
        gW, gH = Image.open(guide).size if guide.exists() else (795, 2000)
        tz = prod.get("template_zones") or {}
        ink_hex = None
        key = 0
        for sid, f in files.items():
            reg = regs[sid]
            slot = next(s for s in prod["art_slots"] if s["id"] == sid)
            x0, y0, x1, y1 = reg["box"]
            w, h = x1 - x0, y1 - y0
            if reg["rot"] == 90:
                w, h = h, w
            ib = ink_bbox_points(str(f), (0, 0, w, h))
            if not ib:
                continue
            ax0, ay0, ax1, ay1 = ib
            aw, ah = max(0.1, ax1 - ax0), max(0.1, ay1 - ay0)
            zx, zy = reg["zone"]
            if reg["rot"] == 180:
                zx, zy = x1 - zx, y1 - zy
            elif reg["rot"] == 90:
                zx, zy = zy - y0, x1 - zx
            else:
                zx, zy = zx - x0, zy - y0
            dx = (ax0 + ax1) / 2 - zx
            dy_down = zy - (ay0 + ay1) / 2
            sw, sh = float(slot["w_pt"]), float(slot["h_pt"])
            fit = min(sw / aw, sh / ah)
            z = tz.get(sid) or {}
            zw_px, zh_px = z.get("w", 0.9) * gW, z.get("h", 0.35) * gH
            here = {"art_key": key, "sc": round(1 / fit, 4),
                    "ox": round(dx / sw * zw_px, 2), "oy": round(dy_down / sh * zh_px, 2),
                    "rot": 0, "w_in": round(aw / 72, 2)}
            if same and sid == "side2":
                # The same art is "2 Sides Same" only where it also sits the
                # same: drawn higher or lower on Side 2, it keeps its own spot.
                s1 = slots_out.get("side1") or {}
                z1 = tz.get("side1") or {}
                z1w, z1h = z1.get("w", 0.9) * gW, z1.get("h", 0.35) * gH
                s1_in = (s1.get("ox", 0) / max(z1w, 1e-6) * sw / 72, s1.get("oy", 0) / max(z1h, 1e-6) * sh / 72)
                s2_in = (dx / 72, dy_down / 72)
                if s1 and max(abs(s1_in[0] - s2_in[0]), abs(s1_in[1] - s2_in[1])) <= 0.05 \
                        and abs(s1.get("w_in", 0) - here["w_in"]) <= 0.05:
                    slots_out[sid] = dict(s1)
                    continue
                same = False
                if s1:
                    here["art_key"] = s1["art_key"]    # the one art file, placed where Side 2 has it
                    slots_out[sid] = here
                    continue
            slots_out[sid] = here
            art.append({"key": key, "orig": f.name, "name": f.name, "orig_path": str(f)})
            key += 1
            if ink_hex is None:
                ink_hex = _main_color(_render_rgba(f, 72))

        # Body: the die fill's color, as the nearest color this item comes in.
        neo = None
        if body_obj and die:
            try:
                full = _render_rgba(pdf_path, 36, page=pi + 1)
                s = 36 / 72.0
                with pikepdf.open(str(pdf_path)) as _p:
                    mb = [float(v) for v in _p.pages[pi].mediabox]
                ph = mb[3] - mb[1]
                dx0, dx1 = die["x"]
                u0, u1 = die["panels"][0]
                pts = [(dx0 + 8, u1 - 8), (dx1 - 8, u1 - 8), (dx0 + 8, u0 + 8), (dx1 - 8, u0 + 8)]
                cols = Counter()
                for (px, py) in pts:
                    X, Y = int((px + off[0]) * s), int((ph - (py + off[1])) * s)
                    if 0 <= X < full.width and 0 <= Y < full.height:
                        r_, g_, b_, a_ = full.getpixel((X, Y))
                        cols["#%02X%02X%02X" % (r_, g_, b_)] += 1
                fill_hex = cols.most_common(1)[0][0] if cols else None
                # White is the blank template's own die: no koozie color was given.
                if fill_hex and min(_hex_rgb(fill_hex)) < 242:
                    neo = _nearest_body(prod.get("material") or "", fill_hex)
            except Exception as e:
                print(f"⚠️ TIF import: body color not read: {e}")

        snap = {"pid": pid, "legacy": False, "source": "tif_template",
                "sides": "same" if same else "diff",
                "slots": slots_out, "art": art,
                "template": {"file_page": pi + 1, "guide": pno, "score": round(info["score"], 2),
                             "offset": list(off)}}
        if neo:
            snap["neo"] = neo
        # The one ink of a one-color item, from the art's color. Items printed
        # in full color (the 24 HR Jotter) keep the art's own colors.
        from products import is_screenprint
        ink = _nearest_ink(ink_hex) if ink_hex and is_screenprint(pid) else None
        if ink:
            snap["ink"] = ink
        return snap
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _hex_rgb(h):
    h = h.lstrip("#"); return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _nearest_body(material, hexv):
    import engine
    pal = engine.SCUBA_FOAM if material.startswith("scuba") else engine.NEOPRENE
    if material.startswith("cotton"):
        return None
    rgb = _hex_rgb(hexv)
    name, hx = min(pal.items(), key=lambda kv: sum((a - b) ** 2 for a, b in zip(_hex_rgb(kv[1]), rgb)))
    return {"name": name, "hex": hx, "from_template": hexv}


def _nearest_ink(hexv):
    """The ink the art is drawn in. Black says nothing: the template asks for
    art in registration black, so the ink is left for the artist to pick."""
    rgb = _hex_rgb(hexv)
    if max(rgb) <= 70 and max(rgb) - min(rgb) <= 24:
        return None
    if min(rgb) >= 235:
        return {"name": "White", "hex": "#FFFFFF", "from_template": hexv}
    try:
        from engine import find_closest_pantone
        m = find_closest_pantone(rgb, top_n=1, boost=False)
        if m:
            return {"name": m[0]["name"], "hex": m[0]["hex"], "from_template": hexv}
    except Exception as e:
        print(f"⚠️ TIF import: ink match failed: {e}")
    return {"name": None, "hex": hexv, "from_template": hexv}
