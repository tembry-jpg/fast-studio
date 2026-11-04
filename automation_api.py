"""
A small HTTP API for an automation (an email reader) to drive the
configurator: find items, check artwork, make a proof. Numo, 2026-11-04.

Every route is under /api/automation/ and needs

    Authorization: Bearer <AUTOMATION_API_KEY>

where AUTOMATION_API_KEY is a Railway variable. The key is only ever
compared (in constant time) - never logged, stored or sent back. With the
variable unset, every route answers 503.

Nothing here re-implements the configurator. The routes call the same
server functions the configurator's own requests reach:

  search-items   _catalog_meta (the catalogue's own search words), the
                 colour palettes and body styles, the art_slots
  check-art      rasterize() - the upload checks (file type, one-colour
                 validation, ink separation and count) - and art_check()
                 (resolution / fine detail at the printed size)
  make-proof     _pdf_worker (the print PDF) and _generic_proof (the customer
                 proof sheet, with the item laid flat - the 3D mockup is drawn
                 by the browser, so it is left off)

Proofs are kept for 7 days under the Railway volume when there is one
(RAILWAY_VOLUME_MOUNT_PATH), else in the app folder (which a redeploy wipes),
and served from an unguessable link.
"""
import hmac
import ipaddress
import json
import os
import re
import secrets
import shutil
import socket
import time
import urllib.parse
import urllib.request
from pathlib import Path

from flask import Blueprint, jsonify, request, send_file

bp = Blueprint("automation", __name__, url_prefix="/api/automation")
_S = None                                  # the server module (set by register)

MAX_BYTES = 25 * 1024 * 1024               # 25 MB per artwork file
ACCEPTED = (".pdf", ".ai", ".eps", ".svg", ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tif", ".tiff", ".webp")
PROOF_DAYS = 7
_KEEP_S = (PROOF_DAYS + 1) * 86400         # links say 7 days; files go a day later
_TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{30,64}$")
_STOP = {"a", "an", "the", "and", "or", "of", "for", "with", "in", "on", "to", "my", "our", "some",
         "please", "item", "items", "custom", "printed", "print", "logo"}

# Items the server can't proof on its own yet: their proof comes from a
# special path (decal plates, glass, pen jig) the automation doesn't drive.
_UNSUPPORTED_WHY = "is not supported by the automation yet (its proof is made a different way) - an artist has to do this one"


def register(app, server_module):
    """Hook the routes into the app (server.py calls this once)."""
    global _S
    _S = server_module
    app.register_blueprint(bp)


# ── Auth ───────────────────────────────────────────────────────────────────

@bp.before_request
def _auth():
    if request.path.startswith("/api/automation/proofs/"):
        return None                         # a proof link: its own unguessable token
    key = os.environ.get("AUTOMATION_API_KEY") or ""
    if not key:
        return _err("The automation API isn't switched on: AUTOMATION_API_KEY is not set on the server.", 503)
    got = request.headers.get("Authorization") or ""
    tok = got[7:].strip() if got[:7].lower() == "bearer " else ""
    if not tok or not hmac.compare_digest(tok.encode("utf-8"), key.encode("utf-8")):
        return _err("Missing or wrong API key. Send the header  Authorization: Bearer <key>.", 401)
    if (request.content_length or 0) > MAX_BYTES + 1024 * 1024:
        return _err(f"The request is too large: artwork files can be up to {MAX_BYTES // (1024 * 1024)} MB.", 413,
                    problem_codes=["file_too_large"])
    return None


def _err(msg, status, **extra):
    return jsonify(dict({"ok": False, "error": msg}, **extra)), status


# ── Items ──────────────────────────────────────────────────────────────────

def _products():
    return {pid: p for pid, p in _S.PRODUCTS.items() if not p.get("alias_of")}


def _find_item(item_id):
    if not item_id:
        return None, None
    s = str(item_id).strip()
    P = _products()
    for pid in P:
        if pid.lower() == s.lower():
            return pid, P[pid]
    return None, None


def _colors(pid, p):
    """[{name, hex}] the item comes in ([] for full-colour items, where the
    print is the colour)."""
    mat = p.get("material") or ""
    if p.get("is_4cp") or "4cp" in mat:
        return []
    out = _S._material_palette(mat)
    if not out:
        try:
            with _S.app.app_context():
                table = _S.get_colors().get_json() or {}
            out = [{"name": c.get("name"), "hex": c.get("hex")} for c in (table.get(mat) or [])
                   if isinstance(c, dict)]
        except Exception:
            out = []
    if not out:
        try:
            out = [{"name": b.get("name"), "hex": b.get("hex")} for b in _S._body_patterns(pid, p) if b.get("name")]
        except Exception:
            out = []
    return [c for c in out if c.get("name")]


def _method(pid, p, meta):
    if _S.is_screenprint(pid):
        return "one-color screen print", 1
    if p.get("is_4cp") or "4cp" in (p.get("material") or ""):
        return "full color (4CP)", None
    if _S.supports_pms_assign(pid):
        return "spot color (PMS inks)", _S._max_inks_for(pid)
    if p.get("print_method") == "decal":
        return "decal", _S._max_inks_for(pid)
    if p.get("mimaki_jig"):
        return "full color (direct print)", None
    return meta.get("printing") or "spot color", meta.get("max_inks")


def _supported(pid, p):
    return not (p.get("print_method") == "decal" or p.get("mimaki_jig") or p.get("proof_shape") == "glass"
                or (p.get("material") or "") in ("glass", "ceramic"))


def _areas(pid, p, max_colors, method):
    out = []
    for s in p.get("art_slots") or []:
        w = round(float(s.get("w_pt") or 0) / 72, 3)
        h = round(float(s.get("h_pt") or 0) / 72, 3)
        limits = []
        if s.get("shape") == "circle":
            limits.append(f"round area, {w}\" across")
        if p.get("one_side_only") and s.get("id") == "side2":
            continue
        out.append({"id": s.get("id"), "name": s.get("label") or s.get("id"),
                    "width_in": w, "height_in": h, "size": s.get("size") or f"{w}\" W x {h}\" H",
                    "max_colors": max_colors, "method": method, "limits": limits})
    return out


def _item_json(pid, p):
    labels = [s.get("label") or s.get("id") for s in p.get("art_slots") or []]
    meta = _S._catalog_meta(pid, p, labels)
    method, max_colors = _method(pid, p, meta)
    desc = ", ".join(x for x in [meta.get("material_label"), meta.get("shape"),
                                  meta.get("fits"), meta.get("printing"), meta.get("program")] if x)
    return {"id": pid, "name": meta.get("name") or p.get("label") or pid, "description": desc,
            "colors": _colors(pid, p), "decoration_areas": _areas(pid, p, max_colors, method),
            "decoration_method": method, "max_colors": max_colors,
            "automation_proofs": _supported(pid, p)}


def _area(p, area):
    if not area:
        return None
    a = str(area).strip().lower()
    for s in p.get("art_slots") or []:
        if a in (str(s.get("id") or "").lower(), str(s.get("label") or "").lower()):
            return s
    return None


# ── Routes ─────────────────────────────────────────────────────────────────

@bp.route("/health", methods=["GET"])
def health():
    return jsonify({"ok": True})


@bp.route("/search-items", methods=["POST"])
def search_items():
    body = request.get_json(silent=True) or {}
    q = str(body.get("query") or "").strip()
    if not q:
        return _err("Send {\"query\": \"...\"} - a few words describing the item.", 400)
    words = [w for w in re.findall(r"[a-z0-9]+(?:-[a-z0-9]+)*", q.lower()) if w not in _STOP]
    if not words:
        return jsonify({"ok": True, "query": q, "matches": []})
    def tokens(text):
        return set(re.findall(r"[a-z0-9]+(?:-[a-z0-9]+)*", (text or "").lower()))

    def hit(w, toks):
        return (w in toks or w.rstrip("s") in toks or (w + "s") in toks
                or any(t.startswith(w) for t in toks if len(w) >= 4))

    named, broad = [], []
    for pid, p in _products().items():
        it = _item_json(pid, p)
        labels = [s.get("label") or s.get("id") for s in p.get("art_slots") or []]
        meta = _S._catalog_meta(pid, p, labels)
        # Every word must be found: in the catalogue's own search words (which
        # include category words like "koozie"), the colours, the description.
        all_toks = tokens(" ".join([meta.get("keywords") or "", it["description"],
                                    " ".join(c["name"] for c in it["colors"])]))
        if not all(hit(w, all_toks) for w in words):
            continue
        # Items whose own name / number match a word come first; category
        # words alone only count when nothing matches by name.
        own = tokens(" ".join([pid, pid.replace("-", " "), meta.get("name") or "", meta.get("base_name") or "",
                               p.get("label") or "", p.get("display_label") or ""]))
        (named if any(hit(w, own) for w in words) else broad).append(it)
    out = sorted(named or broad, key=lambda x: x["id"])
    return jsonify({"ok": True, "query": q, "matches": out})


# ── Artwork in ─────────────────────────────────────────────────────────────

class _ArtError(Exception):
    def __init__(self, code, message, suggestion=None):
        super().__init__(message)
        self.code, self.message, self.suggestion = code, message, suggestion


def _params():
    if request.files or request.form:
        return {k: v for k, v in request.form.items()}
    return request.get_json(silent=True) or {}


def _public_host(host):
    """True when every address the host resolves to is on the public internet."""
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return False
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast
                or ip.is_reserved or ip.is_unspecified):
            return False
    return True


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


