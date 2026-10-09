# engine.py — Color utilities and Pantone matching (Adobe-free)
# No ExtendScript, no win32com, no osascript — runs anywhere.

import os
import math
import importlib.util as _ilu

# ---------------------------------------------------------------------------
# THREAD LIBRARY
# ---------------------------------------------------------------------------

THREADS = {
    "Red": "#D50032", "Burgundy": "#7A263A", "Orange": "#FF6A13", "Neon Orange": "#FF4F00",
    "Yellow": "#FEDD00", "Neon Yellow": "#E1F400", "Neon Green": "#3BD23B", "Class Green": "#006341",
    "Black": "#1C1C1C", "Gray": "#A7A8AA", "Neon Pink": "#FF6EC7", "Cerise": "#E10098",
    "Purple": "#6F2C91", "Navy": "#1D252D", "Royal Blue": "#0033A0", "Teal": "#0097C8",
    "Brown": "#5B3A29", "Khaki": "#C3B091", "White": "#F2F2F2"
}

# ---------------------------------------------------------------------------
# NEOPRENE LIBRARY
# ---------------------------------------------------------------------------

NEOPRENE = {
    "Red": "#AE0D2E", "Garnet": "#8A2432", "Maroon": "#6D1A36", "Texas Orange": "#A6541B", "Brown": "#674230", "Orange": "#FF8200",
    "Blaze Orange": "#FF5715",
    "Mustard": "#D4AE40", "Goldenrod": "#F3BF08", "Bright Yellow": "#F2DE2A",
    "Citron": "#D5DD43", "Fluor Green": "#93DC4A", "Lime": "#70BB78", "Emerald Green": "#007549",
    "Deep Green": "#005749", "Evergreen": "#006745", "Jungle Green": "#2D5A27", "Dark Spruce": "#3B5C2A",
    "Canteen": "#6D712E",
    "Sea Green": "#4BC3A8", "Ice Green": "#A8D5C2", "Mint": "#98DBC6", "Aqua": "#05A3B8",
    "Teal": "#008080", "Tropical": "#58C9D4", "Dark Tropical": "#0AA4C8", "Ocean Blue": "#1CACD6",
    "Sky Blue": "#7DAED3", "Electric Blue": "#0063A2", "Royal": "#003490", "Navy": "#001F5B",
    "Indigo": "#266B91", "Something Blue": "#8FADBD", "Periwinkle": "#7C83BC", "Lilac Breeze": "#B1A0CB",
    "Dark Purple": "#4A1A6B", "Fuchsia": "#CC0066", "Violet": "#5A1F52", "Orchid": "#CE69B1",
    "Magenta": "#A72067", "Rose": "#C62A9D", "Hot Pink": "#D951A4", "Bubblegum": "#ED7A9E",
    "Perfect Pink": "#E35B8F", "Neon Coral": "#EF4755", "Coral": "#FF6B6B", "Peach": "#E8BFB8",
    "Light Peach": "#ECC3B2",
    "Beige": "#B0AA7E", "Gray": "#9E9E9E", "Ash": "#42464E", "Slate": "#555759", "Black": "#1C1C1C", "White": "#E6E6E6"   # was "Off White"
}

# ---------------------------------------------------------------------------
# SCUBA FOAM LIBRARY
# ---------------------------------------------------------------------------

SCUBA_FOAM = {
    "Red": "#CC0000", "Crimson": "#9E2A2B", "Burgundy": "#6B1A36",
    "Texas Orange": "#C26730", "Bright Orange": "#E35205", "Yellow": "#FEDD00",
    "Lime": "#78D64B", "Kelly Green": "#007A3E", "Neon Pink": "#FF0080",
    "Magenta": "#D1469F", "Purple": "#582C83", "Navy": "#1D2951",
    "Royal": "#003DA5", "Neon Blue": "#009CDE", "Teal": "#007B7A",
    "Forest Green": "#024930", "Light Pink": "#F2B8DA", "Grey": "#A7A8AA",
    "Black": "#1C1C1C", "White": "#F0F0F0", "Khaki Dark": "#B5A67D",
    "Khaki": "#D4C9A8", "Brown": "#6B3D2E"
}


