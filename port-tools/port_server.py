"""Build the client (fast-studio) server.py from main's server.py.

Main's features stay; NetSuite, Dropbox, export log, ink coverage, 4imprint,
What's New and the internal sign-in come out; the sandbox rules from the
current fast-studio server go back in.
"""
import re
import sys

src, dst = sys.argv[1], sys.argv[2]
s = open(src, encoding="utf-8").read()


def rep(old, new, count=1):
    global s
    n = s.count(old)
    if n != count:
        raise SystemExit(f"expected {count} of {old[:80]!r}, found {n}")
    s = s.replace(old, new)


def cut(start, end, new="", keep_end=True):
    """Replace the text from `start` up to (not incl.) `end` with `new`."""
    global s
    a = s.index(start)
    if s.count(start) != 1:
        raise SystemExit(f"start not unique: {start[:80]!r}")
    b = s.index(end, a + len(start))
    s = s[:a] + new + (s[b:] if keep_end else s[b + len(end):])


# ── header: client sign-in and the sandbox, no internal blueprints ──────────
cut("# Sign-in for the whole app (internal tool).", "\n\n# Every /api/ error comes back as JSON",
    '''# Client sign-in: one shared password (CLIENT_PASSWORD), client_login.py.
import client_login
client_login.init_app(app)

# ── CLIENT SANDBOX ──────────────────────────────────────────────────────────
# Numo's client ordering site: the configurator, mockups and proofs for the
# This Is Fast items, behind one shared client password.
#   * the catalog lists the This Is Fast items only (the rest are still here,
#     just not listed)
#   * clients get the client view only
#   * no pricing (the price sheet is not fetched)
#   * an export ships the digital proof and the virtual only: no press files,
#     2X2, print PDF, artwork originals or ink coverage
#   * every export, job and restored proof belongs to the browser session that
#     made it (client_login.owner_tag): another client can't open it, even
#     with its link
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
    # Delete what was listed and is not kept (press files, 2X2, artwork, the
    # order details). Files never listed are the build's own working notes
    # (the proof's sidecars), which combining the variants reads.
    for e in listing:
        rel = str(e.get("path") or "")
        if not rel or rel in keep_paths:
            continue
        f = (root / rel).resolve()
        if root in f.parents and f.is_file():
            f.unlink()
    for junk in ("art",):
        d = root / junk
        if d.is_dir():
            shutil.rmtree(d, ignore_errors=True)
    for f in root.glob("*-order.json"):
        f.unlink(missing_ok=True)
    return keep


def _claim(folder):
    """Mark an export / restore folder as this browser session's."""
    try:
        (Path(folder) / "_owner").write_text(client_login.owner_tag())
    except Exception as e:
        print(f"owner not written: {e}")


def _mine(folder):
    """True when the folder was made by this browser session."""
    try:
        return client_login.owns((Path(folder) / "_owner").read_text().strip())
    except Exception:
        return False
''')

# ── pages: no 4imprint page ─────────────────────────────────────────────────
cut('@app.route("/4imprint")\n', '@app.route("/<pid>")\n')

# ── pricing: none ───────────────────────────────────────────────────────────
cut('    """Proxy the pricing CSV from Dropbox to avoid CORS issues."""', "\n\n\n",
    '''    """Sandbox: no pricing. An empty price sheet, so the page shows none."""
    return Response("", mimetype="text/csv")''')

# ── catalog: the client's This Is Fast list ─────────────────────────────────
rep("    out = _tif_catalog(out)\n", "    out = _client_catalog(out)\n")
cut("# The This Is Fast lineup as the website offers it,", "# ---------------------------------------------------------------------------\n# Route – product list",
    '''# ── The client catalog ──────────────────────────────────────────────────────
# Exactly the This Is Fast items on numomfg.com, by their site names. The ones
# set up here open in the configurator (the 4CP items too); the rest show as
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
    ("0837-24HR-IMP", "This Is Fast Jotter Pen", "items/jotter-pen.jpg"),   # the 24 HR Jotter
    ("0070-3w", "This Is Fast 4CP Kolder Kaddy", "items/kolder-kaddy-4cp.jpg"),
    ("1080-3w", "This Is Fast Kolder Kaddy Neoprene for Slim Cans - 4CP", "items/kolder-kaddy-slim-4cp.jpg"),
    ("9100-4CP", "This Is Fast 4CP Pocket Coolie", "items/pocket-coolie-4cp.jpg"),
    ("0472-4CP", "This Is Fast Pocket Coolie for Slim Cans - 4CP", "items/pocket-coolie-slim-4cp.jpg"),
    (None, "This Is Fast Duplex Kolder Kaddy", "soon/duplex-kolder-kaddy.jpg"),
    ("5020-TIF-10-1C", "This Is Fast Shamwow - Natural Canvas", "items/5020-TIF-10-1C.jpg"),
    ("5020-TIF-CC-1C", "This Is Fast Shamwow - Colored Canvas", "items/5020-TIF-CC-1C.jpg"),
    ("5010-TIF-10-1C", "This Is Fast Daily Grind - Natural Canvas", "items/5010-TIF-10-1C.jpg"),
    ("5010-TIF-CC-1C", "This Is Fast Daily Grind - Colored Canvas", "items/5010-TIF-CC-1C.jpg"),
]


_CLIENT_NAMES = {pid: name for pid, name, _ in CLIENT_CATALOG if pid}


def _client_catalog(out):
    by_id = {p["id"]: p for p in out}
    cat = []
    for n, (pid, name, photo) in enumerate(CLIENT_CATALOG):
        if pid and pid in by_id:
            # Every item here is a This Is Fast item, the 4CP ones included.
            p = dict(by_id[pid], name=name, label=name, display_label=name, coming_soon=False, catalog_order=n,
                     program="This Is Fast")
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

''')
rep('''            "label": p.get("label") or p.get("name", pid),
            "display_label": p.get("display_label") or p.get("label") or pid,''',
    '''            "label": p.get("label") or p.get("name", pid),
            "display_label": _CLIENT_NAMES.get(pid) or p.get("display_label") or p.get("label") or pid,''')
