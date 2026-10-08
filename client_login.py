"""
Client sign-in for the sandbox: one shared password for every client.

    CLIENT_USER           the username you give clients (optional; not set =
                          password only). Not case-sensitive.
    CLIENT_PASSWORD       the password you give clients. Not set = no sign-in
                          (the site is open), and a warning in the log.
    SECRET_KEY            signs the session cookie. Set a long random value.
                          Not set = derived from CLIENT_PASSWORD, so changing
                          the password signs everyone out.
    CLIENT_SESSION_HOURS  how long a sign-in lasts (default 12).
    CLIENT_COOKIE_SECURE  "0" only for local testing over plain http.

Everything is behind it except the login page itself. Pages send a signed-out
visitor to /login and back; /api/ calls answer 401. Every signed-in visitor is
a client: /api/session says role "customer", which keeps the configurator in
the client view.
"""
import hashlib
import hmac
import html
import os
import threading
import time
from datetime import timedelta
from urllib.parse import quote

from flask import jsonify, redirect, request, session

OPEN_PATHS = {"/login", "/logout", "/favicon.ico"}
MAX_FAILS, WINDOW_S = 10, 600          # 10 wrong passwords per address per 10 minutes
_FAILS, _LOCK = {}, threading.Lock()


def _env(k, d=""):
    return (os.environ.get(k) or d).strip()


def enabled():
    return bool(_env("CLIENT_PASSWORD"))


def _tag():
    # Changes when the password does, so a new password signs everyone out.
    return hmac.new(_env("CLIENT_PASSWORD").encode(), b"numo-client:" + _env("CLIENT_USER").casefold().encode(),
                    hashlib.sha256).hexdigest()[:24]


def signed_in():
    return not enabled() or session.get("client_ok") == _tag()


def _hours():
    try:
        h = float(_env("CLIENT_SESSION_HOURS", "12"))
        return h if 0 < h < 24 * 90 else 12.0
    except ValueError:
        return 12.0


def _safe_next(n):
    n = str(n or "/")
    return n if n.startswith("/") and not n.startswith("//") and "\\" not in n else "/"


def _ip():
    return (request.headers.get("X-Forwarded-For") or request.remote_addr or "?").split(",")[0].strip()[:64]


def _too_many(ip, now):
    with _LOCK:
        recent = [t for t in _FAILS.get(ip, []) if now - t < WINDOW_S]
        _FAILS[ip] = recent
        return len(recent) >= MAX_FAILS


def _fail(ip, now):
    with _LOCK:
        _FAILS.setdefault(ip, []).append(now)


def _page(body, status=200):
    return (f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Sign in · Numo</title>
<style>
body{{font-family:'Instrument Sans',Inter,system-ui,sans-serif;background:#f5f0eb;color:#1a1a1a;margin:0;
min-height:100vh;display:flex;align-items:center;justify-content:center;padding:16px;box-sizing:border-box}}
.card{{background:#fff;border-radius:14px;padding:32px 28px;width:100%;max-width:360px;box-shadow:0 10px 40px rgba(0,0,0,.08)}}
h1{{font-family:Georgia,serif;font-weight:400;font-size:26px;margin:0 0 6px}}
p{{color:#6b6460;font-size:14px;margin:0 0 20px}}
label{{display:block;font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:#6b6460;margin-bottom:6px}}
input{{width:100%;box-sizing:border-box;padding:11px 12px;border:1.5px solid #ddd5cc;border-radius:8px;font-size:15px}}
button{{margin-top:16px;width:100%;padding:12px;border:0;border-radius:8px;background:#6b1a2a;color:#fff;font-size:15px;cursor:pointer}}
.err{{color:#a3122a;margin:0 0 14px}}
</style></head><body><div class="card">{body}</div></body></html>""", status,
            {"Content-Type": "text/html; charset=utf-8", "Cache-Control": "no-store"})


def _form(nxt, err="", user=""):
    uf = (f'<label for="u">Username</label><input id="u" name="username" autocomplete="username" autocapitalize="none" '
          f'value="{html.escape(user)}" required {"" if user else "autofocus"} style="margin-bottom:14px">'
          if _env("CLIENT_USER") else "")
    return _page(f"""<h1>Numo</h1><p>Sign in to design and order your items.</p>{err}
<form method="post" action="/login"><input type="hidden" name="next" value="{html.escape(nxt)}">
{uf}<label for="pw">Password</label><input id="pw" name="password" type="password" autocomplete="current-password" required>
<button type="submit">Sign in</button></form>""", 401 if err else 200)


def init_app(app):
    if not app.secret_key:
        app.secret_key = _env("SECRET_KEY") or hmac.new(
            (_env("CLIENT_PASSWORD") or "numo-sandbox").encode(), b"numo-client-session", hashlib.sha256).hexdigest()
    app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax",
                      SESSION_COOKIE_SECURE=_env("CLIENT_COOKIE_SECURE") != "0",
                      PERMANENT_SESSION_LIFETIME=timedelta(hours=_hours()))
    if not enabled():
        print("⚠️  CLIENT_PASSWORD is not set: the client site is open to anyone with the link.")

    @app.before_request
    def _gate():
        if request.path in OPEN_PATHS or signed_in():
            return None
        if request.path.startswith("/api/"):
            return jsonify({"error": "Your sign-in has expired. Open the site again to sign in."}), 401
        nxt = request.full_path.rstrip("?") if request.query_string else request.path
        return redirect("/login?next=" + quote(nxt, safe=""))

    @app.route("/login", methods=["GET", "POST"])
    def client_login():
        nxt = _safe_next(request.values.get("next"))
        if not enabled():
            return redirect(nxt)
        if request.method != "POST":
            return redirect(nxt) if signed_in() else _form(nxt)
        ip, now = _ip(), time.time()
        if _too_many(ip, now):
            return _page("<h1>Too many tries</h1><p>Wait a few minutes and try again.</p>", 429)
        user_ok = hmac.compare_digest((request.form.get("username") or "").strip().casefold().encode(),
                                      _env("CLIENT_USER").casefold().encode()) if _env("CLIENT_USER") else True
        pass_ok = hmac.compare_digest((request.form.get("password") or "").strip().encode(),
                                      _env("CLIENT_PASSWORD").encode())
        if user_ok and pass_ok:
            with _LOCK:
                _FAILS.pop(ip, None)
            session.clear()
            session.permanent = True
            session["client_ok"] = _tag()
            return redirect(nxt)
        _fail(ip, now)
        return _form(nxt, '<p class="err">That username or password isn\'t right.</p>' if _env("CLIENT_USER")
                     else '<p class="err">That password isn\'t right.</p>', (request.form.get("username") or "").strip()[:80])

    @app.route("/logout", methods=["GET", "POST"])
    def client_logout():
        session.clear()
        return redirect("/login")

    @app.route("/api/session")
    def client_session():
        # Every visitor here is a client: the configurator stays in the client view.
        return jsonify({"sign_in": enabled(), "role": "customer"})
