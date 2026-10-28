"""
Tidy a finished screen-print press file so it opens clean in Illustrator.

What a sheet carries that nobody needs, and Illustrator shows as boxes:
  1. The vendor template's "NSO NUMBER" / "SPOT COLOR" placeholder text, still
     there under the captions we stamp, and the white (0 %) box drawn over it.
  2. The template's guide layers, emptied when the sheet is built but still
     placed - each an empty clip group.
  3. Every placed form (the art, the template's furniture) as its own clip
     group, cut to the form's bounding box.

tidy() removes 1 and 2 and inlines the forms (3), then renders every page
before and after and keeps the tidied file only if they look the same. Any
problem leaves the file exactly as it was.
"""
import shutil
import subprocess
import tempfile
from pathlib import Path

import pikepdf

PLACEHOLDERS = {"NSO NUMBER", "SPOT COLOR"}
PAINT_OPS = {"f", "F", "f*", "B", "B*", "b", "b*", "S", "s", "sh",
             "Tj", "TJ", "'", '"', "INLINE IMAGE"}
CATS = ("/ColorSpace", "/ExtGState", "/Font", "/XObject", "/Pattern", "/Shading", "/Properties")


def _text_of(operands):
    s = operands[-1] if operands else ""
    if isinstance(s, pikepdf.Array):
        return "".join(str(x) for x in s if isinstance(x, pikepdf.String))
    try:
        return str(s)
    except Exception:
        return ""


def _is_form(x):
    return isinstance(x, pikepdf.Stream) and x.get("/Subtype") == "/Form"


def _painted(x, memo, depth=0):
    """Does this form put down anything at all (itself or a form inside it)?"""
    key = x.objgen
    if key in memo:
        return memo[key]
    memo[key] = True                      # cycles count as painting (leave them)
    res = x.get("/Resources") or pikepdf.Dictionary()
    xo = res.get("/XObject") or {}
    out = False
    try:
        for operands, op in pikepdf.parse_content_stream(x):
            o = str(op)
            if o in PAINT_OPS:
                out = True
                break
            if o == "Do":
                y = xo.get(operands[0])
                if y is None or not _is_form(y) or depth > 20 or _painted(y, memo, depth + 1):
                    out = True
                    break
    except Exception:
        out = True
    memo[key] = out
    return out


class _Ops(list):
    """Content ops plus the resource names they use, as (category, name)."""
    def __init__(self, items=(), refs=None):
        super().__init__(items)
        self.refs = set(refs or ())


class _SegOp:
    """An inlined form already written out as content bytes. It reads as "Do"
    (so an enclosing q ... Q counts as painting); it keeps its ops so a parent
    that has to rename one of its resources can still do so."""
    def __init__(self, ops):
        self.ops = ops
        self.refs = set(ops.refs)
        self._data = None

    @property
    def data(self):
        if self._data is None:
            self._data = _serialize(self.ops)
        return self._data

    def __str__(self):
        return "Do"


# operator -> (where its resource name sits, the resource category)
_REF_OPS = {"cs": (0, "/ColorSpace"), "CS": (0, "/ColorSpace"), "gs": (0, "/ExtGState"),
            "Tf": (0, "/Font"), "Do": (0, "/XObject"), "sh": (0, "/Shading"),
            "BDC": (1, "/Properties"), "DP": (1, "/Properties")}


def _ref_of(o, operands):
    """The resource (category, name) an op uses, or None."""
    if o in ("scn", "SCN"):
        if operands and isinstance(operands[-1], pikepdf.Name):
            return ("/Pattern", str(operands[-1]))
        return None
    r = _REF_OPS.get(o)
    if r and len(operands) > r[0] and isinstance(operands[r[0]], pikepdf.Name):
        return (r[1], str(operands[r[0]]))
    return None


def _serialize(ops):
    """Content bytes for ops that may hold written-out segments."""
    parts, run = [], []
    for operands, op in ops:
        if isinstance(op, _SegOp):
            if run:
                parts.append(pikepdf.unparse_content_stream(run)); run = []
            parts.append(op.data)
        else:
            run.append((operands, op))
    if run:
        parts.append(pikepdf.unparse_content_stream(run))
    return b"\n".join(parts)


