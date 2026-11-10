"""
Export log + proofs to Dropbox (client site only).

Every time a customer downloads their proof, this records the export and
files a copy in Numo's Dropbox:

    <DROPBOX_ROOT>/<Company>/<Project>/<date time> <file>   the proof + virtual
    <DROPBOX_ROOT>/<Company>/<Project>/<date time> details.txt
    <DROPBOX_ROOT>/Export Log.csv      one row per export (opens in Excel)

The customer never waits on Dropbox: the export is queued on disk and sent
by a background thread; anything that fails stays queued and is retried on
the next export (or from the setup page).

Railway variables
    DROPBOX_APP_KEY, DROPBOX_APP_SECRET   from the Dropbox app (App Console)
    DROPBOX_REFRESH_TOKEN                 from /dropbox-setup (one time)
    DROPBOX_SETUP_KEY                     any password; opens /dropbox-setup
    DROPBOX_ROOT                          optional, default "/This Is Fast Proofs"

Without the first three nothing is queued or sent; the site works as before.
"""
import csv
import io
import json
import os
import re
import shutil
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path

import requests

try:
    from zoneinfo import ZoneInfo
    CENTRAL = ZoneInfo("America/Chicago")
except Exception:                                  # pragma: no cover
    CENTRAL = None

HERE = Path(__file__).resolve().parent
QDIR = HERE / "_exportq"
LOG_NAME = "Export Log.csv"
COLUMNS = ["Date (Central)", "Project", "Company", "Name", "Email", "Notes", "Item #", "Item",
           "Details", "Files", "Dropbox folder"]
TOKEN_URL = "https://api.dropboxapi.com/oauth2/token"
API = "https://api.dropboxapi.com/2"
CONTENT = "https://content.dropboxapi.com/2"

_TOKEN = {"value": None, "exp": 0.0}
_TLOCK = threading.Lock()
_RUN = threading.Lock()
STATUS = {"last_ok": None, "last_error": None}


def _env(k, d=""):
    return (os.environ.get(k) or d).strip()


def enabled():
    return bool(_env("DROPBOX_APP_KEY") and _env("DROPBOX_APP_SECRET") and _env("DROPBOX_REFRESH_TOKEN"))


def root():
    r = "/" + _env("DROPBOX_ROOT", "/This Is Fast Proofs").strip("/")
    return r if r != "/" else ""


def now_central():
    return datetime.now(CENTRAL) if CENTRAL else datetime.now()


# ── names ───────────────────────────────────────────────────────────────────
_BAD = re.compile(r'[\\/:*?"<>|\x00-\x1f\x7f]+')


def clean(name, fallback="Unknown"):
    """A safe Dropbox folder or file name."""
    s = _BAD.sub(" ", str(name or "")).strip()
    s = re.sub(r"\s+", " ", s).strip(" .")[:80]
    return s or fallback


# ── Dropbox calls ───────────────────────────────────────────────────────────
class DropboxError(Exception):
    pass


def token(force=False):
    with _TLOCK:
        if not force and _TOKEN["value"] and time.time() < _TOKEN["exp"] - 120:
            return _TOKEN["value"]
        r = requests.post(TOKEN_URL, data={"grant_type": "refresh_token",
                                           "refresh_token": _env("DROPBOX_REFRESH_TOKEN"),
                                           "client_id": _env("DROPBOX_APP_KEY"),
                                           "client_secret": _env("DROPBOX_APP_SECRET")}, timeout=30)
        if r.status_code != 200:
            raise DropboxError(f"Dropbox sign-in failed ({r.status_code}): {r.text[:200]}")
        j = r.json()
        _TOKEN["value"] = j["access_token"]
        _TOKEN["exp"] = time.time() + float(j.get("expires_in") or 14400)
        return _TOKEN["value"]


def _arg(obj):
    # The header must be plain ASCII: json.dumps escapes everything else.
    return json.dumps(obj, ensure_ascii=True).replace("\x7f", "\\u007f")


