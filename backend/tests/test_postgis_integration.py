"""
Integration tests for GeoJSON Ingestion Service with PostgreSQL/PostGIS.

These tests require a running PostgreSQL/PostGIS database.
Run with: TEST_MODE=integration pytest tests/test_postgis_integration.py -v

Prerequisites:
    docker-compose -f docker-compose.test.yml up -d
"""
import pytest
from httpx import AsyncClient


@pytest.mark.integration
class TestPostGISFeatureCRUD:
    """Test CRUD operations with real PostGIS database."""
    
    async def test_create_point_feature(self, integration_client: AsyncClient, sample_feature):
        """Test creating a Point feature with PostGIS."""
        response = await integration_client.post("/v1/ingest", json=sample_feature)
        
        assert response.status_code == 201, f"Expected 201, got {response.status_code}: {response.text}"
        data = response.json()
        assert "id" in data
        assert "feature" in data
        assert data["feature"]["properties"]["name"] == "Test Point"
        assert data["feature"]["properties"]["geometry_type"] == "Point"
    
    async def test_create_polygon_feature(self, integration_client: AsyncClient, sample_polygon_feature):
        """Test creating a Polygon feature with PostGIS."""
        response = await integration_client.post("/v1/ingest", json=sample_polygon_feature)
        
        assert response.status_code == 201, f"Expected 201, got {response.status_code}: {response.text}"
        data = response.json()
        assert data["feature"]["properties"]["geometry_type"] == "Polygon"
    
    async def test_create_linestring_feature(self, integration_client: AsyncClient, sample_linestring_feature):
        """Test creating a LineString feature with PostGIS."""
        response = await integration_client.post("/v1/ingest", json=sample_linestring_feature)
        
        assert response.status_code == 201, f"Expected 201, got {response.status_code}: {response.text}"
        data = response.json()
        assert data["feature"]["properties"]["geometry_type"] == "LineString"
    
    async def test_get_created_feature(self, integration_client: AsyncClient, sample_feature):
        """Test retrieving a feature by ID."""
        # First create a feature
        create_response = await integration_client.post("/v1/ingest", json=sample_feature)
        assert create_response.status_code == 201
        feature_id = create_response.json()["id"]
        
        # Then retrieve it
        get_response = await integration_client.get(f"/v1/features/{feature_id}")
        
        assert get_response.status_code == 200
        data = get_response.json()
        assert data["type"] == "Feature"
        assert data["id"] == feature_id
        assert data["geometry"]["type"] == "Point"
        assert "coordinates" in data["geometry"]
    
    async def test_update_feature_properties(self, integration_client: AsyncClient, sample_feature):
        """Test updating feature properties."""
        # Create feature
        create_response = await integration_client.post("/v1/ingest", json=sample_feature)
        feature_id = create_response.json()["id"]
        
        # Update it
        update_data = {
            "name": "Updated Name",
            "properties": {"description": "Updated description", "updated": True}
        }
        update_response = await integration_client.put(f"/v1/features/{feature_id}", json=update_data)
        
        assert update_response.status_code == 200
        data = update_response.json()
        assert data["feature"]["properties"]["name"] == "Updated Name"
    
    async def test_delete_feature(self, integration_client: AsyncClient, sample_feature):
        """Test deleting a feature."""
        # Create feature
        create_response = await integration_client.post("/v1/ingest", json=sample_feature)
        feature_id = create_response.json()["id"]
        
        # Delete it
        delete_response = await integration_client.delete(f"/v1/features/{feature_id}")
        assert delete_response.status_code == 200
        
        # Verify it's gone
        get_response = await integration_client.get(f"/v1/features/{feature_id}")
        assert get_response.status_code == 404
    
    async def test_get_nonexistent_feature(self, integration_client: AsyncClient):
        """Test getting a non-existent feature returns 404."""
        response = await integration_client.get("/v1/features/99999")
        assert response.status_code == 404
    
    async def test_list_features_pagination(self, integration_client: AsyncClient, sample_feature, sample_polygon_feature):
        """Test listing features with pagination."""
        # Create multiple features
        await integration_client.post("/v1/ingest", json=sample_feature)
        await integration_client.post("/v1/ingest", json=sample_polygon_feature)
        
        # List with pagination
        response = await integration_client.get("/v1/files", params={"skip": 0, "limit": 10})
        
        assert response.status_code == 200
        data = response.json()
        assert "features" in data
        assert "total" in data
        assert "skip" in data
        assert "limit" in data
        assert data["total"] >= 2
        assert len(data["features"]) >= 2
    
    async def test_list_features_filter_by_type(self, integration_client: AsyncClient, sample_feature, sample_polygon_feature):
        """Test filtering features by geometry type."""
        # Create different geometry types
        await integration_client.post("/v1/ingest", json=sample_feature)
        await integration_client.post("/v1/ingest", json=sample_polygon_feature)
        
        # Filter by Point
        response = await integration_client.get("/v1/files", params={"geometry_type": "Point"})
        
        assert response.status_code == 200
        data = response.json()
        # All features should be Points
        for feature in data["features"]:
            assert feature["properties"].get("geometry_type") == "Point"