def _download(url, dest_dir):
    """The artwork at a public http(s) URL -> (path, filename). Redirects are
    followed (up to 4) only to public hosts; MAX_BYTES at most."""
    for _ in range(5):
        u = urllib.parse.urlparse(url)
        if u.scheme not in ("http", "https") or not u.hostname:
            raise _ArtError("bad_url", "The artwork link has to be an http or https web address.")
        if not _public_host(u.hostname):
            raise _ArtError("bad_url", "The artwork link points to a private or local address, which isn't allowed.")
        req = urllib.request.Request(url, headers={"User-Agent": "numo-automation/1.0"})
        opener = urllib.request.build_opener(_NoRedirect)
        try:
            resp = opener.open(req, timeout=30)
        except urllib.error.HTTPError as e:
            if e.code in (301, 302, 303, 307, 308) and e.headers.get("Location"):
                url = urllib.parse.urljoin(url, e.headers["Location"])
                continue
            raise _ArtError("download_failed", f"The artwork link couldn't be downloaded (the site answered {e.code}).")
        except Exception:
            raise _ArtError("download_failed", "The artwork link couldn't be downloaded (no answer from the site).")
        with resp:
            name = ""
            cd = resp.headers.get("Content-Disposition") or ""
            m = re.search(r'filename\*?=(?:UTF-8\'\')?"?([^";]+)', cd)
            if m:
                name = urllib.parse.unquote(m.group(1))
            if not name:
                name = urllib.parse.unquote(Path(u.path).name) or "artwork"
            if not Path(name).suffix:
                ct = (resp.headers.get("Content-Type") or "").split(";")[0].strip().lower()
                name += {"application/pdf": ".pdf", "image/png": ".png", "image/jpeg": ".jpg",
                         "image/svg+xml": ".svg", "application/postscript": ".eps", "image/gif": ".gif",
                         "image/webp": ".webp", "image/tiff": ".tif", "image/bmp": ".bmp"}.get(ct, "")
            dest = Path(dest_dir) / ("dl_" + secrets.token_hex(6) + "_" + re.sub(r"[^\w.\-]", "_", name)[-80:])
            n = 0
            with open(dest, "wb") as fp:
                while True:
                    chunk = resp.read(1 << 16)
                    if not chunk:
                        break
                    n += len(chunk)
                    if n > MAX_BYTES:
                        fp.close(); dest.unlink(missing_ok=True)
                        raise _ArtError("file_too_large", f"The artwork file is larger than {MAX_BYTES // (1024 * 1024)} MB.")
                    fp.write(chunk)
            return dest, name
    raise _ArtError("download_failed", "The artwork link redirected too many times.")


def _take_art(params, file_field="file", url_field="art_url"):
    """The artwork sent (a multipart 'file', or 'art_url') saved into the
    server's uploads -> (path, original filename)."""
    tmp = _S.UPLOADS_DIR / "_automation"
    tmp.mkdir(parents=True, exist_ok=True)
    f = request.files.get(file_field) if request.files else None
    if f is not None and f.filename:
        name = f.filename
        src = tmp / ("up_" + secrets.token_hex(6) + "_" + re.sub(r"[^\w.\-]", "_", name)[-80:])
        f.save(str(src))
        if src.stat().st_size > MAX_BYTES:
            src.unlink(missing_ok=True)
            raise _ArtError("file_too_large", f"The artwork file is larger than {MAX_BYTES // (1024 * 1024)} MB.")
    elif params.get(url_field):
        src, name = _download(str(params[url_field]).strip(), tmp)
    else:
        raise _ArtError("no_artwork", "No artwork was sent: upload it as the multipart field 'file', or give 'art_url'.")
    if src.stat().st_size == 0:
        src.unlink(missing_ok=True)
        raise _ArtError("empty_file", "The artwork file is empty.")
    ext = Path(name).suffix.lower()
    if ext not in ACCEPTED:
        src.unlink(missing_ok=True)
        raise _ArtError("unsupported_file_type",
                        f"Unsupported file type ({ext or 'no extension'}). Send AI, EPS, PDF, SVG, PNG or JPG.",
                        "Vector artwork (AI, EPS, PDF or SVG) works best; a PNG with a transparent background is next best.")
    return src, name