cut("            # 4imprint's item number when their art proofs open on this item\n",
    '            "supports_pms_assign": supports_pms_assign(pid),\n')

# Plain Black: keep the ink, drop the internal record note.
rep('''    # Plain Black (2026-10-15): the shop's standard black, not a Pantone chip -
    # Black C is Pantone's warm brown-black (#2D2926). NetSuite has it as
    # "Black" (id 27174).
''', '''    # Plain Black: the shop's standard black, not a Pantone chip - Black C is
    # Pantone's warm brown-black (#2D2926).
''')
rep('''    # The special inks go out on their own ("special"), not in "colors": the
    # NetSuite bridge reads "colors" as the inks TTool takes from an order line,
    # and its tests use 871 C as an ink it doesn't. The page adds them to its
    # list itself, so they show under Special inks and in search.''',
    '''    # The special inks go out on their own ("special"), not in "colors". The
    # page adds them to its list itself, so they show under Special inks and
    # in search.''')

# ── export: no NetSuite colour block, no Ttool_ 2X2 name, no ink payloads ───
cut("def _netsuite_colors_block(snap):", "\n\n\n", "", keep_end=False)
cut("# Every 2X2 the tool makes starts with this, so a NetSuite search",
    'TOOL_2X2_PREFIX = "Ttool_"', 'TOOL_2X2_PREFIX = ""', keep_end=False)

# export-combine: the ink numbers and the NetSuite payload go; the sandbox trim comes in.
cut('''        inks = []
        for d in srcs:
            try:
                inks.append(json.loads((d / "_ink.json").read_text()))''',
    '''        order = {"2x2": 0,''',
    '''        if SANDBOX:
            out, hidden = _sandbox_trim(out + hidden, serve_dir, keep_hidden=()), []
''')
rep('''                        "ink": ({"grams": ink_field, "lines": len(inks)} if inks else None)})''',
    '''                        "ink": None})''')

# export-bundle
rep('''        press = meta.get("press")
        if press:
            # The saved path is the normal route''',
    '''        press = meta.get("press")
        if press and SANDBOX:
            press["sheets_shared"] = True     # the proof only: no press sheets are made
        if press:
            # The saved path is the normal route''')
cut("        # ── NetSuite color references ──", "        # ── Print PDF ──")
cut('''        if meta.get("_ink") and not isinstance(meta.get("variant"), dict):''',
    '''        (serve_dir / "_files.json").write_text(json.dumps(listing))''',
    '''        if SANDBOX:
            listing = _sandbox_trim(listing, serve_dir)
''')
rep('''        # and keeping it in the archive now means the payload can be read and
        # checked against the files it belongs to before anything posts it.
''', '')

# press files on their own: not in the sandbox
rep('''    the configurator's Export goes through /api/export-bundle."""
    body = request.get_json(force=True) or {}''',
    '''    the configurator's Export goes through /api/export-bundle."""
    if SANDBOX:
        return jsonify({"error": "Press files are not available here."}), 404
    body = request.get_json(force=True) or {}''')

# ── 4imprint: out (its restore source, its routes) ──────────────────────────
cut("def _four_imprint_no(pid):", '@app.route("/api/restore", methods=["POST"])')
cut('''    if request.form.get("source") == "4imprint":''', '''    try:
        pdf = pikepdf.open(str(src))''')
cut("# 4imprint pint glass (9613) -> direct print file (imprint4.py)", '@app.route("/api/restore/<token>")')

