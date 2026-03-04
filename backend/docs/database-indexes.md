# Database Indexes Documentation

This document describes all database indexes used in the GeoJSON Ingestion Microservice.

## Overview

The `geo_features` table uses multiple indexes to optimize query performance for different access patterns.

## Indexes

### 1. Primary Key Index
- **Name:** `geo_features_pkey` (automatic)
- **Type:** B-tree
- **Columns:** `id`
- **Purpose:** Primary key constraint, ensures unique identification of records
- **Usage:** Fast lookups by ID, foreign key references

### 2. Spatial Index (GIST)
- **Name:** `idx_geo_features_geom`
- **Type:** GIST (Generalized Search Tree)
- **Columns:** `geom` (GEOMETRY)
- **Purpose:** Optimizes spatial queries (ST_Contains, ST_Intersects, ST_DWithin, etc.)
- **Usage:** 
  - Spatial searches: "Find all features within a bounding box"
  - Distance queries: "Find features within X meters of a point"
  - Spatial joins and intersections
- **Performance:** Critical for PostGIS spatial operations

### 3. Geometry Type Index
- **Name:** `idx_geo_features_type`
- **Type:** B-tree
- **Columns:** `geometry_type`
- **Purpose:** Fast filtering by geometry type (Point, Polygon, LineString, etc.)
- **Usage:** 
  - "Get all Point features"
  - "Get all Polygon features"
  - Filtering by type before spatial operations

### 4. Name Index
- **Name:** `idx_geo_features_name`
- **Type:** B-tree
- **Columns:** `name`
- **Purpose:** Fast lookups and searches by feature name
- **Usage:** 
  - "Find feature by name"
  - "Get all features with names starting with 'X'"
  - Name-based filtering

### 5. Properties Index (GIN)
- **Name:** `idx_geo_features_properties`
- **Type:** GIN (Generalized Inverted Index)
- **Columns:** `properties` (JSONB)
- **Purpose:** Optimizes JSONB queries on properties
- **Usage:** 
  - "Find features where properties->>'status' = 'active'"
  - "Find features with specific property values"
  - JSONB containment queries (@>, ? operators)
- **Performance:** Essential for querying nested JSON data

## Index Maintenance

### Automatic Maintenance
- PostgreSQL automatically maintains indexes during INSERT, UPDATE, DELETE operations
- Indexes are updated in real-time as data changes

### Vacuum and Analyze
Regular maintenance recommended:
```sql
-- Analyze table to update statistics
ANALYZE geo_features;

-- Vacuum to reclaim space and update statistics
VACUUM ANALYZE geo_features;
```

### Monitoring Index Usage
```sql
-- Check index usage statistics
SELECT 
    schemaname,
    tablename,
    indexname,
    idx_scan,
    idx_tup_read,
    idx_tup_fetch
FROM pg_stat_user_indexes
WHERE tablename = 'geo_features'
ORDER BY idx_scan DESC;
```

## Query Performance

### Spatial Queries
```sql
-- Uses idx_geo_features_geom (GIST)
SELECT * FROM geo_features 
WHERE ST_Contains(ST_MakeEnvelope(-122.5, 37.7, -122.4, 37.8, 4326), geom);
```

### Type Filtering
```sql
-- Uses idx_geo_features_type
SELECT * FROM geo_features WHERE geometry_type = 'Point';
```

### Name Search
```sql
-- Uses idx_geo_features_name
SELECT * FROM geo_features WHERE name LIKE 'San Francisco%';
```

### JSONB Queries
```sql
-- Uses idx_geo_features_properties (GIN)
SELECT * FROM geo_features 
WHERE properties @> '{"status": "active"}'::jsonb;
```

## Index Size

Monitor index sizes:
```sql
SELECT 
    indexname,
    pg_size_pretty(pg_relation_size(indexname::regclass)) AS size
FROM pg_indexes
WHERE tablename = 'geo_features';
```

## Best Practices

1. **Spatial Indexes (GIST):** Always use for geometry columns in PostGIS
2. **GIN Indexes:** Ideal for JSONB columns with frequent queries
3. **B-tree Indexes:** Best for equality and range queries on scalar values
4. **Index Selectivity:** More selective indexes (fewer unique values) are more effective
5. **Write Performance:** More indexes = slower writes, faster reads
6. **Maintenance:** Regular VACUUM ANALYZE keeps indexes efficient

## Future Considerations

Potential additional indexes based on usage patterns:
- Composite index on `(geometry_type, created_at)` for time-based type queries
- Partial index on `properties->>'status'` if status is frequently queried
- Expression index on `ST_Area(geom)` for area-based queries