# ── Checking ───────────────────────────────────────────────────────────────

def _call(view, path, *, form=None, json_body=None):
    """One of the server's own route functions, called directly (the same
    code the configurator's requests reach)."""
    kw = {"method": "POST"}
    if form is not None:
        kw["data"] = form
    if json_body is not None:
        kw["json"] = json_body
    with _S.app.test_request_context(path, **kw):
        rv = view()
    resp = _S.app.make_response(rv)
    try:
        data = resp.get_json(silent=True) or {}
    except Exception:
        data = {}
    return resp.status_code, data


def _opaque_box(path):
    """For an image: (True, 'white') when it has no transparency and a solid
    border - a background that would print as a box."""
    from PIL import Image
    try:
        with Image.open(path) as im:
            im = im.convert("RGBA")
            w, h = im.size
            a = im.getchannel("A")
            if a.getextrema()[0] < 250:
                return False, None
            px = im.load()
            edge = [px[x, 0] for x in range(0, w, max(1, w // 50))] + \
                   [px[x, h - 1] for x in range(0, w, max(1, w // 50))] + \
                   [px[0, y] for y in range(0, h, max(1, h // 50))] + \
                   [px[w - 1, y] for y in range(0, h, max(1, h // 50))]
            r0, g0, b0, _ = edge[0]
            if all(abs(r - r0) + abs(g - g0) + abs(b - b0) < 30 for r, g, b, _ in edge):
                return True, "white" if min(r0, g0, b0) > 235 else "solid-color"
    except Exception:
        pass
    return False, None


def _check(pid, p, slot, src, name, params):
    """Run the configurator's checks on the artwork for this item and area.
    -> dict(problems=[{code, message}], warnings=[...], suggestions=[...],
            info={...}) - info carries what make-proof needs."""
    problems, warnings, suggestions = [], [], []

    def prob(code, msg, sug=None):
        problems.append({"code": code, "message": msg})
        if sug and sug not in suggestions:
            suggestions.append(sug)

    # The upload checks (rasterize): file type, one-colour validation,
    # tracing, ink separation. Given the file from the uploads folder.
    status, up = _call(_S.rasterize, "/api/rasterize",
                       form={"server_path": str(src), "slot_id": slot["id"], "product_id": pid})
    info = {"saved_path": up.get("saved_path"), "upload": up}
    val = up.get("validation") or {}
    for e in val.get("errors") or []:
        code = e.get("code") or "invalid_artwork"
        prob(code, e.get("message") or "The artwork can't be used for this item.",
             {"raster_file": "Send one-color vector artwork (AI, EPS, PDF or SVG).",
              "unsupported_file": "Send one-color vector artwork (AI, EPS, PDF or SVG).",
              "embedded_raster": "Send true vector artwork - the file has a placed image inside it.",
              "embedded_raster_mixed": "Remove the placed image, or send fully vector artwork.",
              "opaque_background": "Send the artwork without its background (transparent PNG or vector).",
              "multicolor": "Send the artwork in one color.",
              }.get(code, "Send clean vector artwork (AI, EPS, PDF or SVG)."))
    for wn in val.get("warnings") or []:
        warnings.append(wn.get("message"))
    if status >= 400 and not problems:
        msg = up.get("error") or "The artwork couldn't be read."
        code = "unsupported_file_type" if msg.startswith("Unsupported format") else "unreadable_file"
        prob(code, msg, "Send AI, EPS, PDF, SVG, PNG or JPG artwork.")
    if problems:
        return {"problems": problems, "warnings": warnings, "suggestions": suggestions, "info": info}

    # How many inks it carries, against what the method prints.
    method, max_colors = _method(pid, p, {})
    sep = up.get("separations") or {}
    inks = [i for i in (sep.get("inks") or []) if not i.get("hidden")]
    if not inks:
        # One-colour art: its colour, from the validation, matched to a
        # Pantone the way the separations are.
        for c in ((val.get("facts") or {}).get("ink_clusters") or []):
            hx = str(c.get("hex") or "")
            if re.fullmatch(r"#[0-9A-Fa-f]{6}", hx):
                ink = {"hex": hx}
                try:
                    m = _S._snap_to_pms(tuple(int(hx[k:k + 2], 16) for k in (1, 3, 5)))
                    if m:
                        ink.update(pms=m["name"], pms_hex=m["hex"])
                except Exception:
                    pass
                inks.append(ink)
    info["inks"] = inks
    if up.get("needs_reduction") or (max_colors == 1 and len(inks) > 1):
        prob("too_many_colors",
             f"Too many colors for this method: the artwork has {max(len(inks), 2)} colors and this item prints 1 color ({method}).",
             "Send the artwork in a single color.")
    elif sep.get("over_limit") and max_colors:
        prob("too_many_colors",
             f"Too many colors for this method: the artwork has {sep.get('detected') or len(inks)} colors and this item prints at most {max_colors}.",
             f"Reduce the artwork to {max_colors} colors or fewer.")

    # A photo or gradient on a spot-ink item: not screen-print art (the
    # configurator's own rule - under half flat colour, more than 8 colours,
    # or a placed photo in a vector file - shows it as a mockup only).
    if _S.supports_pms_assign(pid) or _S.is_screenprint(pid):
        flat = sep.get("flat_share")
        photo_in_vector = "embedded_raster" in str((up.get("press_issue") or {}).get("code") or "")
        if photo_in_vector:
            prob("photo_not_printable",
                 "The file contains a placed photo, which can't be printed with this item's spot inks.",
                 "Send logo artwork in solid colors, fully vector, or pick a full-color (4CP) item.")
        elif up.get("traced") and ((sep.get("detected") or 0) > 8 or not inks or (flat is not None and flat < 0.5)):
            prob("photo_not_printable",
                 "This looks like a photo or gradient, which can't be printed with this item's spot inks: "
                 f"only {int(round((flat or 0) * 100))}% of it is flat color.",
                 "Send logo artwork in solid colors, or pick a full-color (4CP) item for a photo.")

    # Its printed size: as asked, else as large as fits the area.
    aw, ah = (up.get("ink_pt") or [None, None])
    if not aw:
        aw, ah = up.get("width"), up.get("height")
    zone_w, zone_h = float(slot["w_pt"]) / 72, float(slot["h_pt"]) / 72
    aspect = (float(aw) / float(ah)) if aw and ah else 1.0
    try:
        want_w = float(params.get("width_in") or 0)
    except (TypeError, ValueError):
        want_w = 0
    try:
        want_h = float(params.get("height_in") or 0)
    except (TypeError, ValueError):
        want_h = 0
    if want_w <= 0 and want_h > 0:
        want_w = want_h * aspect
    fit_w = min(zone_w, zone_h * aspect)
    pw = want_w if want_w > 0 else fit_w
    ph = pw / aspect
    if pw > zone_w + 0.01 or ph > zone_h + 0.01:
        prob("too_large_for_area",
             f"At {pw:.2f}\" x {ph:.2f}\" the artwork doesn't fit the {slot.get('label') or slot['id']} area "
             f"({zone_w:.2f}\" x {zone_h:.2f}\"); the most it can be is {fit_w:.2f}\" wide.",
             f"Ask for {fit_w:.2f}\" wide or less.")
    info.update(printed_w_in=round(pw, 3), printed_h_in=round(ph, 3), zone_w_in=zone_w, zone_h_in=zone_h)

    # Resolution and fine detail at that size (the art-check the
    # configurator runs as the art is sized).
    saved = up.get("saved_path")
    if saved:
        st, ac = _call(_S.art_check, "/api/art-check", json_body={
            "art_path": saved, "printed_w_in": pw, "printed_h_in": ph, "zone_w_in": zone_w, "zone_h_in": zone_h,
            "product_id": pid, "screen": bool(_S.is_screenprint(pid)),
            "source_inks": [i.get("hex") for i in inks if i.get("hex")]})
        verdict = ac.get("verdict")
        notes = [n for n in (ac.get("notes") or []) if n]
        if verdict == "refuse":
            dpi = ac.get("effective_dpi")
            if ac.get("raster") and dpi is not None and dpi < 50:
                prob("low_resolution", f"Resolution too low for {pw:.2f}\" wide: the image works out to {int(dpi)} DPI at that size. "
                     + " ".join(notes), "Send vector artwork (AI, EPS, PDF or SVG), or a much larger image.")
            else:
                prob("art_not_printable", " ".join(notes) or "The artwork won't print cleanly at this size.",
                     "Send vector artwork (AI, EPS, PDF or SVG) with bolder lines and lettering.")
        elif verdict == "warn":
            warnings.extend(notes)
            if ac.get("raster"):
                sug = "Vector artwork (AI, EPS, PDF or SVG) would print the finest details more cleanly."
                if sug not in suggestions:
                    suggestions.append(sug)

    # An image with a solid box round it where nothing knocks it out.
    if Path(name).suffix.lower() in (".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tif", ".tiff", ".webp") \
            and not up.get("separations") and saved:
        boxy, what = _opaque_box(saved)
        if boxy:
            prob("background_not_transparent",
                 f"Background not transparent: the image has a {what} background, which would print as a {what} box around the art.",
                 "Send a PNG with a transparent background, or vector artwork.")
    return {"problems": problems, "warnings": warnings, "suggestions": suggestions, "info": info}


def _resolve(params, need_supported=False):
    """item + area from the request -> (pid, p, slot) or an error response."""
    pid, p = _find_item(params.get("item_id"))
    if not pid:
        return None, _err(f"Unknown item_id {params.get('item_id')!r}. Use an id from search-items.", 404,
                          code="unknown_item")
    slot = _area(p, params.get("area"))
    if not slot:
        names = [s.get("id") for s in p.get("art_slots") or []]
        return None, _err(f"Unknown decoration area {params.get('area')!r} for {pid}. Areas: {', '.join(names)}.", 400,
                          code="unknown_area")
    return (pid, p, slot), None


@bp.route("/check-art", methods=["POST"])
def check_art():
    params = _params()
    if params.get("areas") not in (None, "", []):
        return _check_art_multi(params)
    got, bad = _resolve(params)
    if bad:
        return bad
    pid, p, slot = got
    try:
        src, name = _take_art(params)
    except _ArtError as e:
        return jsonify({"ok": False, "problems": [e.message], "problem_codes": [e.code],
                        "suggestions": [e.suggestion] if e.suggestion else []})
    try:
        r = _check(pid, p, slot, src, name, params)
    finally:
        src.unlink(missing_ok=True)
    return jsonify({"ok": not r["problems"], "problems": [x["message"] for x in r["problems"]],
                    "problem_codes": [x["code"] for x in r["problems"]],
                    "warnings": r["warnings"], "suggestions": r["suggestions"],
                    "printed_size_in": {"width": r["info"].get("printed_w_in"), "height": r["info"].get("printed_h_in")}})


# ── Proofs ─────────────────────────────────────────────────────────────────

def _proof_dir():
    root = os.environ.get("RAILWAY_VOLUME_MOUNT_PATH")
    d = Path(root) / "automation_proofs" if root else (_S.HERE / "_automation_proofs")
    d.mkdir(parents=True, exist_ok=True)
    return d


def _sweep_proofs():
    cut = time.time() - _KEEP_S
    for f in _proof_dir().glob("*"):
        try:
            if f.stat().st_mtime < cut:
                f.unlink(missing_ok=True)
        except OSError:
            pass


def _base_url():
    base = os.environ.get("PUBLIC_BASE_URL")
    if base:
        return base.rstrip("/")
    proto = (request.headers.get("X-Forwarded-Proto") or request.scheme).split(",")[0].strip()
    host = request.headers.get("X-Forwarded-Host") or request.host
    return f"{proto}://{host}"


def _position(params, slot, pw_in, ph_in):
    """(dx, dy) in pt from the area's centre, +x right, +y up. 'position' is
    center / top / bottom / left / right (or e.g. 'top left'); x_in / y_in
    move it further."""
    zw, zh = float(slot["w_pt"]) / 72, float(slot["h_pt"]) / 72
    pos = str(params.get("position") or "center").lower()
    dx = dy = 0.0
    if "left" in pos:
        dx = -(zw - pw_in) / 2
    elif "right" in pos:
        dx = (zw - pw_in) / 2
    if "top" in pos:
        dy = (zh - ph_in) / 2
    elif "bottom" in pos:
        dy = -(zh - ph_in) / 2
    try:
        dx += float(params.get("x_in") or 0)
        dy += float(params.get("y_in") or 0)
    except (TypeError, ValueError):
        pass
    return dx * 72, dy * 72


@bp.route("/make-proof", methods=["POST"])
def make_proof():
    params = _params()
    if params.get("areas") not in (None, "", []):
        return _make_proof_multi(params)
    got, bad = _resolve(params)
    if bad:
        return bad
    pid, p, slot = got
    if not _supported(pid, p):
        return jsonify({"ok": False, "proof_url": None, "problems": [f"{pid} {_UNSUPPORTED_WHY}."],
                        "problem_codes": ["item_not_supported"]})
    # The item's colour.
    colors = _colors(pid, p)
    color = None
    want = str(params.get("color") or params.get("variant") or "").strip()
    if colors:
        if not want:
            return jsonify({"ok": False, "proof_url": None, "problem_codes": ["color_required"],
                            "problems": [f"Say which color the item is ('color'). {pid} comes in: "
                                         + ", ".join(c['name'] for c in colors) + "."]})
        color = next((c for c in colors if c["name"].lower() == want.lower()), None)
        if not color:
            return jsonify({"ok": False, "proof_url": None, "problem_codes": ["unknown_color"],
                            "problems": [f"{pid} doesn't come in {want!r}. Colors: "
                                         + ", ".join(c['name'] for c in colors) + "."]})
    try:
        src, name = _take_art(params)
    except _ArtError as e:
        return jsonify({"ok": False, "proof_url": None, "problems": [e.message], "problem_codes": [e.code],
                        "suggestions": [e.suggestion] if e.suggestion else []})
    try:
        r = _check(pid, p, slot, src, name, params)
    finally:
        src.unlink(missing_ok=True)
    if r["problems"]:
        return jsonify({"ok": False, "proof_url": None, "problems": [x["message"] for x in r["problems"]],
                        "problem_codes": [x["code"] for x in r["problems"]], "suggestions": r["suggestions"],
                        "warnings": r["warnings"]})
    info = r["info"]
    pw, ph = info["printed_w_in"], info["printed_h_in"]
    dx, dy = _position(params, slot, pw, ph)
    zw, zh = info["zone_w_in"] * 72, info["zone_h_in"] * 72
    if abs(dx) > (zw - pw * 72) / 2 + 0.72 or abs(dy) > (zh - ph * 72) / 2 + 0.72:
        return jsonify({"ok": False, "proof_url": None, "problem_codes": ["outside_area"],
                        "problems": ["At that position the artwork runs outside the decoration area."]})

    # The inks: the art's own colours matched to Pantones (as the configurator
    # does); a one-colour item can be given its ink by name.
    inks = info.get("inks") or []
    one_color = _S.is_screenprint(pid)
    ink_name = str(params.get("ink") or "").strip()
    sp_ink = sp_hex = ""
    if one_color:
        if ink_name:
            nm = ink_name if ink_name in _S.PANTONE_RGB or ink_name in _S.NON_PMS_HEX else (
                f"PANTONE {ink_name}" if f"PANTONE {ink_name}" in _S.PANTONE_RGB else None)
            if not nm:
                return jsonify({"ok": False, "proof_url": None, "problem_codes": ["unknown_ink"],
                                "problems": [f"Unknown ink {ink_name!r} - give a Pantone name like 'PANTONE 186 C'."]})
            sp_ink, sp_hex = nm, _S.NON_PMS_HEX.get(nm) or _S.PANTONE_RGB.get(nm) or ""
        elif inks:
            sp_ink, sp_hex = inks[0].get("pms") or "", inks[0].get("pms_hex") or inks[0].get("hex") or ""

    order_ref = re.sub(r"[^\w\-]", "", str(params.get("reference") or ""))[:40]
    prefix = _S._safe_prefix(f"AUTO-{order_ref or 'PROOF'}-{secrets.token_hex(3).upper()}")
    job_id = _S._unique_id("job")
    _S.new_job(job_id, {})
    body = {
        "product_id": pid, "order_id": order_ref or "AUTO",
        "placement": {slot["id"]: {"ox": dx, "oy": -dy, "sc": 1.0, "rot": 0, "w_pt": pw * 72}},
        # Zones of 1 x 1 and a template the slot's size: offsets are in pt.
        "template_w": float(slot["w_pt"]), "template_h": float(slot["h_pt"]),
        "zones": {slot["id"]: {"w": 1.0, "h": 1.0}},
        "is_4cp": bool(p.get("is_4cp")), "fill_mode": "none",
        "screen_print_ink": sp_ink, "screen_print_ink_hex": sp_hex,
        "hidden_colors": [], "source_inks": [i.get("hex") for i in inks if i.get("hex")],
        "neoprene_name": (color or {}).get("name") or "", "thread_name": "",
    }
    saved = info.get("saved_path")
    # Vector art goes to the print file as PDF, as the configurator sends it
    # (the one-colour ink is applied to PDF art; an SVG kept its own colours).
    if saved and Path(saved).suffix.lower() in (".svg", ".eps"):
        try:
            import press_layout as _pl
            saved = _pl.art_as_pdf(str(saved), work_dir=str(Path(saved).parent))
        except Exception:
            pass
    # A one-colour item: the art itself recoloured to its ink (the separation
    # the configurator makes), so the proof shows the ink, not the art's own
    # colour - the print file then makes it the named spot as always.
    if one_color and sp_ink and saved and Path(saved).suffix.lower() in (".pdf", ".ai"):
        try:
            import onecolor
            out = Path(saved).with_name(Path(saved).stem + ".ink.pdf")
            srcs = [i.get("hex") for i in inks if i.get("hex")] or ["#000000"]
            onecolor.separate(str(saved), [{"sources": srcs, "pms": sp_ink, "pms_hex": sp_hex, "hex": srcs[0]}],
                              str(out), mode="press")
            saved = str(out)
        except Exception as e:
            print(f"automation: one-colour recolour skipped: {e}")
    try:
        _S._pdf_worker(job_id, p, body["order_id"], {slot["id"]: saved}, body)
        job = _S.get_job(job_id) or {}
        if job.get("status") != "done":
            return jsonify({"ok": False, "proof_url": None, "problem_codes": ["proof_failed"],
                            "problems": ["The proof couldn't be built: " + str(job.get("message") or "unknown error")]})
        serve_dir = Path(job["serve_dir"])
        print_pdf = serve_dir / job["production_filename"]
        mat = p.get("material") or ""
        labels = [s.get("label") or s.get("id") for s in p.get("art_slots") or []]
        mat_label = _S._catalog_meta(pid, p, labels).get("material_label") or "Body"
        comps = ([{"label": "Background", "name": "None (white)", "hex": "#FFFFFF"}]
                 if (p.get("is_4cp") or "4cp" in mat) else
                 [{"label": mat_label, "name": color["name"], "hex": color.get("hex") or ""}] if color else [])
        pmeta = {"product_id": pid, "order_id": order_ref or None, "components": comps,
                 "full_color": bool(p.get("is_4cp") or "4cp" in mat or p.get("mimaki_jig")),
                 "inks": ([] if one_color else [{"pms": i.get("pms"), "pms_hex": i.get("pms_hex"),
                                                 "hex": i.get("hex"), "hidden": False} for i in inks if i.get("pms")]),
                 "imprint": {"name": sp_ink, "hex": sp_hex} if one_color and sp_ink else None,
                 "sides": "1side"}
        if pmeta["imprint"] is None:
            pmeta.pop("imprint")
        artist = {"note": str(params.get("notes") or "")[:400] or None,
                  "customer": str(params.get("customer") or "")[:120] or None}
        proof, two = _S._generic_proof(str(print_pdf), prefix, str(serve_dir), pmeta, job, {}, artist, None)
        if not proof or not Path(proof).exists():
            return jsonify({"ok": False, "proof_url": None, "problem_codes": ["proof_failed"],
                            "problems": ["The proof couldn't be built."]})
        _sweep_proofs()
        token = secrets.token_urlsafe(32)
        shutil.copy2(str(proof), str(_proof_dir() / f"{token}.pdf"))
        expires = time.time() + PROOF_DAYS * 86400
        (_proof_dir() / f"{token}.json").write_text(json.dumps({
            "item": pid, "area": slot["id"], "created": time.time(), "expires": expires,
            "filename": f"{prefix}-PROOF.pdf"}))
    finally:
        try:
            shutil.rmtree(str(_S.HERE / "_serve" / job_id), ignore_errors=True)
        except Exception:
            pass
    return jsonify({
        "ok": True,
        "proof_url": f"{_base_url()}/api/automation/proofs/{token}.pdf",
        "expires_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(expires)),
        "problems": [], "warnings": r["warnings"],
        "details": {"item": pid, "area": slot["id"], "color": (color or {}).get("name"),
                    "printed_size_in": {"width": pw, "height": ph},
                    "inks": ([sp_ink] if one_color and sp_ink else [i.get("pms") for i in inks if i.get("pms")])},
    })



# ── Several locations in one request ("areas") ─────────────────────────────
# Each entry: an area id (or {"area": id, width_in | height_in, position,
# x_in, y_in, ink}). Art: the shared file / art_url, or per location
# file_<areaId> (multipart) / art_url_<areaId>. Every location is checked on
# its own; a proof is made only when every one of them works.

_AREA_KEYS = ("width_in", "height_in", "position", "x_in", "y_in", "ink")


def _parse_areas(pid, p, raw):
    """-> ([(slot, settings)], None) or (None, error response)."""
    if isinstance(raw, str):
        txt = raw.strip()
        try:
            raw = json.loads(txt)
        except ValueError:
            raw = [a.strip() for a in txt.split(",") if a.strip()]
    if isinstance(raw, (str, dict)):
        raw = [raw]
    if not isinstance(raw, list) or not raw:
        return None, _err("'areas' must be a list of area ids, e.g. [\"side1\", \"side2\", \"bottom\"].", 400,
                          code="bad_areas")
    offered = {a["id"] for a in _areas(pid, p, None, None)}
    out, seen = [], set()
    for ent in raw:
        if isinstance(ent, dict):
            aid = ent.get("area") or ent.get("id")
            settings = {k: ent[k] for k in _AREA_KEYS if ent.get(k) not in (None, "")}
        else:
            aid, settings = ent, {}
        slot = _area(p, aid)
        if not slot or slot.get("id") not in offered:
            return None, _err(f"Unknown decoration area {aid!r} for {pid}. Areas: {', '.join(sorted(offered))}.", 400,
                              code="unknown_area", area=aid)
        if slot["id"] in seen:
            return None, _err(f"Area {slot['id']!r} is listed twice.", 400, code="duplicate_area", area=slot["id"])
        seen.add(slot["id"])
        out.append((slot, settings))
    # Sides or a wrap, never both (exclusive_slots).
    ids = {sl["id"] for sl, _ in out}
    groups = [set(g) for g in (p.get("exclusive_slots") or []) if set(g) & ids]
    if len(groups) > 1:
        return None, _err(f"{pid} prints either " + " or ".join("/".join(sorted(g)) for g in
                          (set(g) for g in p.get('exclusive_slots'))) + ", not both.", 400, code="areas_conflict")
    return out, None


def _multi_setup(params):
    """item + areas -> (pid, p, [(slot, settings)]) or an error response."""
    pid, p = _find_item(params.get("item_id"))
    if not pid:
        return None, _err(f"Unknown item_id {params.get('item_id')!r}. Use an id from search-items.", 404,
                          code="unknown_item")
    areas, bad = _parse_areas(pid, p, params.get("areas"))
    if bad:
        return None, bad
    return (pid, p, areas), None


def _check_each(pid, p, areas, params):
    """Check every location on its own -> [(slot, settings, result, art_key)].
    result is _check's dict, or one made from an artwork error."""
    shared = None                       # (src, name) or _ArtError, fetched once
    out, temp = [], []
    try:
        for slot, settings in areas:
            sid = slot["id"]
            fld, url = f"file_{sid}", f"art_url_{sid}"
            own = (request.files and request.files.get(fld) and request.files[fld].filename) or params.get(url)
            try:
                if own:
                    src, name = _take_art(params, fld, url)
                    temp.append(src)
                    key = f"{fld}:{name}:{src.stat().st_size}"
                else:
                    if shared is None:
                        try:
                            shared = _take_art(params)
                            temp.append(shared[0])
                        except _ArtError as e:
                            shared = e
                    if isinstance(shared, _ArtError):
                        raise shared
                    src, name = shared
                    key = "shared"
            except _ArtError as e:
                msg = e.message
                if e.code == "no_artwork":
                    msg = (f"No artwork for {sid}: send the shared 'file' / 'art_url', "
                           f"or '{fld}' / '{url}' for this location.")
                out.append((slot, settings, {"problems": [{"code": e.code, "message": msg}], "warnings": [],
                                             "suggestions": [e.suggestion] if e.suggestion else [], "info": {}}, None))
                continue
            sp = dict(params)
            for k in _AREA_KEYS:
                sp.pop(k, None)
            sp.update(settings)
            if "ink" not in settings and params.get("ink"):
                sp["ink"] = params["ink"]
            out.append((slot, settings, _check(pid, p, slot, src, name, sp), key))
    finally:
        for t in temp:
            try:
                Path(t).unlink(missing_ok=True)
            except Exception:
                pass
    return out


def _area_result(slot, r):
    info = r.get("info") or {}
    return {"area": slot["id"], "ok": not r["problems"],
            "problems": [x["message"] for x in r["problems"]],
            "problem_codes": [x["code"] for x in r["problems"]],
            "warnings": r["warnings"], "suggestions": r["suggestions"],
            "printed_size_in": {"width": info.get("printed_w_in"), "height": info.get("printed_h_in")}}


def _check_art_multi(params):
    got, bad = _multi_setup(params)
    if bad:
        return bad
    pid, p, areas = got
    results = [_area_result(slot, r) for slot, _, r, _ in _check_each(pid, p, areas, params)]
    return jsonify({"ok": all(x["ok"] for x in results), "item": pid, "results": results})


def _ink_named(name):
    nm = name if name in _S.PANTONE_RGB or name in _S.NON_PMS_HEX else (
        f"PANTONE {name}" if f"PANTONE {name}" in _S.PANTONE_RGB else None)
    return (nm, _S.NON_PMS_HEX.get(nm) or _S.PANTONE_RGB.get(nm) or "") if nm else (None, None)


def _make_proof_multi(params):
    got, bad = _multi_setup(params)
    if bad:
        return bad
    pid, p, areas = got

    def fail(results, extra_codes=(), extra_problems=()):
        probs = [f"{x['area']}: {m}" for x in results for m in x["problems"]] + list(extra_problems)
        codes = sorted({c for x in results for c in x["problem_codes"]} | set(extra_codes))
        return jsonify({"ok": False, "proof_url": None, "item": pid, "problems": probs, "problem_codes": codes,
                        "results": results})

    if not _supported(pid, p):
        return jsonify({"ok": False, "proof_url": None, "item": pid, "problems": [f"{pid} {_UNSUPPORTED_WHY}."],
                        "problem_codes": ["item_not_supported"], "results": []})
    colors = _colors(pid, p)
    color = None
    want = str(params.get("color") or params.get("variant") or "").strip()
    if colors:
        if not want:
            return jsonify({"ok": False, "proof_url": None, "item": pid, "problem_codes": ["color_required"],
                            "results": [], "problems": [f"Say which color the item is ('color'). {pid} comes in: "
                                                        + ", ".join(c['name'] for c in colors) + "."]})
        color = next((c for c in colors if c["name"].lower() == want.lower()), None)
        if not color:
            return jsonify({"ok": False, "proof_url": None, "item": pid, "problem_codes": ["unknown_color"],
                            "results": [], "problems": [f"{pid} doesn't come in {want!r}. Colors: "
                                                        + ", ".join(c['name'] for c in colors) + "."]})

    checked = _check_each(pid, p, areas, params)
    one_color = _S.is_screenprint(pid)
    parts, results = [], []
    for slot, settings, r, key in checked:
        res = _area_result(slot, r)
        info = r.get("info") or {}
        part = None
        if res["ok"]:
            pw, ph = info["printed_w_in"], info["printed_h_in"]
            sp = dict(settings)
            dx, dy = _position(sp, slot, pw, ph)
            zw, zh = info["zone_w_in"] * 72, info["zone_h_in"] * 72
            if abs(dx) > (zw - pw * 72) / 2 + 0.72 or abs(dy) > (zh - ph * 72) / 2 + 0.72:
                res["problems"].append("At that position the artwork runs outside the decoration area.")
                res["problem_codes"].append("outside_area")
            inks = info.get("inks") or []
            sp_ink = sp_hex = ""
            if one_color:
                want_ink = str(settings.get("ink") or params.get("ink") or "").strip()
                if want_ink:
                    sp_ink, sp_hex = _ink_named(want_ink)
                    if not sp_ink:
                        res["problems"].append(f"Unknown ink {want_ink!r} - give a Pantone name like 'PANTONE 186 C'.")
                        res["problem_codes"].append("unknown_ink")
                        sp_ink = sp_hex = ""
                elif inks:
                    sp_ink, sp_hex = inks[0].get("pms") or "", inks[0].get("pms_hex") or inks[0].get("hex") or ""
            part = {"slot": slot, "info": info, "dx": dx, "dy": dy, "pw": pw, "ph": ph, "inks": inks,
                    "sp_ink": sp_ink, "sp_hex": sp_hex, "key": key, "warnings": r["warnings"]}
        res["ok"] = not res["problems"]
        results.append(res)
        parts.append(part)
    # A one-colour item prints one ink for the whole order.
    if one_color and all(parts):
        first = next((x["sp_ink"] for x in parts if x["sp_ink"]), "")
        for x, res in zip(parts, results):
            if x["sp_ink"] and first and x["sp_ink"] != first:
                res["problems"].append(f"This item prints one ink for the whole order: {parts[0]['slot']['id']} "
                                       f"is {first}, this location asks for {x['sp_ink']}.")
                res["problem_codes"].append("ink_mismatch")
                res["ok"] = False
    if not all(r["ok"] for r in results):
        return fail(results)

    sp_ink = next((x["sp_ink"] for x in parts if x["sp_ink"]), "")
    sp_hex = next((x["sp_hex"] for x in parts if x["sp_ink"] == sp_ink and x["sp_hex"]), "")
    order_ref = re.sub(r"[^\w\-]", "", str(params.get("reference") or ""))[:40]
    prefix = _S._safe_prefix(f"AUTO-{order_ref or 'PROOF'}-{secrets.token_hex(3).upper()}")
    job_id = _S._unique_id("job")
    _S.new_job(job_id, {})
    all_inks = []
    for x in parts:
        for i in x["inks"]:
            if i.get("hex") and i["hex"] not in [j.get("hex") for j in all_inks]:
                all_inks.append(i)
    body = {
        "product_id": pid, "order_id": order_ref or "AUTO",
        # A 1 x 1 template and each zone the slot's own size: offsets in pt.
        "placement": {x["slot"]["id"]: {"ox": x["dx"], "oy": -x["dy"], "sc": 1.0, "rot": 0, "w_pt": x["pw"] * 72}
                      for x in parts},
        "template_w": 1.0, "template_h": 1.0,
        "zones": {x["slot"]["id"]: {"w": float(x["slot"]["w_pt"]), "h": float(x["slot"]["h_pt"])} for x in parts},
        "is_4cp": bool(p.get("is_4cp")), "fill_mode": "none",
        "screen_print_ink": sp_ink, "screen_print_ink_hex": sp_hex,
        "hidden_colors": [], "source_inks": [i.get("hex") for i in all_inks],
        "neoprene_name": (color or {}).get("name") or "", "thread_name": "",
    }
    saved_paths = {}
    for x in parts:
        saved = x["info"].get("saved_path")
        if saved and Path(saved).suffix.lower() in (".svg", ".eps"):
            try:
                import press_layout as _pl
                saved = _pl.art_as_pdf(str(saved), work_dir=str(Path(saved).parent))
            except Exception:
                pass
        if one_color and sp_ink and saved and Path(saved).suffix.lower() in (".pdf", ".ai"):
            try:
                import onecolor
                out = Path(saved).with_name(Path(saved).stem + ".ink.pdf")
                srcs = [i.get("hex") for i in x["inks"] if i.get("hex")] or ["#000000"]
                onecolor.separate(str(saved), [{"sources": srcs, "pms": sp_ink, "pms_hex": sp_hex, "hex": srcs[0]}],
                                  str(out), mode="press")
                saved = str(out)
            except Exception as e:
                print(f"automation: one-colour recolour skipped: {e}")
        saved_paths[x["slot"]["id"]] = saved
    ids = [x["slot"]["id"] for x in parts]
    if "side1" in ids and "side2" in ids:
        k1 = next(x["key"] for x in parts if x["slot"]["id"] == "side1")
        k2 = next(x["key"] for x in parts if x["slot"]["id"] == "side2")
        sides = "2same" if k1 == k2 else "2diff"
    else:
        sides = "1side"
    try:
        _S._pdf_worker(job_id, p, body["order_id"], saved_paths, body)
        job = _S.get_job(job_id) or {}
        if job.get("status") != "done":
            return jsonify({"ok": False, "proof_url": None, "item": pid, "problem_codes": ["proof_failed"],
                            "results": results,
                            "problems": ["The proof couldn't be built: " + str(job.get("message") or "unknown error")]})
        placed = {a.get("id") for a in job.get("art_sizes") or []}
        missing = [i for i in ids if i not in placed]
        if missing:
            return jsonify({"ok": False, "proof_url": None, "item": pid, "problem_codes": ["proof_failed"],
                            "results": results,
                            "problems": [f"The proof couldn't place the art on: {', '.join(missing)}."]})
        serve_dir = Path(job["serve_dir"])
        print_pdf = serve_dir / job["production_filename"]
        mat = p.get("material") or ""
        labels = [s_.get("label") or s_.get("id") for s_ in p.get("art_slots") or []]
        mat_label = _S._catalog_meta(pid, p, labels).get("material_label") or "Body"
        comps = ([{"label": "Background", "name": "None (white)", "hex": "#FFFFFF"}]
                 if (p.get("is_4cp") or "4cp" in mat) else
                 [{"label": mat_label, "name": color["name"], "hex": color.get("hex") or ""}] if color else [])
        pmeta = {"product_id": pid, "order_id": order_ref or None, "components": comps,
                 "full_color": bool(p.get("is_4cp") or "4cp" in mat or p.get("mimaki_jig")),
                 "inks": ([] if one_color else [{"pms": i.get("pms"), "pms_hex": i.get("pms_hex"),
                                                 "hex": i.get("hex"), "hidden": False}
                                                for i in all_inks if i.get("pms")]),
                 "sides": sides}
        if one_color and sp_ink:
            pmeta["imprint"] = {"name": sp_ink, "hex": sp_hex}
        artist = {"note": str(params.get("notes") or "")[:400] or None,
                  "customer": str(params.get("customer") or "")[:120] or None}
        proof, two = _S._generic_proof(str(print_pdf), prefix, str(serve_dir), pmeta, job, {}, artist, None)
        if not proof or not Path(proof).exists():
            return jsonify({"ok": False, "proof_url": None, "item": pid, "problem_codes": ["proof_failed"],
                            "results": results, "problems": ["The proof couldn't be built."]})
        _sweep_proofs()
        token = secrets.token_urlsafe(32)
        shutil.copy2(str(proof), str(_proof_dir() / f"{token}.pdf"))
        expires = time.time() + PROOF_DAYS * 86400
        (_proof_dir() / f"{token}.json").write_text(json.dumps({
            "item": pid, "areas": ids, "created": time.time(), "expires": expires,
            "filename": f"{prefix}-PROOF.pdf"}))
    finally:
        try:
            shutil.rmtree(str(_S.HERE / "_serve" / job_id), ignore_errors=True)
        except Exception:
            pass

    def inks_of(x):
        if one_color:
            return [sp_ink] if sp_ink else []
        return [i.get("pms") for i in x["inks"] if i.get("pms")]
    return jsonify({
        "ok": True,
        "proof_url": f"{_base_url()}/api/automation/proofs/{token}.pdf",
        "expires_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(expires)),
        "problems": [], "warnings": [f"{x['slot']['id']}: {w}" for x in parts for w in x["warnings"]],
        "details": {"item": pid, "color": (color or {}).get("name"),
                    "areas": [{"area": x["slot"]["id"],
                               "printed_size_in": {"width": x["pw"], "height": x["ph"]},
                               "inks": inks_of(x), "warnings": x["warnings"]} for x in parts]},
    })

@bp.route("/proofs/<name>", methods=["GET"])
def get_proof(name):
    """A finished proof, by its link (the token is the access; 7 days)."""
    tok = name[:-4] if name.endswith(".pdf") else name
    if not _TOKEN_RE.match(tok):
        return _err("Not found.", 404)
    d = _proof_dir()
    f, meta = d / f"{tok}.pdf", d / f"{tok}.json"
    try:
        m = json.loads(meta.read_text())
    except Exception:
        return _err("This proof link has expired or doesn't exist.", 404)
    if not f.exists() or time.time() > float(m.get("expires") or 0):
        return _err("This proof link has expired or doesn't exist.", 404)
    return send_file(str(f), mimetype="application/pdf", as_attachment=False,
                     download_name=m.get("filename") or "proof.pdf", max_age=3600)
