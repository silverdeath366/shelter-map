"""
Comprehensive tests to achieve 80%+ coverage.
These tests cover service layer, middleware, and edge cases.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timedelta
import json


# ============================================================================
# Service Layer Tests
# ============================================================================

class TestAPIKeyServiceComprehensive:
    """Comprehensive tests for APIKeyService."""
    
    @pytest.fixture
    def mock_db(self):
        """Create mock database session."""
        session = AsyncMock()
        session.execute = AsyncMock()
        session.get = AsyncMock()
        session.add = MagicMock()
        session.commit = AsyncMock()
        session.refresh = AsyncMock()
        return session
    
    @pytest.mark.asyncio
    async def test_hash_key(self, mock_db):
        """Test _hash_key method."""
        from app.services.api_key_service import APIKeyService
        
        service = APIKeyService(mock_db)
        hash1 = service._hash_key("test_key")
        hash2 = service._hash_key("test_key")
        hash3 = service._hash_key("different_key")
        
        # Same key should produce same hash
        assert hash1 == hash2
        # Different keys should produce different hashes
        assert hash1 != hash3
        # Hash should be hex string
        assert len(hash1) == 64
    
    @pytest.mark.asyncio
    async def test_verify_key(self, mock_db):
        """Test _verify_key method."""
        from app.services.api_key_service import APIKeyService
        
        service = APIKeyService(mock_db)
        key = "test_key"
        key_hash = service._hash_key(key)
        
        assert service._verify_key(key, key_hash) is True
        assert service._verify_key("wrong_key", key_hash) is False
    
    @pytest.mark.asyncio
    async def test_create_api_key_with_expiration(self, mock_db):
        """Test creating API key with expiration."""
        from app.services.api_key_service import APIKeyService
        
        service = APIKeyService(mock_db)
        plain_key, api_key = await service.create_api_key(
            name="Expiring Key",
            rate_limit=100,
            expires_in_days=30,
            metadata={"env": "test"}
        )
        
        assert plain_key.startswith("gk_")
        assert api_key.name == "Expiring Key"
        assert api_key.rate_limit == 100
        assert api_key.expires_at is not None
        assert api_key.key_metadata is not None
    
    @pytest.mark.asyncio
    async def test_create_api_key_without_name(self, mock_db):
        """Test creating API key without name generates default."""
        from app.services.api_key_service import APIKeyService
        
        service = APIKeyService(mock_db)
        plain_key, api_key = await service.create_api_key()
        
        assert api_key.name.startswith("API Key")
    
    @pytest.mark.asyncio
    async def test_verify_api_key_not_found(self, mock_db):
        """Test verifying non-existent API key."""
        from app.services.api_key_service import APIKeyService
        
        service = APIKeyService(mock_db)
        
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result
        
        result = await service.verify_api_key("invalid_key")
        assert result is None
    
    @pytest.mark.asyncio
    async def test_verify_api_key_invalid_expired(self, mock_db):
        """Test verifying expired API key."""
        from app.services.api_key_service import APIKeyService
        from app.models.api_key import APIKey
        
        service = APIKeyService(mock_db)
        
        # Create expired key
        expired_key = APIKey()
        expired_key.id = 1
        expired_key.key_hash = "hash"
        expired_key.is_active = True
        expired_key.expires_at = datetime.utcnow() - timedelta(days=1)
        expired_key.created_at = datetime.utcnow() - timedelta(days=30)
        
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = expired_key
        mock_db.execute.return_value = mock_result
        
        result = await service.verify_api_key("some_key")
        assert result is None
    
    @pytest.mark.asyncio
    async def test_verify_api_key_inactive(self, mock_db):
        """Test verifying inactive API key."""
        from app.services.api_key_service import APIKeyService
        from app.models.api_key import APIKey
        
        service = APIKeyService(mock_db)
        
        inactive_key = APIKey()
        inactive_key.id = 1
        inactive_key.key_hash = "hash"
        inactive_key.is_active = False
        inactive_key.created_at = datetime.utcnow()
        
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = inactive_key
        mock_db.execute.return_value = mock_result
        
        result = await service.verify_api_key("some_key")
        assert result is None
    
    @pytest.mark.asyncio
    async def test_get_api_key(self, mock_db):
        """Test getting API key by ID."""
        from app.services.api_key_service import APIKeyService
        from app.models.api_key import APIKey
        
        service = APIKeyService(mock_db)
        
        mock_key = APIKey()
        mock_key.id = 1
        mock_db.get.return_value = mock_key
        
        result = await service.get_api_key(1)
        assert result.id == 1
    
    @pytest.mark.asyncio
    async def test_list_api_keys_active_only(self, mock_db):
        """Test listing only active API keys."""
        from app.services.api_key_service import APIKeyService
        
        service = APIKeyService(mock_db)
        
        mock_count_result = MagicMock()
        mock_count_result.scalar.return_value = 5
        
        mock_keys_result = MagicMock()
        mock_keys_result.scalars.return_value.all.return_value = []
        
        mock_db.execute.side_effect = [mock_count_result, mock_keys_result]
        
        keys, total = await service.list_api_keys(active_only=True)
        
        assert total == 5
        assert isinstance(keys, list)
    
    @pytest.mark.asyncio
    async def test_update_api_key_not_found(self, mock_db):
        """Test updating non-existent API key."""
        from app.services.api_key_service import APIKeyService
        
        service = APIKeyService(mock_db)
        mock_db.get.return_value = None
        
        result = await service.update_api_key(999, name="New Name")
        assert result is None
    
    @pytest.mark.asyncio
    async def test_update_api_key_all_fields(self, mock_db):
        """Test updating all API key fields."""
        from app.services.api_key_service import APIKeyService
        from app.models.api_key import APIKey
        
        service = APIKeyService(mock_db)
        
        mock_key = APIKey()
        mock_key.id = 1
        mock_key.name = "Old Name"
        mock_key.is_active = True
        mock_key.rate_limit = 60
        mock_key.expires_at = None
        mock_key.key_metadata = None
        mock_key.created_at = datetime.utcnow()
        
        mock_db.get.return_value = mock_key
        
        result = await service.update_api_key(
            key_id=1,
            name="New Name",
            is_active=False,
            rate_limit=120,
            expires_in_days=30,
            metadata={"updated": True}
        )
        
        assert result.name == "New Name"
        assert result.is_active is False
        assert result.rate_limit == 120
        assert result.expires_at is not None
        assert mock_db.commit.called
    
    @pytest.mark.asyncio
    async def test_update_api_key_clear_expiration(self, mock_db):
        """Test clearing API key expiration."""
        from app.services.api_key_service import APIKeyService
        from app.models.api_key import APIKey
        
        service = APIKeyService(mock_db)
        
        mock_key = APIKey()
        mock_key.id = 1
        mock_key.expires_at = datetime.utcnow() + timedelta(days=30)
        mock_key.created_at = datetime.utcnow()
        
        mock_db.get.return_value = mock_key
        
        result = await service.update_api_key(key_id=1, expires_in_days=0)
        
        assert result.expires_at is None
    
    @pytest.mark.asyncio
    async def test_delete_api_key_not_found(self, mock_db):
        """Test deleting non-existent API key."""
        from app.services.api_key_service import APIKeyService
        
        service = APIKeyService(mock_db)
        mock_db.get.return_value = None
        
        result = await service.delete_api_key(999)
        assert result is False
    
    @pytest.mark.asyncio
    async def test_delete_api_key_success(self, mock_db):
        """Test soft deleting API key."""
        from app.services.api_key_service import APIKeyService
        from app.models.api_key import APIKey
        
        service = APIKeyService(mock_db)
        
        mock_key = APIKey()
        mock_key.id = 1
        mock_key.is_active = True
        mock_key.created_at = datetime.utcnow()
        
        mock_db.get.return_value = mock_key
        
        result = await service.delete_api_key(1)
        
        assert result is True
        assert mock_key.is_active is False
        assert mock_db.commit.called
    
    @pytest.mark.asyncio
    async def test_revoke_api_key(self, mock_db):
        """Test revoke_api_key is alias for delete."""
        from app.services.api_key_service import APIKeyService
        from app.models.api_key import APIKey
        
        service = APIKeyService(mock_db)
        
        mock_key = APIKey()
        mock_key.id = 1
        mock_key.is_active = True
        mock_key.created_at = datetime.utcnow()
        
        mock_db.get.return_value = mock_key
        
        result = await service.revoke_api_key(1)
        assert result is True


class TestFeatureServiceComprehensive:
    """Comprehensive tests for FeatureService."""
    
    @pytest.fixture
    def mock_db(self):
        """Create mock database session."""
        session = AsyncMock()
        session.execute = AsyncMock()
        session.get = AsyncMock()
        session.delete = AsyncMock()
        session.commit = AsyncMock()
        session.refresh = AsyncMock()
        return session
    
    @pytest.mark.asyncio
    async def test_get_feature_not_found(self, mock_db):
        """Test getting non-existent feature."""
        from app.services.feature_service import FeatureService
        
        service = FeatureService(mock_db)
        mock_db.get.return_value = None
        
        result = await service.get_feature(999)
        assert result is None
    
    @pytest.mark.asyncio
    async def test_update_feature_not_found(self, mock_db):
        """Test updating non-existent feature."""
        from app.services.feature_service import FeatureService
        
        service = FeatureService(mock_db)
        mock_db.get.return_value = None
        
        result = await service.update_feature(999, properties={"name": "Test"})
        assert result is None
    
    @pytest.mark.asyncio
    async def test_update_feature_with_geometry(self, mock_db):
        """Test updating feature with new geometry."""
        from app.services.feature_service import FeatureService
        from app.models.feature import GeoFeature
        
        service = FeatureService(mock_db)
        
        mock_feature = GeoFeature()
        mock_feature.id = 1
        mock_feature.name = "Test"
        mock_feature.geometry_type = "Point"
        
        mock_db.get.return_value = mock_feature
        
        new_feature_data = {
            "type": "Feature",
            "geometry": {
                "type": "Polygon",
                "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]]
            },
            "properties": {"name": "Updated"}
        }
        
        result = await service.update_feature(1, feature_data=new_feature_data)
        
        assert mock_db.execute.called
        assert mock_db.commit.called
    
    @pytest.mark.asyncio
    async def test_update_feature_with_properties(self, mock_db):
        """Test updating feature properties only."""
        from app.services.feature_service import FeatureService
        from app.models.feature import GeoFeature
        
        service = FeatureService(mock_db)
        
        mock_feature = GeoFeature()
        mock_feature.id = 1
        mock_feature.name = "Test"
        mock_feature.properties = {}
        
        mock_db.get.return_value = mock_feature
        
        result = await service.update_feature(1, properties={"updated": True})
        
        assert mock_feature.properties == {"updated": True}
        assert mock_db.commit.called
    
    @pytest.mark.asyncio
    async def test_delete_feature_not_found(self, mock_db):
        """Test deleting non-existent feature."""
        from app.services.feature_service import FeatureService
        
        service = FeatureService(mock_db)
        mock_db.get.return_value = None
        
        result = await service.delete_feature(999)
        assert result is False
    
    @pytest.mark.asyncio
    async def test_list_features_with_type_filter(self, mock_db):
        """Test listing features with geometry type filter."""
        from app.services.feature_service import FeatureService
        
        service = FeatureService(mock_db)
        
        mock_count_result = MagicMock()
        mock_count_result.scalar.return_value = 3
        
        mock_list_result = MagicMock()
        mock_list_result.scalars.return_value.all.return_value = []
        
        mock_db.execute.side_effect = [mock_count_result, mock_list_result]
        
        features, total = await service.list_features(
            skip=0, limit=10, geometry_type="Point"
        )
        
        assert total == 3
        assert isinstance(features, list)
    
    @pytest.mark.asyncio
    async def test_create_feature_extracts_name(self, mock_db):
        """Test creating feature extracts name from properties."""
        from app.services.feature_service import FeatureService
        from app.models.feature import GeoFeature
        
        service = FeatureService(mock_db)
        
        mock_result = MagicMock()
        mock_row = MagicMock()
        mock_row.id = 1
        mock_result.fetchone.return_value = mock_row
        mock_db.execute.return_value = mock_result
        
        mock_feature = GeoFeature()
        mock_feature.id = 1
        mock_db.get.return_value = mock_feature
        
        feature_data = {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [0, 0]},
            "properties": {"name": "Property Name"}
        }
        
        # Call without explicit name - should extract from properties
        result = await service.create_feature(feature_data)
        
        assert mock_db.execute.called


# ============================================================================
# Middleware Tests
# ============================================================================

class TestRateLimitMiddleware:
    """Test RateLimitMiddleware."""
    
    @pytest.mark.asyncio
    async def test_skip_health_endpoints(self):
        """Test that health endpoints skip rate limiting."""
        from app.middleware import RateLimitMiddleware
        from app.services.rate_limiter import RateLimiter
        from unittest.mock import AsyncMock
        
        app = AsyncMock()
        rate_limiter = RateLimiter(redis_client=None, requests_per_minute=60)
        middleware = RateLimitMiddleware(app, rate_limiter)
        
        request = MagicMock()
        request.url.path = "/healthz"
        
        call_next = AsyncMock()
        call_next.return_value = MagicMock()
        
        result = await middleware.dispatch(request, call_next)
        
        assert call_next.called
    
    @pytest.mark.asyncio
    async def test_skip_metrics_endpoint(self):
        """Test that metrics endpoint skips rate limiting."""
        from app.middleware import RateLimitMiddleware
        from app.services.rate_limiter import RateLimiter
        
        app = MagicMock()
        rate_limiter = RateLimiter(redis_client=None, requests_per_minute=60)
        middleware = RateLimitMiddleware(app, rate_limiter)
        
        request = MagicMock()
        request.url.path = "/metrics"
        
        call_next = AsyncMock()
        call_next.return_value = MagicMock()
        
        result = await middleware.dispatch(request, call_next)
        
        assert call_next.called
    
    @pytest.mark.asyncio
    async def test_rate_limit_with_api_key(self):
        """Test rate limiting with API key in header."""
        from app.middleware import RateLimitMiddleware
        from app.services.rate_limiter import RateLimiter
        
        app = MagicMock()
        rate_limiter = RateLimiter(redis_client=None, requests_per_minute=60)
        middleware = RateLimitMiddleware(app, rate_limiter)
        
        request = MagicMock()
        request.url.path = "/v1/features"
        request.headers = {"X-API-Key": "test_key"}
        request.client = MagicMock()
        request.client.host = "127.0.0.1"
        
        mock_response = MagicMock()
        mock_response.headers = {}
        
        call_next = AsyncMock(return_value=mock_response)
        
        result = await middleware.dispatch(request, call_next)
        
        assert "X-RateLimit-Limit" in result.headers
        assert "X-RateLimit-Remaining" in result.headers
    
    @pytest.mark.asyncio
    async def test_rate_limit_with_bearer_token(self):
        """Test rate limiting with Bearer token."""
        from app.middleware import RateLimitMiddleware
        from app.services.rate_limiter import RateLimiter
        
        app = MagicMock()
        rate_limiter = RateLimiter(redis_client=None, requests_per_minute=60)
        middleware = RateLimitMiddleware(app, rate_limiter)
        
        request = MagicMock()
        request.url.path = "/v1/features"
        request.headers = {"Authorization": "Bearer test_token"}
        request.client = MagicMock()
        request.client.host = "127.0.0.1"
        
        mock_response = MagicMock()
        mock_response.headers = {}
        
        call_next = AsyncMock(return_value=mock_response)
        
        result = await middleware.dispatch(request, call_next)
        
        assert call_next.called
    
    @pytest.mark.asyncio
    async def test_rate_limit_exceeded(self):
        """Test response when rate limit is exceeded."""
        from app.middleware import RateLimitMiddleware
        from app.services.rate_limiter import RateLimiter
        
        app = MagicMock()
        rate_limiter = RateLimiter(redis_client=None, requests_per_minute=1)
        middleware = RateLimitMiddleware(app, rate_limiter)
        
        request = MagicMock()
        request.url.path = "/v1/features"
        request.headers = {}
        request.client = MagicMock()
        request.client.host = "127.0.0.1"
        
        call_next = AsyncMock()
        
        # Exhaust rate limit
        await rate_limiter.check_rate_limit("ip:127.0.0.1")
        
        result = await middleware.dispatch(request, call_next)
        
        assert result.status_code == 429
    
    def test_get_identifier_with_forwarded_for(self):
        """Test identifier extraction with X-Forwarded-For header."""
        from app.middleware import RateLimitMiddleware
        from app.services.rate_limiter import RateLimiter
        
        app = MagicMock()
        rate_limiter = RateLimiter(redis_client=None, requests_per_minute=60)
        middleware = RateLimitMiddleware(app, rate_limiter)
        
        request = MagicMock()
        request.headers = {"X-Forwarded-For": "192.168.1.1, 10.0.0.1"}
        request.client = MagicMock()
        request.client.host = "127.0.0.1"
        
        identifier = middleware._get_identifier(request)
        
        assert identifier == "ip:192.168.1.1"
    
    def test_get_identifier_no_client(self):
        """Test identifier extraction with no client info."""
        from app.middleware import RateLimitMiddleware
        from app.services.rate_limiter import RateLimiter
        
        app = MagicMock()
        rate_limiter = RateLimiter(redis_client=None, requests_per_minute=60)
        middleware = RateLimitMiddleware(app, rate_limiter)
        
        request = MagicMock()
        request.headers = {}
        request.client = None
        
        identifier = middleware._get_identifier(request)
        
        assert identifier == "ip:unknown"


class TestSecurityHeadersMiddleware:
    """Test SecurityHeadersMiddleware."""
    
    @pytest.mark.asyncio
    async def test_adds_security_headers(self):
        """Test that security headers are added to response."""
        from app.middleware import SecurityHeadersMiddleware
        
        app = MagicMock()
        middleware = SecurityHeadersMiddleware(app)
        
        request = MagicMock()
        
        mock_response = MagicMock()
        mock_response.headers = {}
        
        call_next = AsyncMock(return_value=mock_response)
        
        result = await middleware.dispatch(request, call_next)
        
        assert "X-Content-Type-Options" in result.headers
        assert "X-Frame-Options" in result.headers
        assert "X-XSS-Protection" in result.headers
        assert "Strict-Transport-Security" in result.headers
        assert "Content-Security-Policy" in result.headers


class TestRequestLoggingMiddleware:
    """Test RequestLoggingMiddleware."""
    
    @pytest.mark.asyncio
    async def test_logs_request_and_response(self):
        """Test that requests and responses are logged."""
        from app.middleware import RequestLoggingMiddleware
        
        app = MagicMock()
        middleware = RequestLoggingMiddleware(app)
        
        request = MagicMock()
        request.method = "GET"
        request.url.path = "/v1/features"
        request.client = MagicMock()
        request.client.host = "127.0.0.1"
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.headers = {}
        
        call_next = AsyncMock(return_value=mock_response)
        
        result = await middleware.dispatch(request, call_next)
        
        assert "X-Process-Time" in result.headers
        assert "X-Request-ID" in result.headers
    
    @pytest.mark.asyncio
    async def test_logs_errors(self):
        """Test that errors are logged."""
        from app.middleware import RequestLoggingMiddleware
        
        app = MagicMock()
        middleware = RequestLoggingMiddleware(app)
        
        request = MagicMock()
        request.method = "GET"
        request.url.path = "/v1/features"
        request.client = MagicMock()
        request.client.host = "127.0.0.1"
        
        call_next = AsyncMock(side_effect=Exception("Test error"))
        
        with pytest.raises(Exception):
            await middleware.dispatch(request, call_next)


# ============================================================================
# Rate Limiter Tests
# ============================================================================

class TestRateLimiterComprehensive:
    """Comprehensive tests for RateLimiter."""
    
    @pytest.mark.asyncio
    async def test_rate_limiter_window_reset(self):
        """Test that rate limit window resets after timeout."""
        from app.services.rate_limiter import RateLimiter
        import time
        
        limiter = RateLimiter(redis_client=None, requests_per_minute=1)
        
        key = "test_reset_key"
        await limiter.check_rate_limit(key)
        
        # Manually expire the timestamps by setting old values
        # The memory store uses list of timestamps (floats)
        expired_time = time.time() - 120  # 2 minutes ago
        limiter._memory_store[key] = [expired_time]
        
        # Should be allowed after window reset (old timestamps filtered out)
        allowed, remaining = await limiter.check_rate_limit(key)
        assert allowed is True
    
    @pytest.mark.asyncio
    async def test_rate_limiter_reset_key(self):
        """Test reset_rate_limit method clears rate limit for key."""
        from app.services.rate_limiter import RateLimiter
        
        limiter = RateLimiter(redis_client=None, requests_per_minute=1)
        
        key = "test_clear_key"
        await limiter.check_rate_limit(key)
        await limiter.check_rate_limit(key)
        
        # Should be blocked
        allowed, _ = await limiter.check_rate_limit(key)
        assert allowed is False
        
        # Reset the key using the actual method name
        await limiter.reset_rate_limit(key)
        
        # Should be allowed again
        allowed, _ = await limiter.check_rate_limit(key)
        assert allowed is True
    
    @pytest.mark.asyncio
    async def test_cleanup_memory_store(self):
        """Test memory store cleanup."""
        from app.services.rate_limiter import RateLimiter
        import time
        
        limiter = RateLimiter(redis_client=None, requests_per_minute=60)
        
        # Force cleanup by setting last_cleanup to old time
        limiter._last_cleanup = time.time() - 400
        
        # Add some old timestamps
        old_time = time.time() - 200
        limiter._memory_store["old_key"] = [old_time]
        
        # Trigger cleanup via check_rate_limit
        await limiter.check_rate_limit("new_key")
        
        # Old key should be cleaned up (empty list removed)
        assert "old_key" not in limiter._memory_store or len(limiter._memory_store["old_key"]) == 0


# ============================================================================
# Model Tests
# ============================================================================

class TestAPIKeyModel:
    """Test APIKey model."""
    
    def test_generate_key(self):
        """Test API key generation."""
        from app.models.api_key import APIKey
        
        key = APIKey.generate_key()
        
        assert key.startswith("gk_")
        assert len(key) > 40
    
    def test_is_valid_active_not_expired(self):
        """Test is_valid for active, non-expired key."""
        from app.models.api_key import APIKey
        
        key = APIKey()
        key.is_active = True
        key.expires_at = None
        key.created_at = datetime.utcnow()
        
        assert key.is_valid() is True
    
    def test_is_valid_inactive(self):
        """Test is_valid for inactive key."""
        from app.models.api_key import APIKey
        
        key = APIKey()
        key.is_active = False
        key.expires_at = None
        key.created_at = datetime.utcnow()
        
        assert key.is_valid() is False
    
    def test_is_valid_expired(self):
        """Test is_valid for expired key."""
        from app.models.api_key import APIKey
        
        key = APIKey()
        key.is_active = True
        key.expires_at = datetime.utcnow() - timedelta(days=1)
        key.created_at = datetime.utcnow() - timedelta(days=30)
        
        assert key.is_valid() is False
    
    def test_is_valid_future_expiration(self):
        """Test is_valid for key with future expiration."""
        from app.models.api_key import APIKey
        
        key = APIKey()
        key.is_active = True
        key.expires_at = datetime.utcnow() + timedelta(days=30)
        key.created_at = datetime.utcnow()
        
        assert key.is_valid() is True


class TestGeoFeatureModel:
    """Test GeoFeature model."""
    
    def test_to_geojson_with_raw_geometry(self):
        """Test to_geojson output structure."""
        from app.models.feature import GeoFeature
        
        feature = GeoFeature()
        feature.id = 1
        feature.name = "Test Point"
        feature.geometry_type = "Point"
        # Note: When testing outside of DB context, raw_geometry may not work as expected
        feature.properties = {"description": "Test property"}
        feature.created_at = datetime.utcnow()
        feature.updated_at = datetime.utcnow()
        
        geojson = feature.to_geojson()
        
        assert geojson["type"] == "Feature"
        assert geojson["id"] == 1
        # Check that properties are properly merged
        assert "name" in geojson["properties"]
        assert geojson["properties"]["name"] == "Test Point"
        assert geojson["properties"]["geometry_type"] == "Point"
        assert "created_at" in geojson["properties"]
        assert "updated_at" in geojson["properties"]
    
    def test_to_geojson_without_raw_geometry(self):
        """Test to_geojson without raw geometry returns empty dict."""
        from app.models.feature import GeoFeature
        
        feature = GeoFeature()
        feature.id = 2
        feature.name = "Test"
        feature.geometry_type = "Point"
        feature.raw_geometry = None
        feature.geom = None  # No geometry available
        feature.properties = None
        feature.created_at = datetime.utcnow()
        feature.updated_at = datetime.utcnow()
        
        geojson = feature.to_geojson()
        
        assert geojson["type"] == "Feature"
        # When raw_geometry is None, returns {} (empty dict)
        assert geojson["geometry"] == {}
        assert "properties" in geojson
    
    def test_feature_repr(self):
        """Test GeoFeature string representation."""
        from app.models.feature import GeoFeature
        
        feature = GeoFeature()
        feature.id = 1
        feature.name = "Test"
        feature.geometry_type = "Point"
        
        repr_str = repr(feature)
        
        assert "GeoFeature" in repr_str
        assert "id=1" in repr_str
        assert "Test" in repr_str


# ============================================================================
# Config Tests
# ============================================================================

class TestConfig:
    """Test configuration settings."""
    
    def test_get_database_url(self):
        """Test database URL generation."""
        from app.config import settings
        
        url = settings.get_database_url()
        
        assert url is not None
        assert "postgresql" in url
    
    def test_get_api_keys_list_empty(self):
        """Test API keys list when empty."""
        from app.config import Settings
        
        settings_obj = Settings()
        settings_obj.api_keys = ""
        
        keys = settings_obj.get_api_keys_list()
        
        assert keys == []
    
    def test_get_api_keys_list_with_values(self):
        """Test API keys list with values."""
        from app.config import Settings
        
        settings_obj = Settings()
        settings_obj.api_keys = "key1,key2,key3"
        
        keys = settings_obj.get_api_keys_list()
        
        assert keys == ["key1", "key2", "key3"]
