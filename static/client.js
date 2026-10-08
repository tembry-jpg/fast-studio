// Client site header: "Sign out" while the client sign-in (client_login.py) is on.
(async () => {
  let s = {};
  try { const r = await fetch("/api/session", { cache: "no-store" }); if (r.ok) s = await r.json(); } catch (e) {}
  if (s.sign_in !== true || document.getElementById("client-signout")) return;
  const a = document.createElement("a");
  a.id = "client-signout"; a.href = "/logout"; a.textContent = "Sign out"; a.title = "Sign out";
  a.style.whiteSpace = "nowrap";
  const nav = document.querySelector("header nav"), right = document.querySelector("header .header-right");
  if (nav) { nav.style.flexWrap = "wrap"; nav.append(a); return; }
  a.style.cssText += ";font-family:var(--mono,ui-monospace,monospace);font-size:11px;letter-spacing:.4px;"
    + "color:var(--burgundy,#6b1a2a);text-decoration:none;margin-right:16px";
  if (right) right.prepend(a);
  else { a.style.cssText += ";position:fixed;top:12px;right:16px;z-index:9999"; document.body.appendChild(a); }
})();