def _rename(ops, mapping):
    """Resource names in a form's ops -> the names they get in the parent.
    Only names the ops actually use are looked for (ops.refs), so a form whose
    clashing resource is no longer drawn (it was inlined) isn't walked at all."""
    refs = getattr(ops, "refs", None)
    if refs is not None:
        mapping = {k: v for k, v in mapping.items() if k in refs}
    if not mapping:
        return ops if isinstance(ops, _Ops) else _Ops(ops, refs)
    out = _Ops()
    for operands, op in ops:
        if isinstance(op, _SegOp):
            if op.refs & mapping.keys():
                op = _SegOp(_rename(op.ops, mapping))
            out.append((operands, op))
            continue
        o = str(op)
        r = _ref_of(o, operands)
        if r in mapping:
            ops2 = list(operands)
            i = (len(ops2) - 1) if o in ("scn", "SCN") else _REF_OPS[o][0]
            ops2[i] = pikepdf.Name(mapping[r])
            out.append((ops2, op))
        else:
            out.append((operands, op))
    out.refs = {(c, mapping.get((c, n), n)) for c, n in (refs if refs is not None else set())}
    if refs is None:
        out.refs = {x for x in (_ref_of(str(op), opd) for opd, op in out if not isinstance(op, _SegOp)) if x}
    return out


def _drop_empty_blocks(ops):
    """Remove q ... Q blocks that paint nothing.

    The vendor templates leave blocks like `q /Reg cs 1 scn /GS1 gs 0 TL Q`
    where the placeholder text used to be. They draw nothing, but a /GS1 at
    50 % opacity is still transparency on the page, and a separating RIP (and
    Ghostscript) then composites the page and drops the /All registration
    colour from the spot plates. With the empty blocks gone the page has no
    transparency left and registration images on every plate."""
    keep = [True] * len(ops)
    stack = []                                   # [start index, painted?, marked-content depth]
    mc = 0
    for i, (operands, op) in enumerate(ops):
        o = str(op)
        if o == "q":
            stack.append([i, False, mc])
        elif o in ("BDC", "BMC"):
            mc += 1
        elif o == "EMC":
            mc -= 1
        elif o == "Q" and stack:
            start, painted, mc0 = stack.pop()
            if not painted and mc == mc0:
                for j in range(start, i + 1):
                    keep[j] = False
            elif painted and stack:
                stack[-1][1] = True
        elif o in PAINT_OPS or o in ("Do", "BI", "ID", "EI"):
            if stack:
                stack[-1][1] = True
    # The names what's left actually uses (a dropped block's /GS1 must not
    # keep its 50 % graphics state on the page).
    out = _Ops()
    for (operands, op), k in zip(ops, keep):
        if not k:
            continue
        out.append((operands, op))
        if isinstance(op, _SegOp):
            out.refs |= op.refs
        else:
            r = _ref_of(str(op), operands)
            if r:
                out.refs.add(r)
    return out


def transparency_left(pdf):
    """Pages that still set opacity below 100 % or a soft mask (1-based)."""
    out = []
    for n, page in enumerate(pdf.pages, 1):
        res = page.obj.get("/Resources") or {}
        for _, g in (res.get("/ExtGState") or {}).items():
            if float(g.get("/ca", 1)) < 1 or float(g.get("/CA", 1)) < 1 or \
                    str(g.get("/SMask", "/None")) != "/None":
                out.append(n)
                break
    return out


