-- Migration: 003_fines_ledger
-- Description: Table for geofence violation fines (CityGuard Phase 4)
-- Idempotent: safe to re-run (IF NOT EXISTS)
-- Date: 2026-02

CREATE TABLE IF NOT EXISTS fines_ledger (
    id SERIAL PRIMARY KEY,
    scooter_id TEXT,
    lat DOUBLE PRECISION,
    lon DOUBLE PRECISION,
    zone_feature_id INTEGER,
    zone_name TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_fines_ledger_scooter_id ON fines_ledger(scooter_id);
CREATE INDEX IF NOT EXISTS idx_fines_ledger_created_at ON fines_ledger(created_at);

COMMENT ON TABLE fines_ledger IS 'Geofence violations: point inside restricted_zone (CityGuard)';