# ---------------------------------------------------------------------------
# COTTON CANVAS LIBRARY
# ---------------------------------------------------------------------------
#
# Tote bag body fabric. Natural is its own catalogue item priced separately
# from the dyed canvases, which is why 5001-7 (natural) and 5001-cc (colour
# canvas) are two products rather than one product with a colour picker.
#
# 5001-7 therefore offers exactly one colourway, and the configurator hides
# the picker rather than showing a list of one. The dyed colours belong to
# 5001-cc and go in COTTON_CANVAS_DYED when that item is added.

COTTON_CANVAS = {
    "Natural": "#E9DBCA",
}

# The dyed canvases, which are 5001-cc. Natural is deliberately absent: it is
# undyed, priced differently, and sold as 5001-7. Listing it here would let a
# customer configure a natural tote under the colour-canvas item number and be
# quoted the wrong price.
COTTON_CANVAS_DYED = {
    "Fruit Punch":   "#B3263B",
    "Sangria":       "#75313F",
    "Fairytale":     "#F5C7D5",
    "Tickled Pink":  "#D88EA9",
    "Drama Queen":   "#C94770",
    "Peach":         "#FFB3AD",
    "Grapefruit":    "#D34A59",
    "Creamsicle":    "#FFBE8C",
    "Crush":         "#FF8759",
    "Lemon Chiffon": "#F0E68C",
    "Daffodil":      "#F5D84F",
    "Key Lime Pie":  "#B9DFA1",
    "Mint To Be":    "#9BC9B6",
    "Turquoise":     "#27A78E",
    "Easy Breezy":   "#C5E8DF",
    "Pool Blue":     "#008F98",
    "Powder Puff":   "#B6CED8",
    "Cornflower":    "#9499B8",
    "Sapphire":      "#345B84",
    "Midnight":      "#36455F",
    "Pansy":         "#79477D",
    "Lavender":      "#C5B1C9",
    "Overcast":      "#ADA6A4",
    "Marshmallow":   "#F2F2F2",
    "Shadow":        "#252525",
    "Olive":         "#65683F",
    "Rust":          "#885542",
    "Golden Brown":  "#A47B43",
}


# ---------------------------------------------------------------------------
# JOTTER (PEN) COLOR LIBRARY
# ---------------------------------------------------------------------------

JOTTER = {
    "Red":          "#AE0D2E",
    "Orange":       "#FF7F2E",
    "Citron":       "#CFDC00",
    "Grass Green":  "#29AE4C",
    "Bright Blue":  "#00A7CF",
    "Royal Blue":   "#004DB9",
    "Navy":         "#264259",
    "Powder Blue":  "#AED6E3",
    "Purple":       "#6B478E",
    "Lilac":        "#D4BBDD",
    "Blush":        "#FFCFDA",
    "Pink":         "#B02372",
    "Neon Coral":   "#ED5259",
    "Gray":         "#8A8C8C",
    "White":        "#F0F0F0",
    "Black":        "#212121",
    "Gold":         "#977A4F",
    "Camel":        "#A04E21",
    "Banana":       "#E4D483",
    "Olive":        "#5E693E",
    "Sangria":      "#8B1A3A",
    "Teal":         "#32A386",
}


# ---------------------------------------------------------------------------
# 4CP FABRIC COLOR LIBRARY
# ---------------------------------------------------------------------------

