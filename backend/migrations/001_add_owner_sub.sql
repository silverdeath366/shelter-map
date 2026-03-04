-- Migration: 001_add_owner_sub
-- Description: Add owner_sub column for JWT-based ownership and edit_token for legacy support
-- Date: 2026-01-31

-- Add owner_sub column for JWT-based ownership (Cognito sub)
ALTER TABLE geo_features ADD COLUMN IF NOT EXISTS owner_sub TEXT NULL;

-- Add edit_token column for legacy anonymous edit support
ALTER TABLE geo_features ADD COLUMN IF NOT EXISTS edit_token TEXT NULL;

-- Create index on owner_sub for efficient filtering by owner
CREATE INDEX IF NOT EXISTS idx_geo_features_owner_sub ON geo_features(owner_sub);

-- Create index on edit_token for efficient token lookup
CREATE INDEX IF NOT EXISTS idx_geo_features_edit_token ON geo_features(edit_token);

-- Add comment explaining the ownership model
COMMENT ON COLUMN geo_features.owner_sub IS 'Cognito user sub (unique identifier) - set when created via JWT auth';
COMMENT ON COLUMN geo_features.edit_token IS 'Legacy edit token for anonymous edits - only for features without owner_sub';
