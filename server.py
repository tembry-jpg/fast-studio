"""
Numo Production Engine – Web Edition (Adobe-Free)
Run: python3 server.py
Open: http://localhost:8080
"""

import base64
import os, sys, json, time, shutil, threading, tempfile, math, re
from pathlib import Path
from flask import Flask, request, jsonify, send_file, send_from_directory, make_response

HERE = Path(__file__).parent.resolve()
sys.path.insert(0, str(HERE))

from engine import (
    THREADS, NEOPRENE, PANTONE_RGB, JOTTER, LE_PEN, LE_PEN_PMS, STICK_PEN, STICK_PEN_PMS, BANK_BAG_EV, BANK_BAG_LN, BIAS, COTTON_CANVAS, COTTON_CANVAS_DYED,
    hex_to_rgb, find_best, contrast_ratio,
    neoprene_clashes_with_imprint, resolve_pantone_rgbs,
    find_closest_pantone, suggest_pantones_from_palette,
)
try:
    from engine import SCUBA_FOAM
except ImportError:
    SCUBA_FOAM = {}

try:
    from engine import THREE_WAY_PEN
except ImportError:
    THREE_WAY_PEN = {}

try:
    from engine import FABRIC_4CP
except ImportError:
    FABRIC_4CP = {}
from products import (
    PRODUCTS,
    SCREENPRINT_SKU_SUFFIX, SCREENPRINT_PRODUCT_IDS, SCREENPRINT_VECTOR_EXTS,
    SCREENPRINT_BASE_IDS,
    is_screenprint, screenprint_sku, asset_id_for,
    PMS_ASSIGN_PRODUCT_IDS, supports_pms_assign,
)

app = Flask(__name__, static_folder=str(HERE / "static"), static_url_path="/static")

# Sign-in for the whole app (internal tool). Off until TTOOL_PASSWORD is set.
# Client sign-in: one shared password (CLIENT_PASSWORD), client_login.py.
import client_login
client_login.init_app(app)

# ── CLIENT SANDBOX ──────────────────────────────────────────────────────────
# Numo's client ordering site: the configurator, mockups and proofs for the
# screen-print 24 HR (This Is Fast) items, behind one shared client password.
#   * the catalog lists the screen-print TIF items only (the rest are still
#     here, just not listed)
#   * clients get the client view only
#   * no pricing (the price sheet is not fetched)
#   * an export ships the digital proof and the virtual only: no press files,
#     2X2, print PDF, artwork originals or ink coverage
SANDBOX = True
SANDBOX_KINDS = ("digitalproof", "virtualproof")


def _sandbox_trim(listing, serve_dir, keep_hidden=("variant-proof", "variant-2x2")):
    """Only the proof and the virtual go out of a sandbox export. Everything
    else is taken off the listing and deleted from the export's folder. A
    colour variant's held-back proof and 2X2 stay (hidden) until the variants
    are combined, which needs them; they are never served."""
    keep = [e for e in listing
            if (not e.get("hidden") and e.get("kind") in SANDBOX_KINDS)
            or (e.get("hidden") and e.get("kind") in keep_hidden)]
    keep_paths = {str(e.get("path")) for e in keep}
    root = Path(serve_dir).resolve()
    # Delete what was listed and is not kept (press files, 2X2, artwork). Files never listed are the build's own working notes
    # (the proof's sidecars), which combining the variants reads.
    for e in listing:
        rel = str(e.get("path") or "")
        if not rel or rel in keep_paths:
            continue
        f = (root / rel).resolve()
        if root in f.parents and f.is_file():
            f.unlink()
    art = root / "art"
    if art.is_dir():
        shutil.rmtree(art, ignore_errors=True)
    return keep


# Every /api/ error comes back as JSON the page can show. Without this a crash
# returns Flask's HTML error page and the configurator can only report
# "Unexpected token '<'" — which says nothing about what actually failed.
@app.errorhandler(Exception)
def _api_error(e):
    from flask import request
    from werkzeug.exceptions import HTTPException
    code = e.code if isinstance(e, HTTPException) else 500
    if not request.path.startswith("/api/"):
        return e if isinstance(e, HTTPException) else ("Internal Server Error", 500)
    if code == 413:
        msg = "That file is too large to upload."
    elif isinstance(e, HTTPException):
        msg = e.description or e.name
    else:
        import traceback
        traceback.print_exc()
        msg = _explain_crash(e)
    return jsonify({"error": msg}), code


def _explain_crash(e):
    """A crash, in words that point at the fix when it's a missing tool."""
    t = f"{type(e).__name__}: {e}"
    low = t.lower()
    if "poppler" in low or "pdfinfo" in low or "pdftoppm" in low or "pdftocairo" in low:
        return ("Server error: poppler isn't installed (pdftoppm / pdftocairo). "
                "Install poppler-utils and restart. — " + t)
    if "cairo" in low:
        return ("Server error: the cairo library isn't installed. "
                "Install cairo (libcairo2) and restart. — " + t)
    if "ghostscript" in low or "gswin" in low or "'gs'" in low:
        return "Server error: Ghostscript isn't installed. Install it and restart. — " + t
    if isinstance(e, ModuleNotFoundError):
        return (f"Server error: the Python package '{e.name}' isn't installed. "
                "Run: pip install -r requirements.txt — " + t)
    return "Server error — " + t

# Placed PDF/AI art is fitted to its actual ink rather than its artboard. This
# is on for the one-color screen-print workflow, where the canvas preview and
# the exported template have to agree. Set True to apply it to every product
# (it fixes the same artboard mismatch for 4CP vector uploads).
INK_FIT_ALL_PRODUCTS = True   # previews are cropped to the ink on every product now


try:
    from screenprint import MAX_SPOT_INKS as MAX_SPOT_INKS_DEFAULT
except Exception:
    MAX_SPOT_INKS_DEFAULT = 5


def _thumb_url(product_id, asset_id):
    """
    The card image for a product: its own if it has one, else its assets'.

    A This Is Fast twin shares the original's artwork through asset_id, which
    is what keeps the assets from being duplicated — but it can still carry a
    cover of its own. Resolved here rather than probed in the browser: the page
    would otherwise request a file that mostly does not exist and take a 404 on
    every twin, every load, to learn what the server already knows.
    """
    own = HERE / "static" / "assets" / product_id / "thumbnail.png"
    which = product_id if own.exists() else asset_id
    return f"/static/assets/{which}/thumbnail.png"


def _max_inks_for(pid):
    """A product's PMS ink ceiling: its own (metallic 3l: 3), else the press's."""
    try:
        from products import max_spot_inks
        return max_spot_inks(pid, _max_spot_inks())
    except Exception:
        return _max_spot_inks()


def _max_spot_inks():
    """
    The press ceiling for multi-color spot jobs, read from screenprint.py so
    the UI never hardcodes it. Imported lazily to keep this import-safe.
    """
    try:
        from screenprint import MAX_SPOT_INKS
        return MAX_SPOT_INKS
    except Exception:
        return 5

# Create required directories at startup
(HERE / "uploads").mkdir(exist_ok=True)
(HERE / "_serve").mkdir(exist_ok=True)


# ---------------------------------------------------------------------------
# Patch to remove transparency
# ---------------------------------------------------------------------------

from PIL import Image
import io

def get_raster_visible_bbox(path):
    with Image.open(path) as im:
        im = im.convert("RGBA")
        alpha = im.getchannel("A")
        bbox = alpha.getbbox()
        if bbox:
            return bbox, im.size
        return (0, 0, im.width, im.height), im.size


def crop_raster_to_visible(path):
    with Image.open(path) as im:
        im = im.convert("RGBA")
        alpha = im.getchannel("A")
        bbox = alpha.getbbox()

        if not bbox:
            bbox = (0, 0, im.width, im.height)

        cropped = im.crop(bbox)

        out_path = str(Path(path).with_name(Path(path).stem + "_tight.png"))
        cropped.save(out_path)
        return out_path, cropped.width, cropped.height



# ---------------------------------------------------------------------------
# Job store
# ---------------------------------------------------------------------------
# Jobs are kept on disk as well as in memory. With several gunicorn worker
# processes, the request that polls a job is often served by a different
# process than the one running it; memory alone would answer "Unknown job".
JOBS = {}
JOBS_LOCK = threading.Lock()
_JOBS_DIR = HERE / "uploads" / "_jobs"


def _job_file(job_id):
    safe = re.sub(r"[^A-Za-z0-9_-]", "", str(job_id))[:80]
    return _JOBS_DIR / f"{safe}.json" if safe else None


def _job_save(job_id, data):
    f = _job_file(job_id)
    if not f:
        return
    try:
        _JOBS_DIR.mkdir(parents=True, exist_ok=True)
        tmp = f.with_suffix(f".{os.getpid()}.tmp")
        tmp.write_text(json.dumps(data, default=str))
        os.replace(tmp, f)                       # atomic: readers never see half a file
    except Exception as e:
        print(f"job store write failed: {e}")


def new_job(job_id, initial):
    with JOBS_LOCK:
        JOBS[job_id] = {"status": "pending", **initial}
        _job_save(job_id, JOBS[job_id])

def update_job(job_id, patch):
    with JOBS_LOCK:
        if job_id in JOBS:
            JOBS[job_id].update(patch)
            _job_save(job_id, JOBS[job_id])

def get_job(job_id):
    with JOBS_LOCK:
        if job_id in JOBS:
            return dict(JOBS[job_id])
    f = _job_file(job_id)
    try:
        return json.loads(f.read_text()) if f and f.exists() else {}
    except Exception:
        return {}

# ---------------------------------------------------------------------------
# Routes – static pages
# ---------------------------------------------------------------------------

@app.route("/")
@app.route("/start")
def index():
    # "/" shows the items page (home.html picks its view from the path; it is
    # also where sign-in lands). The old program chooser is at /start.
    from flask import make_response
    resp = make_response(send_from_directory(str(HERE / "static"), "home.html"))
    resp.headers["Cache-Control"] = "no-store"
    return resp

@app.route("/tif")
@app.route("/standard")
@app.route("/items")
def program_page():
    # The landing page's two program listings; the page reads its own path.
    from flask import make_response
    resp = make_response(send_from_directory(str(HERE / "static"), "home.html"))
    resp.headers["Cache-Control"] = "no-cache"
    return resp

@app.route("/matcher")
def matcher():
    return send_from_directory(str(HERE / "static"), "matcher.html")

@app.route("/<pid>")
def product_page(pid):
    from flask import make_response
    if pid in PRODUCTS:
        resp = make_response(send_from_directory(str(HERE / "static"), "configurator.html"))
        # Revalidate every load (a deploy shows up at once) but let the browser
        # reuse its copy when unchanged: a 304 instead of 380 KB per visit.
        resp.headers["Cache-Control"] = "no-cache"
        return resp
    return send_from_directory(str(HERE / "static"), pid)

@app.route("/<path:path>")
def static_files(path):
    # Let Flask handle /api/* routes before falling through to static files
    if path.startswith("api/"):
        from flask import abort
        abort(404)
    return send_from_directory(str(HERE / "static"), path)


# Mockup textures, product photos and template guides. Flask's default for
# these is "no-cache", which means the browser re-asks the server about every
# one of them on every page load. The answer is almost always 304 Not Modified,
# so it costs little bandwidth — but each round trip still occupies the worker,
# and with a single worker a burst of visitors spends its time answering
# questions about files that have not changed in months.
_CACHEABLE_SUFFIXES = (".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg",
                       ".woff", ".woff2", ".ttf", ".otf", ".ico")

# Short enough that replacing a product photo shows up the same morning, long
# enough that a spike is not spent revalidating. The ETag still catches any
# change once the hour is up, so nothing goes permanently stale.
_ASSET_MAX_AGE = 3600


@app.after_request
def _cache_static_assets(resp):
    # Pages and API routes set their own caching deliberately — the PMS library
    # in particular revalidates on purpose, so that a change to the ink rules
    # reaches people on their next reload. Only plain asset files are given a
    # lifetime here.
    path = (request.path or "").lower()
    if resp.status_code not in (200, 304):
        return resp
    if path.startswith("/api/"):
        return resp
    if resp.headers.get("Cache-Control") == "no-store":
        return resp
    if path.endswith(_CACHEABLE_SUFFIXES):
        resp.headers["Cache-Control"] = f"public, max-age={_ASSET_MAX_AGE}"
    return resp


# Text responses go out uncompressed by default — the configurator page is
# 305 KB of HTML and the PMS library 149 KB of JSON, and both are mostly
# repeated markup and colour names that gzip to about a fifth of that. Every
# visitor pays for it, so a burst pays for it many times over.
#
# Done here with the standard library rather than by adding Flask-Compress:
# one dependency fewer to install, audit and keep current, for about twenty
# lines. Images, PDFs and the export zip are already compressed and are left
# alone — running them through gzip costs CPU and gives back nothing.
_COMPRESSIBLE_TYPES = ("text/html", "text/css", "text/plain", "text/xml",
                       "application/json", "application/javascript",
                       "image/svg+xml")

# Below roughly a packet there is nothing to win, and the gzip header can make
# a very small body bigger than it started.
_COMPRESS_MIN_BYTES = 1024

# Compressed copies of bodies already seen, keyed by a digest of the body.
#
# The two big responses — the configurator page and the PMS library — are byte
# for byte the same for everybody, so compressing them per request means doing
# identical work once per visitor. Measured on a burst of 100 page loads, that
# cost more than the compression saved: median load went from 0.43s to 1.66s,
# because gzip is CPU and CPU is the scarce thing during a spike, while
# bandwidth is not.
#
# Caching the compressed bytes keeps the bandwidth saving and pays the CPU once.
# Keyed by content digest rather than URL so a deploy that changes a file simply
# misses and recompresses — there is no stale-cache failure mode.
_GZIP_CACHE = {}
_GZIP_CACHE_MAX = 32          # a handful of text responses; these are small
_GZIP_CACHE_MAX_BYTES = 2_000_000   # don't hold anything unreasonable in memory


@app.after_request
def _compress(resp):
    accept = request.headers.get("Accept-Encoding", "")
    if "gzip" not in accept.lower():
        return resp
    if resp.status_code < 200 or resp.status_code >= 300:
        return resp
    if resp.headers.get("Content-Encoding"):
        return resp
    if (resp.mimetype or "") not in _COMPRESSIBLE_TYPES:
        return resp

    # send_file hands back a streaming response; reading it has to be opted
    # into explicitly, or get_data() refuses. Safe here because everything
    # reaching this point is a text file small enough to hold in memory.
    resp.direct_passthrough = False
    data = resp.get_data()
    if len(data) < _COMPRESS_MIN_BYTES:
        return resp

    import gzip as _gzip, hashlib as _hl
    key = _hl.blake2b(data, digest_size=16).digest()
    packed = _GZIP_CACHE.get(key)
    if packed is None:
        # Level 6 is gzip's default and is tuned for archiving, where the file
        # is compressed once. Level 5 gives up a percent or so of ratio for a
        # useful slice of the CPU on the first request of a body we have not
        # seen before.
        packed = _gzip.compress(data, 5)
        if len(data) <= _GZIP_CACHE_MAX_BYTES:
            if len(_GZIP_CACHE) >= _GZIP_CACHE_MAX:
                _GZIP_CACHE.clear()   # tiny and rarely hit; simpler than an LRU
            _GZIP_CACHE[key] = packed
    if len(packed) >= len(data):
        return resp
    resp.set_data(packed)
    resp.headers["Content-Encoding"] = "gzip"
    resp.headers["Content-Length"] = str(len(packed))
    # Caches must key on the encoding, or a gzipped copy can be handed to a
    # client that did not ask for one.
    resp.headers.add("Vary", "Accept-Encoding")
    # The ETag described the uncompressed body; keep it valid by marking this
    # representation as the compressed one.
    if resp.headers.get("ETag"):
        etag = resp.headers["ETag"]
        if not etag.endswith('-gzip"'):
            resp.headers["ETag"] = etag[:-1] + '-gzip"' if etag.endswith('"') else etag
    return resp

@app.route("/api/pricing")
def get_pricing():
    """Sandbox: no pricing. An empty price sheet, so the page shows none."""
    from flask import Response
    return Response("", mimetype="text/csv")


# ---------------------------------------------------------------------------
# Route – lightweight product list for home page
# ---------------------------------------------------------------------------
# ── Catalog facets for the items page ─────────────────────────────────────
# Grouped the way numomfg.com groups its catalog — by shape (what it is), by
# material, and by collection — plus how it prints, which is what an artist
# actually chooses by. Worked out from the product rather than typed per item,
# so a new product lands in the right filters without anyone editing a list.
_CAT_MATERIAL = [
    (r"^neoprene_metallic", "Metallic Neoprene"), (r"^neoprene_heathered", "Heathered Neoprene"),
    (r"^neoprene_denim", "Denim"), (r"^neoprene_burlap", "Burlap"), (r"^neoprene_suede", "Suede"),
    (r"^neoprene", "Neoprene"),
    (r"^scuba", "Scuba Foam"), (r"^cotton_canvas", "Canvas"), (r"^(jotter|three_way_pen)", "Plastic"),
    (r"^expanded_vinyl", "Expanded Vinyl"), (r"^laminated_nylon", "Laminated Nylon"),
]
_CAT_KEYWORDS = {
    "Beverage Insulators": "koozie coozie can cooler insulator huggie hugger kaddy coolie drink sleeve",
    "Totes and Bags": "tote bag canvas cotton shopper",
    "Pens": "pen pens writing jotter retractable 3-way",
    "Key Chains": "key fob keychain key chain key ring lanyard wristlet",
}


def _catalog_meta(pid, p, slot_labels):
    import re as _re
    mat = p.get("material") or ""
    name = _re.sub(r"\s*4CP$", "", (p.get("label") or pid).split(" - ")[0].strip(), flags=_re.I)
    if _re.search(r"jotter|three_way_pen", mat):
        shape = "Pens"
    elif mat.startswith("cotton_canvas") or mat in ("expanded_vinyl", "laminated_nylon"):
        shape = "Totes and Bags"
    elif _re.search(r"key fob|keychain|key chain", name, _re.I):
        shape = "Key Chains"
    else:
        shape = "Beverage Insulators"
    fits = None
    if shape == "Beverage Insulators":
        fits = "Slim can" if _re.search(r"slim", name, _re.I) else "Standard can"
    material = next((lab for rx, lab in _CAT_MATERIAL if _re.search(rx, mat)), "Other")
    # A one-colour item outside the 24-hour programme (the 9210-02 bank bags)
    # says so with "program": "Standard"; it keeps the one-colour artwork
    # rules and press sheets but is not a This Is Fast item.
    program = p.get("program") or ("This Is Fast" if is_screenprint(pid) else "Standard")
    if is_screenprint(pid):
        printing = "One color · 24 HR" if program == "This Is Fast" else "One color"
    elif p.get("is_4cp") or "4cp" in mat:
        printing = "Full color (4CP)"
    else:
        printing = "Spot color"
    # The card name says which version it is, the way the website names them
    # ("Denim Kolder Kaddy", "4CP Kolder Kaddy Slim Can"), so items that share
    # a base name aren't told apart only by their item number.
    lead = []
    if program == "This Is Fast":
        lead.append("24 HR")
    if printing.startswith("Full color"):
        lead.append("4CP")
    lead.append({"Metallic Neoprene": "Metallic", "Heathered Neoprene": "Heathered", "Denim": "Denim",
                 "Burlap": "Burlap", "Suede": "Suede", "Scuba Foam": "Scuba"}.get(material, ""))
    if shape == "Totes and Bags" and mat.startswith("cotton_canvas"):
        lead.append("Colored" if "dyed" in mat else "Natural")
    display = " ".join(w for w in lead + [name] if w)
    bodies = []
    try:
        bodies = [b.get("name") for b in _body_patterns(pid, p) if b.get("name")]
    except Exception:
        pass
    keywords = " ".join(filter(None, [
        pid, pid.replace("-", " "), display, material, printing, program, shape, fits or "",
        _CAT_KEYWORDS.get(shape, ""), " ".join(slot_labels), " ".join(bodies),
        p.get("item_prefix") or "",
    ]))
    return {
        "name": display,
        "base_name": name,
        "item": pid.upper(),
        "family": pid[:4],
        "shape": shape,
        "fits": fits,
        "material_label": material,
        "printing": printing,
        "program": program,
        "max_inks": _max_inks_for(pid) if supports_pms_assign(pid) else (1 if is_screenprint(pid) else None),
        "has_bottom": any(l.lower() == "bottom" for l in slot_labels),
        "bodies": bodies,
        "keywords": keywords.lower(),
    }


# ── The client catalog ─────────────────────────────────────────────────────
# Exactly the This Is Fast items on numomfg.com, by their site names. The ones
# set up here open in the configurator; the rest (and every 4CP item) show as
# "Coming soon" with the site's photo and can't be opened. Every other product
# is still in the app, just not listed. To open one up: give it its product
# id here instead of None.
CLIENT_CATALOG = [
    # (product id or None, name on the site, photo: static/sandbox/...)
    ("0070-3m-24HR-1c", "This Is Fast Kolder Kaddy", "items/0070-3m-24HR-1c.jpg"),
    ("1080-3m-24HR-1c", "This Is Fast Kolder Kaddy Neoprene for Slim Cans", "items/1080-3m-24HR-1c.jpg"),
    ("9100-24HR-1c", "This Is Fast Pocket Coolie", None),
    ("0472-24HR-1c", "This Is Fast Pocket Coolie for Slim Cans", "items/0472-24HR-1c.jpg"),
    ("5001-TIF-7-1C", "This Is Fast Main Squeeze - Natural Canvas", "items/5001-TIF-7-1C.jpg"),
    ("5001-TIF-CC-1C", "This Is Fast Main Squeeze - Colored Canvas", "items/5001-TIF-CC-1C.jpg"),
    ("0837", "This Is Fast Jotter Pen", "items/jotter-pen.jpg"),   # the 0837 Jotter as it is
    (None, "This Is Fast 4CP Kolder Kaddy", "soon/kolder-kaddy-4cp.jpg"),
    (None, "This Is Fast Kolder Kaddy Neoprene for Slim Cans - 4CP", "soon/kolder-kaddy-slim-4cp.jpg"),
    (None, "This Is Fast 4CP Pocket Coolie", "soon/pocket-coolie-4cp.jpg"),
    (None, "This Is Fast Pocket Coolie for Slim Cans - 4CP", "soon/pocket-coolie-slim-4cp.jpg"),
    (None, "This Is Fast Duplex Kolder Kaddy", "soon/duplex-kolder-kaddy.jpg"),
    (None, "This Is Fast Shamwow - Natural Canvas", "soon/shamwow-natural.jpg"),
    (None, "This Is Fast Shamwow - Colored Canvas", "soon/shamwow-colored.jpg"),
    (None, "This Is Fast Daily Grind - Natural Canvas", "soon/daily-grind-natural.jpg"),
    (None, "This Is Fast Daily Grind - Colored Canvas", "soon/daily-grind-colored.jpg"),
]


_CLIENT_NAMES = {pid: name for pid, name, _ in CLIENT_CATALOG if pid}


def _client_catalog(out):
    by_id = {p["id"]: p for p in out}
    cat = []
    for n, (pid, name, photo) in enumerate(CLIENT_CATALOG):
        if pid and pid in by_id:
            p = dict(by_id[pid], name=name, label=name, display_label=name, coming_soon=False, catalog_order=n)
            if photo:
                p["thumb_url"] = f"/static/sandbox/{photo}"
            cat.append(p)
            continue
        low = name.lower()
        is4 = "4cp" in low
        shape = "Pens" if "pen" in low else ("Totes and Bags" if "canvas" in low else "Beverage Insulators")
        slug = re.sub(r"[^a-z0-9]+", "-", low).strip("-")
        cat.append({"id": "soon-" + slug, "name": name, "label": name, "display_label": name,
                    "coming_soon": True, "item": "Coming soon", "sku": "",
                    "thumb_url": f"/static/sandbox/{photo}" if photo else "",
                    "keywords": low + " this is fast", "slots": [], "bodies": [],
                    "shape": shape, "fits": "Slim can" if "slim" in low else ("Standard can" if shape == "Beverage Insulators" else ""),
                    "material_label": "Canvas" if "canvas" in low else ("Plastic" if "pen" in low else "Neoprene"),
                    "printing": "Full color (4CP)" if is4 else "",
                    "program": "This Is Fast", "is_screenprint": False, "max_inks": 0,
                    "family": "", "base_name": name, "catalog_order": n})
    return cat


@app.route("/api/products-lite")
def get_products_lite():
    """Minimal product data for home page — no zones, slots, bleed data."""
    out = []
    for pid, p in PRODUCTS.items():
        slots = p.get("art_slots") or []
        slot_labels = [s.get("label", s.get("id","")) for s in slots]
        out.append({
            "id":       pid,
            "sku":      screenprint_sku(pid),
            "label":    p.get("label") or p.get("name", pid),
            "display_label": p.get("display_label") or p.get("label") or pid,
            "asset_id": p.get("asset_id") or pid,
            "base_id":  p.get("base_id") or pid,
            "material": p.get("material", "neoprene"),
            "is_screenprint": is_screenprint(pid) and (p.get("program") or "This Is Fast") == "This Is Fast",   # the 24 HR list on the home page
            "supports_pms_assign": supports_pms_assign(pid),
            "thumb_url": _thumb_url(pid, p.get("asset_id") or pid),
            "slots":    [{"label": l} for l in slot_labels],
            **_catalog_meta(pid, p, slot_labels),
        })
    out = _client_catalog(out)
    from flask import make_response
    resp = make_response(jsonify(out))
    resp.headers["Cache-Control"] = "public, max-age=300"  # cache 5 min
    return resp

# ---------------------------------------------------------------------------
# Route – product list
# ---------------------------------------------------------------------------

def _body_patterns(pid, p):
    """Printed body materials (camo) a product comes in, beside its solid colors.

    They live with the product's mockup assets, in static/assets/<asset>/patterns/
    patterns.json: [{name, hex, swatch, body}]. `body` is the full-size mockup
    body layer (same size as the color mask), `swatch` the picker tile, `hex`
    the pattern's average color for anything that needs one color. To add a
    pattern to another product, drop its files and a patterns.json there.
    """
    if p.get("is_4cp") or "4cp" in (p.get("material") or ""):
        return []
    aid = p.get("pattern_dir") or p.get("asset_id") or pid
    man = HERE / "static" / "assets" / aid / "patterns" / "patterns.json"
    if not man.exists():
        return []
    try:
        items = json.loads(man.read_text())
    except ValueError:
        return []
    base = f"/static/assets/{aid}/patterns/"
    return [{"name": i["name"], "hex": i.get("hex") or "#808080",
             "swatch": base + i["swatch"], "body": base + i["body"],
             "tile": base + (i.get("tile") or i["swatch"]), "pattern": True}
            for i in items if i.get("name") and i.get("swatch") and i.get("body")]


@app.route("/api/products")
def get_products():
    out = []
    for pid, p in PRODUCTS.items():
        raw_slots = p.get("art_slots") or []
        if not raw_slots and "slots" in p:
            raw_slots = [
                {"id": k, "label": v.get("label", k), "size": v.get("size", ""),
                 "left_pt": 0, "top_pt": 0, "w_pt": 0, "h_pt": 0,
                 "rotation": 0, "shape": "rect"}
                for k, v in p["slots"].items()
            ]
        out.append({
            "id": pid,
            "sku": screenprint_sku(pid),
            "label": p.get("label") or p.get("name", pid),
            "display_label": _CLIENT_NAMES.get(pid) or p.get("display_label") or p.get("label") or pid,
            "asset_id": p.get("asset_id") or pid,
            "base_id": p.get("base_id") or pid,
            "is_screenprint": is_screenprint(pid),
            "supports_pms_assign": supports_pms_assign(pid),
            "max_spot_inks": _max_inks_for(pid) if supports_pms_assign(pid) else 0,
            "metal_of": p.get("metal_of"),
            "twin_of": p.get("twin_of"),
            "twin_kind": p.get("twin_kind"),
            "item_prefix": p.get("item_prefix"),
            "porous": p.get("porous"),
            "sku_suffix": SCREENPRINT_SKU_SUFFIX if (is_screenprint(pid) and not p.get("program")) else "",
            "slots": raw_slots,
            "has_neoprene": p.get("has_neoprene", False),
            "has_stitching": p.get("has_stitching", False),
            "material": p.get("material", "neoprene"),
            "template_zones": p.get("template_zones", {}),
            "body_patterns": _body_patterns(pid, p),
            "mimaki_jig": bool(p.get("mimaki_jig")),
            "bleed_zones": p.get("bleed_zones", {}),
            "proof_bounds": p.get("proof_bounds", {}),
            "proof_shape": p.get("proof_shape", "flat"),
            "proof_warp": p.get("proof_warp", 0),
            "proof_imprint_inset": p.get("proof_imprint_inset", 0),
            "ink_black_only": p.get("ink_black_only", []),
            "is_4cp": p.get("is_4cp", False),
            "bleed_zone_full": p.get("bleed_zone_full", {}),
            "bleed_placement": p.get("bleed_placement", {}),
            "color_components": p.get("color_components", []),
            "shows_inside": bool(p.get("shows_inside")),
            "mockup_bands": p.get("mockup_bands"),
            "inside_colors": p.get("inside_colors"),
            "stitch_fixed": p.get("stitch_fixed"),
            "pen_colors": p.get("pen_colors"),
            "writing_ink": p.get("writing_ink"),
            "program": p.get("program"),
            "ink_fixed": bool(p.get("ink_fixed")),
            "pen_label": p.get("pen_label"),
            "side2_turn": p.get("side2_turn", 180),
            # A coloured part picked like the stitching (the 0799's bias), and
            # where Side 1 moves when it is the only side (opposite the seam).
            "trim": p.get("trim"),
            "one_side_zone": p.get("one_side_zone"),
            "one_side_bounds": p.get("one_side_bounds"),
            "one_side_assets": p.get("one_side_assets"),
            # A lifestyle photo set the "Lifestyle" button renders the item on.
            "lifestyle_assets": p.get("lifestyle_assets"),
        })
    return jsonify(out)

# ---------------------------------------------------------------------------
# Route – color libraries
# ---------------------------------------------------------------------------

def _neo_construction_table():
    """data/neoprene_construction.json for the configurator (face/foam/back)."""
    try:
        import products as _P
        b = _P._neo_build()
        return {k: v for k, v in b.items() if not k.startswith("_")}
    except Exception:
        return {}


@app.route("/api/colors")
def get_colors():
    return jsonify({
        "neoprene":      [{"name": n, "hex": h} for n, h in NEOPRENE.items()],
        "neoprene_construction": _neo_construction_table(),
        "thread":        [{"name": n, "hex": h} for n, h in THREADS.items()],
        "scuba_foam":    [{"name": n, "hex": h} for n, h in SCUBA_FOAM.items()],
        "cotton_canvas": [{"name": n, "hex": h} for n, h in COTTON_CANVAS.items()],
        "cotton_canvas_dyed": [{"name": n, "hex": h} for n, h in COTTON_CANVAS_DYED.items()],
        "jotter":        [{"name": n, "hex": h} for n, h in JOTTER.items()],
        "three_way_pen": [{"name": n, "hex": h} for n, h in THREE_WAY_PEN.items()],
        "le_pen":        [{"name": n, "hex": h, "pms": LE_PEN_PMS.get(n)} for n, h in LE_PEN.items()],
        "stick_pen":     [{"name": n, "hex": h, "pms": STICK_PEN_PMS.get(n)} for n, h in STICK_PEN.items()],
        "expanded_vinyl":  [{"name": n, "hex": h} for n, h in BANK_BAG_EV.items()],
        "laminated_nylon": [{"name": n, "hex": h} for n, h in BANK_BAG_LN.items()],
        "bias": [{"name": n, "hex": h} for n, h in BIAS.items()],
        "fabric_4cp":    [{"name": n, "hex": h} for n, h in FABRIC_4CP.items()],
        # Metallic neoprene (0070-3l / 1080-3l): its bodies are images (body_patterns).
        "neoprene_metallic": [],
        "neoprene_heathered": [],
        "neoprene_denim": [],
        "neoprene_burlap": [],
        "neoprene_suede": [],
    })

