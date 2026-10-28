"""
Numo's special swatches for 4CP (the Fiery), from "Numo Special Swatches
2025.ase". The Fiery knows each one by its exact name and prints it the way
the 4CP team tuned it (a natural canvas that matches the material, a rich
black, a white that stays white instead of dusty or yellowish), so a print
file must carry them as named spots, spelled exactly so, with the alternate
the swatch file gives.

"offered" ones are in the configurator's pickers on 4CP items. The rest are
kept here so a file that already uses them keeps them (never turned to RGB).
"""

# name: (screen colour, alternate space, alternate values, offered)
SWATCHES = {
    "4CP Numo Natural Canvas DC": ("#F5EFE7", "rgb", [0.9608, 0.9373, 0.9059], True),
    "NUMO Spot Black CMYK":       ("#0E0E0E", "cmyk", [1, 1, 1, 1], True),
    "Numo Spot White RGB":        ("#FFFFFF", "rgb", [1, 1, 1], True),
    "4CP Numo 540C DC":           ("#07426B", "rgb", [0.0275, 0.2588, 0.4196], True),
    "Marshmallow":                ("#F0F2F3", "lab", [95.31, -0.5914, -0.8171], True),
    # In the swatch file, not offered: what they're for is the 4CP team's call.
    "Spot White":                 ("#FFFFFF", "cmyk", [1, 0, 0, 0], False),
    "Will print white":           ("#E88FD3", "cmyk", [0.0949, 0.45, 0.0403, 0], False),
    "Only Rep on the Proof":      ("#2E2D2B", "rgb", [0.1808, 0.1783, 0.1689], False),
}
_BY_UPPER = {k.upper(): k for k in SWATCHES}


def name_of(nm):
    """The swatch's exact name for `nm` (any case, "PANTONE " in front or
    not), or None if it isn't one of Numo's."""
    s = str(nm or "").strip()
    if s.upper().startswith("PANTONE "):
        s = s[8:].strip()
    return _BY_UPPER.get(s.upper())


def is_numo(nm):
    return name_of(nm) is not None


def offered():
    """What the configurator lists on 4CP items."""
    return [{"name": k, "short": k, "hex": v[0], "numo": True}
            for k, v in SWATCHES.items() if v[3]]


def separation(pdf, nm):
    """A pikepdf Separation array for swatch `nm`, its alternate exactly as
    in the swatch file; None if `nm` isn't one of Numo's."""
    import pikepdf
    k = name_of(nm)
    if not k:
        return None
    _, space, vals, _ = SWATCHES[k]
    if space == "rgb":
        alt, c0 = pikepdf.Name.DeviceRGB, [1, 1, 1]
    elif space == "cmyk":
        alt, c0 = pikepdf.Name.DeviceCMYK, [0, 0, 0, 0]
    else:
        alt = pikepdf.Array([pikepdf.Name.Lab, pikepdf.Dictionary(
            WhitePoint=[0.9642, 1, 0.8249], Range=[-128, 127, -128, 127])])
        c0 = [100, 0, 0]
    fn = pikepdf.Dictionary(FunctionType=2, Domain=[0, 1], C0=c0, C1=list(vals), N=1)
    arr = pikepdf.Array([pikepdf.Name.Separation, pikepdf.Name("/" + k), alt, fn])
    return pdf.make_indirect(arr) if pdf is not None else arr