def _call(url, *, arg=None, data=None, js=None, retry=True):
    h = {"Authorization": "Bearer " + token()}
    if arg is not None:
        h["Dropbox-API-Arg"] = _arg(arg)
    if data is not None:
        h["Content-Type"] = "application/octet-stream"
    r = requests.post(url, headers=h, data=data, json=js, timeout=120)
    if r.status_code == 401 and retry:
        token(force=True)
        return _call(url, arg=arg, data=data, js=js, retry=False)
    if r.status_code == 429:
        time.sleep(min(30, float(r.headers.get("Retry-After") or 5)))
        return _call(url, arg=arg, data=data, js=js, retry=retry)
    return r


def upload(path, data, mode="add"):
    r = _call(CONTENT + "/files/upload", data=data,
              arg={"path": path, "mode": mode, "autorename": mode == "add", "mute": True})
    if r.status_code != 200:
        raise DropboxError(f"upload {path} failed ({r.status_code}): {r.text[:200]}")
    return r.json()


def download(path):
    """(bytes, rev), or (None, None) if the file isn't there."""
    r = _call(CONTENT + "/files/download", arg={"path": path})
    if r.status_code == 409 and "not_found" in r.text:
        return None, None
    if r.status_code != 200:
        raise DropboxError(f"download {path} failed ({r.status_code}): {r.text[:200]}")
    meta = json.loads(r.headers.get("Dropbox-API-Result") or "{}")
    return r.content, meta.get("rev")


def account():
    r = _call(API + "/users/get_current_account", js=None)
    if r.status_code != 200:
        raise DropboxError(f"account check failed ({r.status_code}): {r.text[:200]}")
    j = r.json()
    return {"name": (j.get("name") or {}).get("display_name"), "email": j.get("email")}


def append_log(row):
    """Add one row to the shared CSV; another worker writing at the same time
    makes Dropbox refuse the stale copy, so it re-reads and tries again."""
    path = f"{root()}/{LOG_NAME}"
    for _ in range(8):
        data, rev = download(path)
        buf = io.StringIO()
        w = csv.writer(buf)
        if data is None:
            w.writerow(COLUMNS)
            text = ""
        else:
            text = data.decode("utf-8-sig", errors="replace")
            if text and not text.endswith("\n"):
                text += "\n"
        w.writerow([row.get(c, "") for c in COLUMNS])
        body = ("﻿" + text + buf.getvalue()) if data is None else ("﻿" + text + buf.getvalue())
        mode = "add" if rev is None else {".tag": "update", "update": rev}
        r = _call(CONTENT + "/files/upload", data=body.encode("utf-8"),
                  arg={"path": path, "mode": mode, "autorename": False, "mute": True})
        if r.status_code == 200:
            return
        if r.status_code == 409 and "conflict" in r.text:
            time.sleep(0.5)
            continue
        raise DropboxError(f"log update failed ({r.status_code}): {r.text[:200]}")
    raise DropboxError("log update kept colliding with another export; will retry")


