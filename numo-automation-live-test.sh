#!/usr/bin/env bash
# Live check of the Numo automation API. Run it on your own computer after the
# patch is deployed and AUTOMATION_API_KEY is set in Railway:
#
#     export AUTOMATION_API_KEY='paste-the-key-here'
#     bash numo-automation-live-test.sh
#
# The key is read from your environment and never printed.
set -u
BASE="${NUMO_BASE:-https://numo-web-production.up.railway.app}/api/automation"
: "${AUTOMATION_API_KEY:?Set AUTOMATION_API_KEY first (export AUTOMATION_API_KEY=...)}"
AUTH="Authorization: Bearer ${AUTOMATION_API_KEY}"
ART="https://raw.githubusercontent.com/python-pillow/Pillow/main/Tests/images/hopper.png"
pass=0; fail=0
check() {  # name, expected text, actual
  if printf '%s' "$3" | grep -q "$2"; then echo "PASS  $1"; pass=$((pass+1)); else echo "FAIL  $1"; echo "      got: ${3:0:300}"; fail=$((fail+1)); fi
}

r=$(curl -s -w ' %{http_code}' "$BASE/health");                                   check "health without a key is refused (401)" ' 401$' "$r"
r=$(curl -s -w ' %{http_code}' -H "Authorization: Bearer wrong" "$BASE/health");  check "health with a wrong key is refused (401)" ' 401$' "$r"
r=$(curl -s -w ' %{http_code}' -H "$AUTH" "$BASE/health");                        check "health with the key" '"ok":true' "$r"

r=$(curl -s -H "$AUTH" -H 'Content-Type: application/json' -d '{"query":"kolder kaddy"}' "$BASE/search-items")
check "search-items finds Kolder Kaddy items" '"id":"0070-3m"' "$r"
r=$(curl -s -H "$AUTH" -H 'Content-Type: application/json' -d '{"query":"navy 6-panel cap"}' "$BASE/search-items")
check "search-items returns nothing for an item Numo doesn't make" '"matches":\[\]' "$r"

# ART is a photo: fine on a full-color (4CP) item, refused on a spot-ink one.
r=$(curl -s -H "$AUTH" -H 'Content-Type: application/json' \
     -d "{\"item_id\":\"0070-3w\",\"area\":\"side1\",\"art_url\":\"$ART\",\"width_in\":2}" "$BASE/check-art")
check "check-art accepts a photo from a link on a full-color item" '"ok":true' "$r"
r=$(curl -s -H "$AUTH" -H 'Content-Type: application/json' \
     -d "{\"item_id\":\"0070-3m\",\"area\":\"side1\",\"art_url\":\"$ART\",\"width_in\":2}" "$BASE/check-art")
check "check-art refuses a photo on a spot-ink item" 'photo_not_printable' "$r"
r=$(curl -s -H "$AUTH" -H 'Content-Type: application/json' \
     -d "{\"item_id\":\"0070-3w\",\"area\":\"side1\",\"art_url\":\"$ART\",\"width_in\":9}" "$BASE/check-art")
check "check-art rejects art too big for the area" 'too_large_for_area' "$r"

r=$(curl -s -H "$AUTH" -H 'Content-Type: application/json' \
     -d "{\"item_id\":\"0070-3w\",\"area\":\"side1\",\"art_url\":\"$ART\",\"width_in\":2,\"notes\":\"live test\"}" "$BASE/make-proof")
check "make-proof builds a proof" '"ok":true' "$r"
url=$(printf '%s' "$r" | sed -n 's/.*"proof_url":"\([^"]*\)".*/\1/p')
if [ -n "$url" ]; then
  code=$(curl -s -o numo-live-proof.pdf -w '%{http_code} %{content_type}' "$url")
  check "the proof link downloads a PDF (saved as numo-live-proof.pdf)" '^200 application/pdf' "$code"
fi
# ── Several locations: Kolder Kaddy (0070-3m) side1 + side2 + bottom ───────
TMPD=$(mktemp -d)
cat > "$TMPD/logo.svg" <<'SVG'
<svg xmlns="http://www.w3.org/2000/svg" width="300" height="200" viewBox="0 0 300 200"><rect x="10" y="10" width="280" height="180" rx="30" fill="#C8102E"/><circle cx="150" cy="100" r="60" fill="#FFCD00"/><path d="M110 100 L150 50 L190 100 L150 150 Z" fill="#000000"/></svg>
SVG
cat > "$TMPD/bottom.svg" <<'SVG'
<svg xmlns="http://www.w3.org/2000/svg" width="200" height="200" viewBox="0 0 200 200"><circle cx="100" cy="100" r="90" fill="#0033A0"/></svg>
SVG
printf 'not art' > "$TMPD/notes.txt"
AREAS='["side1","side2",{"area":"bottom","width_in":1.2}]'

r=$(curl -s -H "$AUTH" -F item_id=0070-3m -F "areas=$AREAS" -F "file=@$TMPD/logo.svg" -F "file_bottom=@$TMPD/bottom.svg" "$BASE/check-art")
check "check-art: 3 locations, all ok" '"ok":true' "$r"
check "check-art: one result per location" '"area":"bottom"' "$r"
r=$(curl -s -H "$AUTH" -F item_id=0070-3m -F "areas=$AREAS" -F "file=@$TMPD/logo.svg" -F "file_bottom=@$TMPD/notes.txt" "$BASE/check-art")
check "check-art: a bad bottom file fails only the bottom" '"area":"bottom".*unsupported_file_type\|unsupported_file_type.*"area":"bottom"' "$r"
r=$(curl -s -w ' %{http_code}' -H "$AUTH" -F item_id=0070-3m -F 'areas=["side1","lid"]' -F "file=@$TMPD/logo.svg" "$BASE/check-art")
check "check-art: unknown area id -> HTTP 400" ' 400$' "$r"
check "check-art: unknown area id names it (unknown_area, lid)" '"area":"lid","code":"unknown_area"' "$r"

r=$(curl -s -H "$AUTH" -F item_id=0070-3m -F color=Navy -F "areas=$AREAS" -F "file=@$TMPD/logo.svg" -F "file_bottom=@$TMPD/notes.txt" "$BASE/make-proof")
check "make-proof: a bad location -> no proof" '"proof_url":null' "$r"
r=$(curl -s -H "$AUTH" -F item_id=0070-3m -F color=Navy -F "areas=$AREAS" -F "file=@$TMPD/logo.svg" -F "file_bottom=@$TMPD/bottom.svg" -F notes="live test, 3 locations" "$BASE/make-proof")
check "make-proof: one proof for side1 + side2 + bottom" '"ok":true' "$r"
check "make-proof: details list every location" '"area":"bottom"' "$r"
url=$(printf '%s' "$r" | sed -n 's/.*"proof_url":"\([^"]*\)".*/\1/p')
if [ -n "$url" ]; then
  code=$(curl -s -o numo-live-proof-3-locations.pdf -w '%{http_code} %{content_type}' "$url")
  check "the 3-location proof downloads (numo-live-proof-3-locations.pdf)" '^200 application/pdf' "$code"
fi
rm -rf "$TMPD"

echo; echo "$pass passed, $fail failed"