FABRIC_4CP = {
    "Red PMS 200":           "#BA0C2F",
    "Sangria PMS 208":       "#7C2855",
    "Fairytale Pink PMS 699":"#F2A0C1",
    "Tickled Pink PMS 1905": "#F4C6C2",
    "Drama Queen PMS 3527":  "#C5498B",
    "Peach PMS 169":         "#FFB09E",
    "Nantucket PMS 7623":    "#963434",
    "Grapefruit PMS 1785":   "#FF5C5C",
    "Coral PMS 170":         "#FF6B54",
    "Creamsicle PMS 1555":   "#FF8C5A",
    "Crush PMS 1575":        "#FF6B35",
    "Burnt Orange PMS 159":  "#C85A1E",
    "Mustard PMS 117":       "#C9952A",
    "Daffodil PMS 109":      "#FFCC00",
    "Lemon Chiffon PMS 100": "#F5E87C",
    "Citron PMS 381":        "#B5CC1A",
    "Key Lime Pie PMS 358":  "#67B346",
    "Jungle Green PMS 5545": "#5C8272",
    "Spruce PMS 7470":       "#4A7C80",
    "Teal PMS 7474":         "#2C7873",
    "Mint PMS 338":          "#60C8A0",
    "Turquoise PMS 319":     "#00A89D",
    "Easy Breezy PMS 635":   "#A8DCE8",
    "Sea Glass PMS 317":     "#B8E0D8",
    "Pool Blue PMS 7710":    "#0090A8",
    "Powder Blue PMS 658":   "#9EC4E8",
    "Bluebird PMS 2145":     "#2B5EB8",
    "Midnight PMS 540":      "#003865",
    "Navy PMS 2378":         "#1B3A5C",
    "Indigo PMS 7699":       "#3D5A8A",
    "Sky Blue PMS 660":      "#7CB5E8",
    "Periwinkle PMS 2113":   "#8585C8",
    "Lavender PMS 263":      "#D8B8E8",
    "Purple PMS 255":        "#6A2C7A",
    "Violet PMS 512":        "#6B3FA0",
    "Espresso PMS 439":      "#4A3728",
    "Brown PMS 469":         "#7C4A2D",
    "Harvest Tan PMS 465":   "#A87850",
    "Desert Tan PMS 467":    "#C8A878",
    "Khaki PMS 7503":        "#C8B88A",
    "Light Olive PMS 616":   "#D8CC90",
    "Olive PMS 5763":        "#7A7A40",
    "Pine PMS 5743":         "#4A5C38",
    "Driftwood Warm Gray 4": "#B8B0A8",
    "Cool Gray 8":           "#8C8C8C",
    "Slate PMS 425":         "#6B6B6B",
    "White":                 "#FFFFFF",
    "Black":                 "#1C1C1C",
}

# ---------------------------------------------------------------------------
# THREE-WAY PEN COLOR LIBRARY
# ---------------------------------------------------------------------------

THREE_WAY_PEN = {
    "Clear":             "#dccebb",
    "Sienna PMS 470":    "#c1733e",
    "Bubblegum PMS 230": "#f9b2de",
    "Salmon PMS 2029":   "#ffa4a4",
    "Red PMS 3517":      "#e02525",
    "Crush PMS 2026":    "#ff7c24",
    "Peach Fuzz PMS 712":"#ffd0b0",
    "Yellow PMS 109":    "#ffd44a",
    "Soft Lime PMS 2281":"#e6ed9f",
    "Mint PMS 6150":     "#b5d2c8",
    "Shamrock PMS 360":  "#72c457",
    "Emerald PMS 3435":  "#294b38",
    "Dark Teal PMS 314": "#1f81a3",
    "Calm Blue PMS 2142":"#a0b7ea",
    "Taro PMS 2705":     "#bbafed",
    "Royal Blue PMS 286":"#111dba",
    "Black":             "#212121",
    "Dark Gray PMS 430": "#9194a6",
    "White":             "#e6e6e6",
}

# ---------------------------------------------------------------------------
# LE PEN (0844) COLOR LIBRARY
# ---------------------------------------------------------------------------
# Screen colours from Numo's Le Pen swatches (2026-10-07); the PMS each colour
# is sold as comes from the Le Pen proof template. The writing ink matches the
# barrel colour.
LE_PEN = {
    "Pink":          "#DB5D9A",
    "Coral Pink":    "#C6929A",
    "Red":           "#7F2540",
    "Burgundy":      "#713645",
    "Orange":        "#E09151",
    "Fluor. Yellow": "#E4E767",
    "Peppermint":    "#C5DBC5",
    "Light Green":   "#8AB560",
    "Olive Green":   "#6D8054",
    "Green":         "#2D6A40",
    "Teal":          "#417794",
    "Light Blue":    "#63A4DA",
    "Blue":          "#2A48AF",
    "Oriental Blue": "#2A4459",
    "Periwinkle":    "#9FABD3",
    "Amethyst":      "#8176B0",
    "Lavender":      "#AC87B6",
    "Brown":         "#503A32",
    "Dark Gray":     "#60676E",
    "Black":         "#212121",
}
LE_PEN_PMS = {
    "Pink": "806 C", "Coral Pink": "1775 C", "Red": "1945 C", "Burgundy": "7638 C",
    "Orange": "1585 C", "Fluor. Yellow": "387 C", "Peppermint": "345 C",
    "Light Green": "361 C", "Olive Green": "364 C", "Green": "3500 C", "Teal": "2231 C",
    "Light Blue": "2995 C", "Blue": "2728 C", "Oriental Blue": "2188 C",
    "Periwinkle": "2122 C", "Amethyst": "2101 C", "Lavender": "266 C",
    "Brown": "4695 C", "Dark Gray": "431 C", "Black": "Black C",
}

