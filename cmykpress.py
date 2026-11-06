"""
Mimaki press files in CMYK.

PANTONE spots are right for the proof and the configurator, but the Mimaki
(RasterLink) should get plain process colour: every spot swatch dropped, its
art painted in the CMYK the swatch carries (the Separation's own alternate,
so the numbers stay exactly what the file already says), and nothing left in
RGB or gray, so the file opens as a CMYK document.

The one spot that stays is WHITE: the Mimaki prints white ink only from a
spot named exactly that (whitespot.py).

convert(path) rewrites the PDF in place:
  - every page and form content stream, recursively: g/rg/sc/scn in gray, RGB,
    ICC, Lab or a spot become k/K in DeviceCMYK;
  - spots and DeviceN are evaluated through their tint function into their
    alternate space, then into CMYK (an alternate that is already CMYK is
    used as is);
  - placed images in RGB, gray, ICC, Indexed or a spot are re-written as CMYK
    pixels;
  - axial / radial shadings (gradients) get a CMYK sampled function;
  - transparency groups are set to DeviceCMYK;
  - the dropped spots are taken out of every resource dictionary, so no spot
    swatch but WHITE is left in the file.
Returns a report: {"converted": n, "spots": [names dropped], "images": n,
"problems": [...]}. Anything listed in problems was left as it was.
"""
import math
import zlib

import pikepdf
from pikepdf import Name, Operator

KEEP = {"WHITE"}
_FALLBACK = set()


# ── colour maths ───────────────────────────────────────────────────────────

def _rgb_cmyk(r, g, b):
    r, g, b = (max(0.0, min(1.0, float(v))) for v in (r, g, b))
    k = 1 - max(r, g, b)
    if k >= 0.9999:
        return [0.0, 0.0, 0.0, 1.0]
    return [round((1 - r - k) / (1 - k), 4), round((1 - g - k) / (1 - k), 4),
            round((1 - b - k) / (1 - k), 4), round(k, 4)]


def _lab_rgb(L, a, b, white=(0.9642, 1.0, 0.8249)):
    try:
        from onecolor import _lab_to_rgb
        return _lab_to_rgb(L, a, b, white)
    except Exception:
        v = max(0.0, min(1.0, L / 100.0))
        return (v, v, v)


# ── PDF functions (types 0, 2, 3, 4) ───────────────────────────────────────

def _num(v):
    return float(v)


def _ps_tokens(src):
    s = src.replace("{", " { ").replace("}", " } ")
    return s.split()


def _ps_parse(tokens, i=0):
    out = []
    while i < len(tokens):
        t = tokens[i]
        if t == "{":
            sub, i = _ps_parse(tokens, i + 1)
            out.append(sub)
        elif t == "}":
            return out, i + 1
        else:
            try:
                out.append(float(t))
            except ValueError:
                out.append(t)
            i += 1
    return out, i


_BIN = {
    "add": lambda a, b: a + b, "sub": lambda a, b: a - b, "mul": lambda a, b: a * b,
    "div": lambda a, b: a / b if b else 0.0, "max": max, "min": min,
    "exp": lambda a, b: a ** b if a >= 0 or b == int(b) else 0.0,
    "atan": lambda a, b: math.degrees(math.atan2(a, b)) % 360,
    "idiv": lambda a, b: int(a / b) if int(b) else 0, "mod": lambda a, b: int(a) % int(b) if int(b) else 0,
    "eq": lambda a, b: a == b, "ne": lambda a, b: a != b, "gt": lambda a, b: a > b,
    "ge": lambda a, b: a >= b, "lt": lambda a, b: a < b, "le": lambda a, b: a <= b,
    "and": lambda a, b: bool(a) and bool(b), "or": lambda a, b: bool(a) or bool(b),
    "xor": lambda a, b: bool(a) != bool(b),
}
_UN = {
    "neg": lambda a: -a, "abs": abs, "sqrt": lambda a: math.sqrt(max(a, 0)),
    "floor": math.floor, "ceiling": math.ceil, "round": lambda a: math.floor(a + 0.5),
    "truncate": int, "cvi": int, "cvr": lambda a: a,
    "sin": lambda a: math.sin(math.radians(a)), "cos": lambda a: math.cos(math.radians(a)),
    "ln": lambda a: math.log(a) if a > 0 else 0.0, "log": lambda a: math.log10(a) if a > 0 else 0.0,
}


