# Numo · This Is Fast — client site

A separate copy of the Production Engine for clients to sign in, set up and
order This Is Fast items. It is its own repo and its own Railway service, and
it has no NetSuite connection or data and none of IT's additions.

## What clients get
- A sign-in page with one shared password (client_login.py).
- The catalog: the This Is Fast items from numomfg.com, by their site names.
  Ready to configure: Kolder Kaddy (0070-3m-24HR-1c), Kolder Kaddy Neoprene for
  Slim Cans (1080-3m-24HR-1c), Pocket Coolie (9100-24HR-1c), Pocket Coolie for
  Slim Cans (0472-24HR-1c), Main Squeeze Natural and Colored Canvas
  (5001-TIF-7-1C, 5001-TIF-CC-1C) and the Jotter Pen (the 0837 as it is).
  Coming soon (photo with an overlay, can't be opened): every 4CP item, Duplex
  Kolder Kaddy, Shamwow and Daily Grind (natural and colored).
- The client view only: color, logo, review, then "Get my proof", which
  downloads their digital proof and virtual.
- No pricing.

## What is not here
- NetSuite: no bridge, order queue, order lookups, colour ids or NetSuite files.
- IT's files: access_gate.py, signout.js, netsuite_bridge.py, the NetSuite
  pages and IT's tests.
- Press files, 2X2, print PDF, artwork originals and ink coverage: an export
  ships the proof and the virtual only (the server enforces it).
- No past jobs from the main app.

## Changing the catalog
server.py, CLIENT_CATALOG: one line per item, in the order shown. An item
that is ready has its product id; a "Coming soon" item has None. Photos live
in static/sandbox/items and static/sandbox/soon.

## Bringing an item over from the main app
An item is its entry in products.py, its folder in static/assets/, and for
screen print its template in press/ (the .pdf and press_spec_*.json). Copy
those into this repo (products.py is the same file in both, so copy it whole),
then add the item to CLIENT_CATALOG. Going the other way works the same.

Product colours: this copy reads data/colors_app.json (names and mockup hex
only). A new colour added in the main app needs adding there too.

## Railway variables
- CLIENT_USER       the username you give clients (optional, not case-sensitive)
- CLIENT_PASSWORD   the password you give clients (not set = open to anyone)
- SECRET_KEY        a long random value of its own
Nothing else is needed. Don't copy any variables from the main service.

## Setting up the repo
The product photos make the whole site too big to send in one file, so it
comes as the files that differ from the main app.

1. Make a NEW repo from a copy of the main app (as of 2026-10-08).
2. Delete from the copy:
   netsuite_bridge.py, access_gate.py, ink_coverage.py, static/ns-bridge.js,
   static/ns-queue.html, static/signout.js, the whole tests/ folder,
   data/netsuite_colors.csv, NOTES-for-IT-netsuite-colors.md,
   CHANGES-2026-09-28.txt, configurator.html (the old copy at the top level),
   numo-4cp-fiery (2).zip if it is there, and uploads/, _serve/, _ns_cache/ if
   they are there.
3. Add the files from the zip (they replace the copy's own).