# ---------------------------------------------------------------------------
# Route – PMS library for one-color screen print ink selection
# ---------------------------------------------------------------------------

# ── inks the shop will not run ─────────────────────────────────────────────
# Stripped from the picker and from automatic matching, so neither a customer
# nor the auto-assignment can land on an ink that cannot be produced:
#
#   5-digit codes (10101 C …)  the premium extended range — 352 chips
#   8xxx series   (8001 C …)   metallics — 294 chips
#   871–877 C                  the classic metallics (golds, silvers)
#
# Fluorescents (800–807) are deliberately left in; they are printable.
# Delete a pattern here to allow that family back.
_PMS_EXCLUDED = re.compile(r"\b(?:\d{5}|8\d{3}|87[1-7])\b")


def is_printable_pms(name):
    """False for PMS chips this shop cannot run as screen-print ink."""
    return not _PMS_EXCLUDED.search(name or "")


# Apply the filter at the source rather than at each endpoint.
#
# Pantone names are returned by several routes — the ink picker, the eyedropper
# (/api/match-pantone-hex), the palette matcher (/api/match-pantone) and the
# artwork analyzer. Filtering them one at a time means every new route is a
# chance to forget, and a missed one quietly offers an ink the shop cannot run.
#
# Patching engine's own module global catches everything downstream, including
# suggest_pantones_from_palette(), which calls it internally.
import engine as _engine

_find_closest_pantone_unfiltered = _engine.find_closest_pantone


def _find_closest_pantone_printable(rgb, top_n=3, boost=False):
    """engine.find_closest_pantone, minus the inks this shop will not run."""
    # Over-fetch so the filter still leaves top_n to return: whole families are
    # being dropped, and near-metallic colors match many of them at once.
    wide = _find_closest_pantone_unfiltered(rgb, top_n=max(top_n * 6, 48), boost=boost)
    return [m for m in wide if is_printable_pms(m["name"])][:top_n]


_engine.find_closest_pantone = _find_closest_pantone_printable
find_closest_pantone = _find_closest_pantone_printable


# Screen-print inks with no PMS chip at all. The solid coated book has no white
# — white is a stock plastisol every printer carries, and on dark neoprene it
# is one of the most-asked-for inks, so it has to be offered explicitly or a
# customer simply cannot specify it.
NON_PMS_INKS = [
    {"name": "White", "short": "White", "hex": "#FFFFFF"},
]

NON_PMS_HEX = {i["name"]: i["hex"] for i in NON_PMS_INKS}


def with_non_pms_inks(matches, rgb, top_n=None):
    """
    Fold the no-chip inks into a list of Pantone matches, ranked by ΔE.

    Used wherever someone is choosing an ink to print. Without this, sampling
    a white area offers the nearest off-white Pantone — 9345 C and friends —
    which prints as a visibly dirty white when the customer plainly wants the
    white ink the shop already stocks.
    """
    try:
        from engine import _rgb_to_lab, _delta_e
        lab = _rgb_to_lab(rgb)
        extra = []
        for ink in NON_PMS_INKS:
            h = ink["hex"].lstrip("#")
            de = _delta_e(lab, _rgb_to_lab(tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))))
            extra.append({"name": ink["name"], "hex": ink["hex"],
                          "delta_e": round(de, 1)})
        out = sorted(list(matches) + extra, key=lambda m: m["delta_e"])
    except Exception:
        out = list(matches)
    return out[:top_n] if top_n else out


# Frequently specified screen-print inks, surfaced first in the picker so the
# customer isn't scrolling 3,000+ swatches to find black.
PMS_QUICK_PICKS = [
    "PANTONE Black C", "PANTONE Cool Gray 11 C",
    "PANTONE 186 C", "PANTONE 200 C", "PANTONE 199 C",
    "PANTONE 286 C", "PANTONE 295 C", "PANTONE 300 C", "PANTONE Blue 072 C",
    "PANTONE Reflex Blue C", "PANTONE 347 C", "PANTONE 356 C", "PANTONE 349 C",
    "PANTONE 123 C", "PANTONE 1235 C", "PANTONE Orange 021 C", "PANTONE 158 C",
    "PANTONE Red 032 C", "PANTONE 259 C", "PANTONE 268 C", "PANTONE 7421 C",
    "PANTONE 4625 C", "PANTONE 464 C", "PANTONE 7503 C",
]

# When auto-assigning an ink to detected artwork, a common ink this close in
# ΔE to the outright nearest match is preferred over it.
#
# The nearest chip by pure color distance is often a specialty ink that beats a
# standard one by a margin no eye can see: artwork drawn in near-black matches
# PANTONE 419 C at ΔE 9.8 and PANTONE Black C at 10.3, and a 0.5 difference is
# not a reason to send a job to press on a specialty black. Near-black is one
# of the most common colors in logos, so without this the default would be
# wrong far more often than it is right.
#
# Raise it to lean harder on stocked inks, set it to 0 to always take the
# closest chip regardless of whether anyone stocks it.
PMS_COMMON_INK_TOLERANCE = 2.0


def _snap_to_pms(rgb):
    """
    The PMS chip to assign to a detected ink.

    Returns the nearest match, unless a commonly stocked ink is within
    PMS_COMMON_INK_TOLERANCE of it — then that one, since the two are
    indistinguishable and one of them is the ink a press room actually has.
    """
    # find_closest_pantone is already filtered to runnable inks; this adds the
    # ones that have no Pantone chip, such as White.
    matches = with_non_pms_inks(find_closest_pantone(rgb, top_n=24), rgb)

    if not matches:
        return None

    best = matches[0]
    common = set(PMS_QUICK_PICKS) | set(NON_PMS_HEX)
    for m in matches:
        if m["name"] in common and m["delta_e"] - best["delta_e"] <= PMS_COMMON_INK_TOLERANCE:
            return m
    return best


@app.route("/api/pantone-library")
def pantone_library():
    """
    The approved PMS library for screen-print ink selection.

    This is the same Pantone data already supplied to the application — served
    to the configurator so the -3M workflow can offer a restricted PMS picker
    instead of a free RGB/HEX picker.
    """
    # Inks the shop cannot run are removed here rather than hidden in the UI,
    # so no code path downstream can reach one.
    colors = [
        {"name": name, "short": name.replace("PANTONE ", ""), "hex": hx}
        for name, hx in PANTONE_RGB.items()
        if is_printable_pms(name)
    ]
    colors = NON_PMS_INKS + colors

    # White leads the quick picks: it has no PMS chip, and on dark neoprene it
    # is the ink customers reach for first.
    quick = list(NON_PMS_INKS)
    for name in PMS_QUICK_PICKS:
        hx = PANTONE_RGB.get(name)
        if hx and is_printable_pms(name):
            quick.append({"name": name, "short": name.replace("PANTONE ", ""), "hex": hx})

    from flask import make_response, request as _rq
    import hashlib

    resp = make_response(jsonify({"colors": colors, "quick": quick}))

    # This list changes whenever the ink rules change — a family is filtered
    # out, White is added, the quick picks are reordered. It used to be served
    # with a 24-hour max-age under a fixed URL, so a browser that had already
    # loaded it kept handing back the old swatches for a day after a deploy and
    # the change looked like it simply hadn't shipped.
    #
    # An ETag over the payload plus no-cache keeps the caching (the body is
    # ~150 KB and the configurator asks for it once per load) while making the
    # browser revalidate, so an edit to the rules above reaches users on their
    # next reload instead of whenever their cache happens to expire.
    resp.set_etag(hashlib.md5(resp.get_data()).hexdigest())
    resp.headers["Cache-Control"] = "no-cache"
    return resp.make_conditional(_rq)

# ---------------------------------------------------------------------------
# Route – analyze uploaded art
# ---------------------------------------------------------------------------

@app.route("/api/analyze", methods=["POST"])
def analyze():
    """Analyze uploaded art files for color palette and Pantone matching."""
    product_id = request.form.get("product_id")
    if not product_id or product_id not in PRODUCTS:
        return jsonify({"error": "Invalid product_id"}), 400

    product = PRODUCTS[product_id]
    slots = product["art_slots"]

    saved_paths = {}
    for slot in slots:
        key = f"file_{slot['id']}"
        if key not in request.files:
            continue
        f = request.files[key]
        if not f.filename:
            continue
        dest = _upload_path(slot["id"], f.filename)
        f.save(str(dest))
        saved_paths[slot["id"]] = str(dest)

    if not saved_paths:
        return jsonify({"error": "No files uploaded"}), 400

    first_path = Path(next(iter(saved_paths.values())))
    raw_stem = first_path.stem
    for slot in slots:
        if raw_stem.startswith(slot["id"] + "_"):
            raw_stem = raw_stem[len(slot["id"]) + 1:]
            break
    order_id = raw_stem.split("-")[0]

    pantone_colors = []
    pantone_suggestions = []

    raster_exts = {'.jpg', '.jpeg', '.png', '.bmp', '.gif', '.tiff', '.webp'}
    for slot_id, path_str in saved_paths.items():
        ext = Path(path_str).suffix.lower()
        if ext in raster_exts:
            try:
                from colorthief import ColorThief
                ct = ColorThief(path_str)
                palette = ct.get_palette(color_count=6, quality=5)
                pantone_suggestions = suggest_pantones_from_palette(palette, top_n=1)
            except Exception:
                pass
            break

    dom = (128, 128, 128)
    for slot_id, path_str in saved_paths.items():
        ext = Path(path_str).suffix.lower()
        if ext in raster_exts:
            try:
                from colorthief import ColorThief
                ct = ColorThief(path_str)
                dom = ct.get_color(quality=5)
            except Exception:
                pass
            break

    thread_name, thread_hex = find_best(dom, THREADS)
    imprint_rgbs = resolve_pantone_rgbs(pantone_colors) if pantone_colors else []

    neoprene_options = []
    for name, hx in NEOPRENE.items():
        clashes = neoprene_clashes_with_imprint(hx, imprint_rgbs, min_contrast=2.5)
        neoprene_options.append({
            "name": name, "hex": hx,
            "safe": len(clashes) == 0,
            "clashes": [{"color": c, "ratio": round(r, 1)} for c, r in clashes],
        })

    short_pantones = [
        s["name"].replace("PANTONE ", "") for s in pantone_suggestions
    ] if pantone_suggestions else []

    return jsonify({
        "order_id":            order_id,
        "product_id":          product_id,
        "saved_paths":         saved_paths,
        "dominant_rgb":        list(dom),
        "thread_name":         thread_name,
        "thread_hex":          thread_hex,
        "pantone_colors":      pantone_colors,
        "short_pantones":      short_pantones,
        "pantone_suggestions": pantone_suggestions,
        "neoprene_options":    neoprene_options,
        "thread_options":      [{"name": n, "hex": hx} for n, hx in THREADS.items()],
    })

# ---------------------------------------------------------------------------
# Route — rasterize vector art to PNG for canvas preview
# ---------------------------------------------------------------------------

