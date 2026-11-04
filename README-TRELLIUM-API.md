# Numo email automation API (for Trellium) - update: several locations per request

## Install (numo-web)
Replace `automation_api.py` in the repo root with this one. Nothing else changes (server.py and
access_gate.py stay as they are). After the deploy:
`export AUTOMATION_API_KEY=...` then `bash numo-automation-live-test.sh` (19 checks, incl. the
Kolder Kaddy side1 + side2 + bottom proof, saved as numo-live-proof-3-locations.pdf).

## For the automation builder

Base: https://numo-web-production.up.railway.app/api/automation
Every request: header  Authorization: Bearer <API key>   (missing/wrong -> 401)
Single-location requests ("area") work exactly as before.

### Several locations: "areas"
Send "areas" instead of "area": a list of area ids from search-items, or objects with their own
settings: {"area": id, "width_in" | "height_in", "position", "x_in", "y_in", "ink"}.
Multipart: send areas as a JSON string (or comma-separated ids).
Art: the shared "file" / "art_url" goes on every location; override one location with
"file_<areaId>" (multipart, e.g. file_bottom) or "art_url_<areaId>" (JSON, e.g. art_url_bottom).

POST /check-art (multipart)
  item_id=0070-3m
  areas=["side1","side2",{"area":"bottom","width_in":1.2}]
  file=@logo.svg            file_bottom=@bottom.svg
-> {"ok": true, "item": "0070-3m", "results": [
     {"area": "side1", "ok": true, "problems": [], "problem_codes": [], "warnings": [], "suggestions": [],
      "printed_size_in": {"width": 3.0, "height": 2.21}},
     {"area": "side2", "ok": true, ...},
     {"area": "bottom", "ok": true, ..., "printed_size_in": {"width": 1.2, "height": 0.738}}]}
  Top-level ok is true only when every location is ok. A bad location, e.g. file_bottom=@notes.txt:
     {"area": "bottom", "ok": false, "problems": ["Unsupported file type (.txt). Send AI, EPS, PDF, SVG, PNG or JPG."],
      "problem_codes": ["unsupported_file_type"], "suggestions": ["Vector artwork ... works best; ..."], ...}

POST /check-art (JSON)
  {"item_id": "0070-3m", "areas": ["side1", {"area": "bottom", "width_in": 1.5}],
   "art_url": "https://.../logo.png", "art_url_bottom": "https://.../round-logo.png"}

POST /make-proof (multipart)
  item_id=0070-3m  color=Navy  reference=NSO555  notes=3 locations
  areas=["side1",{"area":"side2","width_in":2.5,"position":"top"},{"area":"bottom","width_in":1.2}]
  file=@logo.svg   file_bottom=@bottom.svg
-> {"ok": true, "proof_url": "https://.../api/automation/proofs/<token>.pdf", "expires_at": "2026-11-11T22:37:07Z",
    "problems": [], "warnings": [],
    "details": {"item": "0070-3m", "color": "Navy", "areas": [
       {"area": "side1",  "printed_size_in": {"width": 3.0, "height": 2.21},  "inks": ["PANTONE 2347 C","PANTONE Yellow C","Black"], "warnings": []},
       {"area": "side2",  "printed_size_in": {"width": 2.5, "height": 1.842}, "inks": ["PANTONE 2347 C","PANTONE Yellow C","Black"], "warnings": []},
       {"area": "bottom", "printed_size_in": {"width": 1.2, "height": 0.738}, "inks": ["PANTONE 286 C"], "warnings": []}]}}
  ONE proof PDF with every location. If any location can't work: no proof at all -
-> {"ok": false, "proof_url": null, "item": "0070-3m",
    "problems": ["bottom: Unsupported file type (.txt). ..."], "problem_codes": ["unsupported_file_type"],
    "results": [ {"area": "side1", "ok": true, ...}, {"area": "side2", "ok": true, ...},
                 {"area": "bottom", "ok": false, "problems": [...], "problem_codes": [...], "suggestions": [...]} ]}
  -> ask the customer for better art for that location only.

### Per-location problem codes (in results[].problem_codes)
 Art in:      no_artwork, unsupported_file_type, file_too_large, empty_file, bad_url, download_failed, unreadable_file
 Printing:    low_resolution, art_not_printable, too_many_colors, photo_not_printable,
              background_not_transparent, too_large_for_area
 One-color items (upload checks): raster_file, unsupported_file, embedded_raster, embedded_raster_mixed,
              no_vector_geometry, empty_artwork, opaque_background, multicolor
 make-proof only: outside_area, unknown_ink,
              ink_mismatch (one-color items print one ink for the whole order: every location the same ink)

### Request-level errors (no results list)
 HTTP 400 unknown_area   {"ok": false, "code": "unknown_area", "area": "lid", "error": "Unknown decoration area 'lid' for 0070-3m. Areas: bottom, side1, side2."}
 HTTP 400 duplicate_area (an area listed twice), bad_areas (areas not a list), areas_conflict (sides and wrap together)
 HTTP 404 unknown_item
 make-proof, HTTP 200 ok:false: color_required, unknown_color, item_not_supported, proof_failed

### Unchanged
health, search-items, single-area check-art / make-proof, files (AI, EPS, PDF, SVG, PNG, JPG, GIF, BMP, TIF,
WEBP; 25 MB each), art_url public http/https only, proof = one-page PDF at proof_url (no key needed; the link
is the access), 7 days then 404. Not supported yet: the decal, glass, mugs, jig pens.
