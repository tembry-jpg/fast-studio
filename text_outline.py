"""
Live text in uploaded artwork.

A customer's PDF / AI file can carry its lettering as live text instead of
outlines. Everything downstream then depends on that font: the preview, the
press files, and Illustrator when the floor opens them. Illustrator swaps in a
substitute for any font that isn't installed, and a substitute that lacks a
glyph prints a box - "1900" on a street sign came out as a box and two zeros.

    fonts(path)            the fonts the file's text uses, and whether each
                           one's outlines are inside the file
    outline(src, dst)      the same artwork with every letter turned into
                           shapes (Ghostscript, -dNoOutputFonts), checked to
                           look the same as the original

When every font is inside the file, the upload is outlined, so nothing after
it needs the font. When one isn't, nothing can draw that text correctly - not
this site, not Illustrator - so the file is left as it is and the artist is
told which font is missing, to ask the customer for outlined art.
"""
import shutil
import subprocess
import tempfile
from pathlib import Path

import pikepdf

_FONT_FILES = ("/FontFile", "/FontFile2", "/FontFile3")


def _font_record(font):
    """(name, embedded) for one font dictionary."""
    name = str(font.get("/BaseFont") or font.get("/Name") or "?").lstrip("/")
    if "+" in name[:7]:                       # subset tag: ABCDEF+FontName
        name = name.split("+", 1)[1]
    sub = str(font.get("/Subtype") or "")
    if sub == "/Type3":
        return name, True                     # its glyphs are drawn in the file
    desc = font.get("/FontDescriptor")
    if sub == "/Type0":
        kids = font.get("/DescendantFonts") or []
        desc = kids[0].get("/FontDescriptor") if len(kids) else None
    embedded = bool(desc is not None and any(k in desc for k in _FONT_FILES))
    return name, embedded


def fonts(path, max_pages=2):
    """The fonts the file's first pages actually draw text with:
    [{"name", "embedded"}], one per name. Fonts only listed in a page's
    resources (applications often add one by default) don't count."""
    out, seen = {}, set()

    def walk(owner, depth=0):
        if depth > 12:
            return
        res = owner.get("/Resources") or pikepdf.Dictionary()
        fonts_ = res.get("/Font") or {}
        xobj = res.get("/XObject") or {}
        try:
            ops = pikepdf.parse_content_stream(owner)
        except Exception:
            return
        cur = None                            # the font set by the last Tf
        for operands, op in ops:
            o = str(op)
            if o == "Tf" and operands:
                cur = fonts_.get(operands[0])
            elif o in ("Tj", "TJ", "'", '"') and cur is not None:
                # Counted when text is actually drawn in it: a Tf on its own
                # (some applications set one at the top of every page) isn't.
                try:
                    nm, emb = _font_record(cur)
                    out[nm] = out.get(nm, True) and emb
                except Exception:
                    pass
            elif o == "Do" and operands:
                x = xobj.get(operands[0])
                if isinstance(x, pikepdf.Stream) and x.get("/Subtype") == "/Form" and x.objgen not in seen:
                    seen.add(x.objgen)
                    walk(x, depth + 1)

    with pikepdf.open(str(path)) as pdf:
        for page in list(pdf.pages)[:max_pages]:
            walk(page.obj)
    return [{"name": n, "embedded": e} for n, e in out.items()]


def _render(pdf, out_dir, dpi=150):
    subprocess.run(["pdftoppm", "-r", str(dpi), "-f", "1", "-l", "1", "-png", str(pdf), str(Path(out_dir) / "p")],
                   check=True, capture_output=True, timeout=120)
    return sorted(Path(out_dir).glob("p*.png"))[0]


def _looks_same(a_pdf, b_pdf):
    import numpy as np
    from PIL import Image
    from PIL import ImageFilter
    # Outlines and the font's own rasteriser anti-alias thin strokes slightly
    # differently, so both are softened first: what is compared is where the
    # ink is, not how each renderer shades a hairline's edge.
    with tempfile.TemporaryDirectory() as ta, tempfile.TemporaryDirectory() as tb:
        A = np.asarray(Image.open(_render(a_pdf, ta)).convert("L").filter(ImageFilter.GaussianBlur(1.2)), dtype=np.int16)
        B = np.asarray(Image.open(_render(b_pdf, tb)).convert("L").filter(ImageFilter.GaussianBlur(1.2)), dtype=np.int16)
    if A.shape != B.shape:
        return False
    return (np.abs(A - B) > 48).mean() <= 0.003


def outline(src, dst):
    """Write `src` to `dst` with its text as outlines. True if it worked and
    looks the same; on any problem `dst` is not left behind and False comes back."""
    gs = shutil.which("gs") or shutil.which("ghostscript")
    if not gs:
        return False
    dst = Path(dst)
    try:
        subprocess.run([gs, "-q", "-dNOPAUSE", "-dBATCH", "-dSAFER", "-dNoOutputFonts",
                        "-sDEVICE=pdfwrite", "-dCompatibilityLevel=1.7",
                        f"-sOutputFile={dst}", str(src)],
                       check=True, capture_output=True, timeout=180)
        if not dst.is_file() or dst.stat().st_size == 0:
            raise RuntimeError("no output")
        if fonts(dst):
            raise RuntimeError("text left in the file")
        if not _looks_same(src, dst):
            raise RuntimeError("outlined art does not match the original")
        return True
    except Exception as e:
        print(f"⚠️ text not outlined ({Path(src).name}): {e}")
        dst.unlink(missing_ok=True)
        return False


def prepare(path):
    """
    For an uploaded PDF / AI: (path to use, note for the artist or None).

    No text: the file as it is, no note. Text in fonts the file carries: an
    outlined copy beside it. Text in a font the file doesn't carry: the file as
    it is and a warning naming the font.
    """
    path = Path(path)
    try:
        fl = fonts(path)
    except Exception as e:
        print(f"⚠️ fonts not read ({path.name}): {e}")
        return path, None
    if not fl:
        return path, None
    missing = [f["name"] for f in fl if not f["embedded"]]
    if missing:
        names = ", ".join(dict.fromkeys(missing))
        return path, (f"This file has live text in a font it doesn't include ({names}). "
                      "It may print in the wrong font or with missing letters - ask the customer "
                      "for the art with text converted to outlines.")
    out = path.with_name(path.stem + ".outlined.pdf")
    if outline(path, out):
        return out, "Text in this file was converted to outlines."
    return path, ("This file has live text that couldn't be converted to outlines here. "
                  "Check it prints in the right font, or ask for outlined art.")