# ── artist / NetSuite search link, ink coverage, NetSuite line, export log ──
rep('''        "netsuite_search_url": os.environ.get("NETSUITE_SEARCH_URL", ""),\n''', "")
s = re.sub(r"#   NETSUITE_SEARCH_URL.*?hidden\n#\s+when it is not set\.\n", "", s, flags=re.S)
cut("def _ink_coverage(slots):", "_FAVICON_PNG = ")
cut("# ── Export log ──", '@app.route("/api/export-zip/<export_id>")')

# ── ownership: exports, jobs, restored proofs and picked art are the session's ─
rep('''def new_job(job_id, initial):
    with JOBS_LOCK:
        JOBS[job_id] = {"status": "pending", **initial}''',
    '''def new_job(job_id, initial):
    try:
        owner = client_login.owner_tag()
    except RuntimeError:                      # outside a request
        owner = None
    with JOBS_LOCK:
        JOBS[job_id] = {"status": "pending", **initial, "_owner": owner}''')
rep('''def job_status(job_id):
    job = get_job(job_id)
    if not job:
        return jsonify({"error": "Unknown job"}), 404
    return jsonify(job)''',
    '''def job_status(job_id):
    job = get_job(job_id)
    if not job or not client_login.owns(job.get("_owner")):
        return jsonify({"error": "Unknown job"}), 404
    return jsonify({k: v for k, v in job.items() if k not in ("_owner", "serve_dir")})''')
rep('''    job = get_job(job_id)
    if not job or "serve_dir" not in job:
        return jsonify({"error": "Not found"}), 404''',
    '''    job = get_job(job_id)
    if not job or "serve_dir" not in job or not client_login.owns(job.get("_owner")):
        return jsonify({"error": "Not found"}), 404''')
rep('''    job = get_job(job_id)
    if job and "serve_dir" in job:
        try: shutil.rmtree(job["serve_dir"], ignore_errors=True)''',
    '''    job = get_job(job_id)
    if job and "serve_dir" in job and client_login.owns(job.get("_owner")):
        try: shutil.rmtree(job["serve_dir"], ignore_errors=True)''')

# export folders: claimed when made, checked when read
rep('''    serve_dir = HERE / "_serve" / _unique_id("export")''',
    '''    serve_dir = HERE / "_serve" / _unique_id("export")
    serve_dir.mkdir(parents=True, exist_ok=True)
    _claim(serve_dir)''', count=2)
rep('''    manifest = HERE / "_serve" / export_id / "_files.json"
    if not manifest.exists():''',
    '''    manifest = HERE / "_serve" / export_id / "_files.json"
    if not manifest.exists() or not _mine(manifest.parent):''')
rep('''    root = (HERE / "_serve" / export_id).resolve()
    manifest = root / "_files.json"
    if not manifest.exists():
        return jsonify({"error": "These files have expired. Export again."}), 404''',
    '''    root = (HERE / "_serve" / export_id).resolve()
    manifest = root / "_files.json"
    if not manifest.exists() or not _mine(root):
        return jsonify({"error": "These files have expired. Export again."}), 404''', count=2)
rep('''    allowed = {e["path"] for e in json.loads(manifest.read_text())}''',
    '''    allowed = {e["path"] for e in json.loads(manifest.read_text())
               if not (SANDBOX and (e.get("hidden") or e.get("kind") not in SANDBOX_KINDS))}''')
rep('''    customer = request.args.get("customer") == "1"''',
    '''    customer = SANDBOX or request.args.get("customer") == "1"''')
rep('''    VIRTUALS/ and PRESS FILES/. Hidden entries (the old-name 2X2
    the NetSuite bridge reads) stay out. ?name= names the zip.''',
    '''    VIRTUALS/ and PRESS FILES/. Hidden entries stay out. ?name= names the zip.''')

# restored proofs and picked art
rep('''    rdir = HERE / "uploads" / "_restore" / token
    rdir.mkdir(parents=True, exist_ok=True)''',
    '''    rdir = HERE / "uploads" / "_restore" / token
    rdir.mkdir(parents=True, exist_ok=True)
    _claim(rdir)''')
rep('''    f = HERE / "uploads" / "_restore" / token / "bundle.json"
    if not f.exists():
        return jsonify({"error": "That revision link has expired — drop the proof in again."}), 404''',
    '''    f = HERE / "uploads" / "_restore" / token / "bundle.json"
    if not f.exists() or not _mine(f.parent):
        return jsonify({"error": "That revision link has expired — drop the proof in again."}), 404''')
rep('''    f = HERE / "uploads" / "_restore" / token / "bundle.json"
    if not f.exists():
        return jsonify({"error": "Expired."}), 404''',
    '''    f = HERE / "uploads" / "_restore" / token / "bundle.json"
    if not f.exists() or not _mine(f.parent):
        return jsonify({"error": "Expired."}), 404''')

# artist mode header: no NetSuite
cut("# Artist mode — internal artists attaching proofs to an existing NSO by hand",
    "_EXPORT_ID = re.compile",
    '''# Artist mode (the sandbox keeps clients in the client view)
# ---------------------------------------------------------------------------
#
#   ARTIST_PASSCODE      if set, artist mode asks for it once per browser.

''')

