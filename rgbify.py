"""
Rewrite a PDF so every colour is RGB — for 4CP, which the team RIPs in RGB to
match the proofs and virtuals.

CMYK becomes RGB with poppler's own conversion (the one that drew the preview
the customer saw), so the print file carries the colours the virtual showed.
Covered: k/K operators, DeviceCMYK / 4-channel ICC colour spaces set with
cs/CS, Separation colours with a simple (type 2) CMYK tint function, CMYK and
Indexed-CMYK images. The "Notches" spot and Registration (/All) are left alone.
Vectors stay vectors.
"""
import zlib
import numpy as np
import pikepdf
from pikepdf import Name, Operator

KEEP_SPOTS = {"/Notches", "/All"}


def cmyk_to_rgb(c, m, y, k):
    """poppler's GfxDeviceCMYKColorSpace::getRGB (the table interpolation)."""
    c, m, y, k = (np.asarray(v, dtype=np.float64) for v in (c, m, y, k))
    c1, m1, y1, k1 = 1 - c, 1 - m, 1 - y, 1 - k
    r = np.zeros(np.broadcast(c, m, y, k).shape); g = r.copy(); b = r.copy()
    def add(x, rr, gg, bb):
        nonlocal r, g, b
        r = r + rr * x; g = g + gg * x; b = b + bb * x
    add(c1 * m1 * y1 * k1, 1, 1, 1)
    add(c1 * m1 * y1 * k, .1373, .1216, .1255)
    add(c1 * m1 * y * k1, 1, .9490, 0)
    add(c1 * m1 * y * k, .1098, .1020, 0)
    add(c1 * m * y1 * k1, .9255, 0, .5490)
    add(c1 * m * y1 * k, .1412, 0, 0)
    add(c1 * m * y * k1, .9294, .1098, .1412)
    add(c1 * m * y * k, .1333, 0, 0)
    add(c * m1 * y1 * k1, 0, .6784, .9373)
    add(c * m1 * y1 * k, 0, .0588, .1412)
    add(c * m1 * y * k1, 0, .6510, .3137)
    add(c * m1 * y * k, 0, .0745, 0)
    add(c * m * y1 * k1, .1804, .1922, .5725)
    add(c * m * y1 * k, 0, 0, .0078)
    add(c * m * y * k1, .2118, .2119, .2235)
    return np.clip(r, 0, 1), np.clip(g, 0, 1), np.clip(b, 0, 1)


def _rgb(vals):
    r, g, b = cmyk_to_rgb(*[float(v) for v in vals])
    return [round(float(r), 4), round(float(g), 4), round(float(b), 4)]


def _cs_kind(cs):
    """'cmyk', ('sep', C0, C1) for a CMYK-alternate spot, or None."""
    try:
        if isinstance(cs, pikepdf.Name):
            return "cmyk" if cs == Name.DeviceCMYK else None
        if isinstance(cs, pikepdf.Array) and len(cs):
            fam = cs[0]
            if fam == Name.ICCBased and int(cs[1].get("/N", 0)) == 4:
                return "cmyk"
            if fam == Name.Separation and str(cs[1]) not in KEEP_SPOTS and cs[2] == Name.DeviceCMYK:
                fn = cs[3]
                if isinstance(fn, pikepdf.Dictionary) and int(fn.get("/FunctionType", 0)) == 2:
                    c0 = [float(v) for v in fn.get("/C0", [0, 0, 0, 0])]
                    c1 = [float(v) for v in fn.get("/C1", [1, 1, 1, 1])]
                    return ("sep", c0, c1)
    except Exception:
        return None
    return None