def _ps_run(prog, st):
    i = 0
    while i < len(prog):
        t = prog[i]
        if isinstance(t, float):
            st.append(t)
        elif isinstance(t, list):
            # if / ifelse take the procedures that precede them
            nxt = prog[i + 1] if i + 1 < len(prog) else None
            if nxt == "if":
                if st.pop():
                    _ps_run(t, st)
                i += 2
                continue
            if isinstance(nxt, list) and i + 2 < len(prog) and prog[i + 2] == "ifelse":
                _ps_run(t if st.pop() else nxt, st)
                i += 3
                continue
            raise ValueError("bad procedure")
        else:
            op = t
            if op == "dup": st.append(st[-1])
            elif op == "pop": st.pop()
            elif op == "exch": st[-1], st[-2] = st[-2], st[-1]
            elif op == "copy":
                n = int(st.pop()); st.extend(st[-n:] if n else [])
            elif op == "index":
                n = int(st.pop()); st.append(st[-1 - n])
            elif op == "roll":
                j = int(st.pop()); n = int(st.pop())
                if n:
                    seg = st[-n:]; j %= n
                    st[-n:] = seg[-j:] + seg[:-j] if j else seg
            elif op in _BIN:
                b = st.pop(); a = st.pop()
                st.append(float(_BIN[op](a, b)))
            elif op in _UN:
                st.append(float(_UN[op](st.pop())))
            elif op == "not": st.append(float(not st.pop()))
            elif op == "true": st.append(1.0)
            elif op == "false": st.append(0.0)
            else:
                raise ValueError(f"PostScript op {op}")
        i += 1


