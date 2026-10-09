# Numo · This Is Fast — client site

A separate copy of the Production Engine for clients to sign in, set up and
order This Is Fast items. It is its own repo and its own Railway service, and
it has no NetSuite connection or data and none of IT's additions.

## What clients get
- A sign-in page with one shared username and password (client_login.py).
- The catalog: the This Is Fast items from numomfg.com, by their site names.
  Ready to configure: Kolder Kaddy (0070-3m-24HR-1c), Kolder Kaddy Neoprene for
  Slim Cans (1080-3m-24HR-1c), Pocket Coolie (9100-24HR-1c), Pocket Coolie for
  Slim Cans (0472-24HR-1c), Main Squeeze Natural and Colored Canvas
  (5001-TIF-7-1C, 5001-TIF-CC-1C) and the Jotter Pen (the 0837 as it is).
  Full color (4CP): 4CP Kolder Kaddy (0070-3w), Kolder Kaddy Neoprene for Slim
  Cans - 4CP (1080-3w), 4CP Pocket Coolie (9100-4CP), Pocket Coolie for Slim
  Cans - 4CP (0472-4CP).
  Coming soon (photo with an overlay, can't be opened): Duplex
  Kolder Kaddy, Shamwow and Daily Grind (natural and colored).
- The client view only: color, logo (upload it, add text, or pick it out of a
  mockup or template), review, then "Get my proof", which
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

## Update 2026-10-09 (from the main app)
Today's main-app changes, merged into this copy's own files (nothing
NetSuite came across). What clients see:
- The art editor: opens when art comes in, with the item on the left and
  the art's colors (or the one ink) on the right. Clients see the Colors tab
  only; "Make it one color" applies the automatic one-color edit and opens it.
- Special inks in the ink pickers (877 C, Metallic Silver, 871 C, Metallic
  Gold, Shimmer Gold). Blaze Orange is its own color (#FF5715, in
  data/colors_app.json).
- Uploads with live text: outlined automatically when the font is inside
  the file; refused with the font's name when it isn't.
- The proof's Info line (1 Side / 2 Sides Same / 2 Sides Different) and the
  full note, wrapped.
- Adding text: the cursor stays in the text box while typing, and nothing
  can be dragged, sized or typed off the print area.
Files: static/configurator.html, server.py, engine.py (merged); press_layout.py,
onecolor.py, tif_import.py (the main app's, same as before today plus
today's changes); text_outline.py (new); data/colors_app.json.

## Update 2026-10-09, afternoon (from the main app)
Merged into this repo as it was on 2026-10-09 at 4:20 pm (nothing NetSuite
came across). What clients see:
- All 16 This Is Fast items on the items page; 15 open, only the Duplex
  Kolder Kaddy is still "Coming soon".
  - The 4CP items (0070-3w, 1080-3w, 9100-4CP, 0472-4CP) open now: their
    mockups (static/assets/<item>) were not in this repo.
  - New: Daily Grind (5010-TIF-10-1C, 5010-TIF-CC-1C) and Shamwow
    (5020-TIF-10-1C, 5020-TIF-CC-1C) totes, Side 1 (Front).
  - The Jotter is the 24 HR one, 0837-24HR-IMP (Mimaki guides).
- 4CP: Spring Camo and Fall Camo stock backgrounds; "Design background"
  lays out the whole item (background, text, shapes, art); vector
  backgrounds (PDF/AI/EPS/SVG) now print; the background picker shows small
  previews instead of downloading every full-size background (about 25 MB);
  a stock background prints from the server's own file.
- Multi-color art on a one-color item is made one color on upload (no
  pop-up); JPG/PNG art opens in the art editor much faster.
Files: server.py, static/configurator.html (merged; CLIENT_CATALOG updated);
products.py, press_layout.py, onecolor.py, tif_import.py, vectorize.py (the
main app's); press/ (5010, 5020 templates and specs; press/tif/ sources);
static/assets/ (the four 4CP items, 5010/5020 items); static/sandbox/items/
(the four tote photos); tools/ (5010, 5020, camo builders).
- New getting-started guide (static/configurator.html): four short pages for
  the item that is open, replacing the old one-color pop-up.