class _Tidier:
    # A form this big is written out to bytes once and the bytes reused.
    SEG_MIN_OPS = 20000

    def __init__(self, pdf):
        self.pdf = pdf
        self.memo = {}
        self.forms = {}          # a form's tidied ops, worked out once: key -> (ops, placeholders)
        self.n = 0
        self.stats = {"placeholders": 0, "covers": 0, "empty_forms": 0, "inlined": 0}

    # ── one stream: drop placeholders / empty forms, inline the rest ──────────
    def ops_of(self, owner, res, overlay=False, page_ph=None, depth=0):
        res = res if res is not None else pikepdf.Dictionary()
        xo = res.get("/XObject") or {}
        out, tint, pending_re = _Ops(), None, None
        refs = out.refs
        for operands, op in pikepdf.parse_content_stream(owner):
            o = str(op)
            if o in ("Tj", "TJ", "'", '"') and _text_of(operands).strip().upper() in PLACEHOLDERS:
                self.stats["placeholders"] += 1
                if page_ph is not None:
                    page_ph[0] += 1
                continue
            if overlay and o in ("scn", "sc") and operands and not isinstance(operands[-1], pikepdf.Name):
                tint = float(operands[0])
            if overlay and o == "re":
                pending_re = (operands, op)
                continue
            if pending_re is not None:
                # Our caption's white cover box: a lone rectangle filled at 0 %.
                if o in ("f", "f*", "F") and tint == 0 and page_ph is not None and page_ph[0] > 0:
                    self.stats["covers"] += 1
                    pending_re = None
                    continue
                out.append(pending_re)
                pending_re = None
            if o == "Do" and operands:
                x = xo.get(operands[0])
                if x is not None and _is_form(x):
                    if not _painted(x, self.memo):
                        self.stats["empty_forms"] += 1
                        continue
                    if depth < 12 and "/Group" not in x and "/SMask" not in x:
                        sub = self.inline(x, res, page_ph, depth + 1, str(operands[0]))
                        out.extend(sub)
                        refs |= sub.refs
                        self.stats["inlined"] += 1
                        continue
            r = _ref_of(o, operands)
            if r:
                refs.add(r)
            out.append((operands, op))
        if pending_re is not None:
            out.append(pending_re)
        return out

    def _form_key(self, x, overlay):
        """Forms are reused by object; a form with no forms inside it (the art)
        also by its content, so each sheet's copy of the same art is done once."""
        if overlay:
            return None
        xres = x.get("/Resources") or {}
        if not (xres.get("/XObject") or {}):
            import hashlib
            try:
                return ("content", hashlib.sha1(x.read_raw_bytes()).hexdigest(),
                        tuple(sorted(str(k) for c in CATS for k in (xres.get(c) or {}).keys())))
            except Exception:
                pass
        return ("obj", x.objgen) if x.objgen != (0, 0) else None

    def inline(self, x, parent_res, page_ph, depth, name=""):
        """The form's own content, ready to sit in its parent's stream."""
        xres = x.get("/Resources") or pikepdf.Dictionary()
        # reportlab's page merged over the template (pdfrw's "FullPage"): only
        # our captions sit directly in it, so a 0 % box there is a caption cover.
        overlay = (name == "/FullPage")
        # The same art sits on every sheet, and a form can be placed many
        # times: each is tidied once and reused. Parsing, walking, renaming
        # and writing out each copy took over a minute on detailed art. Its
        # empty q ... Q blocks go before it is copied, not after.
        key = self._form_key(x, overlay)
        if key is not None and key in self.forms:
            inner, ph_n = self.forms[key]
            self.stats["placeholders"] += ph_n
            if page_ph is not None:
                page_ph[0] += ph_n
        else:
            before = self.stats["placeholders"]
            inner = self.ops_of(x, xres, overlay=overlay, page_ph=page_ph, depth=depth)
            if not overlay:
                n0 = len(inner)
                inner = _drop_empty_blocks(inner)
                self.stats["empty_ops"] = self.stats.get("empty_ops", 0) + n0 - len(inner)
                if len(inner) >= self.SEG_MIN_OPS:
                    inner = _Ops([([pikepdf.Name("/__seg__")], _SegOp(inner))], inner.refs)
                if key is not None:
                    self.forms[key] = (inner, self.stats["placeholders"] - before)
        self.n += 1
        mapping = {}
        for cat in CATS:
            src = xres.get(cat)
            if not src:
                continue
            if cat not in parent_res:
                parent_res[cat] = pikepdf.Dictionary()
            dst = parent_res[cat]
            for k in list(src.keys()):
                v = src[k]
                if k in dst and getattr(dst[k], "objgen", None) == getattr(v, "objgen", (-1, -1)) \
                        and getattr(v, "objgen", (0, 0)) != (0, 0):
                    continue                                   # the same object already there
                nk = k
                if k in dst:
                    nk = f"{k}_t{self.n}"
                    mapping[(cat, str(k))] = nk
                dst[nk] = v
        inner = _rename(inner, mapping)
        m = x.get("/Matrix")
        pre = [([], pikepdf.Operator("q"))]
        if m is not None:
            pre.append(([float(v) for v in m], pikepdf.Operator("cm")))
        return _Ops(pre + list(inner) + [([], pikepdf.Operator("Q"))], inner.refs)

    def page(self, page):
        res = page.obj.get("/Resources") or pikepdf.Dictionary()
        ph = [0]
        # first pass counts the placeholders; the overlay covers come out only
        # where one was removed on this page
        self._count_placeholders(page.obj, res, ph, set())
        ops = self.ops_of(page.obj, res, overlay=False, page_ph=ph)
        n0 = len(ops)
        ops = _drop_empty_blocks(ops)
        self.stats["empty_ops"] = self.stats.get("empty_ops", 0) + n0 - len(ops)
        page.obj.Contents = self.pdf.make_stream(_serialize(ops))
        used_gs = {n for c, n in ops.refs if c == "/ExtGState"}
        used_xo = {n for c, n in ops.refs if c == "/XObject"}
        # graphics states no page content uses any more (an unused 50 % one
        # still counts as transparency to a RIP)
        if "/ExtGState" in res:
            for k in list(res.ExtGState.keys()):
                if k not in used_gs:
                    del res.ExtGState[k]
        # forms no page content uses any more
        if "/XObject" in res:
            for k in list(res.XObject.keys()):
                if k not in used_xo and _is_form(res.XObject[k]):
                    del res.XObject[k]

    def _count_placeholders(self, owner, res, ph, seen):
        # Only streams that draw text can hold a placeholder (outlined art has none).
        try:
            raw = owner.read_bytes() if hasattr(owner, "read_bytes") else b"".join(
                c.read_bytes() for c in ([owner.Contents] if isinstance(owner.get("/Contents"), pikepdf.Stream)
                                         else list(owner.get("/Contents") or [])))
        except Exception:
            raw = b"Tj"
        if b"Tj" in raw or b"TJ" in raw or b"'" in raw or b'"' in raw:
            for operands, op in pikepdf.parse_content_stream(owner):
                if str(op) in ("Tj", "TJ", "'", '"') and _text_of(operands).strip().upper() in PLACEHOLDERS:
                    ph[0] += 1
        for _, x in ((res or {}).get("/XObject") or {}).items():
            if _is_form(x) and x.objgen not in seen:
                seen.add(x.objgen)
                self._count_placeholders(x, x.get("/Resources"), ph, seen)
        # counted once more while removing; only "any" matters
        ph[0] = 1 if ph[0] else 0