# ── follow-ups (2026-10-28) ─────────────────────────────────────────────────
rep('''        if d.parent != root or not (d / "_files.json").is_file() or not (d / "_variant.json").is_file():''',
    '''        if d.parent != root or not (d / "_files.json").is_file() or not (d / "_variant.json").is_file() \\
                or not _mine(d):''')
rep('''    post to this route, and an order that will become a NetSuite sales order
    should not be able to arrive half-filled without anyone saying so.''', '''    post to this route, and an order should not be able to arrive half-filled
    without anyone saying so.''')
rep('''    Returns the _files.json listing. One hidden entry keeps the 2X2 under its
    old name (PREFIX-2X2.png): the NetSuite bridge finds the 2X2 it puts on
    the order by that name, and is left exactly as it is."""''', '''    Returns the _files.json listing."""''')
rep('''        # Written beside the artwork as its own file. This is what NetSuite
        # will be handed to open the sales order once the customer approves,
''', '''        # Written beside the artwork as its own file (the sandbox trims it).
''')
rep('''_CLIENT_NAMES = {pid: name for pid, name, _ in CLIENT_CATALOG if pid}
''', '''_CLIENT_NAMES = {pid: name for pid, name, _ in CLIENT_CATALOG if pid}


def _prune_products():
    """Only the catalog's items (and the products they borrow from: twins,
    shared assets, base items) stay in the app. The rest aren't offered here,
    and aren't sent to the browser either."""
    keep, todo = set(), [pid for pid, _, _ in CLIENT_CATALOG if pid in PRODUCTS]

    def refs(v):
        if isinstance(v, str):
            if v in PRODUCTS:
                yield v
        elif isinstance(v, dict):
            for x in v.values():
                yield from refs(x)
        elif isinstance(v, (list, tuple)):
            for x in v:
                yield from refs(x)
    while todo:
        pid = todo.pop()
        if pid in keep:
            continue
        keep.add(pid)
        todo.extend(r for r in refs(PRODUCTS[pid]) if r not in keep)
    for pid in [p for p in PRODUCTS if p not in keep]:
        del PRODUCTS[pid]


if SANDBOX:
    _prune_products()
''')
rep('''    for pid, why in missing.items():
        print(f"⚠️  press template''', '''    for pid, why in missing.items():
        if pid not in PRODUCTS:            # not offered on this site
            continue
        print(f"⚠️  press template''')

# ── one imprint location (2026-10-29): the TIF pens print one side only ─────
rep('''if SANDBOX:
    _prune_products()
''', '''if SANDBOX:
    _prune_products()


# Items that print in ONE imprint location here, though they have two (the
# pens: Side 1 or Side 2, not both). The configurator still shows both sides,
# lets the client pick which one prints, and keeps the other empty; the
# export holds to it too (_one_imprint), so the proof shows that one side.
CLIENT_ONE_IMPRINT = {"0837-24HR-IMP"}
for _pid in CLIENT_ONE_IMPRINT:
    if _pid in PRODUCTS:
        PRODUCTS[_pid]["max_imprints"] = 1


def _one_imprint(meta):
    # An export of a one-location item keeps the art of one side only (the
    # first side the job has art on): the press job, the proof's sides and the
    # embedded job are trimmed, whatever the browser sent.
    pid = ((meta.get("press") or {}).get("product_id") or (meta.get("proof") or {}).get("product_id")
           or meta.get("product_id") or "")
    if (PRODUCTS.get(pid) or {}).get("max_imprints") != 1:
        return
    sides = ("side1", "side2")
    press = meta.get("press") if isinstance(meta.get("press"), dict) else {}
    snap = meta.get("snapshot") if isinstance(meta.get("snapshot"), dict) else {}
    have = [s for s in (press.get("slots") or []) if s in sides] \\
        or [s for s in sides if (snap.get("slots") or {}).get(s)]
    keep = have[0] if have else None
    drop = [s for s in sides if s != keep]
    if press:
        press["slots"] = [s for s in (press.get("slots") or []) if s not in drop]
        for k in ("art_paths", "placement", "inks_by_slot", "bg_by_slot"):
            if isinstance(press.get(k), dict):
                for s in drop:
                    press[k].pop(s, None)
        press["sides"] = "1side" if keep else None
    if isinstance(meta.get("proof"), dict) and keep:
        meta["proof"]["sides"] = "1side"
    if isinstance(snap.get("slots"), dict):
        for s in drop:
            snap["slots"].pop(s, None)
        snap["sides"] = "diff"
''')
rep('''            "supports_pms_assign": supports_pms_assign(pid),
            "max_spot_inks": _max_inks_for(pid) if supports_pms_assign(pid) else 0,''',
    '''            "supports_pms_assign": supports_pms_assign(pid),
            "max_imprints": p.get("max_imprints"),
            "max_spot_inks": _max_inks_for(pid) if supports_pms_assign(pid) else 0,''')
