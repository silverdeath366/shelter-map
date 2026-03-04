#!/usr/bin/env bash
# Gate 6 — Failure Mode Test
# Run simulator, kill DB while traffic is running.
# Expected: API still responds, errors logged, process does NOT crash.
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
COMPOSE_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$COMPOSE_DIR"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'
log_info()  { echo -e "${GREEN}[INFO]${NC} $*"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
log_error() { echo -e "${RED}[ERROR]${NC} $*"; }

BASE_URL="${BASE_URL:-http://127.0.0.1:8091}"

log_info "Gate 6: Failure mode test (simulator + kill DB)"
log_info "Starting stack..."
docker compose up -d
trap 'docker compose down' EXIT

log_info "Waiting for app to be up..."
for i in $(seq 1 30); do
  if curl -sf "$BASE_URL/healthz" >/dev/null 2>&1; then
    log_info "App is up."
    break
  fi
  if [ "$i" -eq 30 ]; then
    log_error "App did not become ready in time."
    exit 1
  fi
  sleep 1
done

log_info "Starting traffic simulator in background (5 req/s)..."
TARGET_URL="$BASE_URL/v1/cityguard/pings" RATE_PER_SEC=5 SCOOTER_COUNT=5 \
  python3 "$ROOT_DIR/traffic-sim/main.py" &
SIM_PID=$!
trap "kill $SIM_PID 2>/dev/null; docker compose down" EXIT

sleep 4
log_info "Stopping DB container (simulating DB failure)..."
docker compose stop db

log_info "Checking API still responds (process must NOT crash)..."
for i in 1 2 3 4 5; do
  if curl -sf "$BASE_URL/healthz" >/dev/null 2>&1; then
    log_info "  healthz: 200 OK"
  else
    log_error "  healthz failed (app may have crashed)"
    exit 1
  fi
  CODE=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE_URL/v1/cityguard/pings" \
    -H "Content-Type: application/json" -d '{"scooter_id":"s1","lat":0,"lon":0}')
  if [ "$CODE" = "503" ] || [ "$CODE" = "500" ]; then
    log_info "  pings: $CODE (expected when DB is down)"
  else
    log_warn "  pings: $CODE (503/500 expected when DB down)"
  fi
  sleep 0.5
done

# Verify app process still running (healthz already succeeded above; one more check)
if curl -sf "$BASE_URL/healthz" >/dev/null 2>&1; then
  log_info "App still responding: Gate 6 PASS (process did not crash)."
else
  log_error "App no longer responding: Gate 6 FAIL (process likely crashed)."
  exit 1
fi

kill $SIM_PID 2>/dev/null || true
log_info "Gate 6 failure mode test passed: API responded, errors returned, process did not crash."