def _fix_image(img):
    cs = img.get("/ColorSpace")
    if cs is None:
        return
    # Indexed over CMYK: convert the palette.
    if isinstance(cs, pikepdf.Array) and len(cs) == 4 and cs[0] == Name.Indexed and _cs_kind(cs[1]) == "cmyk":
        look = cs[3]
        data = look.read_bytes() if isinstance(look, pikepdf.Stream) else bytes(look)
        a = np.frombuffer(data[: len(data) // 4 * 4], dtype=np.uint8).reshape(-1, 4) / 255.0
        r, g, b = cmyk_to_rgb(a[:, 0], a[:, 1], a[:, 2], a[:, 3])
        rgb = (np.stack([r, g, b], 1) * 255 + .5).astype(np.uint8).tobytes()
        img.ColorSpace = pikepdf.Array([Name.Indexed, Name.DeviceRGB, cs[2], pikepdf.String(rgb)])
        return
    if _cs_kind(cs) != "cmyk":
        return
    try:
        from pikepdf import PdfImage
        pim = PdfImage(img).as_pil_image()
        if pim.mode != "CMYK":
            return
        a = np.asarray(pim).astype(np.float64) / 255.0
        dec = img.get("/Decode")
        if dec is not None and [float(v) for v in dec][:2] == [1.0, 0.0]:
            a = 1 - a
        r, g, b = cmyk_to_rgb(a[..., 0], a[..., 1], a[..., 2], a[..., 3])
        rgb = (np.stack([r, g, b], -1) * 255 + .5).astype(np.uint8)
        img.write(zlib.compress(rgb.tobytes()), filter=Name.FlateDecode)
        img.ColorSpace = Name.DeviceRGB
        img.BitsPerComponent = 8
        for k in ("/Decode", "/DecodeParms"):
            if k in img:
                del img[k]
    except Exception as e:
        print(f"rgbify: image left as is ({e})")


def _rewrite_stream(owner, res):
    try:
        ops = pikepdf.parse_content_stream(owner)
    except Exception:
        return
    spaces = (res.get("/ColorSpace") if res is not None else None) or {}
    fill = stroke = None                    # current kind for sc/scn
    out, changed = [], False
    for operands, op in ops:
        o = str(op)
        if o in ("k", "K") and len(operands) == 4:
            out.append((_rgb(operands), Operator("rg" if o == "k" else "RG"))); changed = True; continue
        if o in ("cs", "CS"):
            nm = operands[0]
            kind = "cmyk" if nm == Name.DeviceCMYK else _cs_kind(spaces.get(str(nm))) if str(nm) in spaces else None
            if o == "cs": fill = kind
            else: stroke = kind
            if kind:
                out.append(([Name.DeviceRGB], op)); changed = True; continue
        if o in ("sc", "scn", "SC", "SCN"):
            kind = fill if o in ("sc", "scn") else stroke
            if kind == "cmyk" and len(operands) == 4:
                out.append((_rgb(operands), op)); changed = True; continue
            if isinstance(kind, tuple) and len(operands) == 1:
                t = float(operands[0]); c0, c1 = kind[1], kind[2]
                out.append((_rgb([a + (b - a) * t for a, b in zip(c0, c1)]), op)); changed = True; continue
        if o in ("rg", "g", "RG", "G"):
            if o in ("rg", "g"): fill = None
            else: stroke = None
        out.append((operands, op))
    if changed:
        owner.write(pikepdf.unparse_content_stream(out))


def convert(pdf_path, out_path=None):
    pdf = pikepdf.open(str(pdf_path), allow_overwriting_input=True)
    seen = set()
    def walk_res(res):
        if res is None:
            return
        for _, x in (res.get("/XObject") or {}).items():
            if x.objgen in seen:
                continue
            seen.add(x.objgen)
            st = x.get("/Subtype")
            if st == Name.Image:
                _fix_image(x)
                sm = x.get("/SMask")
            elif st == Name.Form:
                _rewrite_stream(x, x.get("/Resources"))
                walk_res(x.get("/Resources"))
    for page in pdf.pages:
        res = page.obj.get("/Resources")
        _rewrite_stream(page, res)
        walk_res(res)
    pdf.save(str(out_path or pdf_path))