rep('''        press = meta.get("press")
        if press and SANDBOX:''', '''        _one_imprint(meta)
        press = meta.get("press")
        if press and SANDBOX:''')

# ── proof matches the 2X2 on one-location items; SVG art on the pen panels ──
rep('''                                Path(serve_dir) / (f"{prefix}-2X2.png" if two else f"{prefix}-flat.png"),
                                two_by_two=two, hand=hand,''',
    '''                                Path(serve_dir) / (f"{prefix}-2X2.png" if two else f"{prefix}-flat.png"),
                                two_by_two=two, hand=hand,
                                # One-location items (the TIF pens): every side, the blank one
                                # too, so the proof lays out exactly as the 2X2 does.
                                show_all=product.get("max_imprints") == 1,''')
rep('''"rot": float((placement.get(slot["id"]) or {}).get("rot") or 0), "file": None, "clip": None})''',
    '''"rot": float((placement.get(slot["id"]) or {}).get("rot") or 0), "file": _svg_tight_png(art_path), "clip": None})''')
rep('''def _svg_drawing(path):''', '''def _svg_tight_png(path):
    """SVG art as a PNG cropped to its ink, for the proof's and the 2X2's
    drawn panels (the pens), which place art from a picture. None if it
    can't be drawn: the panel then falls back as before."""
    try:
        import cairosvg
        out = Path(str(path) + ".tight.png")
        if not out.exists():
            buf = io.BytesIO()
            cairosvg.svg2png(bytestring=Path(path).read_bytes(), write_to=buf, output_width=2000)
            with Image.open(io.BytesIO(buf.getvalue())) as im:
                im = im.convert("RGBA")
                bb = im.getchannel("A").getbbox()
                (im.crop(bb) if bb else im).save(out)
        return str(out)
    except Exception as e:
        print(f"⚠️ SVG panel art not drawn: {e}")
        return None


def _svg_drawing(path):''')

# ── a picture saved inside a PDF/AI is read as that picture (2026-10-29) ────
rep('''        # Live text: outlined here when the file carries its fonts, so the
        # preview, the press files and Illustrator never depend on the font;''',
    '''        # A PDF / AI that is only a placed picture (a JPG or PNG saved into a
        # PDF wrapper, like a logo placed in Illustrator and saved) is read as
        # that picture: drawn to a PNG, it goes the way a PNG upload goes -
        # traced to vector on one-color and spot items - instead of being
        # turned away as "a placed image rather than vector artwork".
        if ext in {".pdf", ".ai"} and (enforce_1c or assign_pms) and vectorize.available():
            _png = _picture_only_pdf_to_png(orig_path)
            if _png:
                orig_path, ext = _png, ".png"
                f.filename = Path(f.filename or "art").stem + ".png"
                trace_raster, trace_multi = enforce_1c, assign_pms

        # Live text: outlined here when the file carries its fonts, so the
        # preview, the press files and Illustrator never depend on the font;''')
rep('''def _svg_tight_png(path):''', '''def _picture_only_pdf_to_png(path):
    """The page of a PDF / AI that holds nothing but placed pictures, drawn
    as a PNG at the pictures' own resolution (x2, at most 4000 px), on a
    transparent page. None when the page has any vector drawing, text or
    nested forms - real vector art keeps the vector path."""
    import pikepdf, subprocess
    try:
        with pikepdf.open(str(path)) as pdf:
            page = pdf.pages[0]
            xo = (page.Resources.get("/XObject") or {}) if page.get("/Resources") else {}
            imgs = [v for v in xo.values() if str(v.get("/Subtype")) == "/Image"]
            if not imgs or any(str(v.get("/Subtype")) != "/Image" for v in xo.values()):
                return None
            draw = {"m", "l", "c", "v", "y", "h", "re", "S", "s", "f", "F", "f*", "B", "B*", "b", "b*",
                    "Tj", "TJ", "'", '"', "sh", "BI"}
            scale = 1.0
            for operands, op in pikepdf.parse_content_stream(page):
                o = str(op)
                if o in draw:
                    return None
                if o == "cm" and len(operands) == 6:
                    scale = max(scale, abs(float(operands[0])), abs(float(operands[3])))
            px = max(int(v.get("/Width") or 0) for v in imgs)
            mb = [float(v) for v in page.mediabox]
        dpi = max(72.0, min(600.0, 72.0 * 2 * px / max(1.0, scale)))
        dpi = min(dpi, 4000 * 72.0 / max(1.0, mb[2] - mb[0], mb[3] - mb[1]))
        out = Path(str(path) + ".picture")
        subprocess.run(["pdftocairo", "-png", "-transp", "-singlefile", "-r", f"{dpi:.1f}", str(path), str(out)],
                       check=True, capture_output=True, timeout=120)
        png = Path(str(out) + ".png")
        return png if png.exists() else None
    except Exception as e:
        print(f"picture-in-PDF check skipped: {e}")
        return None


def _svg_tight_png(path):''')