# ---------------------------------------------------------------------------
# STICK PEN (0846) COLOR LIBRARY
# ---------------------------------------------------------------------------
# The 7 stock colours. Names are working names until Numo confirms them (and
# their PMS). Hex = the cap as photographed.
# The ink comes with the pen (each colour has its own; it can't be changed).
STICK_PEN = {
    "Orange": "#F49935",
    "Red":    "#D93536",
    "Purple": "#9589D5",
    "Aqua":   "#5FCCDA",
    "Blue":   "#2C73D8",
    "Green":  "#127D5E",
    "Black":  "#1E1C16",
}
STICK_PEN_PMS = {}

# ---------------------------------------------------------------------------
# BANK BAG (9210-02) MATERIAL COLORS
# ---------------------------------------------------------------------------
# Horizontal Bank Bag 10.5" x 5.5": expanded vinyl (9210-02-EV-1C) and
# laminated nylon (9210-02-LN-1C). Names from numo's product pages; hex
# sampled from their swatches (2026-10-07). PMS to come from Numo.
BANK_BAG_EV = {
    "Lipstick Red": "#BF3438", "Kelly Green": "#347350", "Forest Green": "#1E443A",
    "Marine Blue":  "#3C81A6", "Royal Blue":  "#223D6D", "Navy Blue":    "#0C263E",
    "Maroon":       "#64313F", "Rawhide":     "#C8AA8C", "Eggshell":     "#DBD0AB",
    "White":        "#F4F4F2", "Gray":        "#9EA1A4", "Black":        "#1A1A1A",
}
BANK_BAG_LN = {
    "Red": "#B13139", "Marine Blue": "#4467AC", "Navy Blue": "#1F2744",
    "Dark Green": "#1E443A", "Burgundy": "#5E3937", "Black": "#1A1A1A",
}

# 0799-3m Liam Can Insulator bias binding (the top edge), Numo's swatch list
# (2026-10-08); hex sampled from the swatches. PMS to come.
BIAS = {
    "Red": "#AB2834", "Maroon": "#50202D", "Clementine": "#F78B31", "Orange": "#EC6334",
    "Yellow Gold": "#F8D347", "Neon Yellow": "#E1E758", "Neon Green": "#99DE5D",
    "Pine Green": "#255540", "Ice Green": "#9DD3BF", "Snow Cone": "#008E9E",
    "Light Blue": "#61B2E1", "Royal Blue": "#12338B", "Navy": "#1A273E", "Indigo": "#345061",
    "Something Blue": "#95ACBB", "Lilac Breeze": "#A994BF", "Violet": "#612B5C",
    "Purple": "#5B2A98", "New Hot Pink": "#993C84", "Bubblegum": "#CE7A90",
    "Pastel Pink": "#EBB0BA", "Neon Coral": "#DD545A", "Coral": "#E28683", "Gray": "#8C8C8C",
    "Slate": "#555759", "Black": "#212121", "White": "#E6E6E6", "Khaki": "#CBC19B",
    "Bourbon": "#996D41", "Brown": "#644435",
}

