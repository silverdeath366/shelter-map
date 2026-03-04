-- Enable PostGIS extension
CREATE EXTENSION IF NOT EXISTS postgis;

-- Create geo_features table
CREATE TABLE IF NOT EXISTS geo_features (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255),
    geometry_type VARCHAR(50),
    geom GEOMETRY(GEOMETRY, 4326),
    properties JSONB,
    raw_geometry JSONB,
    owner_sub TEXT,  -- Cognito user sub for JWT-based ownership
    edit_token TEXT,  -- Legacy edit token for anonymous edits
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create spatial index
CREATE INDEX IF NOT EXISTS idx_geo_features_geom ON geo_features USING GIST (geom);

-- Create index on geometry type for faster filtering
CREATE INDEX IF NOT EXISTS idx_geo_features_type ON geo_features (geometry_type);

-- Create index on name for faster searches
CREATE INDEX IF NOT EXISTS idx_geo_features_name ON geo_features (name);

-- Create index on properties for JSON queries
CREATE INDEX IF NOT EXISTS idx_geo_features_properties ON geo_features USING GIN (properties);

-- Create index on owner_sub for efficient filtering by owner
CREATE INDEX IF NOT EXISTS idx_geo_features_owner_sub ON geo_features(owner_sub);

-- Create index on edit_token for efficient token lookup
CREATE INDEX IF NOT EXISTS idx_geo_features_edit_token ON geo_features(edit_token);

-- Create updated_at trigger function
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Create trigger for updated_at
CREATE TRIGGER update_geo_features_updated_at 
    BEFORE UPDATE ON geo_features 
    FOR EACH ROW 
    EXECUTE FUNCTION update_updated_at_column();

-- Create api_keys table for API key lifecycle management
CREATE TABLE IF NOT EXISTS api_keys (
    id SERIAL PRIMARY KEY,
    key_hash VARCHAR(255) UNIQUE NOT NULL,
    name VARCHAR(255),
    is_active BOOLEAN DEFAULT TRUE NOT NULL,
    rate_limit INTEGER DEFAULT 60 NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    expires_at TIMESTAMP,
    last_used_at TIMESTAMP,
    usage_count INTEGER DEFAULT 0 NOT NULL,
    metadata TEXT
);

-- Create indexes on api_keys table
CREATE INDEX IF NOT EXISTS idx_api_keys_key_hash ON api_keys (key_hash);
CREATE INDEX IF NOT EXISTS idx_api_keys_is_active ON api_keys (is_active);
CREATE INDEX IF NOT EXISTS idx_api_keys_created_at ON api_keys (created_at);

-- Fines ledger for CityGuard (geofence violations)
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

-- Insert some sample data for testing
INSERT INTO geo_features (name, geometry_type, geom, properties, raw_geometry) VALUES
(
    'Sample Point',
    'Point',
    ST_GeomFromGeoJSON('{"type": "Point", "coordinates": [-122.4194, 37.7749]}'),
    '{"name": "Sample Point", "description": "A sample point in San Francisco"}',
    '{"type": "Point", "coordinates": [-122.4194, 37.7749]}'
),
(
    'Sample Polygon',
    'Polygon',
    ST_GeomFromGeoJSON('{"type": "Polygon", "coordinates": [[[-122.5, 37.7], [-122.4, 37.7], [-122.4, 37.8], [-122.5, 37.8], [-122.5, 37.7]]]}'),
    '{"name": "Sample Polygon", "description": "A sample polygon in San Francisco area"}',
    '{"type": "Polygon", "coordinates": [[[-122.5, 37.7], [-122.4, 37.7], [-122.4, 37.8], [-122.5, 37.8], [-122.5, 37.7]]]}'
);