# ── 4CP: the whole-item background sheet built from a side design (2026-10-29)
rep('''@app.route("/api/compose", methods=["POST"])''', '''def _bg_regions(product):
    """The sheet cut into the parts each background fills (points, y up):
    Side 1, the bottom and Side 2 bands across the whole sheet width, split
    halfway between the locations, and each side's visible panel (its bleed
    zone) inside its band. None if the item isn't laid out that way."""
    W, H = float(product.get("page_w") or 0), float(product.get("page_h") or 0)
    z = product.get("bleed_zones") or {}
    if W <= 0 or H <= 0 or not all(k in z for k in ("side1", "side2")):
        return None

    def rect(k):                        # zone fractions are from the top-left
        r = z[k]
        return [r["x"] * W, H - (r["y"] + r["h"]) * H, r["w"] * W, r["h"] * H]
    s1, s2 = rect("side1"), rect("side2")
    b = rect("bottom") if "bottom" in z else None
    s1_bottom = s1[1]                                   # y of Side 1's lower edge
    s2_top = s2[1] + s2[3]
    if b:
        cut1 = (s1_bottom + b[1] + b[3]) / 2.0
        cut2 = (b[1] + s2_top) / 2.0
    else:
        cut1 = cut2 = (s1_bottom + s2_top) / 2.0
    return {"W": W, "H": H,
            "side1": {"band": [0.0, cut1, W, H - cut1], "zone": s1},
            "side2": {"band": [0.0, 0.0, W, cut2], "zone": s2},
            "bottom": {"band": [0.0, cut2, W, cut1 - cut2], "zone": b} if b else None}


def _bg_color(hex_, pms=None):
    from reportlab.lib.colors import HexColor, CMYKColorSep
    hx = hex_ if re.fullmatch(r"#[0-9A-Fa-f]{6}", str(hex_ or "")) else "#FFFFFF"
    nm = str(pms or "").strip()
    if nm:
        try:
            from screenprint import hex_to_cmyk
            full = nm if nm.upper().startswith("PANTONE") else "PANTONE " + nm
            cy, ma, ye, k = hex_to_cmyk(PANTONE_RGB.get(full) or hx)
            return CMYKColorSep(cy, ma, ye, k, spotName=full, density=1)
        except Exception:
            pass
    return HexColor(hx)


def _bg_draw_base(c, base, band, zone, product_id):
    """One part's background: solid, gradient, picture or stock, filling the
    band (pictures cover it, centred on the visible panel)."""
    from reportlab.lib.colors import HexColor
    x, y, w, h = band
    c.saveState()
    p = c.beginPath(); p.rect(x, y, w, h); c.clipPath(p, stroke=0, fill=0)
    kind = base.get("type")
    if kind == "solid":
        c.setFillColor(_bg_color(base.get("hex"), base.get("pms")))
        c.rect(x, y, w, h, stroke=0, fill=1)
    elif kind == "gradient":
        stops = [s for s in (base.get("stops") or []) if re.fullmatch(r"#[0-9A-Fa-f]{6}", str(s))][:2] or ["#FFFFFF", "#000000"]
        if len(stops) == 1:
            stops.append(stops[0])
        zx, zy, zw, zh = zone or band
        d = str(base.get("dir") or "down")
        # Drawn in the side's own way up: "down" = top colour at the top.
        pts = {"down": (zx, zy + zh, zx, zy), "right": (zx, zy, zx + zw, zy),
               "diag": (zx, zy + zh, zx + zw, zy)}.get(d, (zx, zy + zh, zx, zy))
        c.linearGradient(pts[0], pts[1], pts[2], pts[3], (HexColor(stops[0]), HexColor(stops[1])), extend=True)
    elif kind in ("stock", "image"):
        src = _stock_bg_path(product_id, base.get("stock")) if kind == "stock" else _in_uploads(base.get("path"))
        if src:
            zx, zy, zw, zh = zone or band
            cx, cy = zx + zw / 2.0, zy + zh / 2.0
            if Path(src).suffix.lower() in (".pdf", ".ai"):
                from pdfrw import PdfReader
                from pdfrw.buildxobj import pagexobj
                from pdfrw.toreportlab import makerl
                xo = pagexobj(PdfReader(str(src)).pages[0])
                bb = [float(v) for v in xo.BBox]
                iw, ih = bb[2] - bb[0], bb[3] - bb[1]
                s = max(w / iw, h / ih, zw / iw, zh / ih)
                c.translate(cx - iw * s / 2.0, cy - ih * s / 2.0); c.scale(s, s); c.translate(-bb[0], -bb[1])
                c.doForm(makerl(c, xo))
            else:
                with Image.open(src) as im:
                    iw, ih = im.size
                # cover the whole band, centred on the panel
                s = max(w / iw, h / ih) * 1.0
                need = max(abs(cx - x), abs(x + w - cx)) * 2 / iw, max(abs(cy - y), abs(y + h - cy)) * 2 / ih
                s = max(s, need[0], need[1])
                c.drawImage(str(src), cx - iw * s / 2.0, cy - ih * s / 2.0, iw * s, ih * s, mask="auto")
    else:
        c.setFillColor(HexColor("#FFFFFF")); c.rect(x, y, w, h, stroke=0, fill=1)
    c.restoreState()


def _bg_draw_design(c, design_pdf, zone):
    """The shapes / text / art drawn on top, fitted to the visible panel."""
    from pdfrw import PdfReader
    from pdfrw.buildxobj import pagexobj
    from pdfrw.toreportlab import makerl
    xo = pagexobj(PdfReader(str(design_pdf)).pages[0])
    bb = [float(v) for v in xo.BBox]
    zx, zy, zw, zh = zone
    c.saveState()
    c.translate(zx, zy); c.scale(zw / (bb[2] - bb[0]), zh / (bb[3] - bb[1])); c.translate(-bb[0], -bb[1])
    c.doForm(makerl(c, xo))
    c.restoreState()


@app.route("/api/bg-sheet", methods=["POST"])
def bg_sheet():
    """
    The whole-item background for a 4CP insulator, from one side's design.

    Side 1 is designed; Side 2 is the same (upright on the item) or the same
    turned upside down; the bottom carries the background on or takes a solid
    colour. Laid onto the item's print sheet (Side 2 lies upside down on it)
    as one vector PDF, which the page then uses as the full-bleed background.

    {product_id, base: {type: solid|gradient|stock|image|none, hex, pms,
     stops, dir, stock, path}, design_pdf, side2: same|flip,
     bottom: {mode: same|solid, hex, pms}}
    """
    import hashlib
    from reportlab.pdfgen import canvas as rlcanvas
    body = request.get_json(silent=True) or {}
    pid = str(body.get("product_id") or "")
    product = PRODUCTS.get(pid) or {}
    reg = _bg_regions(product)
    if not reg:
        return jsonify({"error": "This item has no background layout."}), 400
    base = body.get("base") if isinstance(body.get("base"), dict) else {"type": "none"}
    design = _in_uploads(body.get("design_pdf")) if body.get("design_pdf") else None
    side2 = "flip" if body.get("side2") == "flip" else "same"
    bottom = body.get("bottom") if isinstance(body.get("bottom"), dict) else {"mode": "same"}
    key = hashlib.sha1(json.dumps([pid, base, str(design or ""), side2, bottom, 1], sort_keys=True,
                                  default=str).encode()).hexdigest()[:14]
    (UPLOADS_DIR / "_bg").mkdir(parents=True, exist_ok=True)
    out = UPLOADS_DIR / "_bg" / f"{pid}-{key}-background.pdf"
    try:
        if not out.exists():
            c = rlcanvas.Canvas(str(out), pagesize=(reg["W"], reg["H"]))
            for sid in ("side1", "side2"):
                band, zone = reg[sid]["band"], reg[sid]["zone"]
                # Side 2 lies upside down on the sheet: turned 180 there it
                # reads upright on the item ("same"); left as drawn, it reads
                # upside down ("flip").
                turn = sid == "side2" and side2 == "same"
                c.saveState()
                if turn:
                    bx, by, bw, bh = band
                    cx, cy = bx + bw / 2.0, by + bh / 2.0
                    c.translate(cx, cy); c.rotate(180); c.translate(-cx, -cy)
                    zx, zy, zw, zh = zone
                    zone = [2 * cx - zx - zw, 2 * cy - zy - zh, zw, zh]
                _bg_draw_base(c, base, band, zone, pid)
                if design:
                    _bg_draw_design(c, design, zone)
                c.restoreState()
            if reg.get("bottom"):
                b = reg["bottom"]
                if bottom.get("mode") == "solid":
                    _bg_draw_base(c, {"type": "solid", "hex": bottom.get("hex"), "pms": bottom.get("pms")},
                                  b["band"], b["zone"], pid)
                else:
                    _bg_draw_base(c, base, b["band"], b["zone"], pid)
            c.showPage(); c.save()
        return jsonify({"saved_path": str(out)})
    except Exception as e:
        import traceback; traceback.print_exc()
        out.unlink(missing_ok=True)
        return jsonify({"error": f"The background couldn't be built: {e}"}), 500


@app.route("/api/compose", methods=["POST"])''')

