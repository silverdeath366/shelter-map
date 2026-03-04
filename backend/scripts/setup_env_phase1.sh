#!/usr/bin/env bash
# Create .env from env.example with Phase 1 defaults (Docker DB + dev_open).
# Run from backend/:  ./scripts/setup_env_phase1.sh

set -e
cd "$(dirname "$0")/.."

if [ -f .env ]; then
  echo ".env already exists. Backing up to .env.bak"
  cp .env .env.bak
fi

cp env.example .env

# Phase 1: Docker Postgres (docker compose up -d db) + dev_open auth
sed -i 's/^DB_HOST=.*/DB_HOST=localhost/' .env
sed -i 's/^DB_PORT=.*/DB_PORT=5434/' .env
sed -i 's/^DB_NAME=.*/DB_NAME=geospatial/' .env
sed -i 's/^DB_USER=.*/DB_USER=postgres/' .env
sed -i 's/^DB_PASSWORD=.*/DB_PASSWORD=postgres/' .env
sed -i 's/^DB_SSLMODE=.*/DB_SSLMODE=disable/' .env
sed -i 's/^AUTH_MODE=.*/AUTH_MODE=dev_open/' .env

echo "Created .env with Phase 1 defaults (DB_PORT=5434, DB_NAME=geospatial, AUTH_MODE=dev_open)."
echo "Next: docker compose up -d db   then   uvicorn app.main:app --reload --port 8005"
echo "See SETUP_PHASE1.md for full steps and optional load_shelters_from_csv."