# ---------------------------------------------------------------------------
# PRODUCT COLOR LISTS (sandbox)
# ---------------------------------------------------------------------------
#
# The main app shapes these lists from its company colour master. The
# sandbox has no company data, so it reads the finished lists — colour names
# and the app's mockup hex, in order, nothing else — from data/colors_app.json.
# They are the same colours, names and order the main app offers.
import json as _json
COLORS_APP_JSON = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "colors_app.json")
APP_RENAMED = {}        # material key -> {old app name: current name} (older saved proofs)
if os.path.exists(COLORS_APP_JSON):
    with open(COLORS_APP_JSON, encoding="utf-8") as _f:
        _lists = _json.load(_f)
    for _k, _lib in (("neoprene", NEOPRENE), ("thread", THREADS), ("scuba_foam", SCUBA_FOAM)):
        if _lists.get(_k):
            _lib.clear(); _lib.update(_lists[_k])
    APP_RENAMED.update(_lists.get("renamed") or {})

# ---------------------------------------------------------------------------
# PANTONE → RGB LOOKUP
# ---------------------------------------------------------------------------

_here = os.path.dirname(os.path.abspath(__file__))
_spec = _ilu.spec_from_file_location("pantone_rgb", os.path.join(_here, "pantone_rgb.py"))
_mod  = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
PANTONE_RGB = _mod.PANTONE_RGB

# ---------------------------------------------------------------------------
# COLOR UTILITIES
# ---------------------------------------------------------------------------

def hex_to_rgb(h):
    return tuple(int(h.lstrip('#')[i:i+2], 16) for i in (0, 2, 4))

def luminance(rgb):
    def chan(c):
        s = c / 255.0
        return s / 12.92 if s <= 0.03928 else ((s + 0.055) / 1.055) ** 2.4
    r, g, b = rgb
    return 0.2126 * chan(r) + 0.7152 * chan(g) + 0.0722 * chan(b)

def contrast_ratio(rgb1, rgb2):
    l1, l2 = luminance(rgb1), luminance(rgb2)
    return (max(l1, l2) + 0.05) / (min(l1, l2) + 0.05)

def find_best(rgb, library):
    best_name, best_hex = "Black", "#1C1C1C"
    min_diff = float("inf")
    for name, hx in library.items():
        lib_rgb = hex_to_rgb(hx)
        diff = sum((a - b) ** 2 for a, b in zip(rgb, lib_rgb))
        if diff < min_diff:
            min_diff = diff
            best_name, best_hex = name, hx
    return best_name, best_hex

def resolve_pantone_rgbs(pantone_colors):
    return [hex_to_rgb(PANTONE_RGB[n]) for n in pantone_colors if n in PANTONE_RGB]

def neoprene_clashes_with_imprint(neo_hex, imprint_rgbs, min_contrast=2.5):
    neo_rgb = hex_to_rgb(neo_hex)
    return [
        (f"color {i+1}", round(contrast_ratio(neo_rgb, imp_rgb), 1))
        for i, imp_rgb in enumerate(imprint_rgbs)
        if contrast_ratio(neo_rgb, imp_rgb) < min_contrast
    ]

# ---------------------------------------------------------------------------
# CIE Lab / Delta-E (CIEDE2000)
# ---------------------------------------------------------------------------

def _rgb_to_lab(rgb):
    r, g, b = [x / 255.0 for x in rgb]
    def lin(c):
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = lin(r), lin(g), lin(b)
    x = (r * 0.4124564 + g * 0.3575761 + b * 0.1804375) / 0.95047
    y = (r * 0.2126729 + g * 0.7151522 + b * 0.0721750) / 1.00000
    z = (r * 0.0193339 + g * 0.1191920 + b * 0.9503041) / 1.08883
    def f(t):
        return t ** (1/3) if t > 0.008856 else 7.787 * t + 16/116
    L = 116 * f(y) - 16
    a = 500 * (f(x) - f(y))
    b_ = 200 * (f(y) - f(z))
    return L, a, b_