def _clip(v, rng):
    if rng is None:
        return v
    r = [float(x) for x in rng]
    return [max(r[2 * i], min(r[2 * i + 1], x)) for i, x in enumerate(v[:len(r) // 2])]


def _fn(fn, ins):
    """Evaluate a PDF function (or an array of 1-out functions) at `ins`."""
    if isinstance(fn, pikepdf.Array):
        return [_fn(f, ins)[0] for f in fn]
    t = int(fn.get("/FunctionType", -1))
    dom = [float(x) for x in fn.get("/Domain", [0, 1] * len(ins))]
    ins = [max(dom[2 * i], min(dom[2 * i + 1], float(x))) for i, x in enumerate(ins)]
    rng = fn.get("/Range")
    if t == 2:
        c0 = [float(x) for x in fn.get("/C0", [0.0])]
        c1 = [float(x) for x in fn.get("/C1", [1.0])]
        n = float(fn.get("/N", 1))
        x = ins[0] ** n if ins[0] >= 0 else 0.0
        return _clip([a + x * (b - a) for a, b in zip(c0, c1)], rng)
    if t == 3:
        fns = fn["/Functions"]
        bounds = [float(b) for b in fn.get("/Bounds", [])]
        enc = [float(e) for e in fn["/Encode"]]
        x = ins[0]
        k = 0
        while k < len(bounds) and x >= bounds[k]:
            k += 1
        lo = dom[0] if k == 0 else bounds[k - 1]
        hi = dom[1] if k == len(bounds) else bounds[k]
        e0, e1 = enc[2 * k], enc[2 * k + 1]
        xx = e0 if hi == lo else e0 + (x - lo) * (e1 - e0) / (hi - lo)
        return _clip(_fn(fns[k], [xx]), rng)
    if t == 4:
        prog, _ = _ps_parse(_ps_tokens(fn.read_bytes().decode("latin-1")))
        st = list(ins)
        _ps_run(prog[0] if len(prog) == 1 and isinstance(prog[0], list) else prog, st)
        return _clip(st, rng)
    if t == 0:
        size = [int(s) for s in fn["/Size"]]
        bps = int(fn["/BitsPerSample"])
        rngf = [float(x) for x in fn["/Range"]]
        nout = len(rngf) // 2
        enc = [float(e) for e in fn.get("/Encode", sum(([0, s - 1] for s in size), []))]
        dec = [float(d) for d in fn.get("/Decode", rngf)]
        if len(size) != 1 or bps not in (8, 16):
            raise ValueError("sampled function shape")
        x = ins[0]
        e = enc[0] + (x - dom[0]) * (enc[1] - enc[0]) / ((dom[1] - dom[0]) or 1)
        j = max(0, min(size[0] - 1, int(round(e))))
        data = fn.read_bytes()
        w = bps // 8
        mx = (1 << bps) - 1
        out = []
        for o in range(nout):
            p = (j * nout + o) * w
            raw = int.from_bytes(data[p:p + w], "big")
            out.append(dec[2 * o] + raw * (dec[2 * o + 1] - dec[2 * o]) / mx)
        return out
    raise ValueError(f"function type {t}")


# ── colour spaces ──────────────────────────────────────────────────────────

def _deref_cs(cs, res):
    if isinstance(cs, Name) and res is not None:
        d = res.get("/ColorSpace")
        if d is not None and cs in d:
            return d[cs]
    return cs


def _is_keep(cs):
    return (isinstance(cs, pikepdf.Array) and len(cs) > 1 and str(cs[0]) == "/Separation"
            and str(cs[1]).lstrip("/").upper() in KEEP)


def _spot_names(cs):
    if isinstance(cs, pikepdf.Array) and len(cs) > 1:
        if str(cs[0]) == "/Separation":
            return [str(cs[1]).lstrip("/")]
        if str(cs[0]) == "/DeviceN":
            return [str(n).lstrip("/") for n in cs[1]]
    return []


def _ncomp(cs):
    if isinstance(cs, Name):
        return {"/DeviceGray": 1, "/G": 1, "/DeviceRGB": 3, "/RGB": 3,
                "/DeviceCMYK": 4, "/CMYK": 4}.get(str(cs), 1)
    h = str(cs[0])
    if h == "/ICCBased":
        return int(cs[1].get("/N", 3))
    if h in ("/CalRGB", "/Lab"):
        return 3
    if h == "/CalGray":
        return 1
    if h == "/Separation":
        return 1
    if h == "/DeviceN":
        return len(cs[1])
    if h == "/Indexed":
        return 1
    return 1


def to_cmyk(cs, vals):
    """CMYK (0..1) for colour `vals` in colour space `cs` (resolved)."""
    vals = [float(v) for v in vals]
    if isinstance(cs, Name):
        n = str(cs)
        if n in ("/DeviceCMYK", "/CMYK"):
            return [round(v, 4) for v in vals[:4]]
        if n in ("/DeviceRGB", "/RGB"):
            return _rgb_cmyk(*vals[:3])
        return [0.0, 0.0, 0.0, round(1 - (vals[0] if vals else 0.0), 4)]
    h = str(cs[0])
    if h == "/ICCBased":
        n = int(cs[1].get("/N", 3))
        alt = {1: Name.DeviceGray, 3: Name.DeviceRGB, 4: Name.DeviceCMYK}.get(n, Name.DeviceRGB)
        return to_cmyk(alt, vals)
    if h == "/CalRGB":
        return _rgb_cmyk(*vals[:3])
    if h == "/CalGray":
        return to_cmyk(Name.DeviceGray, vals)
    if h == "/Lab":
        wp = cs[1].get("/WhitePoint") if len(cs) > 1 else None
        white = tuple(float(v) for v in wp) if wp is not None else (0.9642, 1.0, 0.8249)
        return _rgb_cmyk(*_lab_rgb(vals[0], vals[1], vals[2], white))
    if h == "/Indexed":
        base, hival, lut = cs[1], int(cs[2]), cs[3]
        data = lut.read_bytes() if isinstance(lut, pikepdf.Stream) else bytes(lut)
        nb = _ncomp(base)
        i = max(0, min(hival, int(vals[0] if vals else 0)))
        comp = [data[i * nb + j] / 255.0 for j in range(nb)]
        return to_cmyk(base, comp)
    if h in ("/Separation", "/DeviceN"):
        alt, fn = cs[2], cs[3]
        if h == "/Separation" and str(cs[1]) == "/None":
            return None
        try:
            return to_cmyk(alt, _fn(fn, vals))
        except Exception:
            # Unknown function: the ink's screen colour, mixed toward paper -
            # not the swatch's own CMYK, so convert() reports it.
            _FALLBACK.update(_spot_names(cs) or ["a spot"])
            try:
                from onecolor import _tint_rgb
                return _rgb_cmyk(*_tint_rgb(cs, vals))
            except Exception:
                t = max(vals) if vals else 1.0
                return [0.0, 0.0, 0.0, round(t, 4)]
    return [0.0, 0.0, 0.0, 1.0]


def _initial(cs):
    """The colour a 'cs' operator sets before any 'scn'."""
    if isinstance(cs, Name):
        return [0.0] * _ncomp(cs) if str(cs) not in ("/DeviceCMYK", "/CMYK") else [0, 0, 0, 1]
    h = str(cs[0])
    if h in ("/Separation", "/DeviceN"):
        return [1.0] * _ncomp(cs)
    if h == "/Lab":
        return [0.0, 0.0, 0.0]
    return [0.0] * _ncomp(cs)


def _needs(cs):
    """True if colour space `cs` (resolved) has to become DeviceCMYK."""
    if _is_keep(cs):
        return False
    if isinstance(cs, Name):
        return str(cs) not in ("/DeviceCMYK", "/CMYK", "/Pattern")
    h = str(cs[0])
    if h == "/Pattern":
        return False
    return True


# ── images ─────────────────────────────────────────────────────────────────

def _image(x, report):
    import numpy as np
    if x.get("/ImageMask"):
        return
    cs = x.get("/ColorSpace")
    if cs is None or (isinstance(cs, Name) and str(cs) == "/DeviceCMYK") or _is_keep(cs):
        return
    try:
        pim = pikepdf.PdfImage(x)
        w, h = int(x.Width), int(x.Height)
        head = str(cs) if isinstance(cs, Name) else str(cs[0])
        if head in ("/Separation", "/DeviceN", "/Indexed") or int(x.get("/BitsPerComponent", 8)) != 8 \
                or head == "/Lab":
            # Decode the samples, then map every possible value through to_cmyk.
            raw = np.frombuffer(x.read_bytes(), dtype=np.uint8)
            nc = _ncomp(cs)
            bpc = int(x.get("/BitsPerComponent", 8))
            if bpc != 8:
                bits = np.unpackbits(raw)
                row = w * nc * bpc
                stride = -(-row // 8) * 8
                bits = bits[:h * stride].reshape(h, stride)[:, :row].reshape(-1, bpc)
                vals = (bits * (1 << np.arange(bpc - 1, -1, -1))).sum(axis=1).astype(np.int32)
            else:
                vals = raw[:w * h * nc].astype(np.int32)
            vals = vals.reshape(h * w, nc)
            mx = (1 << bpc) - 1
            if nc == 1:
                lut = np.array([to_cmyk(cs, [v if head == "/Indexed" else v / mx]) or [0, 0, 0, 0]
                                for v in range(mx + 1)], dtype=np.float32)
                out = lut[vals[:, 0]]
            else:
                cache = {}
                out = np.zeros((h * w, 4), dtype=np.float32)
                keys = [tuple(r) for r in vals]
                for i, k in enumerate(keys):
                    if k not in cache:
                        cache[k] = to_cmyk(cs, [v / mx for v in k]) or [0, 0, 0, 0]
                    out[i] = cache[k]
        else:
            im = pim.as_pil_image()
            if im.mode in ("L", "1", "LA", "P", "RGBA", "RGB", "I", "I;16"):
                im = im.convert("RGB")
            if im.mode == "CMYK":
                return
            a = np.asarray(im, dtype=np.float32) / 255.0
            k = 1 - a.max(axis=2)
            d = np.where(k < 0.9999, 1 - k, 1.0)
            c = (1 - a[..., 0] - k) / d
            m = (1 - a[..., 1] - k) / d
            yy = (1 - a[..., 2] - k) / d
            out = np.stack([c, m, yy, k], axis=2).reshape(-1, 4)
        data = (np.clip(out, 0, 1) * 255 + 0.5).astype(np.uint8).tobytes()
        x.write(zlib.compress(data), filter=Name.FlateDecode)
        x.ColorSpace = Name.DeviceCMYK
        x.BitsPerComponent = 8
        for k in ("/Decode", "/DecodeParms", "/Intent"):
            if k in x:
                del x[k]
        report["images"] += 1
    except Exception as e:
        report["problems"].append(f"image left as it was ({e})")


# ── shadings ──────────────────────────────────────────────────────────────

def _shading(sh, report):
    cs = sh.get("/ColorSpace")
    if cs is None or not _needs(cs):
        return
    st = int(sh.get("/ShadingType", 0))
    if st not in (2, 3) or "/Function" not in sh:
        report["problems"].append(f"gradient type {st} left in its own colours")
        return
    try:
        fn = sh.Function
        dom = [float(v) for v in sh.get("/Domain", [0, 1])]
        n = 256
        rows = []
        for i in range(n):
            t = dom[0] + (dom[1] - dom[0]) * i / (n - 1)
            c = to_cmyk(cs, _fn(fn, [t])) or [0, 0, 0, 0]
            rows.append(bytes(int(max(0, min(1, v)) * 255 + 0.5) for v in c))
        return rows, dom
    except Exception as e:
        report["problems"].append(f"gradient left in its own colours ({e})")
        return None


# ── the walker ─────────────────────────────────────────────────────────────

def convert(path):
    report = {"converted": 0, "spots": [], "images": 0, "problems": []}
    _FALLBACK.clear()
    pdf = pikepdf.open(str(path), allow_overwriting_input=True)
    seen = set()
    dropped = set()
    walked_res = []

    def fix_shading(sh):
        if sh is None or (sh.objgen != (0, 0) and sh.objgen in seen):
            return
        if sh.objgen != (0, 0):
            seen.add(sh.objgen)
        got = _shading(sh, report)
        if not got:
            return
        rows, dom = got
        dropped.update(_spot_names(sh.get("/ColorSpace")))
        fs = pdf.make_stream(b"".join(rows))
        fs.FunctionType = 0
        fs.Domain = pikepdf.Array(dom)
        fs.Range = pikepdf.Array([0, 1, 0, 1, 0, 1, 0, 1])
        fs.Size = pikepdf.Array([len(rows)])
        fs.BitsPerSample = 8
        sh.Function = fs
        sh.ColorSpace = Name.DeviceCMYK
        if "/Background" in sh:
            del sh["/Background"]
        report["converted"] += 1

    def fix_res(res):
        """Images, gradients and patterns named in a resource dictionary."""
        if res is None:
            return
        walked_res.append(res)
        for _, x in (res.get("/XObject") or {}).items():
            if x.objgen in seen:
                continue
            seen.add(x.objgen)
            if x.get("/Subtype") == "/Image":
                cs = x.get("/ColorSpace")
                dropped.update(n for n in _spot_names(cs) if n.upper() not in KEEP)
                _image(x, report)
            elif x.get("/Subtype") == "/Form":
                walk(x, x.get("/Resources"))
        for _, sh in (res.get("/Shading") or {}).items():
            fix_shading(sh)
        for _, pat in (res.get("/Pattern") or {}).items():
            if pat.objgen in seen:
                continue
            seen.add(pat.objgen)
            if int(pat.get("/PatternType", 0)) == 2:
                fix_shading(pat.get("/Shading"))
            elif int(pat.get("/PatternType", 0)) == 1:
                walk(pat, pat.get("/Resources"))

    def walk(owner, res, is_page=False):
        grp = owner.get("/Group")
        if grp is not None and "/CS" in grp:
            grp.CS = Name.DeviceCMYK
        fix_res(res)
        ops = pikepdf.parse_content_stream(owner)
        # A page starts in DeviceGray black; say it in CMYK. A form inherits
        # whatever was set when it was drawn - already CMYK once its parent
        # is converted - so until it sets its own, leave its colours alone.
        out = [([0, 0, 0, 1], Operator("k")), ([0, 0, 0, 1], Operator("K"))] if is_page else []
        cur = {"f": Name.DeviceGray, "s": Name.DeviceGray} if is_page else {"f": None, "s": None}
        changed = is_page
        for operands, op in ops:
            o = str(op)
            if o in ("g", "G", "rg", "RG"):
                space = Name.DeviceGray if o.lower() == "g" else Name.DeviceRGB
                c = to_cmyk(space, operands)
                out.append((c, Operator("k" if o.islower() else "K")))
                cur["f" if o.islower() else "s"] = Name.DeviceCMYK
                report["converted"] += 1
                changed = True
                continue
            if o in ("k", "K"):
                cur["f" if o == "k" else "s"] = Name.DeviceCMYK
                out.append((operands, op))
                continue
            if o in ("cs", "CS"):
                key = "f" if o == "cs" else "s"
                cs = _deref_cs(operands[0], res)
                cur[key] = cs
                if _needs(cs):
                    dropped.update(n for n in _spot_names(cs) if n.upper() not in KEEP)
                    c = to_cmyk(cs, _initial(cs))
                    if c is not None:
                        out.append((c, Operator("k" if key == "f" else "K")))
                    changed = True
                    report["converted"] += 1
                    continue
                out.append((operands, op))
                continue
            if o in ("sc", "scn", "SC", "SCN"):
                key = "f" if o in ("sc", "scn") else "s"
                cs = cur[key]
                if cs is not None and _needs(cs):
                    vals = [v for v in operands if not isinstance(v, Name)]
                    c = to_cmyk(cs, vals)
                    if c is not None:
                        out.append((c, Operator("k" if key == "f" else "K")))
                    changed = True
                    report["converted"] += 1
                    continue
                out.append((operands, op))
                continue
            if o == "INLINE IMAGE":
                report["problems"].append("inline image left as it was")
            out.append((operands, op))
        if changed:
            data = pikepdf.unparse_content_stream(out)
            if is_page:
                owner.Contents = pdf.make_stream(data)
            else:
                owner.write(data)

    for page in pdf.pages:
        res = page.obj.get("/Resources")
        if res is None:
            res = getattr(page, "resources", None)
            if res is not None:
                page.obj.Resources = res
        walk(page.obj, res, True)
        if "/Group" in page.obj and "/CS" in page.obj.Group:
            page.obj.Group.CS = Name.DeviceCMYK

    # No spot swatch but WHITE left behind in any colour space dictionary.
    for res in walked_res:
        d = res.get("/ColorSpace")
        if d is None:
            continue
        for k in list(d.keys()):
            v = d[k]
            if _spot_names(v) and not _is_keep(v):
                del d[k]
    report["spots"] = sorted(n for n in dropped if n.upper() not in KEEP)
    for n in sorted(_FALLBACK):
        report["problems"].append(f"{n}: its CMYK couldn't be read from the file, so it was "
                                  "matched from the PANTONE's screen colour - check it")
    pdf.save(str(path))
    report["problems"] = sorted(set(report["problems"]))
    return report


def leftovers(path):
    """Every colour space still used in the file that isn't CMYK or WHITE
    (empty when the file is clean)."""
    pdf = pikepdf.open(str(path))
    bad, seen = set(), set()

    def walk(owner, res):
        for operands, op in pikepdf.parse_content_stream(owner):
            o = str(op)
            if o in ("g", "G", "rg", "RG"):
                bad.add(o)
            elif o in ("cs", "CS"):
                cs = _deref_cs(operands[0], res)
                if _needs(cs):
                    bad.add(str(cs[1]) if isinstance(cs, pikepdf.Array) and len(cs) > 1 else str(cs))
        for _, x in ((res or {}).get("/XObject") or {}).items():
            if x.objgen in seen:
                continue
            seen.add(x.objgen)
            if x.get("/Subtype") == "/Image" and not x.get("/ImageMask"):
                cs = x.get("/ColorSpace")
                if cs is not None and _needs(cs):
                    bad.add("image " + (str(cs) if isinstance(cs, Name) else str(cs[0])))
            elif x.get("/Subtype") == "/Form":
                walk(x, x.get("/Resources"))
        for k, v in (((res or {}).get("/ColorSpace")) or {}).items():
            if _spot_names(v) and not _is_keep(v):
                bad.add("swatch " + _spot_names(v)[0])

    for page in pdf.pages:
        walk(page.obj, page.obj.get("/Resources"))
    return sorted(bad)
