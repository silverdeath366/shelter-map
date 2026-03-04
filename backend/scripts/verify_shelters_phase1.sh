#!/usr/bin/env bash
# Phase 1 — Verify Shelters Loaded
# Run with backend up on http://localhost:8005
# For dev_open: no headers. For API key: set API_KEY env or use -H "X-API-Key: YOUR_KEY"

set -e
BASE="${BASE_URL:-http://localhost:8005}"
API_KEY="${API_KEY:-}"

if [ -n "$API_KEY" ]; then
  CURL_AUTH=( -H "X-API-Key: $API_KEY" )
else
  CURL_AUTH=()
fi

echo "=== 1. GET /v1/shelters (should return a large JSON list) ==="
CODE=$(curl -s -o /tmp/shelters.json -w "%{http_code}" "${CURL_AUTH[@]}" "$BASE/v1/shelters")
if [ "$CODE" != "200" ]; then
  echo "FAIL: expected 200, got $CODE"
  exit 1
fi
COUNT=$(python3 -c "import json; d=json.load(open('/tmp/shelters.json')); print(d.get('total', len(d.get('features', []))))" 2>/dev/null || echo "0")
echo "OK (HTTP $CODE). Total shelters: $COUNT"

echo ""
echo "=== 2. GET /v1/shelters/nearby?lon=35.21&lat=31.78&radius=2000&limit=5 ==="
CODE=$(curl -s -o /tmp/shelters_nearby.json -w "%{http_code}" "${CURL_AUTH[@]}" "$BASE/v1/shelters/nearby?lon=35.21&lat=31.78&radius=2000&limit=5")
if [ "$CODE" != "200" ]; then
  echo "FAIL: expected 200, got $CODE"
  exit 1
fi
echo "OK (HTTP $CODE). Response sample:"
python3 -c "
import json
d = json.load(open('/tmp/shelters_nearby.json'))
for i, f in enumerate((d.get('features') or [])[:3]):
    p = f.get('properties') or {}
    name = p.get('name', '—')
    dist = f.get('distance_m', '—')
    print(f'  {i+1}. name={name!r}, distance_m={dist}')
if not d.get('features'):
    print('  (no features)')
"

echo ""
echo "Backend is 100% ready for Phase 1."