def _delta_e(lab1, lab2):
    L1,a1,b1 = lab1; L2,a2,b2 = lab2
    C1 = math.sqrt(a1**2+b1**2); C2 = math.sqrt(a2**2+b2**2)
    Cb = (C1+C2)/2
    G = 0.5*(1-math.sqrt(Cb**7/(Cb**7+25**7)))
    a1p=a1*(1+G); a2p=a2*(1+G)
    C1p=math.sqrt(a1p**2+b1**2); C2p=math.sqrt(a2p**2+b2**2)
    h1p=math.degrees(math.atan2(b1,a1p))%360
    h2p=math.degrees(math.atan2(b2,a2p))%360
    dLp=L2-L1; dCp=C2p-C1p
    if C1p*C2p==0: dhp=0
    elif abs(h2p-h1p)<=180: dhp=h2p-h1p
    elif h2p-h1p>180: dhp=h2p-h1p-360
    else: dhp=h2p-h1p+360
    dHp=2*math.sqrt(C1p*C2p)*math.sin(math.radians(dhp/2))
    Lbp=(L1+L2)/2; Cbp=(C1p+C2p)/2
    if C1p*C2p==0: hbp=h1p+h2p
    elif abs(h1p-h2p)<=180: hbp=(h1p+h2p)/2
    elif h1p+h2p<360: hbp=(h1p+h2p+360)/2
    else: hbp=(h1p+h2p-360)/2
    T=(1-0.17*math.cos(math.radians(hbp-30))
         +0.24*math.cos(math.radians(2*hbp))
         +0.32*math.cos(math.radians(3*hbp+6))
         -0.20*math.cos(math.radians(4*hbp-63)))
    SL=1+0.015*(Lbp-50)**2/math.sqrt(20+(Lbp-50)**2)
    SC=1+0.045*Cbp; SH=1+0.015*Cbp*T
    d_theta=30*math.exp(-((hbp-275)/25)**2)
    RC=2*math.sqrt(Cbp**7/(Cbp**7+25**7))
    RT=-math.sin(math.radians(2*d_theta))*RC
    return math.sqrt((dLp/SL)**2+(dCp/SC)**2+(dHp/SH)**2+RT*(dCp/SC)*(dHp/SH))

def find_closest_pantone(rgb, top_n=3, boost=False):
    if boost:
        rgb = _boost_saturation(rgb, factor=1.25)
    input_lab = _rgb_to_lab(rgb)
    results = []
    for name, hx in PANTONE_RGB.items():
        if not name.upper().startswith("PANTONE"):
            continue
        try:
            pan_lab = _rgb_to_lab(hex_to_rgb(hx))
            de = _delta_e(input_lab, pan_lab)
            results.append({"name": name, "hex": hx, "delta_e": round(de, 1)})
        except Exception:
            continue
    results.sort(key=lambda x: x["delta_e"])
    return results[:top_n]

def _boost_saturation(rgb, factor=1.25):
    r, g, b = [x/255.0 for x in rgb]
    mx, mn = max(r, g, b), min(r, g, b)
    L = (mx + mn) / 2
    if mx == mn:
        return rgb
    d = mx - mn
    S = d / (2 - mx - mn) if L > 0.5 else d / (mx + mn)
    S = min(1.0, S * factor)
    def hue_to_rgb(p, q, t):
        if t < 0: t += 1
        if t > 1: t -= 1
        if t < 1/6: return p + (q-p)*6*t
        if t < 1/2: return q
        if t < 2/3: return p + (q-p)*(2/3-t)*6
        return p
    H = 0
    if mx == r: H = (g-b)/d % 6
    elif mx == g: H = (b-r)/d + 2
    else: H = (r-g)/d + 4
    H /= 6
    q = L*(1+S) if L < 0.5 else L+S-L*S
    p = 2*L - q
    return (int(hue_to_rgb(p, q, H+1/3)*255),
            int(hue_to_rgb(p, q, H)*255),
            int(hue_to_rgb(p, q, H-1/3)*255))

def suggest_pantones_from_palette(palette_rgbs, top_n=1):
    suggestions = []
    seen = set()
    for rgb in palette_rgbs:
        boosted = _boost_saturation(rgb, factor=1.25)
        matches = find_closest_pantone(boosted, top_n=5)
        for m in matches:
            if m["name"] not in seen:
                seen.add(m["name"])
                suggestions.append({"original_hex": "#{:02X}{:02X}{:02X}".format(*rgb), **m})
                break
    return suggestions