@pytest.mark.integration
class TestPostGISSpatialQueries:
    """Test PostGIS spatial query functionality."""
    
    async def test_query_bbox_finds_features(self, integration_client: AsyncClient, sample_feature, bbox_san_francisco):
        """Test bounding box query finds features within bounds."""
        # Create a feature in San Francisco
        await integration_client.post("/v1/ingest", json=sample_feature)
        
        # Query by SF bounding box
        response = await integration_client.get("/v1/features/bbox", params=bbox_san_francisco)
        
        assert response.status_code == 200
        data = response.json()
        assert data["type"] == "FeatureCollection"
        assert "features" in data
        assert "count" in data
        assert data["count"] >= 1
        assert len(data["features"]) >= 1
    
    async def test_query_bbox_excludes_features_outside(
        self, 
        integration_client: AsyncClient, 
        sample_feature, 
        bbox_new_york
    ):
        """Test bounding box query excludes features outside bounds."""
        # Create a feature in San Francisco
        await integration_client.post("/v1/ingest", json=sample_feature)
        
        # Query by New York bounding box (should not find SF feature)
        response = await integration_client.get("/v1/features/bbox", params=bbox_new_york)
        
        assert response.status_code == 200
        data = response.json()
        assert data["type"] == "FeatureCollection"
        assert data["count"] == 0
        assert len(data["features"]) == 0
    
    async def test_query_proximity_finds_nearby(self, integration_client: AsyncClient, sample_feature):
        """Test proximity query finds features within radius."""
        # Create a feature at SF coordinates
        await integration_client.post("/v1/ingest", json=sample_feature)
        
        # Query nearby (same coordinates, 1km radius)
        response = await integration_client.get(
            "/v1/features/nearby",
            params={
                "lon": -122.4194,
                "lat": 37.7749,
                "radius": 1000,  # 1km
                "limit": 10
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["type"] == "FeatureCollection"
        assert data["count"] >= 1
    
    async def test_query_proximity_excludes_far_features(self, integration_client: AsyncClient, sample_feature):
        """Test proximity query excludes features outside radius."""
        # Create a feature in San Francisco
        await integration_client.post("/v1/ingest", json=sample_feature)
        
        # Query from New York (very far away)
        response = await integration_client.get(
            "/v1/features/nearby",
            params={
                "lon": -74.0060,  # New York
                "lat": 40.7128,
                "radius": 1000,  # 1km
                "limit": 10
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 0
    
    async def test_bbox_with_polygon_intersection(
        self, 
        integration_client: AsyncClient, 
        sample_polygon_feature,
        bbox_san_francisco
    ):
        """Test bounding box query properly intersects with polygons."""
        # Create a polygon in SF area
        await integration_client.post("/v1/ingest", json=sample_polygon_feature)
        
        # Query by SF bounding box
        response = await integration_client.get("/v1/features/bbox", params=bbox_san_francisco)
        
        assert response.status_code == 200
        data = response.json()
        assert data["count"] >= 1
        
        # Verify the polygon is in results
        polygon_found = any(
            f["properties"].get("geometry_type") == "Polygon"
            for f in data["features"]
        )
        assert polygon_found, "Polygon feature not found in bbox results"


@pytest.mark.integration
class TestPostGISExport:
    """Test export functionality with PostGIS."""
    
    async def test_export_all_features(
        self, 
        integration_client: AsyncClient, 
        sample_feature, 
        sample_polygon_feature
    ):
        """Test exporting all features as FeatureCollection."""
        # Create multiple features
        await integration_client.post("/v1/ingest", json=sample_feature)
        await integration_client.post("/v1/ingest", json=sample_polygon_feature)
        
        # Export all
        response = await integration_client.get("/v1/export")
        
        assert response.status_code == 200
        data = response.json()
        assert data["type"] == "FeatureCollection"
        assert len(data["features"]) >= 2
        
        # Verify all features have proper structure
        for feature in data["features"]:
            assert feature["type"] == "Feature"
            assert "geometry" in feature
            assert "properties" in feature
            assert "id" in feature
    
    async def test_export_empty_database(self, integration_client: AsyncClient):
        """Test export with empty database returns empty FeatureCollection."""
        response = await integration_client.get("/v1/export")
        
        assert response.status_code == 200
        data = response.json()
        assert data["type"] == "FeatureCollection"
        assert data["features"] == []


@pytest.mark.integration
class TestPostGISValidation:
    """Test GeoJSON validation with PostGIS."""
    
    async def test_invalid_geometry_type(self, integration_client: AsyncClient):
        """Test that invalid geometry type is rejected."""
        invalid_feature = {
            "type": "Feature",
            "geometry": {
                "type": "InvalidType",
                "coordinates": [0, 0]
            },
            "properties": {}
        }
        
        response = await integration_client.post("/v1/ingest", json=invalid_feature)
        # PostGIS should reject invalid geometry
        assert response.status_code in [400, 422, 500]
    
    async def test_invalid_coordinates(self, integration_client: AsyncClient):
        """Test that invalid coordinates are rejected."""
        invalid_feature = {
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": "not-coordinates"
            },
            "properties": {}
        }
        
        response = await integration_client.post("/v1/ingest", json=invalid_feature)
        assert response.status_code in [400, 422, 500]
    
    async def test_missing_geometry(self, integration_client: AsyncClient):
        """Test that missing geometry is rejected."""
        invalid_feature = {
            "type": "Feature",
            "properties": {"name": "No geometry"}
        }
        
        response = await integration_client.post("/v1/ingest", json=invalid_feature)
        assert response.status_code in [400, 422, 500]
    
    async def test_valid_multipoint(self, integration_client: AsyncClient):
        """Test MultiPoint geometry is accepted."""
        multipoint_feature = {
            "type": "Feature",
            "geometry": {
                "type": "MultiPoint",
                "coordinates": [
                    [-122.4194, 37.7749],
                    [-122.4294, 37.7849]
                ]
            },
            "properties": {"name": "MultiPoint test"}
        }
        
        response = await integration_client.post("/v1/ingest", json=multipoint_feature)
        assert response.status_code == 201
        data = response.json()
        assert data["feature"]["properties"]["geometry_type"] == "MultiPoint"


@pytest.mark.integration
class TestHealthAndMetrics:
    """Test health check and metrics endpoints."""
    
    async def test_health_check(self, integration_client: AsyncClient):
        """Test health check endpoint."""
        response = await integration_client.get("/healthz")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "geojson-ingestion"
    
    async def test_metrics_endpoint(self, integration_client: AsyncClient):
        """Test Prometheus metrics endpoint."""
        response = await integration_client.get("/metrics")
        
        assert response.status_code == 200
        assert "text/plain" in response.headers.get("content-type", "")


@pytest.mark.integration
class TestPostGISAPIKeyEndpoints:
    """Test API key management endpoints."""
    
    async def test_create_api_key(self, integration_client: AsyncClient):
        """Test creating an API key."""
        response = await integration_client.post(
            "/v1/api-keys",
            json={
                "name": "Test API Key",
                "rate_limit": 120
            }
        )
        
        assert response.status_code == 201
        data = response.json()
        assert "key" in data
        assert "id" in data
        assert data["key"].startswith("gk_")
        assert "warning" in data
    
    async def test_create_api_key_with_expiration(self, integration_client: AsyncClient):
        """Test creating an API key with expiration."""
        response = await integration_client.post(
            "/v1/api-keys",
            json={
                "name": "Expiring Key",
                "rate_limit": 60,
                "expires_in_days": 30,
                "metadata": {"environment": "test"}
            }
        )
        
        assert response.status_code == 201
        data = response.json()
        assert data["expires_at"] is not None
    
    async def test_list_api_keys(self, integration_client: AsyncClient):
        """Test listing API keys."""
        # First create a key
        await integration_client.post(
            "/v1/api-keys",
            json={"name": "List Test Key"}
        )
        
        response = await integration_client.get("/v1/api-keys")
        
        assert response.status_code == 200
        data = response.json()
        assert "api_keys" in data
        assert "total" in data
        assert isinstance(data["api_keys"], list)
    
    async def test_list_api_keys_active_only(self, integration_client: AsyncClient):
        """Test listing only active API keys."""
        response = await integration_client.get(
            "/v1/api-keys",
            params={"active_only": True}
        )
        
        assert response.status_code == 200
        data = response.json()
        # All returned keys should be active
        for key in data["api_keys"]:
            assert key["is_active"] is True
    
    async def test_list_api_keys_pagination(self, integration_client: AsyncClient):
        """Test listing API keys with pagination."""
        # Create multiple keys
        for i in range(3):
            await integration_client.post(
                "/v1/api-keys",
                json={"name": f"Pagination Test Key {i}"}
            )
        
        response = await integration_client.get(
            "/v1/api-keys",
            params={"skip": 0, "limit": 2}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert len(data["api_keys"]) <= 2
    
    async def test_update_api_key(self, integration_client: AsyncClient):
        """Test updating an API key."""
        # First create a key
        create_response = await integration_client.post(
            "/v1/api-keys",
            json={"name": "Original Name", "rate_limit": 60}
        )
        assert create_response.status_code == 201
        key_id = create_response.json()["id"]
        
        # Update the key
        response = await integration_client.put(
            f"/v1/api-keys/{key_id}",
            json={
                "name": "Updated Name",
                "rate_limit": 120,
                "is_active": True
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Updated Name"
        assert data["rate_limit"] == 120
        assert "message" in data
    
    async def test_update_api_key_not_found(self, integration_client: AsyncClient):
        """Test updating non-existent API key."""
        response = await integration_client.put(
            "/v1/api-keys/999999",
            json={"name": "New Name"}
        )
        
        assert response.status_code == 404
    
    async def test_delete_api_key(self, integration_client: AsyncClient):
        """Test deleting (deactivating) an API key."""
        # First create a key
        create_response = await integration_client.post(
            "/v1/api-keys",
            json={"name": "To Be Deleted"}
        )
        assert create_response.status_code == 201
        key_id = create_response.json()["id"]
        
        # Delete the key
        response = await integration_client.delete(f"/v1/api-keys/{key_id}")
        
        assert response.status_code == 200
        data = response.json()
        assert "message" in data
        assert "deleted" in data["message"].lower()
    
    async def test_delete_api_key_not_found(self, integration_client: AsyncClient):
        """Test deleting non-existent API key."""
        response = await integration_client.delete("/v1/api-keys/999999")
        
        assert response.status_code == 404


@pytest.mark.integration
class TestPostGISErrorHandling:
    """Test error handling and edge cases."""
    
    async def test_ingest_not_feature_type(self, integration_client: AsyncClient):
        """Test ingesting non-Feature type is rejected."""
        invalid_request = {
            "type": "FeatureCollection",
            "features": []
        }
        
        response = await integration_client.post("/v1/ingest", json=invalid_request)
        
        # API returns 500 for internal errors (exception caught and wrapped)
        # or 400 for validation errors
        assert response.status_code in [400, 500]
        data = response.json()
        assert "detail" in data
    
    async def test_get_feature_string_id(self, integration_client: AsyncClient):
        """Test getting feature with string ID returns 422."""
        response = await integration_client.get("/v1/features/not-a-number")
        
        assert response.status_code == 422
    
    async def test_list_features_pagination(self, integration_client: AsyncClient, sample_feature):
        """Test feature listing with pagination parameters."""
        # Create a few features
        for i in range(3):
            await integration_client.post("/v1/ingest", json=sample_feature)
        
        # Test with skip and limit
        response = await integration_client.get(
            "/v1/files",
            params={"skip": 0, "limit": 2}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "features" in data
        assert "total" in data
        assert len(data["features"]) <= 2
    
    async def test_list_features_geometry_type_filter(
        self, 
        integration_client: AsyncClient, 
        sample_feature,
        sample_polygon_feature
    ):
        """Test filtering features by geometry type."""
        # Create different geometry types
        await integration_client.post("/v1/ingest", json=sample_feature)
        await integration_client.post("/v1/ingest", json=sample_polygon_feature)
        
        # Filter by Point
        response = await integration_client.get(
            "/v1/files",
            params={"geometry_type": "Point"}
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # All returned features should be Points
        for feature in data["features"]:
            assert feature["properties"].get("geometry_type") == "Point"
    
    async def test_bbox_invalid_coordinates(self, integration_client: AsyncClient):
        """Test bbox query with invalid coordinates."""
        response = await integration_client.get(
            "/v1/features/bbox",
            params={
                "min_lon": 200,  # Invalid longitude
                "min_lat": 0,
                "max_lon": 201,
                "max_lat": 1
            }
        )
        
        # Should still return (PostGIS is lenient), but empty or error
        assert response.status_code in [200, 400, 422]
    
    async def test_proximity_large_radius(
        self, 
        integration_client: AsyncClient, 
        sample_feature
    ):
        """Test proximity query with large radius."""
        # Create a feature
        await integration_client.post("/v1/ingest", json=sample_feature)
        
        # Query with large radius (whole world)
        response = await integration_client.get(
            "/v1/features/nearby",
            params={
                "lon": -122.4194,
                "lat": 37.7749,
                "radius": 10000000,  # 10000 km
                "limit": 100
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "features" in data
    
    async def test_update_feature_properties_only(
        self, 
        integration_client: AsyncClient, 
        sample_feature
    ):
        """Test updating only feature properties."""
        # Create a feature
        create_response = await integration_client.post("/v1/ingest", json=sample_feature)
        assert create_response.status_code == 201
        feature_id = create_response.json()["id"]
        
        # Update only properties
        response = await integration_client.put(
            f"/v1/features/{feature_id}",
            json={
                "properties": {
                    "updated": True,
                    "timestamp": "2024-01-01"
                }
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["feature"]["properties"]["updated"] is True
    
    async def test_ingest_with_name_query_param(
        self, 
        integration_client: AsyncClient, 
        sample_feature
    ):
        """Test ingesting feature with explicit name parameter."""
        response = await integration_client.post(
            "/v1/ingest",
            json=sample_feature,
            params={"name": "Custom Named Feature"}
        )
        
        assert response.status_code == 201
        data = response.json()
        # The feature should have the custom name
        assert "Custom Named Feature" in str(data)


@pytest.mark.integration
class TestPostGISGeometryTypes:
    """Test various GeoJSON geometry types."""
    
    async def test_multilinestring(self, integration_client: AsyncClient):
        """Test MultiLineString geometry."""
        feature = {
            "type": "Feature",
            "geometry": {
                "type": "MultiLineString",
                "coordinates": [
                    [[-122.5, 37.7], [-122.4, 37.8]],
                    [[-122.3, 37.7], [-122.2, 37.8]]
                ]
            },
            "properties": {"name": "MultiLineString test"}
        }
        
        response = await integration_client.post("/v1/ingest", json=feature)
        assert response.status_code == 201
        data = response.json()
        assert data["feature"]["properties"]["geometry_type"] == "MultiLineString"
    
    async def test_multipolygon(self, integration_client: AsyncClient):
        """Test MultiPolygon geometry."""
        feature = {
            "type": "Feature",
            "geometry": {
                "type": "MultiPolygon",
                "coordinates": [
                    [[[-122.5, 37.7], [-122.4, 37.7], [-122.4, 37.8], [-122.5, 37.8], [-122.5, 37.7]]],
                    [[[-122.3, 37.6], [-122.2, 37.6], [-122.2, 37.7], [-122.3, 37.7], [-122.3, 37.6]]]
                ]
            },
            "properties": {"name": "MultiPolygon test"}
        }
        
        response = await integration_client.post("/v1/ingest", json=feature)
        assert response.status_code == 201
        data = response.json()
        assert data["feature"]["properties"]["geometry_type"] == "MultiPolygon"
    
    async def test_geometry_collection(self, integration_client: AsyncClient):
        """Test GeometryCollection geometry."""
        feature = {
            "type": "Feature",
            "geometry": {
                "type": "GeometryCollection",
                "geometries": [
                    {"type": "Point", "coordinates": [-122.4194, 37.7749]},
                    {"type": "LineString", "coordinates": [[-122.5, 37.7], [-122.4, 37.8]]}
                ]
            },
            "properties": {"name": "GeometryCollection test"}
        }
        
        response = await integration_client.post("/v1/ingest", json=feature)
        assert response.status_code == 201
        data = response.json()
        assert data["feature"]["properties"]["geometry_type"] == "GeometryCollection"
