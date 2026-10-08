"""Check that registration lands on every plate of a press file.

Separates each PDF with Ghostscript (tiffsep, like a separating RIP) and, per
page, compares every spot plate with the Black plate: everything drawn in
[Registration] (crop marks, targets, the NSO number and captions) is on Black,
so it must be on each spot plate too.

    python3 tools/check_plates.py FILE.pdf [FILE.pdf ...]

Prints one line per page; exits 1 if any spot plate is missing registration.
"""
import subprocess, sys, tempfile
from pathlib import Path
import numpy as np
from PIL import Image

PROCESS = {"Cyan", "Magenta", "Yellow", "Black"}


def check(pdf, dpi=20):
    bad = 0
    with tempfile.TemporaryDirectory() as t:
        subprocess.run(["gs", "-q", "-dNOPAUSE", "-dBATCH", "-sDEVICE=tiffsep", f"-r{dpi}",
                        f"-sOutputFile={t}/p%03d.tif", str(pdf)], check=True, timeout=600)
        pages = sorted(Path(t).glob("p[0-9][0-9][0-9].tif"))
        for pg in pages:
            stem = pg.stem
            plates = {f.name[len(stem) + 1:-5]: f for f in Path(t).glob(f"{stem}(*).tif")}
            k = np.asarray(Image.open(plates["Black"]).convert("L")) < 128
            # Registration = on all four process plates (art in black alone is not)
            reg = k.copy()
            for c in ("Cyan", "Magenta", "Yellow"):
                reg &= np.asarray(Image.open(plates[c]).convert("L")) < 128
            spots = [n for n in plates if n not in PROCESS]
            res = []
            for s in spots:
                sp = np.asarray(Image.open(plates[s]).convert("L")) < 128
                pct = 100.0 * (reg & sp).sum() / max(1, reg.sum())
                res.append(f"{s}: {pct:.0f}%")
                if reg.sum() and pct < 95:
                    bad += 1
            print(f"{Path(pdf).name} p{int(stem[1:])}: registration px {int(reg.sum())}; on spot plates -> "
                  + (", ".join(res) or "no spot plates"))
    return bad


if __name__ == "__main__":
    n = sum(check(f) for f in sys.argv[1:])
    sys.exit(1 if n else 0)