# ── 4CP: a template clients can lay a finished design out on (2026-10-29) ───
rep('''@app.route("/api/bg-sheet", methods=["POST"])''', '''@app.route("/api/bg-template/<pid>")
def bg_template(pid):
    """A PDF the size of the item's print sheet with Side 1, the bottom and
    Side 2 marked, for a client laying out a finished design themselves."""
    from reportlab.pdfgen import canvas as rlcanvas
    from reportlab.lib.colors import HexColor
    product = PRODUCTS.get(pid) or {}
    reg = _bg_regions(product)
    if not reg:
        return jsonify({"error": "No template for this item."}), 404
    buf = io.BytesIO()
    c = rlcanvas.Canvas(buf, pagesize=(reg["W"], reg["H"]))
    c.setTitle(f"{pid} background template")
    for sid, label in (("side1", "SIDE 1"), ("bottom", "BOTTOM"), ("side2", "SIDE 2 (upside down on this sheet)")):
        part = reg.get(sid)
        if not part:
            continue
        bx, by, bw, bh = part["band"]
        c.setFillColor(HexColor({"side1": "#EEF3FB", "bottom": "#F1F8F2", "side2": "#FBF0EE"}[sid]))
        c.rect(bx, by, bw, bh, stroke=0, fill=1)
        z = part.get("zone")
        if z:
            c.setStrokeColor(HexColor("#6B1A2A")); c.setDash(4, 3); c.setLineWidth(0.8)
            if sid == "bottom":
                c.ellipse(z[0], z[1], z[0] + z[2], z[1] + z[3], stroke=1, fill=0)
            else:
                c.rect(z[0], z[1], z[2], z[3], stroke=1, fill=0)
            c.setDash()
            c.setFillColor(HexColor("#6B1A2A")); c.setFont("Helvetica-Bold", 9)
            cx, cy = z[0] + z[2] / 2.0, z[1] + z[3] / 2.0
            c.saveState()
            if sid == "side2":
                c.translate(cx, cy); c.rotate(180); c.translate(-cx, -cy)
            c.drawCentredString(cx, cy, label if sid != "side2" else "SIDE 2")
            c.setFont("Helvetica", 6.5)
            if sid != "bottom":
                c.drawCentredString(cx, cy - 11, "dashed line = what shows on the item")
            c.restoreState()
    c.setFont("Helvetica", 6); c.setFillColor(HexColor("#555555"))
    c.drawString(6, 6, "Fill every colored band edge to edge (it is trimmed). Side 2 is printed upside down - turn your Side 2 art 180 degrees.")
    c.showPage(); c.save()
    resp = make_response(buf.getvalue())
    resp.headers["Content-Type"] = "application/pdf"
    resp.headers["Content-Disposition"] = f'attachment; filename="{pid}-background-template.pdf"'
    return resp


@app.route("/api/bg-sheet", methods=["POST"])''')

