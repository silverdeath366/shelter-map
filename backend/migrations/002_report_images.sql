-- Migration: 002_report_images
-- Description: Table for confirmed report image metadata (Phase 2; no user_sub yet)
-- Idempotent: safe to re-run (IF NOT EXISTS, CREATE INDEX IF NOT EXISTS)
-- Date: 2026-02

CREATE TABLE IF NOT EXISTS report_images (
    image_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    s3_key TEXT NOT NULL UNIQUE,
    content_type TEXT NOT NULL,
    size_bytes BIGINT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_report_images_s3_key ON report_images(s3_key);
CREATE INDEX IF NOT EXISTS idx_report_images_created_at ON report_images(created_at);

COMMENT ON TABLE report_images IS 'Metadata for confirmed S3 uploads (Phase 2 anonymous; user_sub in Phase 3)';
