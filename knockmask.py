"""
Knockouts in full-colour (4CP) art.

On a 4CP item the art sits on a background (a solid, a gradient, a picture).
White in the art that is a knockout - the CC inside a black diamond, a
letter's counter, the white box a logo was drawn on - has to show that
background, as the proof shows it. Leaving the white shape out doesn't do it
(the diamond under it shows instead), and painting it white prints white.

The recolor paints those shapes in a stand-in colour (whitespot.KO_MARK).
Here the art becomes a form drawn through a soft mask: the same art with
every shape white (shows) and every stand-in shape black (hidden), in the
order drawn, so a shape drawn on top of a knockout shows again. Vector stays
vector; the RIP and every viewer handle soft masks.
"""
import pikepdf
from pikepdf import Name, Operator

_COLOR_OPS = {"g", "G", "rg", "RG", "k", "K", "sc", "SC", "scn", "SCN", "cs", "CS"}


def _is_ko(operands, ko, tol=0.002):
    try:
        v = [float(x) for x in operands]
    except Exception:
        return False
    return len(v) == 3 and all(abs(a - b) <= tol for a, b in zip(v, ko))


def _has_ko(owner, res, ko, seen):
    try:
        for operands, op in pikepdf.parse_content_stream(owner):
            if str(op) in ("rg", "RG") and _is_ko(operands, ko):
                return True
            if str(op) == "Do" and res is not None:
                x = (res.get("/XObject") or {}).get(str(operands[0]))
                if x is not None and x.get("/Subtype") == Name.Form and x.objgen not in seen:
                    seen.add(x.objgen)
                    if _has_ko(x, x.get("/Resources"), ko, seen):
                        return True
    except Exception:
        return False
    return False


def _to_mask(owner, res, ko, seen):
    """Rewrite a content stream (and its forms) to its mask: shapes white,
    knockout shapes black."""
    try:
        ops = pikepdf.parse_content_stream(owner)
    except Exception:
        return
    out = []
    for operands, op in ops:
        o = str(op)
        if o in _COLOR_OPS:
            stroke = o.isupper()
            if o in ("cs", "CS"):
                continue                                    # colour comes from rg/RG below
            val = 0 if (o in ("rg", "RG") and _is_ko(operands, ko)) else 1
            out.append(([val, val, val], Operator("RG" if stroke else "rg")))
            continue
        out.append((operands, op))
        if o == "Do" and res is not None:
            x = (res.get("/XObject") or {}).get(str(operands[0]))
            if x is not None and x.get("/Subtype") == Name.Form and x.objgen not in seen:
                seen.add(x.objgen)
                _to_mask(x, x.get("/Resources"), ko, seen)
    owner.write(pikepdf.unparse_content_stream(out))


def apply(pdf_path, ko, out_path=None):
    """Knock out the stand-in shapes of the art in pdf_path (page 1).
    Returns True when the file had any and was rewritten."""
    src = pikepdf.open(str(pdf_path), allow_overwriting_input=True)
    page = src.pages[0]
    if not _has_ko(page.obj, page.obj.get("/Resources"), ko, set()):
        src.close()
        return False
    # The mask: a second copy of the art, recoloured white / black.
    m = pikepdf.open(str(pdf_path))
    mp = m.pages[0]
    mp.contents_coalesce()                       # one stream for the page's own content
    _to_mask(mp.obj.Contents, mp.obj.get("/Resources"), ko, set())
    mask_form = src.copy_foreign(m.make_stream(
        mp.obj.Contents.read_bytes(), Type=Name.XObject, Subtype=Name.Form,
        BBox=[float(v) for v in mp.MediaBox], Resources=mp.obj.get("/Resources") or pikepdf.Dictionary()))
    mask_form.Group = pikepdf.Dictionary(Type=Name.Group, S=Name.Transparency, CS=Name.DeviceRGB)
    # The art as a form of its own: a copy of the page's content, its resources.
    page.contents_coalesce()
    mb = [float(v) for v in page.MediaBox]
    art_form = src.make_stream(page.obj.Contents.read_bytes(), Type=Name.XObject, Subtype=Name.Form,
                               BBox=mb, Resources=page.obj.get("/Resources") or pikepdf.Dictionary())
    gs = pikepdf.Dictionary(Type=Name.ExtGState, SMask=pikepdf.Dictionary(
        Type=Name.Mask, S=Name.Luminosity, G=mask_form))
    page.obj.Resources = pikepdf.Dictionary(
        XObject=pikepdf.Dictionary(NumoArt=art_form),
        ExtGState=pikepdf.Dictionary(NumoKO=src.make_indirect(gs)))
    page.obj.Contents = src.make_stream(b"q /NumoKO gs /NumoArt Do Q\n")
    src.save(str(out_path or pdf_path))
    m.close()
    return True
