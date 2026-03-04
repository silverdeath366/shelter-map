#!/bin/bash
# Test CityGuard pings: outside polygon → violation=false, inside → violation=true, fines_ledger increments.
# Run from app root. Requires: docker-compose up (app + db), migrations, load_zones.

set -e
BASE="http://127.0.0.1:8091/v1/cityguard/pings"

# Hit app inside container so we reach the real service (avoids host port conflicts).
ping_post() {
  docker compose exec -T app python -c "
import urllib.request, sys
j = sys.argv[1] if len(sys.argv)>1 else '{}'
req = urllib.request.Request('$BASE', data=j.encode(), headers={'Content-Type':'application/json'}, method='POST')
with urllib.request.urlopen(req) as r:
    print(r.read().decode())
" "$1"
}

echo "1. Ping outside polygon (0,0)..."
R1=$(ping_post '{"scooter_id":"scoot-1","lat":0,"lon":0}')
echo "   Response: $R1"
echo "$R1" | grep -q '"violation":false' || { echo "FAIL: expected violation=false"; exit 1; }
echo "   OK"

echo ""
echo "2. Ping inside polygon (37.75,-122.45)..."
R2=$(ping_post '{"scooter_id":"scoot-1","lat":37.75,"lon":-122.45}')
echo "   Response: $R2"
echo "$R2" | grep -q '"violation":true' || { echo "FAIL: expected violation=true"; exit 1; }
echo "$R2" | grep -q '"zone"' || { echo "FAIL: expected zone in response"; exit 1; }
echo "   OK"

echo ""
echo "3. Check fines_ledger count..."
COUNT=$(docker compose exec -T db psql -U postgres -d geospatial -t -c "SELECT count(*) FROM fines_ledger;" 2>/dev/null | tr -d ' \n')
echo "   fines_ledger count: $COUNT"
[ -n "$COUNT" ] && [ "$COUNT" -ge 1 ] || { echo "FAIL: fines_ledger should have >= 1 row"; exit 1; }
echo "   OK"

echo ""
echo "All tests passed."
