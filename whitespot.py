"""
White ink as a named spot.

The Mimaki prints white only from a spot color named WHITE. Anything in the
file meant to print white comes out of the customer's art, the recolor step
or the configurator in one of several shapes: RGB/gray/CMYK white, or a
Separation someone named "White", "White Ink", "PANTONE White"… Every one of
them is switched to a single Separation named exactly WHITE.

Vector content only: page and form content streams, recursively. White pixels
inside a raster image can't be a spot; convert() reports how many images it
left alone so the export can say so.
"""
import re
import pikepdf
from pikepdf import Name, Operator

SPOT_NAME = "WHITE"
# Screen preview of the white ink: the same light pink the screen-print press
# files use for their white spot (onecolor.WHITE_SPOT_PREVIEW_CMYK), so the
# white reads on screen and matches the other items (confirmed 2026-10-07).
try:
    from onecolor import WHITE_SPOT_PREVIEW_CMYK as _SP_PINK
    PREVIEW_CMYK = list(_SP_PINK)
except Exception:
    PREVIEW_CMYK = [0.0, 0.25, 0.04, 0.0]
_RES_KEY = "/NumoWHITE"
_TOL = 0.02


def _is_white_name(nm):
    return bool(re.search(r"white", str(nm).lstrip("/"), re.I))


def _num(v):
    try:
        return float(v)
    except Exception:
        return None


def _white_values(kind, vals):
    v = [_num(x) for x in vals]
    if any(x is None for x in v):
        return False
    if kind == "gray" and len(v) == 1:
        return v[0] >= 1 - _TOL
    if kind == "rgb" and len(v) == 3:
        return min(v) >= 1 - _TOL
    if kind == "cmyk" and len(v) == 4:
        return max(v) <= _TOL
    return False


def _space_kind(cs):
    """gray/rgb/cmyk for device and ICC spaces, 'white' for a white-named
    Separation, None for anything else."""
    if cs is None:
        return None
    if isinstance(cs, pikepdf.Name):
        return {"/DeviceGray": "gray", "/DeviceRGB": "rgb", "/DeviceCMYK": "cmyk"}.get(str(cs))
    try:
        head = str(cs[0])
    except Exception:
        return None
    if head == "/ICCBased":
        n = int(cs[1].get("/N", 0))
        return {1: "gray", 3: "rgb", 4: "cmyk"}.get(n)
    if head == "/Separation" and _is_white_name(cs[1]):
        return "white"
    return None


def _is_marker(kind, vals, marker):
    """The exact stand-in colour (rgb 0-1) a recolor painted the white ink in."""
    v = [_num(x) for x in vals]
    return kind == "rgb" and len(v) == 3 and None not in v and \
        all(abs(a - b) <= 0.002 for a, b in zip(v, marker))


def _rewrite(owner, res, stats, marker=None):
    try:
        ops = pikepdf.parse_content_stream(owner)
    except Exception:
        return False
    spaces = (res.get("/ColorSpace") if res is not None else None) or {}
    fill = stroke = None
    out, changed = [], False

    def spot(stroking):
        return [([Name(_RES_KEY)], Operator("CS" if stroking else "cs")),
                ([1], Operator("SCN" if stroking else "scn"))]

    for operands, op in ops:
        o = str(op)
        kind = {"g": "gray", "G": "gray", "rg": "rgb", "RG": "rgb", "k": "cmyk", "K": "cmyk"}.get(o)
        if kind:
            stroking = o.isupper()
            if stroking: stroke = kind
            else: fill = kind
            if (_is_marker(kind, operands, marker) if marker else _white_values(kind, operands)):
                out.extend(spot(stroking)); changed = True; stats["vector"] += 1
                if stroking: stroke = "spot"
                else: fill = "spot"
                continue
        elif o in ("cs", "CS"):
            nm = str(operands[0]) if operands else ""
            k = _space_kind(Name(nm)) if nm in ("/DeviceGray", "/DeviceRGB", "/DeviceCMYK") \
                else _space_kind(spaces.get(nm))
            if o == "cs": fill = k
            else: stroke = k
            if k == "white" and not marker:      # a white-named spot: becomes WHITE
                out.append(([Name(_RES_KEY)], op)); changed = True
                continue
        elif o in ("sc", "scn", "SC", "SCN"):
            k = fill if o in ("sc", "scn") else stroke
            stroking = o in ("SC", "SCN")
            if k == "white" and not marker:
                out.append((operands, op)); stats["vector"] += 1
                continue
            if k in ("gray", "rgb", "cmyk") and (_is_marker(k, operands, marker) if marker
                                                 else _white_values(k, operands)):
                out.extend(spot(stroking)); changed = True; stats["vector"] += 1
                if stroking: stroke = "spot"
                else: fill = "spot"
                continue
        out.append((operands, op))
    if changed:
        owner.write(pikepdf.unparse_content_stream(out))
    return changed


def convert(pdf_path, out_path=None, marker=None):
    """Rewrite every white in pdf_path to the WHITE spot. Returns
    {"vector": n white paints converted, "images": n raster images left}.

    marker: an rgb (0-1) the art was recolored to for a white ink. Only that
    colour becomes WHITE; real whites stay process white, which the Mimaki
    leaves unprinted (the knockouts of a one-ink recolor)."""
    pdf = pikepdf.open(str(pdf_path), allow_overwriting_input=True)
    cs = pdf.make_indirect(pikepdf.Array([
        Name.Separation, Name("/" + SPOT_NAME), Name.DeviceCMYK,
        pikepdf.Dictionary(FunctionType=2, Domain=[0, 1], C0=[0, 0, 0, 0],
                           C1=PREVIEW_CMYK, N=1)]))
    stats = {"vector": 0, "images": 0}
    seen = set()

    def add_space(res):
        if "/ColorSpace" not in res:
            res.ColorSpace = pikepdf.Dictionary()
        res.ColorSpace[_RES_KEY] = cs

    def walk(owner, res):
        if res is None:
            res = pikepdf.Dictionary()
            owner.Resources = res
        _rewrite(owner, res, stats, marker)
        add_space(res)
        for _, x in list((res.get("/XObject") or {}).items()):
            if x.objgen in seen:
                continue
            seen.add(x.objgen)
            st = x.get("/Subtype")
            if st == Name.Form:
                walk(x, x.get("/Resources"))
            elif st == Name.Image:
                stats["images"] += 1

    for page in pdf.pages:
        walk(page.obj, page.obj.get("/Resources"))
    pdf.save(str(out_path or pdf_path))
    return stats