# ── queue ───────────────────────────────────────────────────────────────────
def enqueue(record, files):
    """record: the export's details; files: [(Path, name)] to file with it."""
    if not enabled():
        return False
    QDIR.mkdir(parents=True, exist_ok=True)
    qid = f"{int(time.time() * 1000):013d}-{uuid.uuid4().hex[:8]}"
    tmp = QDIR / (qid + ".tmp")
    tmp.mkdir()
    names = []
    for src, name in files:
        name = clean(name, "file")
        shutil.copy2(str(src), str(tmp / name))
        names.append(name)
    record = dict(record, files=names, tries=0)
    (tmp / "record.json").write_text(json.dumps(record, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.rename(QDIR / qid)
    kick()
    return True


def pending():
    return sorted(p for p in QDIR.glob("*") if p.is_dir() and not p.name.endswith(".tmp")
                  and ".working" not in p.name) if QDIR.exists() else []


def kick():
    if enabled():
        threading.Thread(target=run_queue, daemon=True).start()


def run_queue():
    if not _RUN.acquire(blocking=False):
        return
    try:
        for d in pending():
            mine = d.with_name(d.name + f".working{os.getpid()}")
            try:
                d.rename(mine)              # claim it (other workers skip it)
            except OSError:
                continue
            try:
                _send(mine)
                shutil.rmtree(mine, ignore_errors=True)
                STATUS["last_ok"] = now_central().strftime("%Y-%m-%d %H:%M")
                STATUS["last_error"] = None
            except Exception as e:
                STATUS["last_error"] = f"{now_central():%Y-%m-%d %H:%M}: {e}"
                print(f"⚠️ export log: {e}")
                try:
                    rec = json.loads((mine / "record.json").read_text(encoding="utf-8"))
                    rec["tries"] = int(rec.get("tries") or 0) + 1
                    rec["last_error"] = str(e)[:300]
                    (mine / "record.json").write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
                except Exception:
                    pass
                mine.rename(d)
                break                       # Dropbox is unhappy: try again later
    finally:
        _RUN.release()
    # Claims left behind by a worker that died mid-send go back in the queue.
    if QDIR.exists():
        for w in QDIR.glob("*.working*"):
            if time.time() - w.stat().st_mtime > 900:
                try:
                    w.rename(QDIR / w.name.split(".working")[0])
                except OSError:
                    pass


def _send(d):
    rec = json.loads((d / "record.json").read_text(encoding="utf-8"))
    when = rec.get("when") or now_central().strftime("%Y-%m-%d %H:%M")
    stamp = when.replace(":", "")
    folder = f"{root()}/{clean(rec.get('company'), 'No company')}/{clean(rec.get('project'), 'No project')}"
    if not rec.get("_uploaded"):
        for name in rec.get("files") or []:
            upload(f"{folder}/{stamp} {name}", (d / name).read_bytes())
        upload(f"{folder}/{stamp} details.txt", details_text(rec).encode("utf-8"))
        rec["_uploaded"] = True       # don't upload twice if only the log row failed
        (d / "record.json").write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
    append_log({
        "Date (Central)": when, "Project": rec.get("project", ""), "Company": rec.get("company", ""),
        "Name": rec.get("name", ""), "Email": rec.get("email", ""), "Notes": rec.get("notes", ""),
        "Item #": rec.get("item_id", ""), "Item": rec.get("item", ""),
        "Details": " | ".join(f"{a}: {b}" for a, b in rec.get("details") or []),
        "Files": ", ".join(rec.get("files") or []), "Dropbox folder": folder,
    })


def details_text(rec):
    lines = [f"Exported   {rec.get('when', '')} (Central)",
             f"Project    {rec.get('project', '')}",
             f"Company    {rec.get('company', '')}",
             f"Name       {rec.get('name', '')}",
             f"Email      {rec.get('email', '')}",
             f"Notes      {rec.get('notes', '')}",
             f"Item       {rec.get('item_id', '')} {rec.get('item', '')}".rstrip(), ""]
    for a, b in rec.get("details") or []:
        lines.append(f"{a}: {b}")
    lines += ["", "Files: " + ", ".join(rec.get("files") or [])]
    return "\n".join(lines) + "\n"


# ── one-time setup page ─────────────────────────────────────────────────────
def setup_page(req):
    """GET/POST /dropbox-setup?key=DROPBOX_SETUP_KEY"""
    import html as _h
    key = _env("DROPBOX_SETUP_KEY")
    given = (req.values.get("key") or "").strip()
    if not key or given != key:
        return "Not found.", 404
    e = _h.escape
    app_key = _env("DROPBOX_APP_KEY")
    out = ["<h1>Dropbox for the export log</h1>"]
    if not (app_key and _env("DROPBOX_APP_SECRET")):
        out.append("<p>Add <b>DROPBOX_APP_KEY</b> and <b>DROPBOX_APP_SECRET</b> in Railway first, then reload this page.</p>")
        return _wrap(out)
    if req.method == "POST" and req.form.get("code"):
        r = requests.post(TOKEN_URL, data={"grant_type": "authorization_code", "code": req.form["code"].strip(),
                                           "client_id": app_key, "client_secret": _env("DROPBOX_APP_SECRET")},
                          timeout=30)
        if r.status_code != 200:
            out.append(f"<p class=bad>Dropbox said no ({r.status_code}): {e(r.text[:300])}. Get a new code and try again.</p>")
        else:
            rt = r.json().get("refresh_token") or ""
            out.append("<p class=ok>Connected. Copy this into Railway as <b>DROPBOX_REFRESH_TOKEN</b>, "
                       "then let it redeploy:</p>"
                       f"<textarea readonly rows=3 onclick='this.select()'>{e(rt)}</textarea>"
                       "<p>Keep it private - it lets the site write to that Dropbox.</p>")
            return _wrap(out)
    if req.method == "POST" and req.form.get("test"):
        try:
            acct = account()
            upload(f"{root()}/_connection test.txt",
                   f"Connected {now_central():%Y-%m-%d %H:%M} (Central)\n".encode(), mode="overwrite")
            out.append(f"<p class=ok>Working: signed in as {e(acct['name'] or '')} ({e(acct['email'] or '')}); "
                       f"wrote a test file in {e(root() or '/')}.</p>")
        except Exception as ex:
            out.append(f"<p class=bad>{e(str(ex))}</p>")
    if req.method == "POST" and req.form.get("retry"):
        kick()
        time.sleep(2)
        out.append("<p>Retrying the queue…</p>")
    url = ("https://www.dropbox.com/oauth2/authorize?client_id=" + app_key
           + "&response_type=code&token_access_type=offline")
    if not _env("DROPBOX_REFRESH_TOKEN"):
        out.append(f"<p><b>Step 1.</b> <a href='{e(url)}' target=_blank>Open Dropbox and allow access</a> "
                   "(sign in to the Numo Dropbox account). Dropbox shows a code.</p>"
                   f"<form method=post><input type=hidden name=key value='{e(given)}'>"
                   "<p><b>Step 2.</b> Paste the code here: <input name=code size=50> <button>Connect</button></p></form>")
    else:
        out.append(f"<p>Connected. Proofs go to <b>{e(root() or '/')}</b>, one folder per company, then per project; "
                   f"the log is <b>{e(LOG_NAME)}</b> there.</p>")
        q = pending()
        out.append(f"<p>Waiting to send: <b>{len(q)}</b>. Last sent: {e(STATUS['last_ok'] or '-')}. "
                   f"Last problem: {e(STATUS['last_error'] or 'none')}</p>")
        out.append(f"<form method=post><input type=hidden name=key value='{e(given)}'>"
                   "<button name=test value=1>Test the connection</button> "
                   "<button name=retry value=1>Send anything waiting</button></form>"
                   f"<p style='margin-top:18px'>To connect a different account: <a href='{e(url)}' target=_blank>allow access</a>, "
                   "then paste the code: </p>"
                   f"<form method=post><input type=hidden name=key value='{e(given)}'><input name=code size=50> <button>Connect</button></form>")
    return _wrap(out)


def _wrap(parts):
    return ("<!doctype html><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'>"
            "<title>Dropbox setup</title><style>body{font:15px/1.5 system-ui,sans-serif;max-width:720px;margin:40px auto;"
            "padding:0 16px;color:#222}textarea,input{width:100%;font:13px monospace;padding:8px}button{padding:8px 14px;"
            "margin-top:6px}.ok{color:#1b6b2a}.bad{color:#a01c1c}</style>" + "".join(parts))