@app.route("/api/rasterize", methods=["POST"])
def rasterize():
    # A file already on the server (a composed layout) goes through exactly the
    # same checks as an upload, without sending it back and forth.
    server_path = request.form.get("server_path")
    if server_path:
        up_root = (HERE / "uploads").resolve()
        try:
            sp = Path(server_path).resolve()
        except Exception:
            return jsonify({"error": "Unknown file"}), 400
        if up_root not in sp.parents or not sp.is_file():
            return jsonify({"error": "That file is no longer on the server. Try again."}), 404

        class _ServerFile:
            filename = "layout.pdf" if sp.name.endswith("_layout.pdf") else sp.name
            def save(self, dst):
                if Path(dst).resolve() != sp:
                    shutil.copy2(str(sp), str(dst))
        f = _ServerFile()
    else:
        if "file" not in request.files:
            return jsonify({"error": "No file"}), 400
        f = request.files["file"]
        if not f.filename:
            return jsonify({"error": "Empty filename"}), 400

    slot_id = request.form.get("slot_id", "unknown")
    ext = Path(f.filename).suffix.lower()

    # One-color screen-print products validate artwork before accepting it.
    product_id = request.form.get("product_id") or ""
    # A piece of artwork placed inside a layout: just a clean preview and a
    # saved copy. The finished layout is what gets validated.
    layout_piece = request.form.get("purpose") == "layout"
    enforce_1c = is_screenprint(product_id) and slot_id != "bleed" and not layout_piece

    # Multi-color spot products separate the artwork into inks instead. The two
    # are mutually exclusive: a product either prints one color or assigns
    # several, never both.
    assign_pms = ((not enforce_1c) and supports_pms_assign(product_id) and slot_id != "bleed"
                  and not layout_piece)
    # Every other item (4CP, pens, totes): no screens, but the customer can
    # still recolor the art and give each color a Pantone. Same analysis, no
    # press rules.
    color_edit = ((not enforce_1c) and (not assign_pms) and slot_id != "bleed"
                  and not layout_piece and product_id in PRODUCTS)

    orig_path = _upload_path(slot_id, f.filename)

    # A raster upload on a one-color product is traced to vector rather than
    # turned away, when the art is the kind that can be traced: a flat-colour
    # mark on a plain ground. The gate that used to reject it outright moves
    # to vectorize.assess(), which judges the art against the size the
    # customer actually placed it at rather than against its file extension.
    import vectorize
    trace_raster = (enforce_1c and vectorize.is_raster(f.filename)
                    and vectorize.available())
    # Standard multi-colour items take images too: the inks are found here and
    # the image is traced per ink at export, each ink its own PMS screen.
    trace_multi = (assign_pms and vectorize.is_raster(f.filename)
                   and vectorize.available())
    # Recolorable images on items with no screens: analysed the same way.
    ce_raster = (color_edit and vectorize.is_raster(f.filename) and vectorize.available())
    # Standard multi-colour items read vector art the way the 24HR items do:
    # transparent, cropped to the art, never the whole artboard.
    # A composed layout (sent by server_path) is always rendered transparent
    # and cropped to the art, on every product — it has no artboard to show.
    art_quality = enforce_1c or assign_pms or layout_piece or bool(server_path) or color_edit

    # Gate on file type before writing anything to disk.
    if enforce_1c and not trace_raster:
        from screenprint import check_extension, ArtworkReport
        pre = ArtworkReport()
        check_extension(f.filename, pre)
        if not pre.ok:
            return jsonify({
                "error": pre.errors[0]["message"],
                "validation": pre.as_dict(),
            }), 400

    f.save(str(orig_path))

    try:
        png_path = orig_path.parent / (orig_path.stem + ".preview.png")

        # EPS is converted to PDF first and then follows the PDF path below,
        # rather than being rendered directly.
        #
        # Rendering it directly went through Pillow, which shells out to
        # Ghostscript and hands back an RGB image on white paper — EPS has no
        # alpha channel of its own. One-color artwork is validated on its
        # transparency, so every EPS, however clean, was rejected for "having a
        # white background" it never had. Ghostscript's pdfwrite output has no
        # background, so the same pdftocairo render that PDFs get produces real
        # transparency.
        #
        # -dEPSCrop keeps the artboard at the file's BoundingBox; without it the
        # art lands in the corner of a letter-size page.
        if ext == ".eps":
            import shutil as _sh, subprocess as _sp
            gs = _sh.which("gs") or _sh.which("ghostscript")
            if not gs:
                return jsonify({
                    "error": "EPS artwork needs Ghostscript on the server. "
                             "Re-save the artwork as PDF or AI, or install "
                             "ghostscript.",
                    "code": "no_ghostscript",
                }), 500
            converted = orig_path.parent / (orig_path.stem + ".from_eps.pdf")
            try:
                _sp.run([gs, "-dNOPAUSE", "-dBATCH", "-dEPSCrop",
                         "-sDEVICE=pdfwrite", f"-sOutputFile={converted}",
                         str(orig_path)],
                        check=True, capture_output=True, timeout=120)
            except Exception as e:
                return jsonify({"error": f"EPS could not be converted: {e}"}), 500
            orig_path = converted
            ext = ".pdf"

        if ext in {".pdf", ".ai"}:
            rasterized = False
            try:
                from pdf2image import convert_from_path
                # For screen-print artwork the preview must keep its alpha
                # channel: it becomes the printable mask, and a white page
                # background would otherwise be treated as part of the design
                # — the artboard merged into the art, sized by the page.
                if art_quality:
                    pages = convert_from_path(
                        str(orig_path), dpi=150, first_page=1, last_page=1,
                        transparent=True, use_pdftocairo=True, fmt="png",
                    )
                else:
                    pages = convert_from_path(str(orig_path), dpi=150, first_page=1, last_page=1)
                if pages:
                    pages[0].save(str(png_path), "PNG")
                    rasterized = True
            except Exception as e1:
                print(f"pdf2image failed ({e1}), trying svglib...")

            if not rasterized:
                try:
                    from svglib.svglib import svg2rlg
                    from reportlab.graphics import renderPM
                    from reportlab.graphics.shapes import Drawing
                    drawing = _svg_drawing(orig_path)
                    if drawing and drawing.width > 0:
                        scale = max(1.0, 800.0 / max(drawing.width, drawing.height))
                        scaled = Drawing(drawing.width * scale, drawing.height * scale)
                        scaled.transform = (scale, 0, 0, scale, 0, 0)
                        scaled.add(drawing)
                        renderPM.drawToFile(scaled, str(png_path), fmt="PNG")
                        rasterized = True
                    else:
                        raise ValueError("empty drawing")
                except Exception as e2:
                    print(f"svglib failed ({e2}), trying Pillow...")

            if not rasterized:
                try:
                    from PIL import Image as PILImage
                    img = PILImage.open(str(orig_path))
                    img.save(str(png_path), "PNG")
                    rasterized = True
                except Exception as e3:
                    print(f"Pillow failed ({e3})")

            if not rasterized:
                return jsonify({
                    "error": "Could not rasterize PDF/AI. Install poppler + pdf2image: pip install pdf2image"
                }), 500

        elif ext == ".svg":
            rasterized = False
            # cairosvg preserves the alpha channel, which the one-color mask
            # depends on — try it first for screen-print artwork.
            if art_quality:
                try:
                    import cairosvg
                    cairosvg.svg2png(url=str(orig_path), write_to=str(png_path), scale=2.0)
                    rasterized = True
                except Exception as e0:
                    print(f"cairosvg failed ({e0}), trying svglib...")
            if not rasterized:
                try:
                    from svglib.svglib import svg2rlg
                    from reportlab.graphics import renderPM
                    drawing = _svg_drawing(orig_path)
                    if drawing and drawing.width > 0 and drawing.height > 0:
                        scale = max(1.0, 800.0 / max(drawing.width, drawing.height))
                        from reportlab.graphics.shapes import Drawing
                        scaled = Drawing(drawing.width * scale, drawing.height * scale)
                        scaled.transform = (scale, 0, 0, scale, 0, 0)
                        scaled.add(drawing)
                        renderPM.drawToFile(scaled, str(png_path), fmt="PNG")
                        rasterized = True
                    else:
                        raise ValueError("svg2rlg returned empty drawing")
                except Exception as e:
                    print(f"svglib SVG render failed ({e}), using Pillow/cairosvg fallback...")

            if not rasterized:
                try:
                    import cairosvg
                    cairosvg.svg2png(url=str(orig_path), write_to=str(png_path), scale=2.0)
                    rasterized = True
                except Exception as e2:
                    print(f"cairosvg failed ({e2})")

            if not rasterized:
                # Never substitute a placeholder for one-color artwork — it would
                # silently become the customer's printable design.
                if art_quality:
                    return jsonify({
                        "error": "Artwork could not be processed. Please upload the "
                                 "artwork as a PDF, AI or EPS file and try again.",
                        "validation": {
                            "ok": False,
                            "errors": [{
                                "code": "svg_render_failed",
                                "message": "Artwork could not be processed. Please "
                                           "upload the artwork as a PDF, AI or EPS "
                                           "file and try again.",
                                "detail": "No SVG renderer is available on the server.",
                            }],
                            "warnings": [], "facts": {},
                        },
                    }), 500
                from PIL import Image as PILImage, ImageDraw
                placeholder = PILImage.new("RGBA", (400, 400), (245, 240, 232, 255))
                draw = ImageDraw.Draw(placeholder)
                draw.text((200, 190), "SVG", fill=(107, 26, 42, 200), anchor="mm")
                draw.text((200, 215), f.filename or orig_path.name, fill=(140, 123, 106, 180), anchor="mm")
                placeholder.save(str(png_path), "PNG")
                rasterized = True

        elif ext in {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tiff", ".webp"}:
            try:
                tight_path, tw, th = crop_raster_to_visible(str(orig_path))
                if not (trace_raster or trace_multi or ce_raster):
                    import base64 as _b64
                    with open(tight_path, "rb") as fp:
                        b64 = _b64.b64encode(fp.read()).decode()
                    return jsonify({
                        "preview_b64": b64,
                        "preview_mime": "image/png",
                        "width": tw,
                        "height": th,
                        "saved_path": str(orig_path),
                        "slot_id": slot_id,
                    })
                # Traced art joins the vector path below, which wants a PNG to
                # separate colours from — but it has to be the artwork, not
                # the artwork plus its background. A flattened upload carries
                # its background as opaque white, and a one-colour product
                # recolours every opaque pixel to the ink, so the preview
                # comes back as a solid block. Knocking the background out
                # here means the preview, the colour separation and the trace
                # are all looking at the same shape.
                knocked = orig_path.parent / (orig_path.stem + ".knockout.png")
                png_path = Path(vectorize.knockout_background(
                    tight_path, knocked)[0])
            except Exception as e:
                return jsonify({"error": str(e)}), 500
        else:
            return jsonify({"error": f"Unsupported format: {ext}"}), 400

        # ── one-color screen print: validate the artwork itself ─────────────
        validation = None
        needs_reduction = False
        if trace_raster:
            # Nothing here validates a raster the way it validates a vector —
            # the checks that matter for traced art (resolution and stroke
            # weight at the placed size) depend on how big the customer makes
            # it, so they run from /api/art-check as they resize rather than
            # once at upload.
            #
            # What is settled here is how many colours the art carries, and
            # the separation pass below is what counts them. Asking for it
            # unconditionally would open the reduction panel on art that is
            # already one colour and tell the customer to fix something that
            # is not wrong.
            needs_reduction = True     # provisional; corrected once counted
        elif enforce_1c:
            from screenprint import validate_artwork, ALLOW_MULTICOLOR_REDUCTION
            report = validate_artwork(str(orig_path), f.filename, preview_path=str(png_path))
            validation = report.as_dict()
            if not report.ok:
                # Too many colors is the one rejection the customer can fix
                # here: the art is otherwise sound, it just carries more inks
                # than the press will run. Accept it and hand back the colors
                # so the UI can offer to reduce them, behind its own warning.
                #
                # Every other rejection stands. Raster art, an opaque
                # background or an empty file are not problems a color picker
                # can solve, and accepting them would only move the failure
                # further down the line.
                codes = {e["code"] for e in report.errors}
                if ALLOW_MULTICOLOR_REDUCTION and codes == {"multicolor"}:
                    needs_reduction = True
                else:
                    try:
                        orig_path.unlink(missing_ok=True)
                        png_path.unlink(missing_ok=True)
                    except Exception:
                        pass
                    return jsonify({
                        "error": report.errors[0]["message"],
                        "validation": validation,
                    }), 400

        # ── standard items: is the vector press-ready? ─────────────────────
        # The same checks the 24HR items reject on, used here only to decide
        # whether press sheets can be made. Artists mock up with all sorts of
        # files, so the upload always goes through; what doesn't pass is
        # mockup-only and the export says why.
        press_issue = None
        if assign_pms and not trace_multi:
            try:
                from screenprint import validate_artwork
                rep_ = validate_artwork(str(orig_path), f.filename, preview_path=str(png_path))
                issues = [e for e in rep_.errors if e["code"] != "multicolor"]
                if issues:
                    press_issue = {"code": issues[0]["code"], "message": issues[0]["message"]}
            except Exception as e:
                print(f"press-readiness check failed: {e}")

        # ── multi-color spot: separate the artwork into assignable inks ─────
        # This never blocks an upload. Each detected ink is snapped to its
        # nearest PMS so a customer who knows nothing about production can
        # accept the defaults and still get a printable job. over_limit is the
        # cue for the UI to say the art has more colors than the press can run.
        separations = None
        if assign_pms or needs_reduction or color_edit:
            try:
                from screenprint import analyze_separations
                # A one-color product being reduced is measured against a
                # ceiling of one ink, so the panel reports how far there is
                # still to go rather than judging it against four.
                sep = None
                # Multi-colour vector art is read from the file itself: exact
                # colours and areas, so small inks aren't lost to the artboard.
                if (assign_pms or color_edit) and not needs_reduction and ext in {".pdf", ".ai", ".svg", ".eps"}:
                    try:
                        from screenprint import analyze_vector_separations
                        import press_layout as _pl
                        vec = _pl.art_as_pdf(str(orig_path), work_dir=str(orig_path.parent))
                        sep = analyze_vector_separations(vec, max_inks=_max_inks_for(product_id))
                        if not sep.get("inks"):
                            sep = None
                    except Exception as e:
                        print(f"vector separation failed, using the preview: {e}")
                        sep = None
                if sep is None:
                    sep = analyze_separations(str(png_path),
                                              max_inks=1 if needs_reduction else _max_inks_for(product_id))
                if trace_multi or ce_raster:
                    # An image on a standard item: count its real inks — the
                    # blend along each anti-aliased edge is not one — and say
                    # how much of it is flat colour at all. A photo or gradient
                    # scores low and stays a mockup-only image.
                    raw = analyze_separations(str(png_path), max_inks=12)
                    kept = vectorize.drop_blend_inks(raw.get("inks") or [])
                    if ce_raster and not any(min(int(i["hex"][k:k + 2], 16) for k in (1, 3, 5)) > 235
                                             for i in kept):
                        # A transparent image whose white is still opaque —
                        # a letter's counter, a white ring — carries white as
                        # a colour of its own, to keep, recolor or drop.
                        import numpy as _np
                        with Image.open(str(png_path)) as _im:
                            _a = _np.asarray(_im.convert("RGBA")).astype(int)
                        _op = _a[..., 3] > 250
                        if (_a[..., 3] < 250).any() and _op.any():
                            _w = int((_op & (_a[..., :3].min(axis=2) > 235)).sum())
                            if _w > 0.001 * int(_op.sum()):
                                kept = kept + [{"hex": "#FFFFFF", "share": round(_w / int(_op.sum()), 3),
                                                "sources": ["#FFFFFF"]}]
                    sep = dict(raw, inks=kept, detected=len(kept),
                               max_inks=_max_inks_for(product_id),
                               over_limit=len(kept) > _max_inks_for(product_id))
                    sep["flat_share"] = round(vectorize.flat_share(
                        str(png_path),
                        [tuple(int(i["hex"][k:k + 2], 16) for k in (1, 3, 5)) for i in kept],
                        None, tol=24), 3)
                import onecolor as _oc
                for ink in sep.get("inks", []):
                    rgb = tuple(int(ink["hex"][i:i + 2], 16) for i in (1, 3, 5))
                    if ink["hex"].upper() == _oc.WHITE_INK_HEX:
                        # A spot the designer named white: white ink.
                        ink["pms"], ink["pms_hex"], ink["delta_e"] = "White", "#FFFFFF", 0.0
                        continue
                    match = _snap_to_pms(rgb)
                    if match:
                        ink["pms"] = match["name"]
                        ink["pms_hex"] = match["hex"]
                        ink["delta_e"] = match["delta_e"]
                if color_edit and ext in {".pdf", ".ai", ".svg", ".eps"}:
                    sep["has_images"] = _pdf_has_images(str(orig_path))
                separations = sep
                # Traced art only needs the reduction panel if it is actually
                # carrying more than one colour. An image that is already one
                # ink goes straight through, the way a clean vector does.
                if trace_raster and int(sep.get("detected") or 0) <= 1:
                    needs_reduction = False
            except Exception as e:
                # Separation is an enhancement on top of a working upload. If
                # it fails, the customer keeps their artwork and loses only the
                # automatic ink assignment.
                print(f"separation analysis failed: {e}")
                separations = {
                    "inks": [], "detected": 0, "max_inks": 0,
                    "merged": [], "over_limit": False, "error": str(e),
                }

        try:
            tight_path, tw, th = crop_raster_to_visible(str(png_path))
        except Exception:
            tight_path = str(png_path)
            with Image.open(tight_path) as im:
                tw, th = im.size

        import base64 as _b64
        with open(tight_path, "rb") as fp:
            b64 = _b64.b64encode(fp.read()).decode()

        return jsonify({
            "preview_b64": b64,
            "preview_mime": "image/png",
            "width": tw,
            "height": th,
            "saved_path": str(orig_path),
            "slot_id": slot_id,
            "validation": validation,
            "is_screenprint": bool(enforce_1c),
            "separations": separations,
            "assign_pms": bool(assign_pms),
            "color_edit": bool(color_edit),
            "press_issue": press_issue,
            "needs_reduction": bool(needs_reduction),
            # The art will be traced to vector on export. The UI says so, and
            # checks it against the placed size through /api/art-check.
            "traced": bool(trace_raster or trace_multi),
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/art-check", methods=["POST"])
def art_check():
    """
    Can this raster art be traced at the size the customer has placed it?

    Deliberately cheap — no tracing happens, only measurement on the mask —
    because the configurator calls this every time the art is resized and the
    answer has to arrive while the handle is still moving.
    """
    import vectorize
    body = request.get_json(force=True) or {}
    path = str(_in_uploads(body.get("art_path")) or "")
    if not path:
        return jsonify({"error": "Artwork not found on the server.",
                        "code": "art_missing"}), 400
    # Open-weave bodies (burlap): art is measured against the weave at its
    # printed size, vector too — a vector hairline holds on neoprene, not here.
    import porous
    pid = str(body.get("product_id") or "")
    zone_w = float(body.get("zone_w_in") or 0) or None
    if not vectorize.is_raster(path):
        # Vector art has no resolution to run out of.
        if porous.limits(pid):
            try:
                w_in = float(body.get("printed_w_in") or 0)
                r = porous.check(path, w_in, pid, zone_w) if w_in else None
                if r:
                    r["raster"] = False
                    return jsonify(r)
            except Exception as e:
                print(f"⚠️ porous check failed for {path}: {e}")
        return jsonify({"verdict": "ok", "notes": [], "raster": False})
    if not vectorize.available():
        return jsonify({"verdict": "refuse", "raster": True,
                        "notes": ["Image artwork can't be converted on this "
                                  "server. Please upload vector artwork "
                                  "(AI, EPS, PDF or SVG)."]})
    try:
        w_in = float(body.get("printed_w_in") or 0) or None
        h_in = float(body.get("printed_h_in") or 0) or None
        if not w_in:
            return jsonify({"error": "printed_w_in is required.",
                            "code": "no_size"}), 400
        keep = _kept_inks(body)
        mask = (vectorize.masks_for_inks(path, keep) if keep
                else {"ink": vectorize.ink_mask(path)})
        merged = None
        for m in mask.values():
            merged = m if merged is None else (merged | m)
        out = vectorize.assess(merged, w_in, h_in,
                               n_colors=max(1, len(keep) or 1))
        out["raster"] = True
        if porous.limits(pid):
            try:
                pr = porous.check(path, w_in, pid, zone_w, mask=merged)
                if pr and pr["verdict"] != "ok":
                    out["notes"] = list(out.get("notes") or []) + pr["notes"]
                    out["verdict"] = "refuse" if out.get("verdict") == "refuse" else "warn"
                    out["porous"] = True
            except Exception as e:
                print(f"⚠️ porous check failed for {path}: {e}")
        return jsonify(out)
    except Exception as e:
        print(f"⚠️ art-check failed for {path}: {e}")
        return jsonify({"error": str(e)}), 500


def _kept_inks(body):
    """
    The source colours that will print, as [(name, rgb)].

    Built from the colours the art was found to contain minus the ones the
    customer switched off, so it says the same thing the reduction panel
    shows. An empty list means "everything that is not background", which is
    the one-colour case and needs no separation at all.
    """
    hidden = {tuple(c) for c in _hidden_rgbs(body)}
    out = []
    for h in (body.get("source_inks") or []):
        s = str(h).strip().lstrip("#")
        if len(s) != 6:
            continue
        try:
            rgb = tuple(int(s[i:i + 2], 16) for i in (0, 2, 4))
        except ValueError:
            continue
        if rgb not in hidden:
            out.append((s, rgb))
    return out


def _as_vector(art_path, body, work_dir, inks=None, bg_hex=None):
    """
    A vector file for the press and print paths, tracing raster art if needed.

    Returns the path to use. Traced output carries each colour in the SOURCE
    file's own colour rather than as a separation, so everything downstream —
    dropping the inks the customer switched off, flattening the rest to one
    spot — works on it unchanged. By the time art reaches the press layout, a
    traced upload and an uploaded PDF are the same kind of thing.
    """
    import vectorize
    if not art_path or not vectorize.is_raster(art_path):
        return art_path
    if not vectorize.available():
        raise PressBuildError(
            "Image artwork needs the tracer to build a press file, and it is "
            "not installed on this server. Re-upload the artwork as PDF, AI, "
            "EPS or SVG.", "no_tracer", 500)
    colors = _kept_inks(body) or None
    bg = (255, 255, 255)
    inks = inks if inks is not None else body.get("inks")
    tag = ""
    if inks:
        # Multi-colour: trace EVERY detected ink, hidden ones included, so a
        # hidden colour's pixels stay its own shapes (and are then dropped)
        # rather than being claimed by the nearest ink that still prints.
        colors = []
        for i in inks:
            h = str(i.get("hex") or "").lstrip("#")
            if len(h) == 6:
                colors.append((h, tuple(int(h[k:k + 2], 16) for k in (0, 2, 4))))
        colors = colors or None
        tag = "-" + "".join(sorted(h for h, _ in (colors or [])))[:24]
        b = str((bg_hex if bg_hex is not None else body.get("bg_hex")) or "").lstrip("#")
        if len(b) == 6:
            bg = tuple(int(b[k:k + 2], 16) for k in (0, 2, 4))
    out = Path(work_dir) / (Path(art_path).stem + tag + ".traced.pdf")
    if out.exists():
        return str(out)
    info = vectorize.trace(art_path, out, colors=colors, bg=bg)
    print(f"traced {Path(art_path).name} → {info['total_paths']} paths"
          f"{' (trapped)' if info['trapped'] else ''}")
    return str(out)


@app.route("/api/render-pdf", methods=["POST"])
def render_pdf():
    """Generate a production-ready PDF with art placed on template."""
    body = request.get_json(force=True)
    product_id = body.get("product_id")
    if not product_id or product_id not in PRODUCTS:
        return jsonify({"error": "Invalid product_id"}), 400

    product = PRODUCTS[product_id]
    # The order id names a file on disk (and is printed on the proof), so only
    # what could steer that file elsewhere is replaced: slashes and control
    # characters. The paths are files to read. Neither is taken as-is.
    order_id = re.sub(r"[\x00-\x1f\x7f/\\]", "_", str(body.get("order_id") or ""))[:150] or "ORDER"
    raw_paths = body.get("saved_paths") or {}
    saved_paths = {k: str(p) for k, v in (raw_paths.items() if isinstance(raw_paths, dict) else [])
                   if (p := _in_uploads(v))}
    body["bleed_path"] = str(_in_uploads(body.get("bleed_path")) or "") or None

    job_id = _unique_id("job")
    new_job(job_id, {})
    threading.Thread(
        target=_pdf_worker,
        args=(job_id, product, order_id, saved_paths, body),
        daemon=True
    ).start()
    return jsonify({"job_id": job_id})


def _hidden_rgbs(body):
    """
    Source colors the customer marked "don't print", as sRGB triples.

    These are the artwork's own colors, not the assigned PMS — the export has
    to find them in the customer's file to remove them.
    """
    out = []
    for h in (body.get("hidden_colors") or []):
        s = str(h).strip().lstrip("#")
        if len(s) == 6:
            try:
                out.append(tuple(int(s[i:i + 2], 16) for i in (0, 2, 4)))
            except ValueError:
                continue
    return out


def _spot_color(body):
    """
    Build the PMS spot color for this job as a real PDF separation.

    reportlab writes a CMYKColorSep out as
        /Separation /PANTONE#20186#20C /DeviceCMYK <tint transform>
    so the plate comes off the RIP under the Pantone name rather than as a
    process build. The CMYK values are the on-screen alternate space, derived
    from the Pantone library's RGB — the spot name is the production spec.
    """
    name = (body.get("screen_print_ink") or "").strip()
    if not name:
        return None
    try:
        from reportlab.lib.colors import CMYKColorSep
        from screenprint import hex_to_cmyk
        # NON_PMS_HEX first: inks like White have no Pantone chip, so a lookup
        # against the Pantone table alone misses and falls through to the
        # #000000 default — a white job would come off the press black.
        hexv = (NON_PMS_HEX.get(name)
                or PANTONE_RGB.get(name)
                or PANTONE_RGB.get(f"PANTONE {name}")
                or "#000000")
        cy, ma, ye, k = hex_to_cmyk(hexv)
        return CMYKColorSep(cy, ma, ye, k, spotName=name, density=1)
    except Exception as e:
        print(f"⚠️ Could not build spot color for {name!r}: {e}")
        return None


def _pdf_worker(job_id, product, order_id, saved_paths, body):
    """Build the production PDF using reportlab — tight-fit art, vector-aware."""
    try:
        update_job(job_id, {"status": "running", "message": "Building production PDF…"})

        from reportlab.pdfgen import canvas as pdf_canvas
        from reportlab.lib.utils import ImageReader
        from reportlab.lib.colors import Color
        from reportlab.graphics import renderPDF
        from pathlib import Path
        import shutil
        import os

        slots = product["art_slots"]
        serve_dir = HERE / "_serve" / job_id
        serve_dir.mkdir(parents=True, exist_ok=True)

        production_name = f"{order_id}_production.pdf"
        production_path = serve_dir / production_name

        page_w = product.get("page_w", 320)
        page_h = product.get("page_h", 760)
        print_notes = []          # reported with the export (vectorized / DPI)
        art_sizes = []            # printed size per location, for the proof

        placement = body.get("placement", {})
        template_w = body.get("template_w", 795)
        template_h = body.get("template_h", 2000)
        zones = body.get("zones", {})

        c = pdf_canvas.Canvas(str(production_path), pagesize=(page_w, page_h))
        c.setTitle(f"{order_id} Production Template")

        # ── 4CP: Background fill or bleed image layer ────────────────────
        is_4cp = body.get("is_4cp", False)
        if is_4cp:
            from PIL import Image as PILImage
            import io

            fill_mode = body.get("fill_mode", "none")
            bleed_path = body.get("bleed_path")
            bleed_ox = float(body.get("bleed_ox", 0))
            bleed_oy = float(body.get("bleed_oy", 0))
            bleed_sc = float(body.get("bleed_sc", 1))

            # Determine the full bleed zone in PDF points
            bz = product.get("bleed_zone_full", {})
            if bz:
                bz_x = bz["x"] * page_w
                bz_y_top = page_h - bz["y"] * page_h
                bz_w = bz["w"] * page_w
                bz_h = bz["h"] * page_h
                bz_y_bottom = bz_y_top - bz_h
            else:
                bz_x, bz_y_bottom, bz_w, bz_h = 0, 0, page_w, page_h

            # ── Solid or gradient fill ────────────────────────────────────
            if fill_mode in ("solid", "gradient"):
                c.saveState()

                if fill_mode == "solid":
                    hex_color = body.get("fill_solid_hex", "#ffffff").lstrip("#")
                    r_val = int(hex_color[0:2], 16) / 255
                    g_val = int(hex_color[2:4], 16) / 255
                    b_val = int(hex_color[4:6], 16) / 255
                    # A Pantone background (a stock colour's own, or the one
                    # matched to a custom colour) goes in as that named spot,
                    # shown in the colour the picker shows.
                    spot_nm = _fill_spot_name(body)
                    if spot_nm:
                        try:
                            _spot_rect(c, bz_x, bz_y_bottom, bz_w, bz_h, spot_nm,
                                       (r_val, g_val, b_val), serve_dir)
                            print_notes.append(f"Background: {spot_nm.replace('PANTONE ', '')} (spot)")
                        except Exception as e:
                            print(f"⚠️ Spot background failed, painted RGB: {e}")
                            spot_nm = None
                    if not spot_nm:
                        c.setFillColor(Color(r_val, g_val, b_val))
                        c.rect(bz_x, bz_y_bottom, bz_w, bz_h, fill=1, stroke=0)

                elif fill_mode == "gradient":
                    stops = body.get("fill_gradient_stops", ["#ffffff", "#000000"])
                    direction = body.get("fill_gradient_dir", "to right")
                    # A true vector gradient: sharp at any size, no pixels to
                    # count, and instant — the old version built it pixel by
                    # pixel in Python.
                    from reportlab.lib.colors import HexColor as _Hex
                    cols = [_Hex("#" + str(h).lstrip("#")) for h in stops] or [_Hex("#ffffff")]
                    if len(cols) == 1:
                        cols = cols * 2
                    x0, y0 = bz_x, bz_y_bottom
                    x1, y1 = bz_x + bz_w, bz_y_bottom + bz_h
                    if direction == "to bottom":
                        g = (x0, y1, x0, y0)
                    elif direction == "135deg":
                        g = (x0, y1, x1, y0)
                    elif direction == "45deg":
                        g = (x0, y0, x1, y1)
                    else:
                        g = (x0, y0, x1, y0)
                    p_clip = c.beginPath(); p_clip.rect(bz_x, bz_y_bottom, bz_w, bz_h)
                    c.clipPath(p_clip, stroke=0, fill=0)
                    c.linearGradient(*g, cols, extend=True)

                c.restoreState()

            # ── Bleed background image ────────────────────────────────────
            if bleed_path and os.path.exists(bleed_path):
                try:
                    tight_path, iw, ih = crop_raster_to_visible(bleed_path)

                    # ── Match canvas RT() logic exactly ──────────────────
                    # Canvas scales to cover the FULL canvas (cw × ch), not just
                    # the bleed zone. Mirror that here using page_w × page_h.
                    scale = max(page_w / iw, page_h / ih) * bleed_sc

                    draw_w = iw * scale
                    draw_h = ih * scale

                    # Canvas offset: bleed_ox/oy are in template guide pixels.
                    # Convert to PDF points using the same page_w/template_w ratio.
                    pt_per_px = page_w / float(template_w)
                    draw_x = (page_w - draw_w) / 2 + bleed_ox * pt_per_px
                    draw_y = (page_h - draw_h) / 2 - bleed_oy * pt_per_px

                    c.saveState()
                    # Clip to full page width/height — the bleed_zone_full in products.py
                    # is the print boundary; we let the image fill edge-to-edge like the
                    # canvas preview does, trimming only at the actual page edges.
                    p_clip = c.beginPath()
                    p_clip.rect(0, 0, page_w, page_h)
                    c.clipPath(p_clip, stroke=0, fill=0)
                    c.drawImage(tight_path, draw_x, draw_y, draw_w, draw_h,
                                preserveAspectRatio=False, mask="auto")
                    c.restoreState()
                except Exception as e:
                    print(f"⚠️ Error placing bleed image: {e}")

        # ── Guides ────────────────────────────────────────────────────────
        # A 4CP item printed on the Fiery gets no guides or footer: this file
        # is the print, and anything drawn here prints. Its only marks are the
        # template's own notches, added after the design (see below).
        fiery = product.get("fiery_template") if is_4cp else None
        # A Mimaki jig product (the 0837) likewise: this file is only the
        # source the -RH / -LH jig files are stamped from, box for box.
        jig = product.get("mimaki_jig")
        for slot in ([] if (fiery or jig) else slots):
            sx = slot["left_pt"]
            sy_top = page_h + slot["top_pt"]
            sw = slot["w_pt"]
            sh = slot["h_pt"]
            bx = sx
            by = sy_top - sh

            c.saveState()
            c.setStrokeColor(Color(0.8, 0, 0, alpha=0.5))
            c.setLineWidth(0.5)
            c.setDash(4, 3)

            if slot.get("shape") == "circle":
                c.circle(bx + sw / 2, by + sh / 2, sw / 2, stroke=1, fill=0)
            else:
                c.rect(bx, by, sw, sh, stroke=1, fill=0)

            c.setStrokeColor(Color(0, 0.7, 0.7, alpha=0.4))
            c.setLineWidth(0.3)
            c.setDash(2, 2)

            mid_x = bx + sw / 2
            mid_y = by + sh / 2
            c.line(mid_x, by, mid_x, by + sh)
            c.line(bx, mid_y, bx + sw, mid_y)

            c.setDash()
            c.setFillColor(Color(0, 0.6, 0.6, alpha=0.5))
            c.setFont("Helvetica", 5)
            c.drawCentredString(mid_x, by - 8, f"{slot['label']} — {slot['size']}")
            c.restoreState()

        # ── Art placement ────────────────────────────────────────────────
        for slot in slots:
            art_path = saved_paths.get(slot["id"])
            if not art_path or not os.path.exists(art_path):
                continue

            # On a one-colour product a raster upload is traced first, so the
            # print PDF places the same vector the press file will image
            # rather than the pixels. On every other product it is left alone:
            # a full-colour print has no separation to trace to.
            if is_screenprint(body.get("product_id") or ""):
                try:
                    art_path = _as_vector(art_path, body, Path(art_path).parent)
                except Exception as e:
                    print(f"⚠️ Could not trace {art_path}: {e}")

            ext = Path(art_path).suffix.lower()
            slot_x = slot["left_pt"]
            slot_y = page_h + slot["top_pt"]
            slot_w = slot["w_pt"]
            slot_h = slot["h_pt"]

            p = placement.get(slot["id"], {})
            p_ox = p.get("ox", 0)
            p_oy = p.get("oy", 0)
            p_sc = p.get("sc", 1.0)

            z = zones.get(slot["id"], {})
            zone_w_px = z.get("w", 0.93) * template_w
            zone_h_px = z.get("h", 0.378) * template_h

            ox_pt = p_ox * (slot_w / zone_w_px) if zone_w_px > 0 else 0
            oy_pt = p_oy * (slot_h / zone_h_px) if zone_h_px > 0 else 0

            def begin_slot_transform():
                c.saveState()
                if slot.get("rotation", 0):
                    cx_rot = slot_x + slot_w / 2
                    cy_rot = slot_y - slot_h / 2
                    c.translate(cx_rot, cy_rot)
                    c.rotate(slot["rotation"])
                    c.translate(-cx_rot, -cy_rot)
                # The customer's own rotation, about the art's centre — radians,
                # clockwise on screen, so counter-clockwise negative here.
                import math as _m
                u_rot = float(p.get("rot") or 0)
                if abs(u_rot) > 1e-4:
                    ax = slot_x + slot_w / 2 + ox_pt
                    ay = slot_y - slot_h / 2 - oy_pt
                    c.translate(ax, ay)
                    c.rotate(-_m.degrees(u_rot))
                    c.translate(-ax, -ay)

            def end_slot_transform():
                c.restoreState()

            # ── Recolored art (4CP, pens, totes) ─────────────────────────
            # The customer changed colors in the panel: the art is rebuilt with
            # every shape in its assigned Pantone, each a named spot with a CMYK
            # alternate, so the RIP (the Fiery on 4CP) matches the Pantone
            # rather than the file's RGB. Images are traced per ink first.
            slot_inks = (body.get("inks_by_slot") or {}).get(slot["id"])
            if slot_inks and not is_screenprint(body.get("product_id") or ""):
                try:
                    art_path, ext = _recolor_art(art_path, slot_inks,
                                                 (body.get("bg_by_slot") or {}).get(slot["id"]),
                                                 full_color=bool(is_4cp)), ".pdf"
                    names = [str(i.get("pms") or "").replace("PANTONE ", "")
                             for i in slot_inks if not i.get("hidden") and i.get("pms")]
                    print_notes.append(f"{slot['label']}: recolored — " + ", ".join(dict.fromkeys(names)))
                except Exception as e:
                    import traceback; traceback.print_exc()
                    print(f"⚠️ Recolor skipped for {art_path}: {e}")

            # ── 4CP raster: vector when the art is flat colour ───────────
            # Logos, type and flat illustrations are traced to vector so they
            # print sharp at any size; photographic art stays an image and is
            # checked for resolution below.
            if is_4cp and ext in {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tiff", ".webp"}:
                try:
                    vec = _vectorize_4cp(art_path)
                    if vec:
                        art_path, ext = vec, ".pdf"
                        print_notes.append(f"{slot['label']}: converted to vector")
                except Exception as e:
                    print(f"⚠️ 4CP vectorize skipped for {art_path}: {e}")

            # ── Raster: trim transparency before fitting ────────────────
            if ext in {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tiff", ".webp"}:
                try:
                    tight_path, iw, ih = crop_raster_to_visible(art_path)

                    scale = _cap_fit(min(slot_w / iw, slot_h / ih) * p_sc, iw, ih, slot_w, slot_h, p.get("rot"), slot.get("shape") == "circle")
                    draw_w = iw * scale
                    draw_h = ih * scale
                    if is_4cp and draw_w > 0:
                        dpi = iw / (draw_w / 72.0)
                        print_notes.append(
                            f"{slot['label']}: photo art at {dpi:.0f} DPI"
                            + ("" if dpi >= MIN_4CP_DPI else f" — under {MIN_4CP_DPI}, may print soft"))

                    dx = slot_x + (slot_w - draw_w) / 2 + ox_pt
                    dy = slot_y - slot_h + (slot_h - draw_h) / 2 - oy_pt

                    art_sizes.append({"label": slot["label"], "id": slot["id"], "size": f'{draw_w / 72:.2f}" W × {draw_h / 72:.2f}" H', "x": dx - slot_x, "y": slot_y - (dy + draw_h), "w": draw_w, "h": draw_h, "rot": float((placement.get(slot["id"]) or {}).get("rot") or 0), "file": str(tight_path), "clip": None})
                    begin_slot_transform()
                    c.drawImage(
                        tight_path,
                        dx,
                        dy,
                        draw_w,
                        draw_h,
                        preserveAspectRatio=True,
                        mask="auto",
                    )
                    end_slot_transform()

                except Exception as e:
                    print(f"⚠️ Error placing raster art {art_path}: {e}")

            # ── SVG: fit to actual vector content, not artboard ─────────
            elif ext == ".svg":
                try:
                    from svglib.svglib import svg2rlg

                    drawing = _svg_drawing(art_path)
                    if drawing:
                        x1, y1, x2, y2 = drawing.getBounds()
                        content_w = max(1, x2 - x1)
                        content_h = max(1, y2 - y1)

                        scale = _cap_fit(min(slot_w / content_w, slot_h / content_h) * p_sc, content_w, content_h, slot_w, slot_h, p.get("rot"), slot.get("shape") == "circle")
                        draw_w = content_w * scale
                        draw_h = content_h * scale

                        dx = slot_x + (slot_w - draw_w) / 2 + ox_pt
                        dy = slot_y - slot_h + (slot_h - draw_h) / 2 - oy_pt

                        art_sizes.append({"label": slot["label"], "id": slot["id"], "size": f'{draw_w / 72:.2f}" W × {draw_h / 72:.2f}" H', "x": dx - slot_x, "y": slot_y - (dy + draw_h), "w": draw_w, "h": draw_h, "rot": float((placement.get(slot["id"]) or {}).get("rot") or 0), "file": None, "clip": None})
                        begin_slot_transform()
                        c.translate(dx, dy)
                        c.scale(scale, scale)
                        c.translate(-x1, -y1)
                        renderPDF.draw(drawing, c, 0, 0)
                        end_slot_transform()

                except Exception as e:
                    print(f"⚠️ Error placing SVG art {art_path}: {e}")

            # ── PDF / AI: place as vector form XObject ──────────────────
            elif ext in {".pdf", ".ai"}:
                try:
                    from pdfrw import PdfReader
                    from pdfrw.buildxobj import pagexobj
                    from pdfrw.toreportlab import makerl

                    pdf = PdfReader(art_path)
                    page = pdf.pages[0]
                    xobj = pagexobj(page)

                    bbox = getattr(xobj, "BBox", None)
                    if bbox and len(bbox) == 4:
                        x1, y1, x2, y2 = [float(v) for v in bbox]
                    else:
                        x1, y1, x2, y2 = 0.0, 0.0, float(slot_w), float(slot_h)

                    # The BBox above is the artboard. The canvas preview fits
                    # art to its ink, so fit to the ink here too — otherwise
                    # art drawn on an oversized artboard exports far smaller
                    # than the customer positioned it.
                    if is_screenprint(body.get("product_id") or "") or INK_FIT_ALL_PRODUCTS:
                        from screenprint import ink_bbox_points
                        ink = ink_bbox_points(art_path, (x1, y1, x2, y2))
                        if ink:
                            x1, y1, x2, y2 = ink

                    content_w = max(1, x2 - x1)
                    content_h = max(1, y2 - y1)

                    scale = _cap_fit(min(slot_w / content_w, slot_h / content_h) * p_sc, content_w, content_h, slot_w, slot_h, p.get("rot"), slot.get("shape") == "circle")
                    draw_w = content_w * scale
                    draw_h = content_h * scale

                    dx = slot_x + (slot_w - draw_w) / 2 + ox_pt
                    dy = slot_y - slot_h + (slot_h - draw_h) / 2 - oy_pt

                    # One-color screen print: the job leaves here as a single
                    # named PMS separation, not in the customer's own colors.
                    spot = None
                    if is_screenprint(body.get("product_id") or ""):
                        from screenprint import recolor_form_to_spot

                        # Colors the customer marked "don't print" while
                        # reducing the art. They were knocked out of the canvas
                        # preview in the browser; this is where they come out
                        # of the artwork that actually goes to press. Done
                        # before the recolor, which flattens every remaining
                        # color into the one ink and would otherwise make the
                        # hidden ones indistinguishable.
                        hidden = _hidden_rgbs(body)
                        if hidden:
                            from screenprint import drop_colors_from_form
                            if not drop_colors_from_form(xobj, hidden):
                                print("⚠️ Hidden colors could NOT be removed from "
                                      f"{art_path} — its content stream could not be "
                                      "rewritten. The artwork still carries them.")

                        # White shapes punched over a fill are knockouts, not
                        # ink. Without this the flatten below turns them into
                        # the job's ink and the detail fills in solid.
                        from screenprint import drop_white_knockouts
                        drop_white_knockouts(xobj)

                        spot = _spot_color(body)
                        if spot is not None and not recolor_form_to_spot(xobj):
                            print("⚠️ Artwork kept its original color — its "
                                  "content stream could not be rewritten.")
                            spot = None

                    art_sizes.append({"label": slot["label"], "id": slot["id"], "size": f'{draw_w / 72:.2f}" W × {draw_h / 72:.2f}" H', "x": dx - slot_x, "y": slot_y - (dy + draw_h), "w": draw_w, "h": draw_h, "rot": float((placement.get(slot["id"]) or {}).get("rot") or 0), "file": str(art_path), "clip": [x1, y1, x2, y2]})
                    begin_slot_transform()
                    c.translate(dx, dy)
                    c.scale(scale, scale)
                    c.translate(-x1, -y1)
                    if spot is not None:
                        c.setFillColor(spot)
                        c.setStrokeColor(spot)
                    c.doForm(makerl(c, xobj))
                    end_slot_transform()

                except Exception as e:
                    print(f"⚠️ Error placing PDF/AI art {art_path}: {e}")

            else:
                print(f"⚠️ Unsupported art format skipped: {art_path}")

        # ── Footer ───────────────────────────────────────────────────────
        from reportlab.lib.colors import Color as RLColor

        c.setFont("Helvetica", 6)
        c.setFillColor(RLColor(0.4, 0.4, 0.4))

        neoprene_name = body.get("neoprene_name", "")
        thread_name = body.get("thread_name", "")

        footer = f"Order: {order_id}  |  Material: {neoprene_name}"
        # This Is Fast jobs carry the suffixed item id and the PMS ink onto the
        # production sheet so the floor has the full spec.
        _pid = body.get("product_id") or ""
        if is_screenprint(_pid):
            footer = (f"Order: {order_id}  |  Item: {screenprint_sku(_pid)}"
                      f"  |  Material: {neoprene_name}")
            ink = body.get("screen_print_ink") or ""
            if ink:
                footer += f"  |  Ink: {ink}"
        if thread_name and product.get("has_stitching"):
            footer += f"  |  Thread: {thread_name}"
        if body.get("show_price") and body.get("unit_price") is not None:
            footer += f"  |  Available As Low As: ${body['unit_price']:.2f} ea"

        if not (fiery or jig):
            c.drawCentredString(page_w / 2, 10, footer)
        c.save()
        if is_4cp:
            # The team RIPs 4CP in RGB to match the proofs and virtuals, so
            # the print file is RGB throughout — CMYK images and vectors in
            # customer art included. Done before the notches go on: they stay
            # the template's own "Notches" spot.
            try:
                _to_rgb_pdf(production_path)
            except Exception as e:
                print(f"⚠️ RGB conversion skipped: {e}")
        if fiery:
            try:
                note = _apply_fiery_notches(production_path, HERE / fiery)
                print(f"fiery notches: {note}")
            except Exception as e:
                import traceback; traceback.print_exc()
                print(f"⚠️ Could not add the Fiery notches: {e}")

        for slot in slots:
            art_src = saved_paths.get(slot["id"])
            if art_src and os.path.exists(art_src):
                shutil.copy2(art_src, str(serve_dir / Path(art_src).name))

        update_job(job_id, {
            "status": "done",
            "message": "Done",
            "serve_dir": str(serve_dir),
            "production_filename": production_name,
            "print_notes": print_notes,
            "art_sizes": art_sizes,
            "order_id": order_id,
            "neoprene_name": neoprene_name,
            "thread_name": thread_name,
        })

    except Exception as e:
        update_job(job_id, {"status": "error", "message": str(e)})

# ---------------------------------------------------------------------------
# Route — press file: customer proof + imposed press sheets
# ---------------------------------------------------------------------------

def _upload_path(slot_id, filename):
    """
    Where an uploaded artwork file is saved: unique per upload.

    Named "<slot>_<filename>" before, so a second upload with the same file
    name — the customer re-exporting logo.pdf, or another customer on the
    same server who also has a logo.pdf — overwrote the first on disk. Every
    location still pointing at the old path then silently printed the new art.
    A short random token keeps each upload its own file. The name the browser
    sent is also sanitised: it went into the path as-is.
    """
    import uuid
    from werkzeug.utils import secure_filename
    name = secure_filename(filename or "") or "art"
    slot = _safe_prefix(str(slot_id)) or "slot"
    d = HERE / "uploads"
    d.mkdir(exist_ok=True)
    return d / f"{slot}_{uuid.uuid4().hex[:10]}_{name}"


UPLOADS_DIR = (HERE / "uploads").resolve()


def _in_uploads(raw):
    """
    The resolved path if `raw` is an existing file inside uploads/, else None.

    File paths that arrive from the browser, or from inside an uploaded proof,
    are only trusted there. Everything this server hands the page to send back
    (uploads, converted EPS, traced vectors, one-color versions, layouts,
    restored art) lives in uploads/, so this refuses only paths nobody should
    be sending: without it a request could name any file on the server.
    """
    if not raw:
        return None
    try:
        p = Path(str(raw)).resolve()
    except Exception:
        return None
    return p if UPLOADS_DIR in p.parents and p.is_file() else None


def _unique_id(prefix):
    """
    An id for a render job or an export folder. Milliseconds alone collide when
    two artists render or export at the same moment, and one of them then gets
    the other's files; nine random digits keep ids unique and still all digits
    (see _EXPORT_ID).
    """
    import secrets
    return f"{prefix}_{int(time.time() * 1000)}{secrets.randbelow(10 ** 9):09d}"


def _svg_drawing(path):
    """
    svg2rlg on the file's bytes rather than its path. Given a path, svglib also
    draws other files the SVG links to (href="/some/other.svg"), so artwork
    could pull files from elsewhere on the server into a PDF; given the bytes
    it only follows links inside the SVG itself (and embedded data: images).
    """
    from svglib.svglib import svg2rlg
    return svg2rlg(io.BytesIO(Path(path).read_bytes()))


_SLOT_SHORT = {"side1": "side1", "side2": "side2", "bottom": "bottom"}


def _art_files(entries, prefix, serve_dir):
    """Copy each location's uploaded artwork (and its one-colour version) into art/."""
    import re as _re
    uploads = (HERE / "uploads").resolve()
    out = []
    for e in entries[:12]:
        slots = [_safe_prefix(str(x)) for x in (e.get("slots") or [])][:6]
        where = "all" if len(slots) >= 3 else "-".join(slots) or "art"
        pairs = [(e.get("path"), "")]
        if e.get("one_color"):
            pairs.append((e.get("one_color"), "-1color"))
        for raw, tag in pairs:
            try:
                p = Path(str(raw)).resolve()
            except Exception:
                continue
            if uploads not in p.parents or not p.is_file():
                continue
            # An EPS was converted to PDF on upload; ship the file they sent.
            if p.name.endswith(".from_eps.pdf") and not tag:
                eps = p.with_name(p.name[: -len(".from_eps.pdf")] + ".eps")
                if eps.exists():
                    p = eps
            # "<slot>_<token>_<their name>" -> "<their name>"
            m = _re.match(r"^[^_]+_[0-9a-f]{10}_(.+)$", p.name)
            theirs = m.group(1) if m else p.name
            stem, ext = Path(theirs).stem, p.suffix
            if tag:
                stem = _re.sub(r"\.1c-[0-9a-f]{8}$", "", Path(theirs).stem)
            dest = serve_dir / "art" / f"{prefix}-art-{where}-{stem}{tag}{ext}"
            dest.parent.mkdir(exist_ok=True)
            shutil.copy2(str(p), str(dest))
            out.append(("art", dest))
    return out


# ── Jobs inside proofs ────────────────────────────────────────────────────
#
# Every digital proof carries the job that made it as PDF attachments:
# numo-job.json (product, colours, ink, NSO, artist, revision, and each
# location's placement and one-colour edits) plus the artwork files. The proof
# stays one ordinary PDF; dropping it into the configurator rebuilds the job.

JOB_ATTACHMENT = "numo-job.json"


def _embed_job(proof_pdf, snapshot, art_entries):
    import pikepdf, mimetypes
    uploads = (HERE / "uploads").resolve()
    snap = json.loads(json.dumps(snapshot))            # a copy we can edit
    pdf = pikepdf.open(str(proof_pdf), allow_overwriting_input=True)
    arts, key_of = [], {}
    for i, e in enumerate(art_entries[:40]):
        rec = {"key": i, "slots": e.get("slots") or []}
        for kind, raw in (("orig", e.get("path")), ("one_color", e.get("one_color"))):
            if not raw:
                continue
            try:
                p = Path(str(raw)).resolve()
            except Exception:
                continue
            if uploads not in p.parents or not p.is_file():
                continue
            m = re.match(r"^[^_]+_[0-9a-f]{10}_(.+)$", p.name)
            name = f"art{i}-{kind}{p.suffix}"
            pdf.attachments[name] = pikepdf.AttachedFileSpec(
                pdf, p.read_bytes(), filename=name,
                mime_type=mimetypes.guess_type(p.name)[0] or "application/octet-stream",
                description=(m.group(1) if m else p.name))
            rec[kind] = name
            if kind == "orig":
                rec["name"] = m.group(1) if m else p.name
            key_of[str(raw)] = i
        arts.append(rec)
    for sid, sl in (snap.get("slots") or {}).items():
        src = sl.pop("art_path", None)
        if src is not None and str(src) in key_of:
            sl["art_key"] = key_of[str(src)]
    # Color variants and the order's other items (snapshot "variants" and
    # "order") point at their art the same way, so one proof can reopen them.
    def _nested(o):
        if isinstance(o, dict):
            if "art_path" in o and str(o.get("art_path")) in key_of:
                o["art_key"] = key_of[str(o["art_path"])]
            for v in o.values():
                _nested(v)
        elif isinstance(o, list):
            for v in o:
                _nested(v)
    _nested(snap.get("variants"))
    _nested(snap.get("order"))
    snap["art"] = arts
    pdf.attachments[JOB_ATTACHMENT] = pikepdf.AttachedFileSpec(
        pdf, json.dumps(snap, indent=1).encode(), filename=JOB_ATTACHMENT,
        mime_type="application/json", description="Numo configurator job")
    pdf.save(str(proof_pdf))


def _read_old_proof(pdf_path):
    """
    What an older proof (no job inside) still tells us, from its printed text:
    NSO, revision, artist, item, component colours, ink, and art sizes.
    """
    import subprocess
    txt = subprocess.run(["pdftotext", "-layout", "-l", "1", str(pdf_path), "-"],
                         capture_output=True, text=True, timeout=30).stdout
    if "DIGITAL PROOF" not in txt:
        return None
    fields, sizes = {}, {}
    in_sizes = False
    for line in txt.splitlines():
        m = re.match(r"^\s*(\S.*?)\s{2,}(\S.*?)\s*$", line)
        if not m:
            if line.strip().lower() == "art size":
                in_sizes = True
            continue
        k, v = m.group(1).strip(), m.group(2).strip()
        if in_sizes and k in ("Side 1", "Side 2", "Bottom"):
            mm = re.match(r'([\d.]+)"\s*W\s*x\s*([\d.]+)"\s*H', v)
            if mm:
                sizes[{"Side 1": "side1", "Side 2": "side2", "Bottom": "bottom"}[k]] = \
                    {"w_in": float(mm.group(1)), "h_in": float(mm.group(2))}
            continue
        if k == "Art Size":
            in_sizes = True
            continue
        if k in ("Info", "Artist Note", "Available Product Colors"):
            in_sizes = False
        fields.setdefault(k, v)
    nso = fields.get("NSO#") or ""
    rev = None
    mr = re.search(r"Rev\s+(\d+)", nso)
    if mr:
        rev = int(mr.group(1))
        nso = re.sub(r"\s*·?\s*Rev\s+\d+\s*$", "", nso).strip()
    known = {"NSO#", "Customer", "Artist", "Item#", "Description", "Imprint",
             "Quantity", "Art Size", "Info", "Artist Note"}
    components = {k: v for k, v in fields.items() if k not in known}
    ink = fields.get("Imprint") or ""
    return {"v": 0, "legacy": True,
            "pid": fields.get("Item#") or "",
            "nso": nso, "revision": rev,
            "artist": fields.get("Artist") if fields.get("Artist") not in (None, "—") else None,
            "components": components,          # e.g. {"Neoprene": "Red", "Stitching": "White"}
            "ink_name": ("PANTONE " + ink) if ink and not ink.upper().startswith("PANTONE") else ink,
            "sizes": sizes, "slots": {}, "art": []}


def _safe_prefix(raw):
    """The job's NSO number, reduced to something safe in a filename."""
    cleaned = "".join(ch if (ch.isalnum() or ch in "-_") else "_"
                      for ch in (raw or "").strip())
    return cleaned.strip("_")[:60]


def _zip_files(files, zip_path, prune=False):
    """
    Gather already-named files into one archive, flat, no folders.

    With prune, the originals go as soon as they are safely inside: an export
    is tens of megabytes of press sheets, and keeping a second copy of every
    one of them around until some later sweep is what fills the disk.
    """
    import zipfile
    zip_path = Path(zip_path)
    with zipfile.ZipFile(str(zip_path), "w", zipfile.ZIP_DEFLATED) as z:
        for f in files:
            # A (folder, path) pair files that one inside a folder in the
            # archive. The press sheets go in one so a dozen of them do not
            # bury the proof and the mockups at the top level.
            folder, f = f if isinstance(f, tuple) else (None, f)
            f = Path(f)
            if f.exists():
                z.write(str(f), arcname=f"{folder}/{f.name}" if folder else f.name)
    if prune:
        for f in files:
            f = Path(f[1] if isinstance(f, tuple) else f)
            if f != zip_path:
                try: f.unlink()
                except OSError: pass
    return zip_path


def _sweep_serve(max_age_s=3600):
    """
    Drop served exports once they are old enough that nobody is downloading
    them. The archive has to outlive the request that built it, so it cannot
    be deleted inline; this keeps the directory from growing without bound.
    """
    root = HERE / "_serve"
    if not root.is_dir():
        return
    cutoff = time.time() - max_age_s
    for d in root.iterdir():
        try:
            if d.is_dir() and d.stat().st_mtime < cutoff:
                shutil.rmtree(d, ignore_errors=True)
        except OSError:
            pass


_LAST_SWEEP = 0.0


def _sweep_uploads(max_age_s=86400):
    """
    Drop uploaded artwork once no export could still be referring to it.

    Every upload leaves the original plus its preview renders behind, and
    nothing ever removed them — a busy day quietly accumulated hundreds of
    megabytes. They cannot go at the end of a request, because the press
    imposition reads the saved vector back by path when the customer finally
    hits Export, which may be an hour of fiddling later.

    A day is far longer than any session and still bounds the directory.
    """
    global _LAST_SWEEP
    # Walking the whole uploads tree on every export gets expensive with many
    # people exporting at once; once every ten minutes per process is plenty.
    if time.time() - _LAST_SWEEP < 600:
        return
    _LAST_SWEEP = time.time()
    root = HERE / "uploads"
    if not root.is_dir():
        return
    cutoff = time.time() - max_age_s
    for f in root.rglob("*"):      # includes _onecolor/ working files
        try:
            if f.is_file() and f.stat().st_mtime < cutoff:
                f.unlink()
        except OSError:
            pass


# Which colour library each material is offered in. Keyed by the product's
# own `material`, which is the same key /api/colors publishes to the
# configurator — so the swatch row on the proof is the row the customer chose
# from, not a second list that can drift out of step with it.
def _material_palette(material):
    from engine import THREE_WAY_PEN, FABRIC_4CP
    table = {
        "neoprene": NEOPRENE,
        "scuba_foam": SCUBA_FOAM,
        "cotton_canvas": COTTON_CANVAS,
        "cotton_canvas_dyed": COTTON_CANVAS_DYED,
        "jotter": JOTTER,
        "three_way_pen": THREE_WAY_PEN,
        "le_pen": LE_PEN,
        "stick_pen": STICK_PEN,
        "expanded_vinyl": BANK_BAG_EV,
        "laminated_nylon": BANK_BAG_LN,
        "fabric_4cp": FABRIC_4CP,
    }.get(material or "")
    return [{"name": n, "hex": h} for n, h in (table or {}).items()]


# The ceiling, matching ORDER_QTY_MAX in the configurator. Above it a run is
# quoted rather than ordered through here.
ORDER_QTY_MAX = 1000


def _order_problems(order):
    """
    What is wrong with the order block, as plain sentences.

    The browser checks the same things at the point of entry, where they can
    be fixed; this exists because the browser is not the only thing that can
    post to this route, and an order should not be able to arrive half-filled without anyone saying so.

    The minimum is only enforced when the order carries one. It comes from the
    pricing sheet, which is shared with other tools and does not list every
    product — a missing minimum is a gap in that sheet, not a bad order.
    """
    out = []
    cust = (order.get("customer") or {})
    if not (cust.get("name") or "").strip():
        out.append("no customer name")
    email = (cust.get("email") or "").strip()
    if "@" not in email or "." not in email.split("@")[-1]:
        out.append("customer email looks wrong")
    qty, moq = order.get("quantity"), order.get("moq_at_order")
    if not isinstance(qty, int) or qty < 1:
        out.append("no quantity")
    elif qty > ORDER_QTY_MAX:
        out.append(f"quantity {qty} is over the {ORDER_QTY_MAX} ceiling")
    elif isinstance(moq, int) and qty < moq:
        out.append(f"quantity {qty} is under the {moq} minimum")
    return out


def _proof_order_fields(order):
    """Who the proof is for and how many, from the order block.

    On the proof because it is the document the customer approves, and an
    approval that does not say who approved it or for what quantity is not
    much of a record.
    """
    if not isinstance(order, dict):
        return {}
    qty = order.get("quantity")
    return {"customer": ((order.get("customer") or {}).get("name") or "").strip() or None,
            "quantity": qty if isinstance(qty, int) and qty > 0 else None}


def _artist_fields(raw):
    """
    The artist-mode block from the export: who built the proof, for which
    customer, which revision, and any note for the floor. Every value is
    trimmed and capped — it is typed into a browser and printed on a proof.
    """
    if not isinstance(raw, dict):
        return {}
    def clean(key, cap):
        v = raw.get(key)
        v = "" if v is None else str(v)
        v = " ".join(v.split())[:cap]
        return v or None
    rev = raw.get("revision")
    try:
        rev = int(rev)
    except (TypeError, ValueError):
        rev = None
    out = {"artist": clean("artist", 60),
           "artist_note": clean("note", 180),
           "revision": rev if rev and 0 < rev < 100 else None}
    cust = clean("customer", 80)
    if cust:
        out["customer"] = cust     # overrides the order block's customer
    return out


def _proof_extra(product_id):
    """
    The catalogue facts the proof shows that the press geometry knows nothing
    about: what the product is called, and every colour it can be had in.
    """
    p = PRODUCTS.get(product_id) or {}
    label = p.get("display_label") or p.get("label") or product_id
    # The catalogue label carries the item number — "Kolder Kaddy - 0070-3m-
    # 24HR-1c" — and the proof prints Item# on its own line a row above, so
    # the suffix would read twice.
    if label.lower().endswith(f" - {product_id}".lower()):
        label = label[: -len(f" - {product_id}")]
    return {"label": label,
            "product_colors": _material_palette(p.get("pen_colors") or p.get("material"))}


def _press_export_files(press_pdf, out_dir, prefix, product_id, info):
    """
    The press file, the customer proof and the flat 2X2 — three files.

    One file, deliberately. The production artist opens it, writes the NSO
    sales order number onto each sheet as they check it, and sends the whole
    thing to production — a job that is done once in one document, not
    reassembled from a folder of separate PDFs.

    Which sheet is which is carried ON the sheets instead of by artboard name.
    Illustrator keeps artboard names in its own private copy of the document,
    which this export strips from every page — stripping it is what makes the
    imposed artwork visible in Illustrator at all — and nothing in the PDF
    format carries an artboard name in its place. So the name is printed into
    the sheet's own job slug, beside the NSO number the artist is about to
    fill in, where it cannot be lost by any conversion.

    Returns the list of files to go in the export.
    """
    import press_layout

    # One file per press sheet, named for its artboard.
    #
    # This is the press room's mass export, done here instead of there.
    # Opening a multi-artboard master in Illustrator and exporting artboards
    # gets you "Artboard 1..N", because the names Illustrator would have used
    # live in its private copy of the document — which this export strips from
    # every page, since stripping it is what makes the imposed artwork visible
    # in the first place. Writing the files here skips that round trip and
    # names them correctly the first time: STRYKER, JAVELIN AUTO, DISCO, DBC.
    #
    # The master is not shipped alongside them. It held the same sheets twice
    # over at a couple of megabytes a copy, and the reason it used to be one
    # document — so the artist could write the sales order number onto each
    # sheet as they checked it — is gone now that the number is printed on.
    sheets = press_layout.split_sheets(press_pdf, out_dir, prefix,
                                       info.get("page_names") or [])
    files = list(sheets) if sheets else [Path(press_pdf)]

    # The customer proof, as its own document. The press files are nothing but
    # screens now — one per sheet, ready to go straight to the floor.
    proof = info.get("proof")
    if proof and Path(proof).exists():
        files.append(Path(proof))

    # The flat 2X2 comes out of the build, which cuts it from the vendor guide
    # page before discarding that page. It cannot be re-rendered from either
    # finished file: the guide's die shapes are in neither of them.
    flat = info.get("flat_proof")
    if flat and Path(flat).exists():
        dest = Path(out_dir) / f"{prefix}-2X2.png"
        if Path(flat) != dest:
            shutil.move(str(flat), str(dest))
        files.append(dest)

    return files


class _SandboxSkip(Exception):
    """A step the sandbox leaves out."""


class PressBuildError(Exception):
    """Press file could not be built; carries the message shown to the user."""
    def __init__(self, message, code=None, status=400):
        super().__init__(message)
        self.code = code
        self.status = status


def _press_inks(raw, check=True, limit=None):
    """The inks of a multi-colour job, checked: at most MAX_SPOT_INKS (5)
    screens, or the product's own limit (the metallic 3l: 3)."""
    limit = limit or MAX_SPOT_INKS_DEFAULT
    if not raw:
        return None
    inks = []
    for i in raw[:12]:
        if not isinstance(i, dict):
            continue
        inks.append({"hex": str(i.get("hex") or ""),
                     "sources": [str(x) for x in (i.get("sources") or [])][:12],
                     "pms": (str(i["pms"])[:60] if i.get("pms") else None),
                     "pms_hex": str(i.get("pms_hex") or i.get("hex") or ""),
                     "hidden": bool(i.get("hidden"))})
    screens = {i["pms"] or i["hex"] for i in inks if not i["hidden"]}
    if check and len(screens) > limit:
        raise PressBuildError(f"This artwork needs {len(screens)} screens; the most is "
                              f"{limit}.", "too_many_inks")
    return inks or None


def _job_inks(body, slots):
    """
    The inks for the press build: one list for the whole job, or {slot: list}
    when the configurator sent each location's own colors. The screen limit is
    for the job — every location shares the same press sheets.
    """
    limit = _max_inks_for(body.get("product_id") or "")
    by_slot = body.get("inks_by_slot")
    if not by_slot:
        return _press_inks(body.get("inks"), limit=limit)
    out = {}
    for sl in slots:
        raw = by_slot.get(sl)
        if raw:
            out[sl] = _press_inks(raw, check=False)
    screens = {i["pms"] or i["hex"] for v in out.values() for i in v if not i["hidden"]}
    if len(screens) > limit:
        raise PressBuildError(f"This job needs {len(screens)} screens across its "
                              f"locations; the most is {limit}.",
                              "too_many_inks")
    return out or None


def _file_digest(path):
    import hashlib
    try:
        with open(path, "rb") as fh:
            return hashlib.sha1(fh.read()).hexdigest()
    except OSError:
        return None


def _sides_mode(body, slots):
    """
    "1side", "2same" or "2diff" for the sides this job prints.

    Same means the same file at the same size, position and rotation on both
    sides. Anything else — a different file, or the same file placed
    differently — is two different screens.
    """
    has1, has2 = "side1" in slots, "side2" in slots
    if not (has1 and has2):
        return "1side" if (has1 or has2) else None
    # The configurator asks: same art on both sides, or different. When it
    # says, that is the answer.
    picked = body.get("sides")
    if picked in ("2same", "2diff"):
        return picked
    paths = body.get("art_paths") or {}
    a = paths.get("side1") or body.get("art_path")
    b = paths.get("side2") or body.get("art_path")
    if not a or not b:
        return "2diff"
    # The same file uploaded to each side separately is saved twice under
    # different names, so compare what is in the files, not what they're called.
    if a != b and (_file_digest(a) is None or _file_digest(a) != _file_digest(b)):
        return "2diff"
    pl = body.get("placement") or {}
    p1, p2 = pl.get("side1") or {}, pl.get("side2") or {}
    for k, default, tol in (("sc", 1, 0.005), ("ox", 0, 0.002), ("oy", 0, 0.002), ("rot", 0, 0.5)):
        if abs(float(p1.get(k, default) or default) - float(p2.get(k, default) or default)) > tol:
            return "2diff"
    return "2same"


def _build_press_files(body, prefix, out_dir, mockup_img=None, order=None,
                       artist=None):
    """
    Impose a This Is Fast job onto its press template and split the result.

    The proof page is chosen from the imprint locations actually used, printed
    in the selected PMS; the press sheets are imposed in registration black.
    Only products with a measured template can produce one.

    Returns the list of per-page files, ready to be zipped.
    """
    import press_layout

    pid = body.get("product_id") or ""
    if not press_layout.has_press_template(pid):
        raise PressBuildError(f"No press template is set up for {pid}.",
                              "no_template", 404)

    slots = [s for s in body.get("slots") or [] if s in press_layout.ALL_SLOTS]
    if not slots:
        raise PressBuildError("No artwork to impose.", "no_artwork")

    # One artwork per location. `art_paths` is {slot: path}; the older single
    # `art_path` is still honoured and means "the same art everywhere".
    # Only files in uploads/ are used: these paths come from the browser.
    raw_paths = body.get("art_paths") or {}
    art_paths = {sl: str(_in_uploads(v) or "")          # refused = missing, so the message names it
                 for sl, v in (raw_paths.items() if isinstance(raw_paths, dict) else [])}
    body["art_paths"] = art_paths
    if body.get("art_path"):
        body["art_path"] = str(_in_uploads(body["art_path"]) or "") or None
    if art_paths:
        missing = [sl for sl in slots
                   if not art_paths.get(sl) or not os.path.exists(art_paths[sl])]
        if missing:
            raise PressBuildError(
                "The uploaded artwork for " + ", ".join(missing)
                + " could not be found on the server.", "art_missing")
        vec = {}
        art = {}
        by_slot = body.get("inks_by_slot") or {}
        bg_by_slot = body.get("bg_by_slot") or {}
        for sl in slots:
            src = art_paths[sl]
            key = (src, json.dumps(by_slot.get(sl), sort_keys=True), bg_by_slot.get(sl))
            if key not in vec:
                vec[key] = _as_vector(src, body, out_dir, inks=by_slot.get(sl),
                                      bg_hex=bg_by_slot.get(sl))
            art[sl] = vec[key]
    else:
        art = body.get("art_path")
        if not art or not os.path.exists(art):
            raise PressBuildError(
                "The uploaded artwork could not be found on the server.",
                "art_missing")
        art = _as_vector(art, body, out_dir)

    # No stand-in. This goes onto every screen in place of the vendor's "NSO
    # NUMBER" placeholder, and a job with no number should leave that
    # placeholder showing for the artist to fill in — not print the word
    # "ORDER" on a press sheet as though it were one.
    order_id = (body.get("order_id") or "").strip() or None
    out = Path(out_dir) / f"{prefix}-press.pdf"

    try:
        info = press_layout.build_for_job(
            pid, art, slots,
            body.get("pms_name") or "", body.get("pms_hex") or "",
            str(out), order_id=order_id, item=screenprint_sku(pid),
            components=body.get("components") or [],
            # The same two things the print PDF has always been told, and the
            # press file was not: which inks the customer switched off, and
            # how big and where they put the mark. Without them the press file
            # carries every original colour flattened into one, at full zone
            # size — a preview and a press sheet that disagree.
            hidden_colors=body.get("hidden_colors") or [],
            placement=body.get("placement") or {},
            accepted_risks=body.get("accepted_risks") or [],
            # Page one is a customer proof, so it carries the product by name
            # and in every colour it comes in, with the customer's own render
            # in the corner instead of a stock photo of a blank one.
            proof_extra=dict(_proof_extra(pid), **_proof_order_fields(order),
                             **_artist_fields(artist)),
            mockup_img=str(mockup_img) if mockup_img else None,
            proof_path=str(Path(out_dir) / f"{prefix}-digitalproof.pdf"),
            sides=_sides_mode(body, slots),
            inks=_job_inks(body, slots),
            # Colourways sharing one set of screens (same art, same place,
            # only the PMS changes): the first builds the sheets with every
            # colourway's PMS on each screen's caption; the rest send
            # sheets_shared and get their proof only.
            include_press_sheets=not body.get("sheets_shared"),
            caption_names=body.get("caption_names") or None)
    except Exception as e:
        raise PressBuildError(str(e), "build_failed", 500)
    if info and info.get("sheet_note"):
        body["_sheet_note"] = info["sheet_note"]
    # The proof carries the job inside it, so dropping it back into the
    # configurator rebuilds the job for a revision.
    if info and info.get("proof") and body.get("_snapshot"):
        try:
            _embed_job(info["proof"], body["_snapshot"], body.get("_art_files") or [])
            body["_job_saved"] = "ok"
        except Exception as e:
            import traceback; traceback.print_exc()
            print(f"⚠️ job could not be embedded in the proof: {e}")
            body["_job_saved"] = f"error: {e}"[:200]
    elif info and info.get("proof"):
        body["_job_saved"] = "error: the page sent no job — reload the configurator (it may be an old copy)"
    if not info:
        raise PressBuildError(f"No press template is set up for {pid}.",
                              "no_template", 404)

    traced = []
    for p_ in sorted({str(v) for v in (art.values() if isinstance(art, dict) else [art])}):
        if p_.endswith(".traced.pdf") and Path(p_).exists():
            where = "-".join(sl for sl, v in (art.items() if isinstance(art, dict) else [])
                             if str(v) == p_) or "art"
            if isinstance(art, dict) and len([1 for v in art.values() if str(v) == p_]) >= 3:
                where = "all"
            dest = Path(out_dir) / "art" / f"{prefix}-art-{where}-traced.pdf"
            dest.parent.mkdir(exist_ok=True)
            shutil.copy2(p_, dest)
            traced.append(("art", dest))
    try:
        return _press_export_files(out, Path(out_dir), prefix, pid, info) + traced
    except Exception as e:
        # The press file itself is built and usable; only the flat proof can
        # fail here, and that is not worth losing the imposition over.
        print(f"⚠️ Could not assemble the press export: {e}")
        return [out]


@app.route("/api/press-file", methods=["POST"])
def press_file():
    """The press files on their own, as a zip. Kept for direct/diagnostic use;
    the configurator's Export goes through /api/export-bundle."""
    if SANDBOX:
        return jsonify({"error": "Press files are not available in the sandbox."}), 404
    body = request.get_json(force=True) or {}

    prefix = _safe_prefix(body.get("prefix") or body.get("export_prefix") or "")
    if not prefix:
        return jsonify({"error": "Enter the NSO number before exporting.",
                        "code": "prefix_required"}), 400

    serve_dir = HERE / "_serve" / _unique_id("press")
    serve_dir.mkdir(parents=True, exist_ok=True)
    try:
        files = _build_press_files(body, prefix, serve_dir)
    except PressBuildError as e:
        return jsonify({"error": str(e), "code": e.code}), e.status

    zip_path = _zip_files(files, serve_dir / f"{prefix}.zip")
    return send_file(str(zip_path), as_attachment=True,
                     download_name=zip_path.name, mimetype="application/zip")


# ---------------------------------------------------------------------------
# Route — export bundle: everything the job produces, in one archive
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Digital proof for items without press sheets (4CP, pens, totes)
# ---------------------------------------------------------------------------
def _render_art_piece(entry, k, work):
    """One placed artwork as an RGBA image at k px per point, as it prints."""
    import subprocess, pikepdf
    W, H = max(1, int(round(entry["w"] * k))), max(1, int(round(entry["h"] * k)))
    f = entry.get("file")
    if not f or not Path(f).exists():
        return None
    if entry.get("clip"):
        x1, y1, x2, y2 = [float(v) for v in entry["clip"]]
        with pikepdf.open(f) as pdf:
            mb = [float(v) for v in pdf.pages[0].mediabox]
        ph = mb[3] - mb[1]
        up = max(1.0, 900.0 / max(W, H))          # render big, then scale down: small art stays sharp
        res = 72.0 * W * up / max(1e-6, x2 - x1)
        out = work / f"a{abs(hash(f)) % 10**8}"
        subprocess.run(["pdftocairo", "-png", "-transp", "-singlefile", "-r", f"{res:.3f}",
                        "-x", str(int((x1 - mb[0]) * res / 72)), "-y", str(int((ph - (y2 - mb[1])) * res / 72)),
                        "-W", str(int(W * up)), "-H", str(int(H * up)), f, str(out)], check=True)
        im = Image.open(f"{out}.png").convert("RGBA")
    else:
        im = Image.open(f).convert("RGBA")
    im = im.resize((W, H), Image.LANCZOS)
    if entry.get("rot"):
        import math
        im = im.rotate(-math.degrees(entry["rot"]), expand=True, resample=Image.BICUBIC)
    return im


def _ink_slug(ink):
    """WHITE, BLACK, PMS186C: the ink as it goes in a file name."""
    nm = str((ink or {}).get("name") or "").strip()
    if re.fullmatch(r"(?i)(pantone\s+)?black(\s+c)?", nm):
        return "BLACK"
    nm = re.sub(r"(?i)^pantone\s+", "PMS ", nm)
    return re.sub(r"[^A-Za-z0-9]+", "", nm.upper()) or "INK"


def _ink_groups(variants):
    """[(ink or None, [pen colour names])] in order: one Mimaki file each. No
    variants, or every colour keeping the art's own colours, is one group."""
    groups = []
    for v in variants or []:
        ink = v.get("ink") if isinstance(v.get("ink"), dict) and v["ink"].get("hex") else None
        cmap = [m for m in (v.get("map") or []) if isinstance(m, dict) and m.get("from") and m.get("hex")]
        if cmap:
            # Custom PMS colors: its own file, named for the pen color.
            ink = {"map": cmap, "name": "CUSTOM " + str(v.get("name") or "")}
            key = "MAP:" + json.dumps(sorted((m["from"].upper(), m["hex"].upper()) for m in cmap))
        else:
            key = _ink_slug(ink) if ink else None
        for g in groups:
            if g[2] == key:
                g[1].append(v.get("name") or "")
                break
        else:
            groups.append([ink, [v.get("name") or ""], key])
    return [(g[0], g[1]) for g in groups] or [(None, [])]


def _mimaki_jig_files(print_pdf, product, slot_ids, prefix, out_dir, hand="RH", variants=None):
    """
    The pen's production files: each imprint stamped into every box of the
    Mimaki jig, one file per side — PREFIX-SIDE1.pdf, PREFIX-SIDE2.pdf (PDF for RasterLink).

    Side 1 and Side 2 are the pen's two faces. The pens sit in the jig all the
    same way round, so one side's art goes on upside down: for an RH imprint
    (the standard) Side 1 is turned 180 deg in every box, for an LH imprint
    Side 2 is (spec "turn"). Each copy turns about its own box's centre.

    The print file holds each side's imprint box exactly as the customer
    placed the art in it. Here that box is cut out (clipped to the box, so
    nothing outside the imprint area prints) and repeated at each of the jig's
    boxes on the jig's own artboard. Nothing else goes on the page: no pen
    outlines, no boxes, no guides. The one exception is the jig's tiny
    "leave ON" square in the corner, which holds the artboard's size on the RIP.
    Both sides use the same jig; the file name says which side it is.

    The artboard is held at both ends: the jig's "leave ON" square sits in the
    bottom-right corner, and a matching one goes in the top-left. Illustrator
    sizes the artboard of an EPS it didn't write to the artwork's extent; with
    only the bottom-right square, the artboard came out short at the top-left
    and the art landed off position on the RIP.
    """
    from pdfrw import PdfReader
    from pdfrw.buildxobj import pagexobj
    from pdfrw.toreportlab import makerl
    from reportlab.pdfgen import canvas as _cv
    from reportlab.lib.colors import CMYKColor
    spec = json.loads((HERE / product["mimaki_jig"]).read_text())
    aw, ah = spec["artboard"]
    bw, bh = spec["box"]
    page = PdfReader(str(print_pdf)).pages[0]
    page_h = float(page.MediaBox[3]) - float(page.MediaBox[1])
    out, notes = [], []
    groups = _ink_groups(variants)
    hand = "LH" if str(hand or "").upper() == "LH" else "RH"
    turns = (spec.get("turn") or {}).get(hand) or {}
    # A file per side. On the jotter a side is one imprint; on the 3-way pen
    # (0845) a side is two — the barrel and the clip, each with its own boxes
    # in the jig ("box_sets" / "slot_box") — and both go in that side's file.
    by_tag = {}
    for sl in product.get("art_slots") or []:
        if sl["id"] not in slot_ids:
            continue
        tag = (spec.get("files") or {}).get(sl["id"]) or sl["id"].upper()
        turn = int(turns.get(sl["id"]) or 0) % 360
        sx, sy = float(sl["left_pt"]), page_h + float(sl["top_pt"]) - float(sl["h_pt"])
        bs = (spec.get("box_sets") or {}).get((spec.get("slot_box") or {}).get(sl["id"]) or "")
        boxes, box = (bs["boxes"], bs["box"]) if bs else (spec["boxes"], spec["box"])
        by_tag.setdefault(tag, []).append((sl, turn, sx, sy, boxes, box))
    for tag, parts in by_tag.items():
        for ink, colours in groups:
            out_path, note = _mimaki_one(print_pdf, product, spec, parts, tag, prefix,
                                         out_dir, ink, colours, len(groups) > 1)
            notes.extend(note)
            if out_path:
                out.append(out_path)
    return out, notes


def _jig_eps(pdf, eps, aw, ah):
    """The jig PDF as an EPS whose bounding box is exactly the artboard."""
    import subprocess
    subprocess.run(["gs", "-q", "-dSAFER", "-dNOPAUSE", "-dBATCH", "-sDEVICE=eps2write",
                    "-dNoOutputFonts", "-dLanguageLevel=3", f"-sOutputFile={eps}", str(pdf)],
                   check=True, capture_output=True, timeout=180)
    data = Path(eps).read_bytes()
    head, sep, rest = data.partition(b"%%EndComments")
    if not sep:
        raise RuntimeError("eps2write wrote no DSC header")
    lines = [l for l in head.split(b"\n") if not l.startswith((b"%%BoundingBox", b"%%HiResBoundingBox",
                                                                b"%%CropBox"))]
    box = (f"%%BoundingBox: 0 0 {int(-(-aw // 1))} {int(-(-ah // 1))}\n"
           f"%%HiResBoundingBox: 0 0 {aw:.4f} {ah:.4f}\n"
           f"%%CropBox: 0 0 {aw:.4f} {ah:.4f}\n").encode()
    lines.insert(1, box.rstrip(b"\n"))
    Path(eps).write_bytes(b"\n".join(lines) + sep + rest)


def _mimaki_one(print_pdf, product, spec, parts, tag, prefix, out_dir, ink, colours, split):
        """One Mimaki file: one side, one ink (None = the art's own colours).
        parts: [(slot, turn, sx, sy, boxes, (bw, bh))] — every imprint of
        that side, each stamped into its own boxes."""
        from pdfrw import PdfReader
        from pdfrw.buildxobj import pagexobj
        from pdfrw.toreportlab import makerl
        from reportlab.pdfgen import canvas as _cv
        from reportlab.lib.colors import CMYKColor
        aw, ah = spec["artboard"]
        bw, bh = spec["box"]
        notes = []
        src_pdf = print_pdf
        cmap = (ink or {}).get("map")
        if cmap:
            # The art's colours, each painted in the PMS this pen colour takes.
            import onecolor
            src_pdf = Path(out_dir) / f"{prefix}-{tag}-{_ink_slug(ink)}.recolor.pdf"
            onecolor.separate(str(print_pdf),
                              [{"hex": m["from"], "sources": [m["from"]], "pms": m.get("name"),
                                "pms_hex": m["hex"]} for m in cmap],
                              str(src_pdf), mode="proof", knockout_white=False)
        xobj = pagexobj(PdfReader(str(src_pdf)).pages[0])
        if cmap:
            ink = None                          # from here on: art in its (new) own colours
        WHITE_MARK = (0.0, 0.9961, 0.0)          # stand-in for white ink, made WHITE below
        white_ink = False
        if ink:
            hx = str(ink.get("hex") or "#000000").lstrip("#")
            rgb = tuple(int(hx[i:i + 2], 16) / 255.0 for i in (0, 2, 4))
            white_ink = min(rgb) >= 0.96 or str(ink.get("name") or "").strip().lower() == "white"
            from screenprint import paint_ink_and_knockouts
            if not paint_ink_and_knockouts(xobj, WHITE_MARK if white_ink else rgb, (1.0, 1.0, 1.0)):
                notes.append(f"{tag}: the art could not be recolored to {ink.get('name')}")
        # Named for the pen body colour(s) this file prints on: …-OLIVE, …-NAVY+KIWI.
        suffix = ("--" + "+".join(re.sub(r"[^A-Za-z0-9]+", "", str(c).upper()) for c in colours if c)) \
            if split and any(colours) else ""
        path = Path(out_dir) / f"{prefix}-{tag}{suffix}.pdf"
        c = _cv.Canvas(str(path), pagesize=(aw, ah))
        c.setTitle(f"{prefix}-{tag}  {product.get('label', '')}  Mimaki jig")
        form = makerl(c, xobj)
        for sl, turn, sx, sy, boxes, (bw, bh) in parts:
            # The slot's imprint centred in the jig box (they match on the
            # jotter; the pen's boxes are a hair larger than its imprints).
            dx, dy = (bw - float(sl["w_pt"])) / 2.0, (bh - float(sl["h_pt"])) / 2.0
            for bx, by in boxes:
                c.saveState()
                clip = c.beginPath(); clip.rect(bx, by, bw, bh)
                c.clipPath(clip, stroke=0, fill=0)
                if turn == 180:
                    c.translate(bx + bw - dx, by + bh - dy)    # turn about the box's centre
                    c.rotate(180)
                    c.translate(-sx, -sy)
                else:
                    c.translate(bx + dx - sx, by + dy - sy)
                c.doForm(form)
                c.restoreState()
        a = spec.get("anchor")
        if a:
            c.setFillColor(CMYKColor(0, 0, 0, 1))
            c.rect(a["x"], a["y"], a["w"], a["h"], stroke=0, fill=1)
            # Its twin in the opposite corner, so the artboard is held on both ends.
            c.rect(aw - a["x"] - a["w"], ah - a["y"] - a["h"], a["w"], a["h"], stroke=0, fill=1)
        c.showPage(); c.save()
        # Anything that prints white goes on the spot named WHITE, which is
        # the only white the Mimaki prints.
        # A recolor to one ink: real whites are knockouts and stay unprinted;
        # for a white ink only the stand-in colour becomes WHITE. A recolor
        # to a coloured ink has no white to set.
        try:
            import whitespot
            ws = whitespot.convert(path, marker=WHITE_MARK) if white_ink else \
                ({"images": 0} if ink else whitespot.convert(path))
            if ws["images"]:
                notes.append(f"{tag}: {ws['images']} image(s) in the art - white inside a "
                             "picture can't be the WHITE spot; use vector art for white")
        except Exception as e:
            import traceback; traceback.print_exc()
            notes.append(f"{tag}: white could not be set to the WHITE spot ({e})")
        # Shipped as PDF, straight into RasterLink. An EPS not written by
        # Illustrator opens in Illustrator on a made-up artboard (it trusts
        # only its own private data, whatever the %%BoundingBox says); a PDF's
        # page is its artboard everywhere. Every page box is the jig's
        # artboard, so nothing can crop or re-centre it.
        try:
            import pikepdf
            with pikepdf.open(str(path), allow_overwriting_input=True) as pdf:
                pg = pdf.pages[0]
                box = pikepdf.Array([0, 0, aw, ah])
                for k in ("/MediaBox", "/CropBox", "/TrimBox", "/ArtBox", "/BleedBox"):
                    pg.obj[k] = box
                pdf.save(str(path))
        except Exception as e:
            print(f"⚠️ jig page boxes not set: {e}")
        if cmap:
            Path(src_pdf).unlink(missing_ok=True)
        return path, notes



def _cap_fit(scale, w, h, slot_w, slot_h, rot=0.0, circle=False):
    """Never larger than the imprint area: the art's box (turned by the
    customer's rotation, radians) is held inside the slot. The browser
    already stops there; this is the backstop for anything that reaches the
    server above it (a job reopened from an older proof, art whose bounds
    changed after it was sized). Circles are sized by the browser's own fit."""
    import math
    if circle or not (w > 0 and h > 0 and slot_w > 0 and slot_h > 0):
        return scale
    try:
        a = float(rot or 0.0)
    except (TypeError, ValueError):
        a = 0.0
    c, n = abs(math.cos(a)), abs(math.sin(a))
    bw, bh = w * c + h * n, w * n + h * c
    return min(scale, slot_w / bw, slot_h / bh)

def _pen_art_one_ink(art, ink_hex):
    """The art as one ink: coloured pixels take the ink; white inside art that
    has colour is a knockout (dropped); art that is only white is all ink."""
    import numpy as np
    a = np.asarray(art.convert("RGBA")).copy()
    op = a[..., 3] > 8
    white = op & (a[..., :3].min(axis=2) > 235)
    colour = op & ~white
    ink = [int(ink_hex.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4)]
    if colour.any():
        a[white, 3] = 0
        a[colour, :3] = ink
    else:
        a[op, :3] = ink
    return Image.fromarray(a, "RGBA")


def _pen_variants_flat(product, entries, variants, hand, out_png):
    """The proof / 2X2 lay for one design on several pen colours: a row per
    colour, its sides side by side, each labelled with the colour and ink."""
    import tempfile
    from PIL import ImageDraw, ImageFont
    work = Path(tempfile.mkdtemp(prefix="penv_"))
    try:
        outline = json.loads((HERE / product["mimaki_jig"]).read_text()).get("pen_outline")
        by_id = {e.get("id"): e for e in entries if e.get("id")}
        slots = [sl for sl in (product.get("art_slots") or []) if by_id.get(sl["id"], {}).get("file")]
        if not outline or not slots:
            return None
        span = sum(sl["w_pt"] * 1.12 for sl in slots) or 500.0
        k = max(1.0, min(4.0, 1600.0 / span))
        rows = []
        for v in variants:
            ink = v.get("ink") if isinstance(v.get("ink"), dict) and v["ink"].get("hex") else None
            cells = []
            for sl in slots:
                e = dict(by_id[sl["id"]])
                im = _pen_panel(e, sl, outline, v.get("hex"), k, work, hand=hand,
                                ink_hex=ink.get("hex") if ink else None, cmap=v.get("map"),
                                writing_hex=(v.get("writing") or {}).get("hex") if isinstance(v.get("writing"), dict) else None)
                cells.append((sl.get("label") or sl["id"], im))
            cm = [m for m in (v.get("map") or []) if isinstance(m, dict)]
            label = f"{v.get('name') or ''} · " + (
                " + ".join(str(m.get("name") or "").replace("PANTONE ", "") for m in cm) if cm else
                f"{str(ink.get('name')).replace('PANTONE ', '')} ink" if ink else
                " + ".join(str(x).replace("PANTONE ", "") for x in (v.get("pms") or [])) or "as supplied")
            wr = v.get("writing") if isinstance(v.get("writing"), dict) else None
            if wr and wr.get("name"):
                label += f"  ·  ink: {wr['name']}"
            rows.append((label, cells))
        cw = max(im.width for _, cells in rows for _, im in cells)
        ch = max(im.height for _, cells in rows for _, im in cells)
        gap = int(cw * 0.06)
        ncol = len(slots)
        W = gap + ncol * (cw + gap)
        try:
            font = ImageFont.truetype(str(HERE / "static" / "fonts" / "Inter-Regular.ttf"), max(16, int(W / 70)))
            bold = ImageFont.truetype(str(HERE / "static" / "fonts" / "Inter-Bold.ttf"), max(18, int(W / 60)))
        except Exception:
            font = bold = ImageFont.load_default()
        lh = int(getattr(bold, "size", 18) * 1.6)
        sh = int(getattr(font, "size", 16) * 1.5)
        H = gap + len(rows) * (lh + ch + sh + gap)
        out = Image.new("RGB", (W, H), (255, 255, 255))
        d = ImageDraw.Draw(out)
        y = gap
        for label, cells in rows:
            d.text((gap, y), label, fill=(40, 40, 40), font=bold)
            y += lh
            x = gap
            for side, im in cells:
                out.paste(im, (x + (cw - im.width) // 2, y + (ch - im.height) // 2), im)
                tw = d.textlength(side, font=font)
                d.text((x + (cw - tw) / 2, y + ch + 4), side, fill=(110, 110, 110), font=font)
                x += cw + gap
            y += ch + sh + gap
        out.save(out_png)
        return str(out_png)
    finally:
        shutil.rmtree(work, ignore_errors=True)


def _pen_art_mapped(art, cmap):
    """The art with each of its colours painted in the PMS mapped to it
    (nearest source colour per pixel, so antialiased edges follow)."""
    import numpy as np
    srcs, dsts = [], []
    for m in cmap or []:
        try:
            f = str(m["from"]).lstrip("#"); t = str(m["hex"]).lstrip("#")
            srcs.append([int(f[i:i + 2], 16) for i in (0, 2, 4)])
            dsts.append([int(t[i:i + 2], 16) for i in (0, 2, 4)])
        except Exception:
            continue
    if not srcs:
        return art
    a = np.asarray(art.convert("RGBA")).copy()
    op = a[..., 3] > 0
    px = a[..., :3][op].astype(np.int32)
    d = ((px[:, None, :] - np.array(srcs)[None, :, :]) ** 2).sum(axis=2)
    a[..., :3][op] = np.array(dsts, dtype=np.uint8)[d.argmin(axis=1)]
    return Image.fromarray(a, "RGBA")


def _pen_panel(e, sl, outline, body_hex, k, work, hand="RH", ink_hex=None, cmap=None, writing_hex=None):
    """One side of a pen for the proof: the jig's pen silhouette in the body
    color, the art where it sits in the imprint box, clipped to the box.

    The jig file carries the pen twice, clip down and clip up; one pen is
    drawn, clip up, as the virtual shows it. Side 2 is the jig's own way
    round (tip right), Side 1 is the pen turned end for end (tip left), the
    art reading the same way on both. An LH imprint is the same pen turned
    180 deg with the art kept upright: the motif reads the other way from the
    clip."""
    from PIL import ImageDraw
    if outline and len(outline) > 1:
        outline = [max(outline, key=lambda sub: max(p[1] for p in sub))]     # clip up
    flip = sl.get("id") == "side1"
    lh = str(hand or "").upper() == "LH"
    pts = [p for sub in outline for p in sub]
    x0 = min(p[0] for p in pts); x1 = max(p[0] for p in pts)
    y0 = min(p[1] for p in pts); y1 = max(p[1] for p in pts)
    m = 4.0
    W, H = int((x1 - x0 + 2 * m) * k), int((y1 - y0 + 2 * m) * k)
    im = Image.new("RGBA", (W, H), (255, 255, 255, 0))
    d = ImageDraw.Draw(im)
    body = body_hex if re.fullmatch(r"#[0-9A-Fa-f]{6}", str(body_hex or "")) else "#FFFFFF"
    def P(x, y):   # outline coords are points from the box's bottom-left, y up
        if flip:
            x = x0 + x1 - x
        return ((x - x0 + m) * k, (y1 - y + m) * k)
    for sub in outline:
        d.polygon([P(*p) for p in sub], fill=body, outline=(150, 150, 150))
    art = _render_art_piece(e, k, work) if (e or {}).get("file") else None
    if art is not None:
        if cmap:
            art = _pen_art_mapped(art, cmap)
        elif ink_hex and re.fullmatch(r"#[0-9A-Fa-f]{6}", str(ink_hex)):
            art = _pen_art_one_ink(art, ink_hex)
        box = Image.new("RGBA", (int(sl["w_pt"] * k), int(sl["h_pt"] * k)), (0, 0, 0, 0))
        cx = int((e["x"] + e["w"] / 2) * k - art.width / 2)
        cy = int((e["y"] + e["h"] / 2) * k - art.height / 2)
        if lh:
            art = art.rotate(180)
        box.paste(art, (cx, cy), art)
        # The imprint box's top-left corner on the drawn pen (turned with it).
        bx, by = P(sl["w_pt"] if flip else 0, sl["h_pt"])
        im.alpha_composite(box, (int(bx), int(by)))
    if writing_hex and re.fullmatch(r"#[0-9A-Fa-f]{6}", str(writing_hex)):
        im = _pen_squiggle(im, outline, P, k, writing_hex, flip)
    if lh:
        im = im.rotate(180)
    return im


def _pen_squiggle(im, outline, P, k, hex_, flip):
    """The written line coming off the pen's tip, as the virtual shows it,
    in the pen's writing ink."""
    import math
    from PIL import ImageDraw
    pts = [p for sub in outline for p in sub]
    tip = max(pts, key=lambda p: p[0])                 # the jig's pen points right
    tx, ty = P(*tip)
    L, A = 62.0 * k, 6.5 * k                            # length and swing, in points
    side = -1 if flip else 1                            # Side 1 is drawn turned end for end
    grow = int(L + 4 * k)
    big = Image.new("RGBA", (im.width + grow, im.height), (255, 255, 255, 0))
    big.alpha_composite(im, (grow if side < 0 else 0, 0))
    ox = grow if side < 0 else 0
    d = ImageDraw.Draw(big)
    line = []
    for n in range(121):
        t = n / 120.0
        x = tx + ox + side * (t * L + 1.5 * k)
        amp = A * min(1.0, t * 3.0)                    # starts at the nib, then swings
        y = ty + amp * math.sin(t * math.pi * 5.0)
        line.append((x, y))
    h = hex_.lstrip("#")
    d.line(line, fill=tuple(int(h[i:i + 2], 16) for i in (0, 2, 4)) + (255,), width=max(2, int(1.3 * k)),
           joint="curve")
    return big


# Panels of a 4CP flat lay that are the print file cropped (see _flat_from_print),
# keyed by the panel image, while one lay is being built.
_VEC_PANELS = {}


def _vec_sidecar(out_png, print_pdf, size, placed):
    """Beside a flat-lay PNG: which print-file region each panel shows and where
    it sits in the PNG, for press_layout to draw the vector over the picture."""
    p = Path(f"{out_png}.vec.json")
    if placed:
        p.write_text(json.dumps({"pdf": str(print_pdf), "png": list(size), "panels": placed}))
    elif p.exists():
        p.unlink()


def _flat_2x2(panels, out_png, size=1600, print_pdf=None):
    """
    The 2X2: sides side by side across the top, the bottom disc centered below,
    captioned, on a white square. The same arrangement the screen-print 2X2 is
    cut into, at one scale for every piece so they keep their true sizes.
    """
    from PIL import ImageDraw, ImageFont
    rects = [p for p in panels if p[2] != "circle"]
    circles = [p for p in panels if p[2] == "circle"]
    out = Image.new("RGB", (size, size), (255, 255, 255))
    d = ImageDraw.Draw(out)
    try:
        font = ImageFont.truetype(str(HERE / "static" / "fonts" / "Inter-Regular.ttf"), max(12, size // 46))
    except Exception:
        font = ImageFont.load_default()
    margin, gap, lgap = int(size * 0.045), int(size * 0.035), int(size * 0.018)
    cap = getattr(font, "size", 14) + lgap
    n = max(1, len(rects))
    cell_w = (size - 2 * margin - gap * (n - 1)) / n
    rh = max((p[1].height for p in rects), default=1)
    rw = max((p[1].width for p in rects), default=1)
    k = min(cell_w / rw, size * (0.58 if circles else 0.78) / rh)
    top = margin if circles else max(margin, int((size - rh * k - cap) / 2))
    total = sum(int(p[1].width * k) for p in rects) + gap * (len(rects) - 1)
    x = (size - total) // 2
    placed = []

    def put(label, im, shape, x, y):
        v = _VEC_PANELS.get(id(im))
        im = im.resize((max(1, int(im.width * k)), max(1, int(im.height * k))), Image.LANCZOS)
        out.paste(im, (x, y), im)
        if v:
            placed.append(dict(v, at=[x, y, im.width, im.height]))
        (d.ellipse if shape == "circle" else d.rectangle)(
            [x, y, x + im.width - 1, y + im.height - 1], outline=(200, 200, 200), width=2)
        tw = d.textlength(label, font=font)
        d.text((x + (im.width - tw) / 2, y + im.height + lgap), label, fill=(140, 140, 140), font=font)
        return im
    for label, im, shape in rects:
        put(label, im, shape, x, top + int(rh * k) - int(im.height * k))
        x += int(im.width * k) + gap
    if circles:
        y0 = top + int(rh * k) + cap + gap if rects else margin
        room = size - y0 - margin - cap
        cw = sum(p[1].width for p in circles) * k + gap * (len(circles) - 1)
        ch = max(p[1].height for p in circles) * k
        if ch > room or cw > size - 2 * margin:
            k *= min(room / ch, (size - 2 * margin) / cw)
            cw = sum(p[1].width for p in circles) * k + gap * (len(circles) - 1)
        x = int((size - cw) / 2)
        for label, im, shape in circles:
            x += put(label, im, shape, x, y0).width + gap
    out.save(out_png)
    if print_pdf:
        _vec_sidecar(out_png, print_pdf, out.size, placed)
    return str(out_png)


def _flat_from_print(print_pdf, product, entries, body_hex, out_png, dpi=110, two_by_two=False, hand="RH",
                     writing_hex=None, show_all=False):
    """
    The proof's flat lay: each imprint location that carries art, upright,
    side by side and at true relative size, labelled underneath.

    4CP items are cut from the print file itself, background and all. Other
    items have guides drawn on their print file, so their panels are built from
    the placed artwork on the product colour instead — same sizes, same spots.
    """
    import subprocess, tempfile
    from PIL import ImageDraw, ImageFont
    work = Path(tempfile.mkdtemp(prefix="flat_"))
    is4 = bool(product.get("is_4cp") or "4cp" in str(product.get("material") or ""))
    by_id = {e.get("id"): e for e in entries if e.get("id")}
    # A jig product (the 0837) shows each side on the pen's own silhouette.
    pen_outline = None
    if product.get("mimaki_jig"):
        try:
            pen_outline = json.loads((HERE / product["mimaki_jig"]).read_text()).get("pen_outline")
        except Exception:
            pen_outline = None
    # A 4CP item prints its background on every location, art or not, so every
    # location is shown; other items show the locations that carry art.
    used = set() if (is4 or show_all) else {e.get("label") for e in entries}
    try:
        # Sized so the whole lay comes out about 1600 px wide, whatever the
        # product: a pen barrel and a tote side both fill the proof's width.
        span = sum(sl["w_pt"] * 1.12 for sl in (product.get("art_slots") or [])
                   if not used or sl.get("label") in used) or 500.0
        dpi = max(60.0, min(300.0, 1600.0 * 72.0 / span))
        k = dpi / 72.0
        page = None
        panels = []
        sewn = {o.get("slot") for o in (product.get("sewn_on") or [])}
        for sl in product.get("art_slots") or []:
            if used and sl.get("label") not in used:
                continue
            vec_meta = None
            e = by_id.get(sl["id"])
            pad = min(0.06 * max(sl["w_pt"], sl["h_pt"]), 0.3 * min(sl["w_pt"], sl["h_pt"]))
            im = None
            if pen_outline and ((e and e.get("file")) or show_all):
                try:
                    im = _pen_panel(e or {}, sl, pen_outline, body_hex, k, work, hand=hand, writing_hex=writing_hex)
                    if im is not None:
                        panels.append((sl.get("label") or sl["id"], im, "pen"))
                        continue
                except Exception as ex:
                    print(f"⚠️ pen panel failed for {sl['id']}: {ex}")
                    im = None
            if im is None and not is4 and e and e.get("file"):
                try:
                    art = _render_art_piece(e, k, work)
                    if art is not None:
                        pw, ph = int((sl["w_pt"] + 2 * pad) * k), int((sl["h_pt"] + 2 * pad) * k)
                        im = Image.new("RGBA", (pw, ph), (255, 255, 255, 255))
                        d0 = ImageDraw.Draw(im)
                        bx = [int(pad * k), int(pad * k), int((pad + sl["w_pt"]) * k), int((pad + sl["h_pt"]) * k)]
                        col = body_hex if re.fullmatch(r"#[0-9A-Fa-f]{6}", str(body_hex or "")) else "#FFFFFF"
                        (d0.ellipse if sl.get("shape") == "circle" else d0.rectangle)(bx, fill=col)
                        cx = int((pad + e["x"] + e["w"] / 2) * k - art.width / 2)
                        cy = int((pad + e["y"] + e["h"] / 2) * k - art.height / 2)
                        im.paste(art, (cx, cy), art)
                        # A small mark on a long, thin location (a pen barrel)
                        # would be a speck across the proof: show the part of
                        # the location around it instead.
                        if e["w"] < 0.35 * sl["w_pt"] and sl["w_pt"] > 3 * sl["h_pt"]:
                            half = max(e["w"] * 0.85, sl["h_pt"] * 1.6) * k
                            mid = cx + art.width / 2
                            l_ = int(max(0, mid - half)); r_ = int(min(im.width, mid + half))
                            im = im.crop((l_, 0, r_, im.height))
                except Exception as ex:
                    print(f"⚠️ flat panel from art failed for {sl['id']}: {ex}")
                    im = None
            if im is None and show_all and not is4 and not (e and e.get("file")):
                pw, ph = int((sl["w_pt"] + 2 * pad) * k), int((sl["h_pt"] + 2 * pad) * k)
                im = Image.new("RGBA", (pw, ph), (255, 255, 255, 255))
                col = body_hex if re.fullmatch(r"#[0-9A-Fa-f]{6}", str(body_hex or "")) else "#FFFFFF"
                bx = [int(pad * k), int(pad * k), int((pad + sl["w_pt"]) * k), int((pad + sl["h_pt"]) * k)]
                (ImageDraw.Draw(im).ellipse if sl.get("shape") == "circle" else ImageDraw.Draw(im).rectangle)(bx, fill=col)
            if im is None:
                if page is None:
                    subprocess.run(["pdftoppm", "-png", "-r", f"{dpi:.2f}", "-singlefile", str(print_pdf),
                                    str(work / "p")], check=True)
                    page = Image.open(work / "p.png").convert("RGB")
                x0 = (sl["left_pt"] - pad) * k
                y0 = (-sl["top_pt"] - pad) * k
                x1 = (sl["left_pt"] + sl["w_pt"] + pad) * k
                y1 = (-sl["top_pt"] + sl["h_pt"] + pad) * k
                box = [int(max(0, x0)), int(max(0, y0)), int(min(page.width, x1)), int(min(page.height, y1))]
                if box[2] - box[0] < 4 or box[3] - box[1] < 4:
                    continue
                im = page.crop(box)
                if sl.get("rotation"):
                    im = im.rotate(sl["rotation"], expand=True, fillcolor=(255, 255, 255))
                im = im.convert("RGBA")
                # Where this panel came from in the print file, so the proof
                # can lay the print file's own vector (its named spots) over
                # the picture: crop box in points from the page's top-left.
                vec_meta = {"box": [b / k for b in box], "rot": int(sl.get("rotation") or 0) % 360,
                            "circle": sl.get("shape") == "circle",
                            "inset": (pad * k * 0.5) / max(1, im.width)}
            if sl.get("shape") == "circle":
                m = Image.new("L", im.size, 0)
                ImageDraw.Draw(m).ellipse([pad * k * 0.5, pad * k * 0.5, im.width - pad * k * 0.5,
                                           im.height - pad * k * 0.5], fill=255)
                im.putalpha(m)
            import press_layout as _pl
            im = _pl.paste_sewn_on(im, sl["id"], 72.0 * k, product)
            if vec_meta and sl["id"] not in sewn and vec_meta["rot"] in (0, 180):
                _VEC_PANELS[id(im)] = dict(vec_meta, w=im.width, h=im.height)
            panels.append((sl.get("label") or sl["id"], im, sl.get("shape")))
        if not panels:
            return None
        if two_by_two:
            return _flat_2x2(panels, out_png, print_pdf=print_pdf)
        if show_all and len(panels) > 1 and all(p[1].width > 2.5 * p[1].height for p in panels):
            # Long, thin locations (a pen barrel): one above the other, so the
            # 2X2's square isn't mostly empty.
            Wv = max(p[1].width for p in panels)
            lab = max(18, int(Wv / 45))
            try:
                font = ImageFont.truetype(str(HERE / "static" / "fonts" / "Inter-Regular.ttf"), lab)
            except Exception:
                font = ImageFont.load_default()
            gap = int(lab * 1.2)
            Hv = sum(p[1].height + lab + gap for p in panels) + gap
            out = Image.new("RGB", (Wv + 2 * gap, Hv), (255, 255, 255))
            d = ImageDraw.Draw(out)
            y = gap
            for label, im, shape in panels:
                x = gap + (Wv - im.width) // 2
                out.paste(im, (x, y), im)
                tw = d.textlength(label, font=font)
                d.text((gap + (Wv - tw) / 2, y + im.height + lab * 0.2), label, fill=(90, 90, 90), font=font)
                y += im.height + lab + gap
            out.save(out_png)
            return str(out_png)
        gap = max(16, int(sum(p[1].width for p in panels) / 40))
        W = sum(p[1].width for p in panels) + gap * (len(panels) + 1)
        lab = max(24, int(W / 38))
        H = max(p[1].height for p in panels) + lab + gap * 2
        out = Image.new("RGB", (W, H), (255, 255, 255))
        d = ImageDraw.Draw(out)
        try:
            font = ImageFont.truetype(str(HERE / "static" / "fonts" / "Inter-Regular.ttf"),
                                      max(14, int(W / 55)))
        except Exception:
            font = ImageFont.load_default()
        x = gap
        base = gap + max(p[1].height for p in panels)
        placed = []
        for label, im, shape in panels:
            y = base - im.height if shape != "circle" else gap + (base - gap - im.height) // 2
            out.paste(im, (x, y), im)
            if id(im) in _VEC_PANELS:
                placed.append(dict(_VEC_PANELS[id(im)], at=[x, y, im.width, im.height]))
            if shape == "pen":
                pass       # the silhouette is its own outline
            elif shape == "circle":
                d.ellipse([x, y, x + im.width - 1, y + im.height - 1], outline=(200, 200, 200), width=2)
            else:
                d.rectangle([x, y, x + im.width - 1, y + im.height - 1], outline=(200, 200, 200), width=2)
            tw = d.textlength(label, font=font)
            d.text((x + (im.width - tw) / 2, base + lab * 0.35), label, fill=(90, 90, 90), font=font)
            x += im.width + gap
        out.save(out_png)
        _vec_sidecar(out_png, print_pdf, out.size, placed)
        return str(out_png)
    finally:
        _VEC_PANELS.clear()
        shutil.rmtree(work, ignore_errors=True)


def _generic_proof(print_pdf, prefix, serve_dir, pmeta, job, order, artist, mockup_img):
    """Numo's digital proof for a product with no press template."""
    import press_layout
    pid = pmeta.get("product_id") or ""
    product = PRODUCTS.get(pid) or {}
    sizes = (job or {}).get("art_sizes") or []
    comps = [c for c in (pmeta.get("components") or []) if isinstance(c, dict)]
    # 4CP can insulators get the 2X2 (sides over the bottom disc), which also
    # ships in the zip; everything else keeps the one-row flat lay.
    is4 = bool(product.get("is_4cp") or "4cp" in str(product.get("material") or ""))
    two = is4 and any(sl.get("shape") == "circle" for sl in (product.get("art_slots") or []))
    hand = pmeta.get("pen_hand") or (job or {}).get("pen_hand") or "RH"
    variants = [v for v in (pmeta.get("pen_variants") or []) if isinstance(v, dict)]
    flat = None
    if product.get("mimaki_jig") and (len(variants) > 1 or any(v.get("ink") or v.get("map") for v in variants)):
        try:
            flat = _pen_variants_flat(product, sizes, variants, hand, Path(serve_dir) / f"{prefix}-flat.png")
        except Exception as e:
            import traceback; traceback.print_exc()
            flat = None
    if not flat:
        flat = _flat_from_print(print_pdf, product, sizes, (comps[0].get("hex") if comps else None),
                                Path(serve_dir) / (f"{prefix}-2X2.png" if two else f"{prefix}-flat.png"),
                                two_by_two=two, hand=hand,
                                writing_hex=(pmeta.get("pen_writing") or {}).get("hex"))
    extra = dict(_proof_extra(pid), **_proof_order_fields(order), **_artist_fields(artist))
    inks = press_layout._imprint_inks(pmeta.get("inks") or [])
    imprint = pmeta.get("imprint") or {}
    if pmeta.get("full_color"):
        inks = [{"name": "Full color", "hex": "#E9E9EA"}] + inks
    import math as _m
    def _sz(x):
        r = abs(_m.degrees(float(x.get("rot") or 0))) % 360
        return x.get("size") + (f" · turned {round(r)}°" if 0.5 < r < 359.5 else "")
    meta = {
        "order_id": (pmeta.get("order_id") or "").strip() or None,
        "item": pid,
        "label": extra.get("label"),
        "customer": extra.get("customer"),
        "artist": extra.get("artist"),
        "artist_note": extra.get("artist_note"),
        "revision": extra.get("revision"),
        "quantity": extra.get("quantity"),
        "item_color": comps[0] if comps else {},
        "components_extra": comps[1:],
        "imprint": ({"name": " + ".join(str(m["name"]).replace("PANTONE ", "") for m in pmeta["pen_art_pms"]
                                        if isinstance(m, dict) and m.get("name")),
                     "hex": (pmeta["pen_art_pms"][0] or {}).get("hex")}
                    if product.get("mimaki_jig") and pmeta.get("pen_art_pms") else
                    imprint if imprint.get("name") else (inks[0] if len(inks) == 1 else {})),
        "imprint_inks": [] if (product.get("mimaki_jig") and pmeta.get("pen_art_pms")) else (inks if len(inks) > 1 else []),
        "art_sizes": [{"label": x.get("label"), "size": _sz(x)} for x in sizes]
                     + ([{"label": "Writing ink",
                          "size": " / ".join(f"{v.get('name')}: {(v.get('writing') or {}).get('name')}"
                                             for v in (pmeta.get("pen_variants") or [])
                                             if isinstance(v, dict) and isinstance(v.get("writing"), dict))
                                  or (pmeta.get("pen_writing") or {}).get("name") or "—"}]
                        if product.get("mimaki_jig") else [])
                     + ([{"label": "Imprint style",
                          "size": "Left Hand (LH)" if str(pmeta.get("pen_hand") or (job or {}).get("pen_hand") or "").upper() == "LH"
                                  else "Right Hand (RH)"}] if product.get("mimaki_jig") else []),
        "accepted_risks": [],
        "product_colors": extra.get("product_colors"),
        "footer": extra.get("footer"),
    }
    out = Path(serve_dir) / f"{prefix}-digitalproof.pdf"
    press_layout.build_proof_page(str(out), meta, flat_png=flat, mockup_img=mockup_img)
    # Every item ships a 2X2, for production to check the art against: the
    # item laid flat, every location shown (a blank side too), one color
    # only — the first pen color when there are several.
    dest = Path(serve_dir) / f"{prefix}-2X2.png"
    two_png = None
    try:
        first = variants[0] if variants else {}
        body = first.get("hex") or (comps[0].get("hex") if comps else None)
        tmp = Path(serve_dir) / f"{prefix}-2X2-lay.png"
        two_png = _flat_from_print(print_pdf, product, sizes, body, tmp, two_by_two=bool(
                                       any(sl.get("shape") == "circle" for sl in (product.get("art_slots") or []))),
                                   hand=hand, writing_hex=((first.get("writing") or {}).get("hex") if first
                                                          else (pmeta.get("pen_writing") or {}).get("hex")),
                                   show_all=True)
    except Exception as e:
        import traceback; traceback.print_exc()
        two_png = None
    if two_png:
        shutil.move(str(two_png), str(dest))
        if flat and Path(flat).exists() and Path(flat) != dest:
            Path(flat).unlink(missing_ok=True)
        return out, dest
    if flat:
        if Path(flat) != dest:
            shutil.move(str(flat), str(dest))
        return out, dest
    return out, None



def _hdr(text):
    """A response header value: HTTP headers are ASCII, notes are not."""
    t = str(text).replace("\u2014", "-").replace("\u2013", "-").replace("\u00d7", "x") \
        .replace("\u2019", "'").replace("\u2026", "...").replace("\u2192", "->")
    return t.encode("ascii", "replace").decode()


# ── Export file names ───────────────────────────────────────────────────────
#
#   NSO-ITEM-ASSET[-R#].ext   e.g. NSO123456-0070-3M-3C-digitalproof-R1.pdf
#
# The customer-facing files (2X2, digital proof, virtual proof) carry the
# revision. The press files never do: they land in the press room's hot
# folder, and a revision has to replace the file there, not sit beside it.
# So a press file is named for the job, the item and the machine only —
# NSO123456-0070-3M-3C-STRYKER.pdf — and every revision overwrites it.
#
# The JSON files, the original artwork and (where press sheets exist) the
# print PDF are not shipped.

_REV_SUFFIX = re.compile(r"-R(\d{1,2})$", re.I)


def _export_nso_rev(meta, prefix):
    m = _REV_SUFFIX.search(prefix)
    base = prefix[:m.start()] if m else prefix
    nso = _safe_prefix(meta.get("nso") or "") or base
    return nso, (f"-R{m.group(1)}" if m else "")


def _export_item(meta):
    raw = str(meta.get("item_number") or "").strip()
    if not raw:
        pid = ((meta.get("press") or {}).get("product_id") or (meta.get("proof") or {}).get("product_id") or "")
        raw = (PRODUCTS.get(pid) or {}).get("sku") or pid
    return _safe_prefix(raw.upper())


def _artist_initials(artist):
    """"Cesar Lugo" -> "CL"; "Candy" -> "C"; an artist object or nothing -> ""."""
    if isinstance(artist, dict):
        artist = artist.get("name") or artist.get("artist") or ""
    t = str(artist or "").strip()
    if re.fullmatch(r"[A-Za-z]{1,4}", t):          # typed as initials already
        return t.upper()
    words = re.findall(r"[A-Za-z]+", t)
    return "".join(w[0].upper() for w in words[:3])


def _export_initials(meta):
    return _artist_initials(meta.get("initials") or meta.get("artist"))


def _pen_side_modes(job):
    """{"side1": "SAME" | "DIFFERENT" | "ONLY", …} for a pen's sides that print:
    both sides with the same art in the same place read SAME."""
    import hashlib
    ent = {e.get("id"): e for e in ((job or {}).get("art_sizes") or []) if e.get("id")}
    def sig(e):
        f = e.get("file")
        try:
            h = hashlib.sha1(Path(f).read_bytes()).hexdigest() if f else ""
        except Exception:
            h = str(f)
        return (h, round(float(e.get("x") or 0), 1), round(float(e.get("y") or 0), 1),
                round(float(e.get("w") or 0), 1), round(float(e.get("h") or 0), 1))
    ids = [i for i in ("side1", "side2") if i in ent]
    if len(ids) == 1:
        return {ids[0]: "ONLY"}
    if len(ids) == 2:
        m = "SAME" if sig(ent["side1"]) == sig(ent["side2"]) else "DIFFERENT"
        return {"side1": m, "side2": m}
    return {}


def _export_stem(meta, prefix):
    """("NSO CB-ITEM[-LH]", "-R2" or "") for an export's file names."""
    nso, rev = _export_nso_rev(meta, prefix)
    item = _export_item(meta)
    # NSO INITIALS-ITEM-ASSET: a space after the NSO (production barcode
    # readers), the artist's initials, the item code, then what the file is.
    ini = _export_initials(meta)
    head = f"{nso} {ini}" if ini else nso
    stem = f"{head}-{item}" if item else head
    if str(meta.get("pen_hand") or "").upper() == "LH":
        stem += "-LH"          # a Left Hand pen order: every file says so
    return stem, rev


def _deliverables(files, meta, prefix, serve_dir, press_ok):
    """Rename the export's files to their final names and list them.

    Returns the _files.json listing."""
    stem, rev = _export_stem(meta, prefix)
    # A color variant of a multi-variant export (see export_combine): its
    # press files and virtual carry its body color and PMS; its proof and 2X2
    # stay unnamed and hidden until every variant is in, then become one each.
    var = meta.get("variant") if isinstance(meta.get("variant"), dict) else None
    tag = _safe_prefix(str((var or {}).get("tag") or "").upper())[:60] if var else ""
    vt = f"-{tag}" if tag else ""
    # Press sheets shared by several colourways are named for all their PMS
    # ("-WHITE+2685C") rather than for the first colourway alone.
    ptag = _safe_prefix(str((var or {}).get("press_tag") or "").upper())[:60] if var else ""
    pvt = f"-{ptag}" if ptag else vt
    out, hidden = [], []

    def keep(src, kind):
        src = Path(src)
        hidden.append({"name": src.name, "folder": None, "path": src.name,
                       "bytes": src.stat().st_size, "kind": kind, "hidden": True})

    def add(src, new_name, kind):
        src = Path(src)
        dest = serve_dir / new_name
        if src.resolve() != dest.resolve():
            if dest.exists():
                dest.unlink()
            src.rename(dest)
        out.append({"name": dest.name, "folder": None, "path": dest.name,
                    "bytes": dest.stat().st_size, "kind": kind})

    for f in files:
        if isinstance(f, tuple):          # art/ originals: not shipped
            continue
        f = Path(f)
        if not f.exists() or serve_dir.resolve() not in f.resolve().parents:
            continue
        n = f.name
        if n.endswith(".json"):
            continue
        if n == f"{prefix}-virtualproof.jpg":
            add(f, f"{stem}-VIRTUAL{vt}{rev}.jpg", "virtualproof")
        elif n == f"{prefix}-label.png":
            add(f, f"{stem}-LABEL{vt}{rev}.png", "label")
        elif n == f"{prefix}-virtualproof-pricing.jpg":
            add(f, f"{stem}-VIRTUAL-PRICING{vt}{rev}.jpg", "virtualproof")
        elif var and n in (f"{prefix}-digitalproof.pdf", f"{prefix}-2X2.png"):
            keep(f, "variant-proof" if n.endswith(".pdf") else "variant-2x2")
        elif n == f"{prefix}-digitalproof.pdf":
            add(f, f"{stem}-PROOF{rev}.pdf", "digitalproof")
        elif n == f"{prefix}-2X2.png":
            try:
                _annotate_2x2(f, meta)
            except Exception as e:
                print(f"⚠️ 2X2 details not added: {e}")
            try:
                _fit_2x2(f)          # always the gold-standard size, even without the header
            except Exception as e:
                print(f"⚠️ 2X2 not resized: {e}")
            new = serve_dir / f"{stem}-2X2{rev}.png"
            shutil.copy2(str(f), str(new))
            out.append({"name": new.name, "folder": None, "path": new.name,
                        "bytes": new.stat().st_size, "kind": "2x2"})
            hidden.append({"name": f.name, "folder": None, "path": f.name,
                           "bytes": f.stat().st_size, "kind": "2x2", "hidden": True})
        elif n.startswith(f"{prefix} - ") and n.endswith(".pdf"):
            # A press sheet: "PREFIX - STRYKER - BTM 2 Sides Same.pdf"
            #   -> NSO CB-ITEM-STRYKER-BTM 2 SIDES SAME.pdf (never a revision)
            rest = n[len(prefix) + 3:-4]
            parts = [p.strip() for p in rest.split(" - ") if p.strip()]
            machine = parts[0].split(" (")[0] if parts else ""
            what = ""
            m2 = re.search(r"\s+((?:BTM\s+)?(?:1 Side|2 Sides Same|2 Sides Different))$", machine, re.I)
            if m2:
                what, machine = m2.group(1), machine[:m2.start()]
            elif len(parts) > 1:
                what = parts[1]
            what = re.sub(r"[^A-Za-z0-9 ]+", " ", what).strip().upper()
            what = re.sub(r"\s+", " ", what)
            add(f, f"{stem}-{_safe_prefix(machine.upper()) or 'PRESS'}" + (f"-{what}" if what else "") + f"{pvt}.pdf", "press")
        elif n == f"{prefix}-print.pdf":
            if press_ok:                  # the press sheets are the production files
                continue
            add(f, f"{stem}-PRESS{pvt}.pdf", "press")
        elif n.startswith(f"{prefix}-") and n.endswith((".eps", ".pdf")) and \
                re.fullmatch(r"SIDE\d(--.+)?", n[len(prefix) + 1:-4]):
            # The pen's Mimaki file: NSO CB-0837-MIMAKI-RH-SIDE 1-SAME[-INK].pdf
            # (never a revision).
            ext = n[-4:]
            side, _, ink = n[len(prefix) + 1:-4].partition("--")     # SIDE1 / SIDE2 [, INK]
            hand = "LH" if str(meta.get("pen_hand") or "").upper() == "LH" else "RH"
            mode = (meta.get("_pen_sides") or {}).get(side.lower(), "")
            parts = [stem, "MIMAKI"] + ([] if hand == "LH" else [hand]) + \
                    [f"SIDE {side[-1]}" if side[-1:].isdigit() else side]
            if mode:
                parts.append(mode)
            if ink:
                parts.append(ink)
            add(f, "-".join(parts) + ext, "press")
        else:
            continue
    order = {"2x2": 0, "digitalproof": 1, "virtualproof": 2, "press": 3}
    out.sort(key=lambda e: (order.get(e["kind"], 9), e["name"]))
    return out + hidden


_MAT_LABEL = {"neoprene": "Neoprene", "neoprene_metallic": "Metallic Neoprene", "neoprene_heathered": "Heathered Neoprene", "neoprene_denim": "Denim Neoprene", "neoprene_burlap": "Burlap Neoprene", "neoprene_suede": "Suede", "scuba_foam": "Scuba Foam", "neoprene_4cp": "Neoprene",
              "scuba_foam_4cp": "Scuba Foam", "jotter": "Pen", "three_way_pen": "Pen",
              "cotton_canvas": "Canvas", "cotton_canvas_dyed": "Canvas"}


def _two_by_two_details(meta):
    """NSO, item, substrate and its color(s), and the ink(s), for the 2X2."""
    press, proof = meta.get("press") or {}, meta.get("proof") or {}
    pid = press.get("product_id") or proof.get("product_id") or ""
    prod = PRODUCTS.get(pid) or {}
    nso = (meta.get("nso") or "").strip() or _export_nso_rev(meta, _safe_prefix(meta.get("prefix") or ""))[0]
    item = _export_item(meta)
    mat = _MAT_LABEL.get(prod.get("material") or "", "")
    if "4cp" in (prod.get("material") or ""):
        mat += " (4CP)"
    comps = [c for c in (press.get("components") or proof.get("components") or []) if isinstance(c, dict)]
    substrate = []
    for c in comps:
        if not c.get("name"):
            continue
        lbl = (c.get("label") or "").strip()
        substrate.append((f"{lbl}: {c['name']}" if lbl else c["name"], c.get("hex")))
    inks = []
    if press.get("inks"):
        seen = set()
        for i in press["inks"]:
            nm = (i.get("pms") or i.get("hex") or "").replace("PANTONE ", "")
            if i.get("hidden") or not nm or nm in seen:
                continue
            seen.add(nm); inks.append((nm, i.get("pms_hex") or i.get("hex")))
    elif press.get("pms_name"):
        inks.append((press["pms_name"].replace("PANTONE ", ""), press.get("pms_hex")))
    else:
        if proof.get("full_color"):
            inks.append(("Full color", None))
        for i in proof.get("inks") or []:
            nm = (i.get("pms") or "").replace("PANTONE ", "")
            if nm:
                inks.append((nm, i.get("pms_hex") or i.get("hex")))
    # A pen: "Ink" is the pen's writing ink (Black, or Match · PMS …); the
    # imprint colours ride with the body ("Body: Olive · White + 485 C").
    if prod.get("mimaki_jig") and prod.get("material") == "jotter":
        variants = [v for v in (proof.get("pen_variants") or []) if isinstance(v, dict)]
        if variants:
            inks = [(f"{v.get('name')}: {(v.get('writing') or {}).get('name') or '—'}",
                     (v.get("writing") or {}).get("hex")) for v in variants if isinstance(v.get("writing"), dict)]
        else:
            w = proof.get("pen_writing") or {}
            inks = [(w.get("name") or "—", w.get("hex"))]
            imp = [str(m.get("name") or "").replace("PANTONE ", "") for m in (proof.get("pen_art_pms") or [])
                   if isinstance(m, dict) and m.get("name")] or [n for n, _ in proof_inks_named(proof)]
            if imp and substrate:
                t, h = substrate[-1]
                substrate[-1] = (f"{t} · {' + '.join(imp)}", h)
    # The material leads unless a component already names it ("Neoprene: Navy").
    if mat and not any(t.lower().startswith(mat.split(" (")[0].lower() + ":") for t, _ in substrate):
        substrate.insert(0, (mat, None))
    return {"nso": nso, "item": item, "material": mat, "substrate": substrate, "inks": inks}


def proof_inks_named(proof):
    """The imprint's PMS colours the proof lists, short names."""
    out = []
    for i in proof.get("inks") or []:
        nm = (i.get("pms") or "").replace("PANTONE ", "")
        if nm and nm not in [o[0] for o in out]:
            out.append((nm, i.get("pms_hex") or i.get("hex")))
    return out


# Gold-standard 2X2: 800 x 800 px, the pixel size of the handmade 2X2 that
# is verified to work downstream, and 2 x 2 inches when opened (Photoshop's
# Image Size): 800 px / 2 in = 400 pixels per inch. At 72 it opened 11.111 in.
TWO_BY_TWO_PX = 800
TWO_BY_TWO_IN = 2.0
TWO_BY_TWO_DPI = TWO_BY_TWO_PX / TWO_BY_TWO_IN


def _fit_2x2(png):
    """Make a 2X2 exactly TWO_BY_TWO_PX square at TWO_BY_TWO_DPI, whatever
    size it was drawn at (lay-out centred on white, never stretched)."""
    im = Image.open(png).convert("RGB")
    N = TWO_BY_TWO_PX
    if im.size != (N, N):
        k = min(N / im.width, N / im.height)
        lay = im.resize((max(1, round(im.width * k)), max(1, round(im.height * k))), Image.LANCZOS)
        im = Image.new("RGB", (N, N), (255, 255, 255))
        im.paste(lay, ((N - lay.width) // 2, (N - lay.height) // 2))
    im.save(png, dpi=(TWO_BY_TWO_DPI, TWO_BY_TWO_DPI))


def _plain_2x2(lay, png):
    """The 2X2 production checks the art against: just the item, laid flat,
    trimmed to it and filling the square (no NSO, colors or inks on it)."""
    from PIL import ImageChops
    lay = lay.convert("RGB")
    # Near-white counts as background, so a faint edge doesn't keep a margin.
    diff = ImageChops.difference(lay, Image.new("RGB", lay.size, (255, 255, 255))).convert("L")
    bb = diff.point(lambda v: 255 if v > 12 else 0).getbbox()
    if bb:
        lay = lay.crop(bb)
    N = TWO_BY_TWO_PX
    m = int(N * 0.02)
    k = min((N - 2 * m) / lay.width, (N - 2 * m) / lay.height)
    lay = lay.resize((max(1, round(lay.width * k)), max(1, round(lay.height * k))), Image.LANCZOS)
    out = Image.new("RGB", (N, N), (255, 255, 255))
    out.paste(lay, ((N - lay.width) // 2, (N - lay.height) // 2))
    out.save(png, dpi=(TWO_BY_TWO_DPI, TWO_BY_TWO_DPI))


def _annotate_2x2(png, meta):
    """The 2X2 as production wants it: the item only (see _plain_2x2)."""
    _plain_2x2(Image.open(png), png)


def _with_embed_all(own, meta):
    """The art a proof embeds: its own, then every other item's and variant's
    on the order (meta.embed_all), so one proof can reopen the whole order."""
    out, seen = [], set()
    for e in list(own or []) + list(meta.get("embed_all") or []):
        if isinstance(e, dict) and e.get("path") and str(e["path"]) not in seen:
            seen.add(str(e["path"])); out.append(e)
    return out


def _annotate_2x2_variants(lays, variants, meta, png):
    """One 2X2 for an order with several lines: the first line's item only,
    as _plain_2x2 draws it — production checks the art, not the colorways."""
    def line_no(k):
        ln = ((variants[k] or {}).get("variant") or {}).get("line") or {}
        try:
            return int(ln.get("line_no"))
        except (TypeError, ValueError):
            return 10 ** 6 + k
    k = min(range(len(lays)), key=line_no) if lays else 0
    _plain_2x2(lays[k] if lays else Image.new("RGB", (10, 10), (255, 255, 255)), png)


_VAR_EXPORT_ID = re.compile(r"^export_[0-9_]+$")


@app.route("/api/export-combine", methods=["POST"])
def export_combine():
    """
    The color variants of one item on one order, exported together.

    The browser exports each variant on its own (export_bundle with
    meta.variant): its virtual and press files come out named for its body
    color and PMS, its proof and 2X2 are kept back. This puts them in one
    export: every variant's files, ONE proof (a page per variant, the first
    carrying the job and every variant for revisions) and ONE 2X2 with all the
    variants on it.
    """
    body = request.get_json(silent=True) or {}
    ids = [str(i) for i in (body.get("exports") or [])]
    meta = body.get("meta") if isinstance(body.get("meta"), dict) else {}
    prefix = _safe_prefix(meta.get("prefix") or "")
    if not prefix or not ids or len(ids) > 40 or not all(_VAR_EXPORT_ID.match(i) for i in ids):
        return jsonify({"error": "Pass the variant exports and the NSO."}), 400
    root = (HERE / "_serve").resolve()
    srcs = []
    for i in ids:
        d = (root / i).resolve()
        if d.parent != root or not (d / "_files.json").is_file() or not (d / "_variant.json").is_file():
            return jsonify({"error": "A variant's export has expired: export again."}), 404
        srcs.append(d)
    serve_dir = HERE / "_serve" / _unique_id("export")
    serve_dir.mkdir(parents=True, exist_ok=True)
    try:
        stem, rev = _export_stem(meta, prefix)
        out, hidden, proofs, lays, variants = [], [], [], [], []
        notes, info, saved = [], [], []
        for k, d in enumerate(srcs):
            listing = json.loads((d / "_files.json").read_text())
            vj = json.loads((d / "_variant.json").read_text())
            variants.append(vj)
            notes += [f"variant {k + 1}: {x}" for x in (vj.get("notes") or [])]
            info += [x for x in (vj.get("info") or []) if x not in info]
            saved.append(vj.get("job_saved"))
            lay = None
            for e in listing:
                f = (d / str(e.get("path") or "")).resolve()
                if f.parent != d or not f.is_file():
                    continue
                if e.get("kind") == "variant-proof":
                    proofs.append((f, vj))
                elif e.get("kind") == "variant-2x2":
                    lay = f
                elif not e.get("hidden"):
                    dest = serve_dir / f.name
                    if dest.exists():                     # two variants named alike: keep both
                        dest = serve_dir / f"{f.stem}-{k + 1}{f.suffix}"
                    shutil.move(str(f), str(dest))
                    out.append({**e, "name": dest.name, "path": dest.name, "bytes": dest.stat().st_size})
            if lay is None:
                notes.append(f"variant {k + 1} has no 2X2 lay-out")
                lays.append(Image.new("RGB", (400, 400), (255, 255, 255)))
            else:
                lays.append(Image.open(lay).convert("RGB"))
        # A proof per item: every color variant (order line) of the item on
        # its one page. The first variant's file is kept as the base, so the
        # job it carries (and every variant and item of the order) still
        # reopens for revisions.
        groups = {}
        for pth, vj in proofs:
            groups.setdefault(vj.get("stem") or stem, []).append((pth, vj))
        import press_layout, pikepdf
        for g_stem, members in groups.items():
            dest = serve_dir / f"{g_stem}-PROOF{members[0][1].get('rev', rev)}.pdf"
            base_pdf = members[0][0]
            if len(members) > 1:
                try:
                    metas, flats = [], []
                    for pth, vj in members:
                        mt = json.loads(Path(f"{pth}.meta.json").read_text())
                        ln = (vj.get("variant") or {}).get("line") or {}
                        if ln.get("line_no"):
                            mt["line_no"] = ln["line_no"]
                        if ln.get("qty"):
                            mt["quantity"] = ln["qty"]
                        metas.append(mt)
                        fl = Path(f"{pth}.flat.png")
                        flats.append(str(fl) if fl.exists() else None)
                    mock = Path(f"{base_pdf}.mock.img")
                    page = serve_dir / f"_page-{len(out)}.pdf"
                    press_layout.build_proof_page_multi(str(page), metas, flats,
                                                        mockup_img=str(mock) if mock.exists() else None)
                    pdf = pikepdf.open(str(base_pdf))
                    newp = pikepdf.open(str(page))
                    del pdf.pages[:]
                    pdf.pages.extend(newp.pages)
                    pdf.save(str(dest))
                    pdf.close(); newp.close()
                    page.unlink(missing_ok=True)
                except Exception as e:
                    import traceback; traceback.print_exc()
                    notes.append(f"{g_stem}: the colors couldn't be put on one proof page ({e}); one proof per color instead")
                    for k, (pth, vj) in enumerate(members):
                        tag = _safe_prefix(str((vj.get("variant") or {}).get("tag") or "").upper())[:60] or str(k + 1)
                        d2 = serve_dir / f"{g_stem}-PROOF-{tag}{vj.get('rev', rev)}.pdf"
                        shutil.move(str(pth), str(d2))
                        out.append({"name": d2.name, "folder": None, "path": d2.name,
                                    "bytes": d2.stat().st_size, "kind": "digitalproof"})
                    continue
            else:
                shutil.move(str(base_pdf), str(dest))
            out.append({"name": dest.name, "folder": None, "path": dest.name,
                        "bytes": dest.stat().st_size, "kind": "digitalproof"})
        if not proofs:
            notes.append("no proof was made for the variants")
        # One 2X2 with every variant of every item.
        items = list(dict.fromkeys(v.get("item") for v in variants if v.get("item")))
        two = serve_dir / f"{prefix}-2X2.png"
        _annotate_2x2_variants(lays, variants, meta, two)
        # Named for the item it shows: the order's first line.
        def _ln(v):
            try:
                return int(((v.get("variant") or {}).get("line") or {}).get("line_no"))
            except (TypeError, ValueError):
                return 10 ** 6
        shown = min(variants, key=_ln) if variants else {}
        new = serve_dir / f"{shown.get('stem') or stem}-2X2{shown.get('rev', rev)}.png"
        shutil.copy2(str(two), str(new))
        out.append({"name": new.name, "folder": None, "path": new.name, "bytes": new.stat().st_size, "kind": "2x2"})
        hidden.append({"name": two.name, "folder": None, "path": two.name,
                       "bytes": two.stat().st_size, "kind": "2x2", "hidden": True})
        ink_field = None
        order = {"2x2": 0, "digitalproof": 1, "virtualproof": 2, "press": 3}
        out.sort(key=lambda e: (order.get(e["kind"], 9), e["name"]))
        if SANDBOX:
            out, hidden = _sandbox_trim(out + hidden, serve_dir, keep_hidden=()), []
        (serve_dir / "_files.json").write_text(json.dumps(out + hidden))
        for d in srcs:
            shutil.rmtree(d, ignore_errors=True)
        js = saved[0] if saved else None
        return jsonify({"export_id": serve_dir.name, "files": out,
                        "notes": " | ".join(notes)[:600] or None,
                        "info": " | ".join(info)[:600] or None,
                        "job_saved": js, "variants": len(srcs),
                        "ink": None})
    except Exception as e:
        import traceback; traceback.print_exc()
        shutil.rmtree(serve_dir, ignore_errors=True)
        return jsonify({"error": str(e)}), 500


@app.route("/api/export-bundle", methods=["POST"])
def export_bundle():
    """
    One zip per job.

    The export used to fire four separate downloads — two canvas JPEGs, the
    print PDF, and the press zip — which arrive in the browser's download
    folder interleaved with everything else and have to be gathered back
    together by hand. Everything now lands in a single PREFIX.zip.

    The pieces come from three different places, which is why this is a
    multipart post rather than plain JSON: the mockups are rendered in the
    browser and uploaded here, the press sheets are imposed on the spot, and
    the print PDF is collected from a render job that has already finished.
    """
    meta = {}
    raw = request.form.get("meta")
    if raw:
        try:
            meta = json.loads(raw)
        except ValueError:
            return jsonify({"error": "Malformed export metadata."}), 400

    prefix = _safe_prefix(meta.get("prefix") or "")
    if not prefix:
        return jsonify({"error": "Enter the NSO number before exporting.",
                        "code": "prefix_required"}), 400

    _sweep_serve()
    _sweep_uploads()
    serve_dir = HERE / "_serve" / _unique_id("export")
    serve_dir.mkdir(parents=True, exist_ok=True)
    files = []
    notes = []
    info_notes = []      # worth saying, but nothing is missing
    job_saved = None     # whether the proof carries the job for revisions
    mockup_img = None

    try:
        # ── Canvas mockups, rendered in the browser ─────────────────────────
        # The field name carries the suffix, so the pricing variant needs no
        # special case here.
        for field in sorted(request.files.keys()):
            if not field.startswith("mockup"):
                continue
            up = request.files[field]
            suffix = field[len("mockup"):]          # "" or "-pricing"
            path = serve_dir / f"{prefix}-virtualproof{suffix}.jpg"
            up.save(str(path))
            files.append(path)
            if not suffix:
                mockup_img = path

        # ── Box label (3-way pen), rendered in the browser ──────────────────
        # Saved with its print resolution so it opens at 2.75" (270 ppi).
        if "label" in request.files:
            path = serve_dir / f"{prefix}-label.png"
            request.files["label"].save(str(path))
            try:
                from PIL import Image as _LI
                _ppi = int(((PRODUCTS.get(meta.get("product_id") or "") or {}).get("pen_label") or {}).get("ppi") or 270)
                with _LI.open(str(path)) as _im:
                    _im.load(); _im.save(str(path), dpi=(_ppi, _ppi), optimize=True)
            except Exception as e:
                print(f"⚠️ label resolution not set: {e}")
            files.append(path)

        # ── The order ───────────────────────────────────────────────────────
        # Written beside the artwork as its own file.
        order = meta.get("order")
        if isinstance(order, dict) and order:
            order_path = serve_dir / f"{prefix}-order.json"
            order_path.write_text(json.dumps(order, indent=2, ensure_ascii=False),
                                  encoding="utf-8")
            files.append(order_path)
            bad = _order_problems(order)
            if bad:
                # Recorded rather than refused. The browser checks these and
                # this is the backstop; an export that reached here has files
                # worth keeping, and a note is more use than a lost archive.
                notes.append("Order details need a look: " + "; ".join(bad))

        # ── Press sheets, when the product has a measured template ──────────
        press_ok = False
        press = meta.get("press")
        if press and SANDBOX:
            press["sheets_shared"] = True     # the proof only: no press sheets are made
        if press:
            # The saved path is the normal route and the upload is the safety
            # net. It matters because uploads/ is not part of the deploy and
            # does not survive one: a configurator left open across a release
            # comes back with a path pointing at a file that is gone, and the
            # imposition then failed with "artwork could not be found" and the
            # customer got an archive holding nothing but the mockup.
            art = press.get("art_path")
            if not _in_uploads(art) and "pressart" in request.files:
                rescued = _upload_path(prefix, request.files["pressart"].filename)
                request.files["pressart"].save(str(rescued))
                press["art_path"] = str(rescued)
                print(f"↻ press art restored from the upload: {rescued.name}")
            # The same rescue, per location. Locations that shared one file
            # upload it once, under the first of them, and the rest follow it.
            paths = press.get("art_paths") or {}
            restored = {}
            for sl in list(paths):
                p_ = paths[sl]
                if _in_uploads(p_):
                    continue
                if p_ in restored:
                    paths[sl] = restored[p_]
                    continue
                up = request.files.get(f"pressart-{sl}")
                if up is None:
                    continue
                rescued = _upload_path(f"{prefix}-{sl}", up.filename)
                up.save(str(rescued))
                restored[p_] = paths[sl] = str(rescued)
                print(f"↻ {sl} press art restored from the upload: {rescued.name}")
            if isinstance(meta.get("snapshot"), dict):
                press["_snapshot"] = meta["snapshot"]
                press["_art_files"] = _with_embed_all(meta.get("art_files") or [], meta)
            try:
                files.extend(_build_press_files(press, prefix, serve_dir,
                                                mockup_img=mockup_img,
                                                order=order,
                                                artist=meta.get("artist")))
                press_ok = True
                if press.get("_sheet_note"):
                    info_notes.append(press["_sheet_note"])
                job_saved = press.get("_job_saved")
            except PressBuildError as e:
                notes.append(str(e))

        # ── The artwork, as uploaded ────────────────────────────────────────
        # In an art/ folder so the originals travel with the job. Named for
        # the job and the locations that use them, with the customer's own
        # file name kept. Only files in uploads/ are taken — the paths come
        # from the browser.
        try:
            files.extend(_art_files(meta.get("art_files") or [], prefix, serve_dir))
        except Exception as e:
            notes.append(f"Artwork originals could not be added: {e}")
        for field in sorted(request.files.keys()):
            if field.startswith("rawart-"):
                from werkzeug.utils import secure_filename
                up = request.files[field]
                slot = _safe_prefix(field[len("rawart-"):])
                dest = serve_dir / "art" / f"{prefix}-art-{slot}-{secure_filename(up.filename or 'art')}"
                dest.parent.mkdir(exist_ok=True)
                up.save(str(dest))
                files.append(("art", dest))

        # ── Print PDF ───────────────────────────────────────────────────────
        # Superseded by the press sheets, which carry the same artwork imposed
        # for the actual press, so it is only worth including for products
        # that have no template.
        job_id = meta.get("print_job_id")
        if job_id:
            job = get_job(job_id)
            src = None
            if job and job.get("serve_dir") and job.get("production_filename"):
                src = Path(job["serve_dir"]) / job["production_filename"]
            if (not press_ok or meta.get("keep_print")) and src and src.exists():
                dest = serve_dir / f"{prefix}-print.pdf"
                shutil.copy2(str(src), str(dest))
                files.append(dest)
                info_notes.extend((job or {}).get("print_notes") or [])
                # No press sheets means no proof from them: build Numo's proof
                # from the print file, with the job embedded for revisions.
                if not press_ok and isinstance(meta.get("proof"), dict):
                    try:
                        proof, two_by_two = _generic_proof(dest, prefix, serve_dir, meta["proof"], job,
                                                           order, meta.get("artist"), mockup_img)
                        files.append(proof)
                        if two_by_two:
                            files.append(two_by_two)
                        if isinstance(meta.get("snapshot"), dict):
                            try:
                                _embed_job(proof, meta["snapshot"],
                                           _with_embed_all(meta.get("embed_files") or meta.get("art_files") or [], meta))
                                job_saved = "ok"
                            except Exception as e:
                                job_saved = f"error: {e}"[:200]
                    except Exception as e:
                        import traceback; traceback.print_exc()
                        notes.append(f"The digital proof could not be built: {e}")
                # A jig product (the 0837) ships its jig files in place of the
                # print file: one per side that carries art, -SIDE1 / -SIDE2.
                _prod = PRODUCTS.get((meta.get("proof") or {}).get("product_id")
                                     or (job or {}).get("product_id") or "") or {}
                if _prod.get("mimaki_jig"):
                    try:
                        sides = {e.get("id") for e in ((job or {}).get("art_sizes") or []) if e.get("id")}
                        meta["_pen_sides"] = _pen_side_modes(job)
                        jig_files, jig_notes = _mimaki_jig_files(dest, _prod, sides, prefix, serve_dir,
                                                                 hand=meta.get("pen_hand") or "RH",
                                                                 variants=meta.get("pen_variants"))
                        info_notes.extend(jig_notes)
                        if jig_files:
                            files.remove(dest)
                            files.extend(jig_files)
                        else:
                            notes.append("No artwork on either side of the pen - no jig file made.")
                    except Exception as e:
                        import traceback; traceback.print_exc()
                        notes.append(f"The Mimaki jig files could not be built: {e}")
            if job and job.get("serve_dir"):
                shutil.rmtree(job["serve_dir"], ignore_errors=True)

        if not files:
            return jsonify({"error": "Nothing to export.",
                            "code": "empty"}), 400

        # The files go out one by one, named NSO-ITEM-ASSET, not as a zip.
        # See _deliverables: what ships, what each is called, and the press
        # files' fixed names for the hot folder.
        listing = _deliverables(files, meta, prefix, serve_dir, press_ok)
        if SANDBOX:
            listing = _sandbox_trim(listing, serve_dir)
        (serve_dir / "_files.json").write_text(json.dumps(listing))
        if isinstance(meta.get("variant"), dict):
            try:
                det = _two_by_two_details(meta)
            except Exception:
                det = {}
            v_stem, v_rev = _export_stem(meta, prefix)
            (serve_dir / "_variant.json").write_text(json.dumps({
                "variant": meta["variant"], "details": det, "prefix": prefix,
                "stem": v_stem, "rev": v_rev, "item": _export_item(meta),
                "notes": notes, "info": info_notes, "job_saved": job_saved}))
        shown = [e for e in listing if not e.get("hidden")]
        if not shown:
            return jsonify({"error": "Nothing to export.", "code": "empty"}), 400
        return jsonify({
            "export_id": serve_dir.name,
            "files": shown,
            "notes": " | ".join(notes)[:600] or None,
            "info": " | ".join(info_notes)[:600] or None,
            "job_saved": job_saved,
            "ink": ({"grams": meta["_ink"]["grams"], "sq_in": meta["_ink"]["sq_in"]} if meta.get("_ink") else None),
        })
    except Exception as e:
        shutil.rmtree(serve_dir, ignore_errors=True)
        return jsonify({"error": str(e)}), 500


# ---------------------------------------------------------------------------
# Make one colour — reduce multi-colour vector art for the one-ink program
# ---------------------------------------------------------------------------
#
# The configurator's easy button posts the uploaded file's saved path; the
# answer carries a proposal for every shape (print / knockout / remove), an ID
# map so a click can say which shape was hit, and the one-colour result. Each
# edit posts the same path with the artist's overrides. The result is written
# as its own PDF — black ink, white knockouts — and the slot then points at it,
# so the proof and the press sheets need no special handling.

_ONECOLOR_CACHE = {}


def _b64_file(path):
    import base64
    return base64.b64encode(Path(path).read_bytes()).decode()


# ---------------------------------------------------------------------------
# Layouts: stacked text lines and artwork, built into one vector PDF
# ---------------------------------------------------------------------------
#
# The configurator previews the stack in the browser while it is edited; the
# server builds the real file once, when the customer is done. The result is
# an ordinary vector PDF, so everything downstream — press sheets, one-color
# reduction, multi-color inks, proofs, Revise from proof — treats it exactly
# like an uploaded logo. Text is set with real fonts, never traced.

FONTS_DIR = HERE / "static" / "fonts"
LAYOUT_FONTS = {
    # key: (label, styles available)
    "Inter": ("Inter", ("Regular", "Bold", "RegularItalic", "BoldItalic")),
    "Montserrat": ("Montserrat", ("Regular", "Bold", "RegularItalic", "BoldItalic")),
    "Oswald": ("Oswald", ("Regular", "Bold")),
    "BebasNeue": ("Bebas Neue", ("Regular",)),
    "Anton": ("Anton", ("Regular",)),
    "Graduate": ("Graduate", ("Regular",)),
    "RobotoSlab": ("Roboto Slab", ("Regular", "Bold")),
    "PlayfairDisplay": ("Playfair Display", ("Regular", "Bold", "RegularItalic", "BoldItalic")),
    "Pacifico": ("Pacifico", ("Regular",)),
    "PermanentMarker": ("Permanent Marker", ("Regular",)),
}
_FONT_LOCK = threading.Lock()
_FONTS_REGISTERED = set()


def _layout_font(key, bold=False, italic=False):
    """ReportLab font name for a layout font, registering it on first use."""
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    fam = key if key in LAYOUT_FONTS else "Inter"
    styles = LAYOUT_FONTS[fam][1]
    want = ("Bold" if bold else "Regular") + ("Italic" if italic else "")
    style = next((st for st in (want, "Bold" if bold else "Regular", "Regular")
                  if st in styles), "Regular")
    name = f"{fam}-{style}"
    with _FONT_LOCK:
        if name not in _FONTS_REGISTERED:
            pdfmetrics.registerFont(TTFont(name, str(FONTS_DIR / f"{name}.ttf")))
            _FONTS_REGISTERED.add(name)
    return name


_FT_CACHE = {}


def _text_ink(font_name, text, size):
    """
    How far the letters of `text` actually reach above and below the baseline,
    in points: (top, bottom). Lines are stacked on these ink bounds rather
    than on the font's line box, so the gap the customer sets is the gap they
    see — the browser preview measures the same thing.
    """
    with _FONT_LOCK:                 # fontTools objects aren't thread-safe
        return _text_ink_locked(font_name, text, size)


def _text_ink_locked(font_name, text, size):
    try:
        from fontTools.ttLib import TTFont as FTFont
        ft = _FT_CACHE.get(font_name)
        if ft is None:
            ft = FTFont(str(FONTS_DIR / f"{font_name}.ttf"), lazy=True)
            _FT_CACHE[font_name] = ft
        cmap, glyf = ft.getBestCmap(), ft["glyf"]
        upm = ft["head"].unitsPerEm
        top, bot = None, None
        for ch in text:
            g = cmap.get(ord(ch))
            if not g:
                continue
            gl = glyf[g]
            if getattr(gl, "numberOfContours", 0) == 0:
                continue
            if not hasattr(gl, "yMax"):
                gl.recalcBounds(glyf)
            top = gl.yMax if top is None else max(top, gl.yMax)
            bot = gl.yMin if bot is None else min(bot, gl.yMin)
        if top is None:
            return None
        return top * size / upm, bot * size / upm
    except Exception as e:
        print(f"text ink measure failed ({font_name}): {e}")
        return None


@app.route("/api/layout-fonts")
def layout_fonts():
    out = []
    for key, (label, styles) in LAYOUT_FONTS.items():
        out.append({"key": key, "label": label, "styles": list(styles),
                    "files": {st: f"/static/fonts/{key}-{st}.ttf" for st in styles}})
    resp = jsonify(out)
    resp.headers["Cache-Control"] = "public, max-age=86400"
    return resp


def _layout_art_pdf(src, uploads, full_color=False):
    """
    A PDF for one artwork piece of a layout. Images are traced to vector —
    except on full-colour (4CP) items, where only flat-colour art is traced and
    a photo is embedded as the image itself, at its full resolution.
    """
    import press_layout, vectorize
    if vectorize.is_raster(str(src)):
        if full_color:
            vec = _vectorize_4cp(str(src))
            if vec:
                return Path(vec)
            out = Path(src).with_suffix(".4cp-image.pdf")
            if not out.exists():
                from reportlab.pdfgen import canvas as rlcanvas
                tight, iw, ih = crop_raster_to_visible(str(src))
                c = rlcanvas.Canvas(str(out), pagesize=(iw, ih))
                c.drawImage(tight, 0, 0, iw, ih, mask="auto")
                c.save()
            return out
        return _trace_for_one_color(Path(src), uploads)
    return Path(press_layout.art_as_pdf(str(src), work_dir=str(uploads)))


@app.route("/api/compose", methods=["POST"])
def compose_layout():
    import hashlib
    import press_layout
    from reportlab.pdfgen import canvas as rlcanvas
    from reportlab.pdfbase import pdfmetrics
    from reportlab.lib.colors import HexColor
    from pdfrw import PdfReader
    from pdfrw.buildxobj import pagexobj
    from pdfrw.toreportlab import makerl

    body = request.get_json(silent=True) or {}
    if body.get("version") == 2:
        return _compose_board(body)
    items = [i for i in (body.get("items") or []) if isinstance(i, dict)][:20]
    align = body.get("align") if body.get("align") in ("left", "center", "right") else "center"
    try:
        gap = max(0.0, min(400.0, float(body.get("gap", 12))))
    except (TypeError, ValueError):
        gap = 12.0
    slot = re.sub(r"[^a-z0-9_]", "", str(body.get("slot_id") or "layout"))[:20] or "layout"
    uploads = (HERE / "uploads").resolve()

    _pp = PRODUCTS.get(str(body.get("product_id") or "")) or {}
    full_color = bool(_pp.get("is_4cp") or "4cp" in str(_pp.get("material") or ""))
    key = hashlib.sha1(json.dumps([items, align, gap, full_color], sort_keys=True).encode()).hexdigest()[:12]
    out = uploads / f"{slot}_{key}_layout.pdf"
    if out.exists():
        return jsonify({"saved_path": str(out)})

    try:
        pieces = []                                   # (kind, w, h, data)
        for it in items:
            if it.get("type") == "text":
                txt = str(it.get("text") or "").strip()[:200]
                if not txt:
                    continue
                size = max(4.0, min(600.0, float(it.get("size") or 36)))
                fn = _layout_font(str(it.get("font") or "Inter"),
                                  bool(it.get("bold")), bool(it.get("italic")))
                w = pdfmetrics.stringWidth(txt, fn, size)
                ink = _text_ink(fn, txt, size) or pdfmetrics.getAscentDescent(fn, size)
                asc, desc = ink
                pieces.append(("text", w, asc - desc, dict(text=txt, font=fn, size=size, asc=asc,
                                                            color=str(it.get("color") or "#000000"))))
            elif it.get("type") == "art":
                src = Path(str(it.get("src") or "")).resolve()
                if uploads not in src.parents or not src.exists():
                    return jsonify({"error": "An artwork in this layout is no longer on the "
                                             "server. Remove it and add it again."}), 404
                pdf = _layout_art_pdf(src, uploads, full_color=full_color)
                art = press_layout.Artwork(str(pdf))
                width = max(10.0, min(3000.0, float(it.get("width") or 300)))
                s = width / art.w if art.w else 1.0
                pieces.append(("art", art.w * s, art.h * s, dict(pdf=str(pdf), art=art, s=s)))
        if not pieces:
            return jsonify({"error": "The layout is empty."}), 400

        W = max(p[1] for p in pieces)
        H = sum(p[2] for p in pieces) + gap * (len(pieces) - 1)
        c = rlcanvas.Canvas(str(out), pagesize=(W, H))
        y = H
        for kind, w, h, d in pieces:
            x = 0.0 if align == "left" else (W - w if align == "right" else (W - w) / 2)
            if kind == "text":
                col = d["color"] if re.fullmatch(r"#[0-9A-Fa-f]{6}", d["color"]) else "#000000"
                c.setFillColor(HexColor(col))
                c.setFont(d["font"], d["size"])
                c.drawString(x, y - d["asc"], d["text"])
            else:
                art, s = d["art"], d["s"]
                c.saveState()
                c.translate(x, y - h)
                c.scale(s, s)
                c.translate(-art.x0, -art.y0)
                c.doForm(makerl(c, pagexobj(PdfReader(d["pdf"]).pages[0])))
                c.restoreState()
            y -= h + gap
        c.showPage()
        c.save()
        return jsonify({"saved_path": str(out)})
    except Exception as e:
        import traceback; traceback.print_exc()
        try:
            out.unlink()
        except OSError:
            pass
        return jsonify({"error": f"Could not build the layout: {e}"}), 500


def _board_text_chars(text, font, size, spacing):
    """Per-character advances for board text: each glyph's own width plus the
    letter spacing (thousandths of an em). Drawn glyph by glyph, the same way
    the browser's preview does, so the two agree without either kerning."""
    from reportlab.pdfbase import pdfmetrics
    tr = size * float(spacing or 0) / 1000.0
    ws = [pdfmetrics.stringWidth(ch, font, size) for ch in text]
    total = sum(ws) + tr * max(0, len(text) - 1)
    return ws, tr, total


def _board_text_glyphs(it, font):
    """Where each glyph of a board text sits: (char, x, y, angle_rad) in board
    points, y DOWN, x/y the glyph's baseline centre, angle clockwise. The
    browser runs the same arithmetic (studioGlyphs)."""
    import math
    text = str(it.get("text") or "")[:200]
    size = max(4.0, min(600.0, float(it.get("size") or 36)))
    ws, tr, total = _board_text_chars(text, font, size, it.get("spacing"))
    cx, cy = float(it.get("x") or 0), float(it.get("y") or 0)
    by = cy + 0.35 * size
    curve = max(-100.0, min(100.0, float(it.get("curve") or 0)))
    out, pos = [], 0.0
    span = abs(curve) / 100.0 * math.pi
    R = total / span if span > 0.01 and total > 0 else None
    for ch, w in zip(text, ws):
        mid = pos + w / 2.0 - total / 2.0
        if R is None:
            out.append((ch, cx + mid, by, 0.0))
        elif curve > 0:                              # arch: centre below
            th = mid / R
            out.append((ch, cx + R * math.sin(th), by + R - R * math.cos(th), th))
        else:                                        # smile: centre above
            ph = mid / R
            out.append((ch, cx + R * math.sin(ph), by - R + R * math.cos(ph), -ph))
        pos += w + tr
    return out, size


def _board_shape(c, sh, H, HexColor):
    """A board shape on the reportlab canvas (y up). Same shapes as the
    browser: line, ring, frame, star, dot."""
    import math
    kind = sh.get("shape")
    x, y = float(sh.get("x") or 0), H - float(sh.get("y") or 0)
    w = max(1.0, float(sh.get("w") or 40)); h = max(1.0, float(sh.get("h") or w))
    t = max(0.25, float(sh.get("stroke") or 3))
    col = HexColor(sh.get("color") if re.fullmatch(r"#[0-9A-Fa-f]{6}", str(sh.get("color") or "")) else "#000000")
    c.saveState(); c.setFillColor(col); c.setStrokeColor(col); c.setLineWidth(t)
    if kind == "line":
        c.setLineCap(1); c.line(x - w / 2, y, x + w / 2, y)
    elif kind == "ring":
        c.circle(x, y, max(0.5, w / 2 - t / 2), stroke=1, fill=0)
    elif kind == "frame":
        r = min(w, h) * 0.12
        c.roundRect(x - w / 2 + t / 2, y - h / 2 + t / 2, w - t, h - t, r, stroke=1, fill=0)
    elif kind == "dot":
        c.circle(x, y, w / 2, stroke=0, fill=1)
    elif kind == "star":
        p = c.beginPath(); ro, ri = w / 2, w / 2 * 0.45
        for k in range(10):
            r_ = ro if k % 2 == 0 else ri
            a = math.pi / 2 + k * math.pi / 5
            (p.moveTo if k == 0 else p.lineTo)(x + r_ * math.cos(a), y + r_ * math.sin(a))
        p.close(); c.drawPath(p, stroke=0, fill=1)
    c.restoreState()


def _compose_board(body):
    """
    Design-studio layouts: everything placed freely on a board the size of
    the imprint area (points; x/y are each item's centre, y down). Text can be
    letter-spaced and curved; simple shapes; artwork. Writes a PDF the size of
    the board and returns where the ink sits on it, so the browser can set the
    art at exactly the size and place it was designed.
    """
    import hashlib, math
    import press_layout
    from reportlab.pdfgen import canvas as rlcanvas
    from reportlab.lib.colors import HexColor
    from pdfrw import PdfReader
    from pdfrw.buildxobj import pagexobj
    from pdfrw.toreportlab import makerl
    try:
        W = max(10.0, min(5000.0, float(body.get("W") or 0)))
        H = max(10.0, min(5000.0, float(body.get("H") or 0)))
    except (TypeError, ValueError):
        return jsonify({"error": "The design has no size."}), 400
    items = [i for i in (body.get("items") or []) if isinstance(i, dict)][:40]
    slot = re.sub(r"[^a-z0-9_]", "", str(body.get("slot_id") or "layout"))[:20] or "layout"
    uploads = (HERE / "uploads").resolve()
    _pp = PRODUCTS.get(str(body.get("product_id") or "")) or {}
    full_color = bool(_pp.get("is_4cp") or "4cp" in str(_pp.get("material") or ""))
    key = hashlib.sha1(json.dumps([items, W, H, full_color, 2], sort_keys=True).encode()).hexdigest()[:12]
    out = uploads / f"{slot}_{key}_design.pdf"
    try:
        if not out.exists():
            c = rlcanvas.Canvas(str(out), pagesize=(W, H))
            drawn = 0
            for it in items:
                kind = it.get("type")
                if kind == "text":
                    if not str(it.get("text") or "").strip():
                        continue
                    fn = _layout_font(str(it.get("font") or "Inter"), bool(it.get("bold")), bool(it.get("italic")))
                    glyphs, size = _board_text_glyphs(it, fn)
                    col = str(it.get("color") or "#000000")
                    c.saveState()
                    c.setFillColor(HexColor(col if re.fullmatch(r"#[0-9A-Fa-f]{6}", col) else "#000000"))
                    c.setFont(fn, size)
                    from reportlab.pdfbase import pdfmetrics
                    for ch, gx, gy, ang in glyphs:
                        if not ch.strip():
                            continue
                        cw = pdfmetrics.stringWidth(ch, fn, size)
                        c.saveState(); c.translate(gx, H - gy); c.rotate(-math.degrees(ang))
                        c.drawString(-cw / 2, 0, ch); c.restoreState()
                    c.restoreState(); drawn += 1
                elif kind == "shape":
                    _board_shape(c, it, H, HexColor); drawn += 1
                elif kind == "art":
                    src = Path(str(it.get("src") or "")).resolve()
                    if uploads not in src.parents or not src.exists():
                        return jsonify({"error": "An artwork in this design is no longer on the "
                                                 "server. Remove it and add it again."}), 404
                    pdf = _layout_art_pdf(src, uploads, full_color=full_color)
                    art = press_layout.Artwork(str(pdf))
                    w = max(4.0, min(5000.0, float(it.get("w") or 100)))
                    s_ = w / art.w if art.w else 1.0
                    x, y = float(it.get("x") or 0), float(it.get("y") or 0)
                    c.saveState()
                    c.translate(x - art.w * s_ / 2, H - y - art.h * s_ / 2)
                    c.scale(s_, s_); c.translate(-art.x0, -art.y0)
                    c.doForm(makerl(c, pagexobj(PdfReader(str(pdf)).pages[0])))
                    c.restoreState(); drawn += 1
            if not drawn:
                return jsonify({"error": "The design is empty."}), 400
            c.showPage(); c.save()
        from screenprint import ink_bbox_points
        ink = ink_bbox_points(str(out), (0, 0, W, H), dpi=200) or (0, 0, W, H)
        x0, y0, x1, y1 = ink
        return jsonify({"saved_path": str(out), "W": W, "H": H,
                        "bbox": [x0, H - y1, x1, H - y0]})          # board coords, y down
    except Exception as e:
        import traceback; traceback.print_exc()
        try:
            out.unlink()
        except OSError:
            pass
        return jsonify({"error": f"Could not build the design: {e}"}), 500


def _to_rgb_pdf(pdf_path):
    """Every colour in the print file in RGB, converted the way the preview was."""
    import rgbify
    rgbify.convert(pdf_path)


def _pdf_has_images(path):
    """Whether a vector file carries placed images (or smooth shades)."""
    try:
        import pikepdf
        with pikepdf.open(path) as pdf:
            seen = set()
            def walk(res):
                if res is None:
                    return False
                if res.get("/Shading"):
                    return True
                for _, x in (res.get("/XObject") or {}).items():
                    if x.objgen in seen:
                        continue
                    seen.add(x.objgen)
                    if x.get("/Subtype") == "/Image" and int(x.get("/Width", 0)) * int(x.get("/Height", 0)) > 64:
                        return True
                    if x.get("/Subtype") == "/Form" and walk(x.get("/Resources")):
                        return True
                return False
            return walk(pdf.pages[0].Resources)
    except Exception:
        return False


def _fill_spot_name(body):
    """The Pantone a 4CP solid background is: the PMS picked or matched for
    it, else the one a stock colour names ("Red PMS 200" -> PANTONE 200 C)."""
    import re as _re
    nm = (body.get("fill_solid_pms") or "").strip()
    if not nm:
        m = _re.search(r"\bPMS\s*([0-9A-Za-z][0-9A-Za-z \-]*)$", str(body.get("fill_stock_name") or ""))
        if m:
            nm = m.group(1).strip()
            if not _re.search(r"\s[CU]$", nm):
                nm += " C"
    if not nm:
        return None
    return nm if nm.upper().startswith("PANTONE") else "PANTONE " + nm


def _spot_rect(c, x, y, w, h, name, rgb, work_dir):
    """A rectangle filled with the named spot `name`, its alternate the exact
    RGB the picker shows, placed on reportlab canvas `c` as a form."""
    import pikepdf, hashlib
    from pdfrw import PdfReader
    from pdfrw.buildxobj import pagexobj
    from pdfrw.toreportlab import makerl
    key = hashlib.sha1(f"{name}|{rgb}|{w:.2f}|{h:.2f}".encode()).hexdigest()[:10]
    path = Path(work_dir) / f"spot-{key}.pdf"
    if not path.exists():
        pdf = pikepdf.new()
        pg = pdf.add_blank_page(page_size=(w, h))
        sep = pdf.make_indirect(pikepdf.Array([
            pikepdf.Name.Separation, pikepdf.Name("/" + name), pikepdf.Name.DeviceRGB,
            pikepdf.Dictionary(FunctionType=2, Domain=[0, 1], C0=[1, 1, 1],
                               C1=[round(v, 4) for v in rgb], N=1)]))
        pg.obj.Resources = pikepdf.Dictionary(ColorSpace=pikepdf.Dictionary(SpotBg=sep))
        pg.obj.Contents = pdf.make_stream(f"/SpotBg cs 1 scn 0 0 {w:.3f} {h:.3f} re f".encode())
        pdf.save(str(path))
    xobj = pagexobj(PdfReader(str(path)).pages[0])
    c.saveState()
    c.translate(x, y)
    c.doForm(makerl(c, xobj))
    c.restoreState()


def _recolor_art(art_path, inks, bg_hex=None, full_color=False):
    """
    The art with each color replaced by its assigned Pantone, as a PDF of named
    spots. `inks` is the configurator's list for the location:
    [{hex, sources, pms, pms_hex, hidden}].
    """
    import hashlib, onecolor, press_layout, vectorize
    src = Path(art_path)
    key = hashlib.sha1(json.dumps([str(src), inks, bg_hex, full_color], sort_keys=True).encode()).hexdigest()[:10]
    out = src.with_name(f"{src.stem}.pms-{key}.pdf")
    if out.exists():
        return str(out)
    # White is paint here, not a spot: a white "spot" has an empty CMYK
    # alternate and would print nothing over a 4CP background. Inks whose
    # Pantone is white are painted solid white; white the customer marked
    # "don't print" is left out so the background shows.
    def _white(h):
        h = str(h or "").lstrip("#")
        return len(h) == 6 and min(int(h[k:k + 2], 16) for k in (0, 2, 4)) > 235
    trace_inks = inks
    inks = [dict(i, paint_white=True) if not i.get("hidden") and _white(i.get("pms_hex") or i.get("hex"))
            else i for i in inks]
    overprint = False
    if vectorize.is_raster(str(src)):
        # Transparent images: white that is still opaque is design, not
        # background, so the background is a colour nothing maps to.
        bg = bg_hex
        if not bg:
            from PIL import Image as _Im
            with _Im.open(str(src)) as im:
                if "A" in im.getbands() and im.getchannel("A").getextrema()[0] < 250:
                    bg = "#01FE01"
        vec = _as_vector(str(src), {}, src.parent, inks=trace_inks, bg_hex=bg)
        overprint = True
    else:
        vec = press_layout.art_as_pdf(str(src), work_dir=str(src.parent))
    # Every item gets named spots, one per Pantone. On 4CP each spot's
    # alternate is the Pantone's screen colour in RGB — what the colour picker
    # shows — so the proof and any viewer show exactly that, and the Fiery
    # matches the Pantone by name. Pens and totes keep CMYK alternates.
    onecolor.separate(vec, inks, str(out), mode="press",
                      overprint=overprint, knockout_white=False,
                      alternate="rgb" if full_color else "cmyk")
    return str(out)


# ---------------------------------------------------------------------------
# 4CP artwork: vector when possible, else at least 250 DPI
# ---------------------------------------------------------------------------
MIN_4CP_DPI = 250


def _vectorize_4cp(art_path):
    """
    A full-colour vector PDF of a flat-colour image, or None for photographic
    art. Uses the same test as the standard items: few distinct colours and
    most of the image made of them (photos and gradients score far lower).
    """
    import vectorize
    from screenprint import analyze_separations
    if not vectorize.available() or not vectorize.is_raster(str(art_path)):
        return None
    out = Path(art_path).with_suffix(".4cp-vector.pdf")
    if out.exists():
        return str(out)
    sep = analyze_separations(str(art_path), max_inks=16)
    inks = vectorize.drop_blend_inks(sep.get("inks") or [])
    if not inks or len(inks) > 12:
        return None
    rgbs = [tuple(int(i["hex"][k:k + 2], 16) for k in (1, 3, 5)) for i in inks]
    if vectorize.flat_share(str(art_path), rgbs, tol=24) < 0.85:
        return None
    colors = [(i["hex"].lstrip("#"), rgb) for i, rgb in zip(inks, rgbs)]
    bg = (255, 255, 255)
    # With transparency, white that is still opaque is part of the design (a
    # white ring, white lettering) and must print white over a dark
    # background — not fall away as "background" and let the fill show through.
    import numpy as np
    from PIL import Image as _Im
    a = np.asarray(_Im.open(str(art_path)).convert("RGBA")).astype(int)
    opaque = a[..., 3] > 128
    if (a[..., 3] < 250).any() and opaque.any():
        white = opaque & (a[..., :3].min(axis=2) > 235)
        if white.sum() > 0.005 * opaque.sum():
            # Pure white must map to the white ink, not to a white "background"
            # that the tracer leaves empty (which would print as a hole).
            colors = [(h, c) for h, c in colors if min(c) <= 235]
            colors.append(("FFFFFF", (255, 255, 255)))
            bg = (1, 254, 1)            # a colour no artwork uses: nothing maps to it
    vectorize.trace(str(art_path), out, colors=colors, bg=bg)
    return str(out)


# ---------------------------------------------------------------------------
# Fiery notches for 4CP print files
# ---------------------------------------------------------------------------
# The Fiery templates carry the cut notches in a spot named "Notches". The
# notches have to stand out against whatever is printed under them: black on a
# light design, white on a dark one, and a vivid colour on mid tones or busy
# textures. The design is rendered, the pixels under every notch are measured,
# and the candidate with the best worst-case contrast wins. The spot keeps its
# name; only its colour changes.
_NOTCH_CANDIDATES = [            # name, sRGB, CMYK
    ("black",   (0, 0, 0),       [0, 0, 0, 1]),
    ("white",   (255, 255, 255), [0, 0, 0, 0]),
    ("yellow",  (255, 237, 0),   [0, 0, 1, 0]),
    ("magenta", (236, 0, 140),   [0, 1, 0, 0]),
    ("cyan",    (0, 174, 239),   [1, 0, 0, 0]),
]


def _rel_lum(rgb):
    import numpy as np
    c = np.asarray(rgb, dtype=float) / 255.0
    c = np.where(c <= 0.03928, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
    return 0.2126 * c[..., 0] + 0.7152 * c[..., 1] + 0.0722 * c[..., 2]


def _apply_fiery_notches(pdf_path, template_path, dpi=36):
    import numpy as np, pikepdf, subprocess, tempfile
    from PIL import Image
    from pdfrw import PdfReader, PdfWriter, PageMerge

    work = Path(tempfile.mkdtemp(prefix="fiery_"))
    try:
        # The template with its guide layer emptied: notches only.
        tpl = pikepdf.open(str(template_path))
        page = tpl.pages[0]
        for _, x in (page.Resources.get("/XObject") or {}).items():
            if x.get("/Subtype") == "/Form":
                x.write(b"")
        cs = next((v for v in (page.Resources.get("/ColorSpace") or {}).values()
                   if isinstance(v, pikepdf.Array) and str(v[0]) == "/Separation"
                   and str(v[1]) == "/Notches"), None)
        if cs is None:
            return "template has no Notches spot"

        def set_cmyk(cmyk):
            cs[2] = pikepdf.Name.DeviceCMYK
            cs[3] = pikepdf.Dictionary(FunctionType=2, Domain=[0, 1], N=1,
                                       C0=[0, 0, 0, 0], C1=cmyk)

        # Where the notches are: render them black on white.
        set_cmyk([0, 0, 0, 1])
        mask_pdf = work / "mask.pdf"; tpl.save(str(mask_pdf))
        subprocess.run(["pdftoppm", "-png", "-r", str(dpi), "-singlefile", str(mask_pdf),
                        str(work / "mask")], check=True)
        subprocess.run(["pdftoppm", "-png", "-r", str(dpi), "-singlefile", str(pdf_path),
                        str(work / "art")], check=True)
        m = np.asarray(Image.open(work / "mask.png").convert("L")) < 128
        art = Image.open(work / "art.png").convert("RGB")
        if art.size != (m.shape[1], m.shape[0]):
            art = art.resize((m.shape[1], m.shape[0]))
        a = np.asarray(art)
        # Under and just around each notch.
        grow = m.copy()
        for _ in range(3):
            g = grow.copy()
            g[1:, :] |= grow[:-1, :]; g[:-1, :] |= grow[1:, :]
            g[:, 1:] |= grow[:, :-1]; g[:, :-1] |= grow[:, 1:]
            grow = g
        px = a[grow]
        if not len(px):
            px = np.array([[255, 255, 255]])
        L = _rel_lum(px)
        best, best_score = None, -1
        for name, rgb, cmyk in _NOTCH_CANDIDATES:
            lc = float(_rel_lum(np.array(rgb)))
            ratio = (np.maximum(L, lc) + 0.05) / (np.minimum(L, lc) + 0.05)
            score = float(np.percentile(ratio, 10))      # worst-case, not average
            if score > best_score + 0.25:                 # prefer earlier (black/white) on near-ties
                best, best_score = (name, cmyk), score
        set_cmyk(best[1])
        notch_pdf = work / "notches.pdf"; tpl.save(str(notch_pdf))

        base = PdfReader(str(pdf_path))
        over = PdfReader(str(notch_pdf)).pages[0]
        PageMerge(base.pages[0]).add(over).render()
        PdfWriter(str(pdf_path), trailer=base).write()
        return f"{best[0]} (contrast {best_score:.1f}:1)"
    finally:
        shutil.rmtree(work, ignore_errors=True)


def _trace_for_one_color(srcp, uploads):
    """Trace a raster upload into per-color vector shapes, once per file."""
    import vectorize
    from screenprint import analyze_separations
    out = uploads / f"{srcp.stem}.octrace.pdf"
    if out.exists() and out.stat().st_mtime >= srcp.stat().st_mtime:
        return out
    if not vectorize.available():
        raise RuntimeError("the image tracer is not installed on this server")
    sep = analyze_separations(str(srcp), max_inks=12)
    inks = vectorize.drop_blend_inks(sep.get("inks") or [])
    colors = []
    for i in inks:
        h = str(i.get("hex") or "").lstrip("#")
        if len(h) == 6:
            colors.append((h, tuple(int(h[k:k + 2], 16) for k in (0, 2, 4))))
    bg = (255, 255, 255)
    b = str(sep.get("background_hex") or "").lstrip("#")
    if len(b) == 6:
        bg = tuple(int(b[k:k + 2], 16) for k in (0, 2, 4))
    vectorize.trace(str(srcp), out, colors=colors or None, bg=bg)
    return out


@app.route("/api/one-color", methods=["POST"])
def one_color():
    import hashlib
    import onecolor
    import press_layout
    body = request.get_json(silent=True) or {}
    src = body.get("art_path") or ""
    uploads = (HERE / "uploads").resolve()
    try:
        srcp = Path(src).resolve()
    except Exception:
        return jsonify({"error": "Unknown artwork."}), 400
    if uploads not in srcp.parents or not srcp.exists():
        return jsonify({"error": "The uploaded artwork could not be found. Upload it again."}), 404
    ext = srcp.suffix.lower()
    import vectorize
    raster = vectorize.is_raster(str(srcp))
    if ext not in {".pdf", ".ai", ".svg", ".eps"} and not raster:
        return jsonify({"error": "Make one color needs vector artwork or a PNG/JPG."}), 400
    try:
        if raster:
            # An image goes through the same editor as vector art: it is traced
            # first, one set of shapes per color it contains, and those shapes
            # are what get printed, knocked out or removed.
            pdf = _trace_for_one_color(srcp, uploads)
        else:
            pdf = Path(press_layout.art_as_pdf(str(srcp), work_dir=str(uploads)))
        key = (str(pdf), pdf.stat().st_mtime)
        an = _ONECOLOR_CACHE.get(key)
        if an is None:
            if len(_ONECOLOR_CACHE) > 64:
                _ONECOLOR_CACHE.clear()
            an = onecolor.analyze(pdf, uploads / "_onecolor")
            _ONECOLOR_CACHE[key] = an
        auto = {s["i"]: s["auto"] for s in an["shapes"]}
        raw = body.get("decisions") or {}
        decisions = {str(k): v for k, v in raw.items()
                     if v in ("print", "knockout", "remove")}
        if all(v == "remove" or auto.get(int(k)) == "remove" for k, v in decisions.items()) \
                and len(decisions) >= len(auto) and auto:
            return jsonify({"error": "That removes everything."}), 400
        tag = hashlib.sha1(json.dumps(sorted(decisions.items())).encode()).hexdigest()[:8]
        out = uploads / f"{pdf.stem}.1c-{tag}.pdf"
        onecolor.apply(pdf, decisions, auto, out)
        prev, pw, ph = onecolor.preview(out, uploads / "_onecolor" / f"{out.stem}.mask.png")
        effective = {str(s["i"]): decisions.get(str(s["i"]), s["auto"]) for s in an["shapes"]}
        return jsonify({
            "shapes": [{k: s.get(k) for k in ("i", "hex", "auto", "why", "area", "kind")}
                       for s in an["shapes"]],
            "groups": an["groups"],
            "decisions": effective,
            "idmap_b64": _b64_file(an["idmap_png"]),
            "colour_b64": _b64_file(an["colour_png"]),
            "grid": {"width": an["width"], "height": an["height"]},
            "preview_b64": _b64_file(prev),
            "width": pw, "height": ph,
            "saved_path": str(out),
        })
    except Exception as e:
        import traceback; traceback.print_exc()
        return jsonify({"error": f"Could not reduce this artwork: {e}"}), 500


# ---------------------------------------------------------------------------
# Revise from proof
# ---------------------------------------------------------------------------

@app.route("/api/restore", methods=["POST"])
def restore_from_proof():
    import pikepdf, uuid
    up = request.files.get("file")
    if not up or not (up.filename or "").lower().endswith(".pdf"):
        return jsonify({"error": "Drop in the digital proof PDF."}), 400
    token = uuid.uuid4().hex[:16]
    rdir = HERE / "uploads" / "_restore" / token
    rdir.mkdir(parents=True, exist_ok=True)
    src = rdir / "proof.pdf"
    up.save(str(src))
    try:
        pdf = pikepdf.open(str(src))
        att = pdf.attachments
    except Exception:
        return jsonify({"error": "That file couldn't be read as a PDF."}), 400
    if JOB_ATTACHMENT in att:
        try:
            snap = json.loads(att[JOB_ATTACHMENT].get_file().read_bytes())
        except ValueError:
            return jsonify({"error": "The job inside that proof couldn't be read."}), 400
        if not isinstance(snap, dict):
            return jsonify({"error": "The job inside that proof couldn't be read."}), 400
        arts = snap.get("art")
        snap["art"] = [r for r in arts if isinstance(r, dict)] if isinstance(arts, list) else []
        for rec in snap["art"]:
            # Paths are set below from the proof's own attachments, never read from it.
            rec.pop("orig_path", None)
            rec.pop("one_color_path", None)
        for rec in snap.get("art") or []:
            for kind in ("orig", "one_color"):
                name = rec.get(kind)
                if name and name in att:
                    theirs = rec.get("name") or name
                    if kind == "one_color":
                        theirs = Path(theirs).stem + ".1color" + Path(name).suffix
                    dest = _upload_path("restore", theirs)
                    dest.write_bytes(att[name].get_file().read_bytes())
                    rec[kind + "_path"] = str(dest)
        snap["legacy"] = False
    else:
        snap = _read_old_proof(src)
        # An older proof the reader can't place on an item (another layout of
        # "DIGITAL PROOF") gives an empty job; its art can still be picked out.
        if snap and not snap.get("pid") and not snap.get("sizes"):
            snap = None
        if not snap:
            # A customer's filled-in This Is Fast template: the art is cut out
            # of the imprint locations and opened as a new job (tif_import.py).
            try:
                import tif_import
                stem = re.sub(r"[^A-Za-z0-9_-]+", "_", Path(up.filename).stem)[:40] or "template"
                snap = tif_import.extract(src, rdir / "art", stem)
            except Exception as e:
                import traceback; traceback.print_exc()
                snap = None
            if snap and snap.get("empty"):
                return jsonify({"error": f"That's our {snap['pid']} template, but there's no art "
                                         "in the imprint locations on page 1 or 2."}), 400
        if not snap:
            # Not ours: the page can still carry the customer's art (a mockup,
            # an approval form, another supplier's template). The page offers
            # to pick it out (art_pick.py).
            return jsonify({"error": "That doesn't look like one of our digital proofs "
                                     "or a filled-in This Is Fast template.",
                            "code": "not_proof"}), 400
    if snap.get("pid") and snap["pid"] not in PRODUCTS:
        return jsonify({"error": f"Item {snap['pid']} isn't in the catalog."}), 400
    bundle = {"token": token, "job": snap}
    (rdir / "bundle.json").write_text(json.dumps(bundle))
    return jsonify(bundle)


# ---------------------------------------------------------------------------
# Pick the art out of a mockup, an approval form or another template
# ---------------------------------------------------------------------------
_PICK_TOKEN = re.compile(r"^[0-9a-f]{16}$")


@app.route("/api/art-pick", methods=["POST"])
def art_pick_analyze():
    """
    A PDF/AI with the customer's art somewhere on it: the page, its pieces
    (outlined boxes) and where each one probably goes. Either a file, or the
    token of an earlier read plus another page number.
    """
    import art_pick
    pid = request.form.get("product_id") or ""
    prod = PRODUCTS.get(pid) or {}
    slot_ids = [s["id"] for s in (prod.get("art_slots") or [])] or ["side1"]
    page = request.form.get("page")
    page_index = int(page) - 1 if page and page.isdigit() else None
    token = request.form.get("token") or ""
    if token:
        if not _PICK_TOKEN.match(token):
            return jsonify({"error": "Unknown."}), 404
        src = art_pick.pick_dir(HERE / "uploads") / token / "src.pdf"
        if not src.exists():
            return jsonify({"error": "That file has expired — drop it in again."}), 404
    else:
        up = request.files.get("file")
        if not up or not up.filename:
            return jsonify({"error": "No file"}), 400
        ext = Path(up.filename).suffix.lower()
        if ext not in (".pdf", ".ai"):
            return jsonify({"error": "Pick art from a PDF or AI file."}), 400
        src = _upload_path("pick", up.filename)
        up.save(str(src))
    try:
        with open(src, "rb") as fh:
            if fh.read(5) != b"%PDF-":
                return jsonify({"error": "That AI file was saved without PDF content — "
                                         "save it with \"Create PDF Compatible File\" on."}), 400
        a = art_pick.analyze(src, HERE / "uploads", slot_ids, page_index)
    except Exception as e:
        import traceback; traceback.print_exc()
        return jsonify({"error": f"Couldn't read that file: {e}"}), 400
    import base64 as _b64
    a["png_b64"] = _b64.b64encode(a.pop("png")).decode()
    a["slots"] = [{"id": s["id"], "label": s.get("label") or s["id"]} for s in (prod.get("art_slots") or [])]
    return jsonify(a)


@app.route("/api/art-pick/place", methods=["POST"])
def art_pick_place():
    """The chosen pieces, cut out as one vector PDF per location."""
    import art_pick
    body = request.get_json(force=True) or {}
    token = str(body.get("token") or "")
    if not _PICK_TOKEN.match(token):
        return jsonify({"error": "Unknown."}), 404
    if not (art_pick.pick_dir(HERE / "uploads") / token / "pieces.json").exists():
        return jsonify({"error": "That file has expired — drop it in again."}), 404
    assign = {str(k): [int(i) for i in v] for k, v in (body.get("assign") or {}).items()
              if re.match(r"^[a-z0-9_]{1,24}$", str(k)) and isinstance(v, list)}
    rot = {str(k): (180 if int(v or 0) == 180 else 0) for k, v in (body.get("rot") or {}).items()}
    if not any(assign.values()):
        return jsonify({"error": "Choose the art for at least one location."}), 400
    try:
        out = art_pick.place(HERE / "uploads", token, assign, rot)
    except Exception as e:
        import traceback; traceback.print_exc()
        return jsonify({"error": f"Couldn't cut the art out: {e}"}), 500
    return jsonify({"files": out})


@app.route("/api/restore/<token>")
def restore_bundle(token):
    if not re.match(r"^[0-9a-f]{16}$", token):
        return jsonify({"error": "Unknown."}), 404
    f = HERE / "uploads" / "_restore" / token / "bundle.json"
    if not f.exists():
        return jsonify({"error": "That revision link has expired — drop the proof in again."}), 404
    return jsonify(json.loads(f.read_text()))


@app.route("/api/restore-file/<token>/<int:key>/<kind>")
def restore_file(token, key, kind):
    if not re.match(r"^[0-9a-f]{16}$", token) or kind not in ("orig", "one_color"):
        return jsonify({"error": "Unknown."}), 404
    f = HERE / "uploads" / "_restore" / token / "bundle.json"
    if not f.exists():
        return jsonify({"error": "Expired."}), 404
    job = json.loads(f.read_text())["job"]
    rec = next((r for r in job.get("art") or [] if isinstance(r, dict) and r.get("key") == key), None)
    path = _in_uploads(rec and rec.get(kind + "_path"))
    if not path:
        return jsonify({"error": "Missing."}), 404
    return send_file(path, as_attachment=True,
                     download_name=(rec.get("name") if kind == "orig" else Path(path).name))


# ---------------------------------------------------------------------------
# Artist mode (the sandbox keeps clients in the client view)
# ---------------------------------------------------------------------------
#
#   ARTIST_PASSCODE      if set, artist mode asks for it once per browser.

_EXPORT_ID = re.compile(r"^export_\d+$")


@app.route("/api/artist/config")
def artist_config():
    return jsonify({
        "passcode_required": bool(os.environ.get("ARTIST_PASSCODE")),
    })


@app.route("/api/artist/unlock", methods=["POST"])
def artist_unlock():
    import hmac
    want = os.environ.get("ARTIST_PASSCODE", "")
    if not want:
        return jsonify({"ok": True})
    got = str((request.get_json(silent=True) or {}).get("code") or "")
    time.sleep(0.4)          # enough to make guessing tedious
    return jsonify({"ok": hmac.compare_digest(got.encode(), want.encode())})


@app.route("/api/export-files/<export_id>")
def export_files(export_id):
    if not _EXPORT_ID.match(export_id):
        return jsonify({"error": "Unknown export."}), 404
    manifest = HERE / "_serve" / export_id / "_files.json"
    if not manifest.exists():
        return jsonify({"error": "These files have expired. Export again."}), 404
    return jsonify({"files": json.loads(manifest.read_text())})


@app.route("/api/export-file/<export_id>/<path:rel>")
def export_file(export_id, rel):
    if not _EXPORT_ID.match(export_id):
        return jsonify({"error": "Unknown export."}), 404
    root = (HERE / "_serve" / export_id).resolve()
    manifest = root / "_files.json"
    if not manifest.exists():
        return jsonify({"error": "These files have expired. Export again."}), 404
    allowed = {e["path"] for e in json.loads(manifest.read_text())
               if not (SANDBOX and (e.get("hidden") or e.get("kind") not in SANDBOX_KINDS))}
    if rel not in allowed:
        return jsonify({"error": "Unknown file."}), 404
    f = (root / rel).resolve()
    if root not in f.parents or not f.exists():
        return jsonify({"error": "Unknown file."}), 404
    return send_file(str(f), as_attachment=True, download_name=f.name)


def _ink_coverage(slots):
    """ink_coverage.job() for {slot: {path, w_in, inks}} from the browser,
    reading only files in uploads/."""
    import ink_coverage
    clean = {}
    for sid, v in (slots or {}).items():
        if not isinstance(v, dict):
            continue
        p = _in_uploads(v.get("path"))
        try:
            w = float(v.get("w_in")) if v.get("w_in") else None
        except (TypeError, ValueError):
            w = None
        inks = [i for i in (v.get("inks") or []) if isinstance(i, dict)] or None
        one = str(v.get("one_ink"))[:60] if v.get("one_ink") else None
        clean[_safe_prefix(str(sid))[:24]] = {"path": str(p) if p else None, "w_in": w, "inks": inks, "one_ink": one}
    return ink_coverage.job(clean)


@app.route("/api/ink-coverage", methods=["POST"])
def ink_coverage_route():
    """Square inches and grams of ink per imprint and for the item, as the
    art department's InkCoverage.jsx works them out (ink_coverage.py)."""
    if SANDBOX:
        return jsonify({"error": "Not available in the sandbox."}), 404
    body = request.get_json(silent=True) or {}
    try:
        return jsonify(_ink_coverage(body.get("slots")))
    except Exception as e:
        return jsonify({"error": str(e)[:200]}), 500


_FAVICON_PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAACAAAAAgCAYAAABzenr0AAAFiklEQVR42r1XXWwcVxX+zrkz47XHsV1D3CRIKBQVRQ4IFSGVB/oEFVJBqC3sSjxVKlIsNf7ZZIkqHmB2xENonbF3dwhqLEEq4IUZHhDwhCBSJaBF6SNeKTxWaQxu3eZnnWxm7r2Hh91tF2OT3ThwpJVWc6/u/e53vu/cc4EhIggC7v0XEapUKn7/t2KxqDBk0JBzpVwuPwF2nrPGfp4gEwK6SUyXtdU/PV+vvx4EAYdhaPcLgIIg6J3GNptNSpLElsunGsr15pkYWuew1oKZ4boujDG4m2U/OB/Xv18sFlWapuaBMjC/uNQY98cXWq2WASCe5znMDK01tNYZEamxsTG1fWd76Uf1emNQELQbzZVKZcYYeR6gDSL7B63xKW/EvZRlWU5EDjOTMfoSMb8lVh5zXfezeZ4bZoaIbLsOPxpF0aaIEBHJfwPg7BAZhWEoWZZ9rDDqnwWAdrt9HZA7WmsBwMws1thvx436xZ4Yl05VXnQc52ye53mhUJhoZ+2nALxarVYVAD0wgF4opSjPNYzRORFNEfOUMcZ4nqfyXL8ZN1YvBkHAGxsbiohyAD9cWCjPMfNRAMKiHgPw6iCp5V0/Mres2CtKKZeIYLS2RAQiggAbQRBws9mktbU13RUsg3CLiCEiJGJnAKDZbMpQAHr2WVlZ+ftDkwc+bbT5OoB/OK7LACwAKBK1w2ZSrVYFIP5AUYTCoOLmvQbCsGriuPZba/JnALT3nCtCfcUJIoIe2NnZWbpvAAChWCyqOI7fMMZcUUqp7uLoq3wMIknTlEWERzwvLxQKOQQmSRIVhqGWPoBDAoCkaWo6VsIHlNs+FGmamiiKRkulkhHIrY8enKGHDx3hkZGRrVKpZKIomr6XDfmehWKPBdI0tedqtS+6I37z5eWV5MjhI4/4/rjjOErNPHzoq8srtVe80fH15Wh1scNWoga24SBRLBYZoqYBOToxOXX09nbrd+3b2z+xLLdZqWdHCoU513HQBk8lSaLW19fpwQDoMpKmqUnT9DfLUa2VZVn6ndNLz/fN+n1Ua/yJgJ+LkV+XSiXTf2vuA8CHhzi3Gn/FdVXFaMNisu+JCK2trTnXrl0TAKiUF3/xcrT64qg/9quVWnzeH/V+LB1ByVAa+M+boqNqEnP24MGZJ7U2m9PT01sAMDc3p8Mw1MePHxcRIWb1t8nJiUdFpOZ5nk9EstMVwwGQD1NgGXPv/HPzonKcw1tbWx8nIkmSxL1w4YK7vr7eOanYx9+/fv2SEH/Z9/1bHU3/OwPOsAyIEQMAZ8rlywAuL5+rPUPKWz1x4sTTpVIp602NVuvfLRRGP3G7deNrZ86caXY1IPsWYe8EQRDw+NRHnh4rFKYcx33q2OxnLp9brf+MQNsQ+caYP/6koxTuKG8xSZKTXRfYoevA3qU6FCV8RWv91xs33lu9efPmtD/mRwcOTLyS5/rwdqu12L7b/guIXiuVSma3zfddB06fnl8H8AUAOHly4Uue686M+T5vbm7+eSV6KQYQ77zo7pMBkm7+ZLcu+VQUjbJSB9599x2+9vZVyrO7U0EQON0fD92Q7CI+pk6AhKg/DQCAq1cBgLU2bscsImEY6m5faPcPQCQTkVyshYXNdw5rrS1IWSKg27jQoA3vQClQTM9CzDFr8mPMMt8rxb3xRqORAWgRUacnAA4BkNnZWRm8tt5n9B4iC4vl11zXfSLLclGK74h1ZxuNl96610OFB8uAUBAEHAQB79JgcLdA/NFxHIJIzsw+Uf7Lcrl8uLsC/c8YAEAignK5PCngN5VSnzTGGiJ5zxr9uTiO3xaRPfsKfgAApFqtUr1ev06w37TW3igURpRY8604jq8Wi0W+V1f0QKLn9xdeWHp8fnGxsvM1/X+J/g0H3fxf/ODBZsLLDqgAAAAASUVORK5CYII=")    # the gear n, 32 px, if favicon.ico is missing


@app.route("/favicon.ico")
def favicon():
    """The tab icon (the gear n), on every page, including ones that don't link it."""
    if (HERE / "static" / "favicon.ico").is_file():
        resp = make_response(send_from_directory(str(HERE / "static"), "favicon.ico", mimetype="image/x-icon"))
    else:
        resp = make_response(_FAVICON_PNG)
        resp.headers["Content-Type"] = "image/png"
    resp.headers["Cache-Control"] = "public, max-age=86400"
    return resp


@app.route("/api/file-preview", methods=["POST"])
def file_preview():
    """
    A picture of an art file, to look at before using it: page 1 of a PDF or
    AI, an EPS, an SVG or an image, as a PNG on the picker's cream (#FBEEDE)
    so white art shows. Nothing is kept.
    """
    import subprocess, tempfile, io
    up = request.files.get("file")
    if not up:
        return jsonify({"error": "No file."}), 400
    name = (up.filename or "art").lower()
    ext = Path(name).suffix
    raw = up.read(16 * 1024 * 1024 + 1)
    if len(raw) > 16 * 1024 * 1024:
        return jsonify({"error": "That file is too large to preview."}), 413
    bg = (0xFB, 0xEE, 0xDE)
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        src = d / ("in" + (ext if re.fullmatch(r"\.[a-z0-9]{1,5}", ext or "") else ""))
        src.write_bytes(raw)
        png = d / "out.png"
        try:
            if ext in (".pdf", ".ai") or raw[:5] == b"%PDF-":
                subprocess.run(["pdftocairo", "-png", "-transp", "-singlefile", "-scale-to", "1600",
                                "-f", "1", "-l", "1", str(src), str(d / "out")],
                               check=True, capture_output=True, timeout=90)
            elif ext in (".eps", ".ps"):
                subprocess.run(["gs", "-q", "-dSAFER", "-dBATCH", "-dNOPAUSE", "-dEPSCrop", "-sDEVICE=pngalpha",
                                "-r150", f"-sOutputFile={png}", str(src)],
                               check=True, capture_output=True, timeout=90)
            elif ext == ".svg":
                import cairosvg
                cairosvg.svg2png(bytestring=raw, write_to=str(png), output_width=1600, unsafe=False)
            else:
                Image.open(io.BytesIO(raw)).save(png)
            im = Image.open(png).convert("RGBA")
            if max(im.size) > 2000:
                k = 2000 / max(im.size)
                im = im.resize((int(im.width * k), int(im.height * k)), Image.LANCZOS)
            out = Image.new("RGBA", im.size, bg + (255,))
            out.alpha_composite(im)
            buf = io.BytesIO()
            out.convert("RGB").save(buf, "PNG", optimize=True)
        except Exception as e:
            return jsonify({"error": f"That file couldn't be previewed ({str(e)[:120]})."}), 422
    resp = make_response(buf.getvalue())
    resp.headers["Content-Type"] = "image/png"
    resp.headers["Cache-Control"] = "no-store"
    return resp


@app.route("/api/export-zip/<export_id>")
def export_zip(export_id):
    """
    Everything an export made, as one zip: the 2X2 at the top, then PROOFS/,
    VIRTUALS/. Hidden entries stay out. ?name= names the zip.
    """
    import zipfile
    if not _EXPORT_ID.match(export_id):
        return jsonify({"error": "Unknown export."}), 404
    root = (HERE / "_serve" / export_id).resolve()
    manifest = root / "_files.json"
    if not manifest.exists():
        return jsonify({"error": "These files have expired. Export again."}), 404
    name = re.sub(r"[^A-Za-z0-9 _+.-]+", "_", request.args.get("name") or "").strip(" ._")[:120] or export_id
    # ?customer=1: the customer's copy — the proof and the virtual only, no
    # press files or 2X2 (customer mode in the configurator).
    customer = SANDBOX or request.args.get("customer") == "1"
    zp = root / ("_bundle_customer.zip" if customer else "_bundle.zip")
    with zipfile.ZipFile(zp, "w", zipfile.ZIP_DEFLATED) as z:
        for e in json.loads(manifest.read_text()):
            if e.get("hidden"):
                continue
            if customer and e.get("kind") not in ("digitalproof", "virtualproof"):
                continue
            f = (root / str(e.get("path") or "")).resolve()
            if root not in f.parents or not f.is_file():
                continue
            folder = {"press": "PRESS FILES/", "digitalproof": "PROOFS/", "virtualproof": "VIRTUALS/",
                      "label": "LABELS/"}.get(e.get("kind"), "")
            z.write(str(f), folder + f.name)
    return send_file(str(zp), as_attachment=True, download_name=f"{name}.zip", mimetype="application/zip")


@app.route("/api/press-available/<path:product_id>")
def press_available(product_id):
    import press_layout
    # `version` reports the press_layout build this process actually has loaded.
    # Open this URL in a browser after deploying: if it doesn't match the file
    # you uploaded, the process is running old code (needs a restart, or a stale
    # __pycache__ needs clearing) and the export will be the old file.
    # `status` separates "this product is not meant to have one" from "it is,
    # but its files are not on the server" — the two produce an identical
    # export and only one of them is a problem.
    return jsonify({"available": press_layout.has_press_template(product_id),
                    "status": press_layout.press_template_status(product_id),
                    "version": getattr(press_layout, "VERSION", "unknown")})


@app.route("/api/match-pantone-hex", methods=["POST"])
def match_pantone_hex():
    body = request.get_json(force=True)
    hex_color = body.get("hex", "").strip().lstrip("#")
    if len(hex_color) != 6:
        return jsonify({"error": "Invalid hex color"}), 400
    try:
        rgb = tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
    except ValueError:
        return jsonify({"error": "Invalid hex color"}), 400
    matches = with_non_pms_inks(find_closest_pantone(rgb, top_n=5, boost=False), rgb, top_n=5)
    return jsonify({"matches": matches})

@app.route("/api/match-pantone", methods=["POST"])
def match_pantone():
    if "file" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400
    f = request.files["file"]
    if not f.filename:
        return jsonify({"error": "Empty filename"}), 400

    tmp_path = Path(tempfile.gettempdir()) / f"match_{f.filename}"
    f.save(str(tmp_path))

    results = []
    try:
        from colorthief import ColorThief
        ct = ColorThief(str(tmp_path))
        palette = ct.get_palette(color_count=12, quality=3)

        def rgb_to_hsv(rgb):
            r,g,b = [x/255 for x in rgb]
            mx=max(r,g,b); mn=min(r,g,b); d=mx-mn
            v=mx; s=0 if mx==0 else d/mx
            if d==0: h=0
            elif mx==r: h=60*((g-b)/d%6)
            elif mx==g: h=60*((b-r)/d+2)
            else: h=60*((r-g)/d+4)
            return h,s,v

        def hue_dist(a, b):
            diff = abs(a - b) % 360
            return min(diff, 360 - diff)

        def saturation(rgb): return rgb_to_hsv(rgb)[1]
        def brightness(rgb): return sum(rgb) / (3 * 255)

        filtered = [
            rgb for rgb in palette
            if saturation(rgb) >= 0.25 and brightness(rgb) <= 0.85 and brightness(rgb) >= 0.08
        ]
        if not filtered:
            filtered = palette

        palette_sorted = sorted(filtered, key=saturation, reverse=True)
        deduped = []
        for rgb in palette_sorted:
            h, s, v = rgb_to_hsv(rgb)
            if not any(hue_dist(h, rgb_to_hsv(kept)[0]) < 20 for kept in deduped):
                deduped.append(rgb)

        is_raster = tmp_path.suffix.lower() in {'.jpg', '.jpeg', '.png', '.bmp', '.gif', '.tiff', '.webp'}
        seen_pantones = set()
        for rgb in deduped[:8]:
            matches = find_closest_pantone(rgb, top_n=3, boost=is_raster)
            original_hex = "#{:02X}{:02X}{:02X}".format(*rgb)
            top_matches = [m for m in matches if m["name"] not in seen_pantones]
            for m in top_matches:
                seen_pantones.add(m["name"])
            if top_matches:
                results.append({
                    "original_hex": original_hex,
                    "original_rgb": list(rgb),
                    "matches": top_matches[:3],
                })
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        try: tmp_path.unlink(missing_ok=True)
        except: pass

    return jsonify({"colors": results})

# ---------------------------------------------------------------------------
# Job status & file delivery
# ---------------------------------------------------------------------------

@app.route("/api/job/<job_id>")
def job_status(job_id):
    job = get_job(job_id)
    if not job:
        return jsonify({"error": "Unknown job"}), 404
    return jsonify(job)

@app.route("/api/production/<job_id>")
def get_production(job_id):
    job = get_job(job_id)
    if not job or "serve_dir" not in job:
        return jsonify({"error": "Not found"}), 404
    p = Path(job["serve_dir"]) / job["production_filename"]
    if not p.exists():
        return jsonify({"error": "File not found"}), 404
    return send_file(str(p), mimetype="application/pdf",
                     as_attachment=True, download_name=job["production_filename"])

@app.route("/api/cleanup/<job_id>", methods=["POST"])
def cleanup_job(job_id):
    job = get_job(job_id)
    if job and "serve_dir" in job:
        try: shutil.rmtree(job["serve_dir"], ignore_errors=True)
        except: pass
    return jsonify({"status": "ok"})

# ---------------------------------------------------------------------------
# Mockup asset manifest
# ---------------------------------------------------------------------------

@app.route("/api/mockup-assets/<product_id>")
def mockup_assets(product_id):
    # This Is Fast twins reuse the base product's mockup assets.
    asset_dir = HERE / "static" / "assets" / asset_id_for(product_id)
    manifest_path = asset_dir / "manifest.json"
    if manifest_path.exists():
        return send_file(str(manifest_path), mimetype="application/json")
    return jsonify({
        "product": product_id,
        "width": 1350,
        "height": 1350,
        "exports": {},
        "status": "assets_not_exported"
    })

# ---------------------------------------------------------------------------
_STOCK_BG_CACHE = {}  # in-memory cache per product_id

@app.route("/api/stock-backgrounds/<product_id>")
def stock_backgrounds(product_id):
    global _STOCK_BG_CACHE
    _twin_of = (PRODUCTS.get(product_id) or {}).get("twin_of")
    product_id = asset_id_for(product_id)   # twins share the base product's folder
    # A twin with mockup layers of its own (the MMKK 4CP's magnet) still uses
    # its base's stock backgrounds rather than a second copy of them.
    _own = HERE / "static" / "assets" / product_id / "stockbackgrounds"
    if _twin_of and not _own.exists():
        product_id = asset_id_for(_twin_of)
    if product_id in _STOCK_BG_CACHE:
        return jsonify(_STOCK_BG_CACHE[product_id])

    assets_dir = HERE / "static" / "assets"
    folder = None
    if assets_dir.exists():
        for d in assets_dir.iterdir():
            if d.name.lower() == product_id.lower():
                candidate = d / "stockbackgrounds"
                if candidate.exists():
                    folder = candidate
                    break
    if not folder:
        return jsonify([])

    files = sorted([
        f.name for f in folder.iterdir()
        if f.suffix.lower() in (".jpg", ".jpeg", ".png") and not f.name.startswith(".")
    ])
    actual_pid = folder.parent.name
    base_url = f"/static/assets/{actual_pid}/stockbackgrounds"

    # Get dimensions of first file for upload validation (cached, no re-fetch needed)
    first_w, first_h = None, None
    if files:
        try:
            from PIL import Image as _PILImage
            first_path = folder / files[0]
            with _PILImage.open(str(first_path)) as _im:
                first_w, first_h = _im.width, _im.height
        except Exception:
            pass

    result = {"files": files, "base_url": base_url, "first_w": first_w, "first_h": first_h}
    _STOCK_BG_CACHE[product_id] = result

    from flask import make_response
    resp = make_response(jsonify(result))
    resp.headers["Cache-Control"] = "public, max-age=600"
    return resp


def _warn_missing_press_files():
    """
    Say so at boot when a registered press template did not make it onto the
    server.

    At module level, not under __main__, because in production gunicorn
    imports this file and never runs that block — and production is exactly
    where a file goes missing. Without this the first sign is a customer's
    export coming back with no press file in it.
    """
    try:
        import press_layout as _pl
        missing = _pl.missing_press_files()
    except Exception as e:
        print(f"⚠️  press_layout did not load: {e}")
        return
    for pid, why in missing.items():
        print(f"⚠️  press template for {pid} is registered but {why} — "
              f"exports for it will fall back to a print PDF with no 2X2")


_warn_missing_press_files()


if __name__ == "__main__":
    (HERE / "uploads").mkdir(exist_ok=True)
    (HERE / "_serve").mkdir(exist_ok=True)
    print("─" * 50)
    print("  🧴  Numo Production Engine – Web Edition")
    print("  Open → http://localhost:8080")
    print("  No Adobe required!")
    try:
        import press_layout as _pl
        print(f"  press_layout: {getattr(_pl, 'VERSION', 'unknown')}")
    except Exception as _e:
        print(f"  press_layout: NOT LOADED ({_e})")
    print("─" * 50)
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)
