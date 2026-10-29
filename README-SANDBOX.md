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
- NetSuite: no bridge, order queue, order lookups, colour ids or NetSuite files,
  and no mention of it in the page clients download (the page is shipped
  without code comments; see "Bringing the main app's changes over").
- IT's files: access_gate.py, signout.js, netsuite_bridge.py, the NetSuite
  pages and IT's tests. Also not here: the export log, ink coverage, What's
  New, the 4imprint uploader, Raster to Vector, Get.Stitched.
- Products that aren't in CLIENT_CATALOG (or borrowed by one) are dropped at
  start-up, so /api/products only lists the client's items.
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
- SECRET_KEY        a long random value of its own. Set it: without it the
                    session key is made from CLIENT_PASSWORD, which every
                    client knows.
Nothing else is needed. Don't copy any variables from the main service.

## Each client's files are their own
Every client signs in with the same password, so the server tells them apart
by browser session (client_login.owner_tag). Each export, render job and
reopened proof is marked with the session that made it; another session gets
"expired" / "unknown" for it, even with the exact link. Exports are deleted
after an hour, uploads after a day.

## Update 2026-10-29: pens print one side
- The Jotter (0837-24HR-IMP) prints in ONE imprint location here. Clients see
  both sides of the pen, pick "Side 1" or "Side 2" under Artwork, and the
  other side stays blank. server.py, CLIENT_ONE_IMPRINT: add an item id to
  give it the same rule (any item with Side 1 / Side 2).
- The export holds to it whatever the browser sends (_one_imprint): the proof
  says "1 Side", and the proof's lay and the 2X2 both show the two sides with
  the art on the chosen one only - the same picture.
- SVG art now shows on the pen drawings in the proof and the 2X2 (it was left
  off; PDF/AI/PNG art was fine). The main app has the same gap.

## Update 2026-10-28 (from the main app, as of 2026-10-28)
Brought over from the main app (nothing NetSuite came across). What clients see:
- Size: the W typed is the W on the proof, exactly (it could print 1-2% big);
  H follows the art's own proportions.
- 4CP: exact hex or Pantone per color, Numo's own 4CP swatches listed first,
  type a PMS for a solid background, vector backgrounds print as vector,
  white inside 4CP art cuts out to the background as the proof shows.
- White inside the art on pens and totes cuts out (the proof matches).
- "Match <part>" inks (match the bias, the stitching, the zipper).
- Pastel Pink and Light Coral neoprene, Yellow thread (data/colors_app.json).
- Picking art from a template: Side 2 comes out the right way up; customer
  TIF templates keep their rings and white ink; picking from a mockup leaves
  out the bottom's colored circle.
- Jotter: both sides read toward the clip, Side 2 is the pen rolled over,
  prints 0.02" shorter than the listed height; plain Black ink.
- Art editor: the main app's new editor, clients see its Colors view only.
- Proof: the bottom imprint on the info line; many color combos go in columns.
Also: each client's exports are their own (see above); the Jotter's Side 1
mask was a 12.5 MB PNG, now 37 KB (same pixels).

## Bringing the main app's changes over
Python files: take the main app's own copy, except server.py, engine.py
(this copy reads data/colors_app.json) and client_login.py (this copy only).
server.py and static/configurator.html are rebuilt from the main app's by
two scripts kept outside this repo (port_server.py, port_html.mjs): they take
the internal-only parts out, put the client rules back in and strip comments
from the page. Rebuild them that way rather than copying either file across
by hand.

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
