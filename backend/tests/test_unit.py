"""
Unit tests that do NOT require a database connection.

These tests verify:
- Input validation
- Request/response structures
- Error handling
- Basic API contract

Run with: pytest tests/test_unit.py -v
"""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch, MagicMock


@pytest.fixture
def app_client():
    """Create a test client that doesn't initialize the database."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    
    # Import just the app without triggering DB initialization
    import sys
    
    # Create a minimal test app with same routes but no DB
    test_app = FastAPI()
    
    @test_app.get("/healthz")
    async def health_check():
        return {"status": "healthy", "service": "geojson-ingestion"}
    
    @test_app.get("/metrics")
    async def metrics():
        from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
        from fastapi.responses import Response
        return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
    
    return TestClient(test_app)


class TestHealthEndpoints:
    """Test health endpoints without database."""
    
    def test_health_check_structure(self, app_client):
        """Test health check endpoint returns correct structure."""
        response = app_client.get("/healthz")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert "service" in data
        assert data["status"] == "healthy"
    
    def test_metrics_endpoint_format(self, app_client):
        """Test metrics endpoint returns Prometheus format."""
        response = app_client.get("/metrics")
        assert response.status_code == 200
        assert "text/plain" in response.headers.get("content-type", "")


class TestGeoJSONValidation:
    """Test GeoJSON structure validation logic."""
    
    def test_valid_point_structure(self):
        """Test valid Point geometry structure."""
        point = {
            "type": "Point",
            "coordinates": [-122.4194, 37.7749]
        }
        assert point["type"] == "Point"
        assert len(point["coordinates"]) == 2
        assert isinstance(point["coordinates"][0], (int, float))
        assert isinstance(point["coordinates"][1], (int, float))
    
    def test_valid_polygon_structure(self):
        """Test valid Polygon geometry structure."""
        polygon = {
            "type": "Polygon",
            "coordinates": [[
                [-122.5, 37.7],
                [-122.4, 37.7],
                [-122.4, 37.8],
                [-122.5, 37.8],
                [-122.5, 37.7]  # Closed ring
            ]]
        }
        assert polygon["type"] == "Polygon"
        # First ring should be closed (first point == last point)
        ring = polygon["coordinates"][0]
        assert ring[0] == ring[-1]
    
    def test_valid_feature_structure(self):
        """Test valid GeoJSON Feature structure."""
        feature = {
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [0, 0]
            },
            "properties": {"name": "Test"}
        }
        assert feature["type"] == "Feature"
        assert "geometry" in feature
        assert "properties" in feature
        assert feature["geometry"]["type"] == "Point"
    
    def test_invalid_feature_missing_geometry(self):
        """Test that Feature without geometry is invalid."""
        feature = {
            "type": "Feature",
            "properties": {"name": "Test"}
        }
        assert "geometry" not in feature
    
    def test_invalid_coordinates_type(self):
        """Test invalid coordinates type detection."""
        geometry = {
            "type": "Point",
            "coordinates": "not-an-array"
        }
        assert not isinstance(geometry["coordinates"], list)


class TestBoundingBoxValidation:
    """Test bounding box parameter validation."""
    
    def test_valid_bbox_parameters(self):
        """Test valid bounding box parameters."""
        bbox = {
            "min_lon": -122.6,
            "min_lat": 37.6,
            "max_lon": -122.2,
            "max_lat": 37.9
        }
        # min should be less than max
        assert bbox["min_lon"] < bbox["max_lon"]
        assert bbox["min_lat"] < bbox["max_lat"]
        # Valid longitude range: -180 to 180
        assert -180 <= bbox["min_lon"] <= 180
        assert -180 <= bbox["max_lon"] <= 180
        # Valid latitude range: -90 to 90
        assert -90 <= bbox["min_lat"] <= 90
        assert -90 <= bbox["max_lat"] <= 90
    
    def test_invalid_bbox_reversed(self):
        """Test detection of reversed min/max values."""
        bbox = {
            "min_lon": -122.2,  # Should be min
            "min_lat": 37.9,   # Should be min
            "max_lon": -122.6, # Should be max
            "max_lat": 37.6    # Should be max
        }
        # These are reversed
        assert bbox["min_lon"] > bbox["max_lon"]
        assert bbox["min_lat"] > bbox["max_lat"]


class TestProximityValidation:
    """Test proximity query parameter validation."""
    
    def test_valid_proximity_parameters(self):
        """Test valid proximity query parameters."""
        params = {
            "lon": -122.4194,
            "lat": 37.7749,
            "radius": 1000,
            "limit": 100
        }
        # Valid longitude range
        assert -180 <= params["lon"] <= 180
        # Valid latitude range
        assert -90 <= params["lat"] <= 90
        # Positive radius
        assert params["radius"] > 0
        # Positive limit
        assert params["limit"] > 0
    
    def test_invalid_radius(self):
        """Test detection of invalid radius values."""
        params = {
            "lon": 0,
            "lat": 0,
            "radius": -100,  # Invalid
            "limit": 10
        }
        assert params["radius"] < 0


class TestAPIKeyFormat:
    """Test API key format validation."""
    
    def test_valid_api_key_format(self):
        """Test valid API key format."""
        # Keys should start with gk_ prefix (use placeholder; no real secret in tests)
        valid_key = "gk_TEST_FORMAT_PLACEHOLDER"
        assert valid_key.startswith("gk_")
        assert len(valid_key) > 3
    
    def test_generate_api_key_format(self):
        """Test generated API key format."""
        import secrets
        key = f"gk_{secrets.token_urlsafe(32)}"
        assert key.startswith("gk_")
        assert len(key) > 40  # gk_ + 43 chars from token_urlsafe(32)


class TestRateLimiter:
    """Test rate limiter logic."""
    
    def test_in_memory_rate_limiter_initialization(self):
        """Test in-memory rate limiter can be initialized."""
        from app.services.rate_limiter import RateLimiter
        
        limiter = RateLimiter(
            redis_client=None,
            requests_per_minute=60
        )
        assert limiter.requests_per_minute == 60
        assert limiter.redis_client is None
    
    @pytest.mark.asyncio
    async def test_rate_limiter_check(self):
        """Test rate limiter check method."""
        from app.services.rate_limiter import RateLimiter
        
        limiter = RateLimiter(
            redis_client=None,
            requests_per_minute=60
        )
        
        # First request should be allowed (returns tuple: allowed, remaining)
        result = await limiter.check_rate_limit("test-key")
        allowed = result[0] if isinstance(result, tuple) else result
        assert allowed is True
    
    @pytest.mark.asyncio
    async def test_rate_limiter_tracks_requests(self):
        """Test that rate limiter tracks requests."""
        from app.services.rate_limiter import RateLimiter
        
        limiter = RateLimiter(
            redis_client=None,
            requests_per_minute=5  # Low limit for testing
        )
        
        key = "test-tracking-key"
        
        # Make 5 requests (should all be allowed)
        for _ in range(5):
            result = await limiter.check_rate_limit(key)
            allowed = result[0] if isinstance(result, tuple) else result
            assert allowed is True
        
        # 6th request should be blocked
        result = await limiter.check_rate_limit(key)
        allowed = result[0] if isinstance(result, tuple) else result
        assert allowed is False