# ── Ask Numo, the chat assistant (2026-11-04): assistant.py ─────────────────
rep('''@app.route("/api/bg-template/<pid>")''', '''@app.route("/api/assistant/status")
def assistant_status():
    import assistant
    return jsonify({"enabled": assistant.enabled()})


@app.route("/api/assistant", methods=["POST"])
def assistant_route():
    """One turn of Ask Numo (assistant.py). Behind the client sign-in, with a
    per-session and per-address limit, so the monthly credits can't be run
    down from outside."""
    import assistant
    if request.content_length and request.content_length > assistant.MAX_BODY_BYTES:
        return jsonify({"error": "That's too much to send at once - try a smaller picture."}), 413
    body = request.get_json(silent=True) or {}
    msgs = body.get("messages") if isinstance(body.get("messages"), list) else []
    if not assistant.enabled():
        return jsonify({"error": assistant.UNAVAILABLE, "code": "unavailable"}), 503
    over = assistant.check_limits(msgs, client_login.owner_tag(), client_login._ip())
    if over:
        return jsonify(over[1]), over[0]
    status, out = assistant.chat(msgs)
    return jsonify(out), status


@app.route("/api/bg-template/<pid>")''')

# ── Mimaki press files in CMYK (2026-11-06): cmykpress.py ───────────────────
# Same change goes in the main app (see main-app-cmyk.md).
rep('''            notes.append(f"{tag}: white could not be set to the WHITE spot ({e})")
''', '''            notes.append(f"{tag}: white could not be set to the WHITE spot ({e})")
        # The Mimaki gets process colour: every PANTONE spot swatch dropped and
        # its art painted in the CMYK that swatch carries, nothing left in RGB
        # or gray, so the file is a CMYK document. WHITE stays a spot - the
        # Mimaki prints white ink only from it. Proofs and the app keep PMS.
        try:
            import cmykpress
            cr = cmykpress.convert(path)
            notes.extend(f"{tag}: {p}" for p in cr["problems"])
            left = cmykpress.leftovers(path)
            if left:
                notes.append(f"{tag}: not everything could be made CMYK ({', '.join(left)})")
        except Exception as e:
            import traceback; traceback.print_exc()
            notes.append(f"{tag}: the file could not be set to CMYK ({e})")
''')

open(dst, "w", encoding="utf-8").write(s)
print("ok", len(s.splitlines()), "lines")