def _render(pdf_path, out_dir, dpi=24):
    subprocess.run(["pdftoppm", "-r", str(dpi), "-gray", "-png", str(pdf_path), str(Path(out_dir) / "p")],
                   check=True, capture_output=True, timeout=300)
    return sorted(Path(out_dir).glob("p*.png"))


def _same_look(a_pdf, b_pdf):
    import numpy as np
    from PIL import Image
    with tempfile.TemporaryDirectory() as ta, tempfile.TemporaryDirectory() as tb:
        ra, rb = _render(a_pdf, ta), _render(b_pdf, tb)
        if len(ra) != len(rb):
            return False
        for fa, fb in zip(ra, rb):
            A = np.asarray(Image.open(fa), dtype=np.int16)
            B = np.asarray(Image.open(fb), dtype=np.int16)
            if A.shape != B.shape:
                return False
            d = np.abs(A - B)
            # The placeholders and their covers sit under our captions; allow
            # that much change and nothing else.
            if (d > 60).mean() > 0.002:
                return False
    return True


def tidy(pdf_path, verify=True):
    """Tidy the press file in place. Returns stats, or {"skipped": reason}."""
    src = Path(pdf_path)
    tmp = src.with_name(src.stem + ".tidy.pdf")
    try:
        pdf = pikepdf.open(str(src))
        t = _Tidier(pdf)
        for page in pdf.pages:
            t.page(page)
        pdf.remove_unreferenced_resources()
        t.stats["transparency_pages"] = transparency_left(pdf)
        pdf.save(str(tmp))
        pdf.close()
        if verify and not _same_look(src, tmp):
            tmp.unlink(missing_ok=True)
            return {"skipped": "tidied sheet did not render the same"}
        shutil.move(str(tmp), str(src))
        return t.stats
    except Exception as e:
        tmp.unlink(missing_ok=True)
        return {"skipped": f"{type(e).__name__}: {e}"}
