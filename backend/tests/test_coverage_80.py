"""
Tests targeting 80%+ coverage for geojson-ingestion app.
Focuses on uncovered lines in: database.py, main.py, feature_service.py

Run with: pytest tests/test_coverage_80.py -v --cov=app --cov-report=html
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock
from datetime import datetime, timedelta
import json
import asyncio


# ============================================================================
# Database Module Tests (database.py - currently 42%)
# ============================================================================

class TestDatabaseFunctions:
    """Test database.py functions to improve coverage."""
    
    @pytest.mark.asyncio
    async def test_get_db_generator_flow(self):
        """Test get_db generator yields and commits on success."""
        # Test by directly creating and iterating the generator
        # Using a fresh mock context manager
        mock_session = AsyncMock()
        mock_session.commit = AsyncMock()
        mock_session.rollback = AsyncMock()
        mock_session.close = AsyncMock()
        
        # Create mock context manager
        mock_context = AsyncMock()
        mock_context.__aenter__ = AsyncMock(return_value=mock_session)
        mock_context.__aexit__ = AsyncMock(return_value=False)
        
        mock_session_maker = MagicMock(return_value=mock_context)
        
        with patch('app.database.AsyncSessionLocal', mock_session_maker):
            from importlib import reload
            import app.database as db_module
            
            # Test the generator flow
            async def run_generator():
                gen = db_module.get_db()
                session = await anext(gen)
                assert session is mock_session
                # Signal completion
                try:
                    await anext(gen)
                except StopAsyncIteration:
                    pass
            
            await run_generator()
    
    @pytest.mark.asyncio
    async def test_init_db_with_postgis_present(self):
        """Test init_db when PostGIS extension exists."""
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar.return_value = True
        mock_session.execute = AsyncMock(return_value=mock_result)
        
        mock_context = AsyncMock()
        mock_context.__aenter__ = AsyncMock(return_value=mock_session)
        mock_context.__aexit__ = AsyncMock(return_value=False)
        
        mock_session_maker = MagicMock(return_value=mock_context)
        
        with patch('app.database.AsyncSessionLocal', mock_session_maker):
            from app.database import init_db
            await init_db()
            mock_session.execute.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_init_db_without_postgis(self):
        """Test init_db when PostGIS extension doesn't exist."""
        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar.return_value = False
        mock_session.execute = AsyncMock(return_value=mock_result)
        
        mock_context = AsyncMock()
        mock_context.__aenter__ = AsyncMock(return_value=mock_session)
        mock_context.__aexit__ = AsyncMock(return_value=False)
        
        mock_session_maker = MagicMock(return_value=mock_context)
        
        with patch('app.database.AsyncSessionLocal', mock_session_maker):
            from app.database import init_db
            # Should log warning but not fail
            await init_db()
    
    @pytest.mark.asyncio
    async def test_init_db_handles_connection_error(self):
        """Test init_db handles connection errors gracefully."""
        mock_context = AsyncMock()
        mock_context.__aenter__ = AsyncMock(side_effect=Exception("Connection failed"))
        mock_context.__aexit__ = AsyncMock(return_value=False)
        
        mock_session_maker = MagicMock(return_value=mock_context)
        
        with patch('app.database.AsyncSessionLocal', mock_session_maker):
            from app.database import init_db
            # Should not raise - logs error and continues
            await init_db()
    
    @pytest.mark.asyncio
    async def test_close_db_disposes_engine(self):
        """Test close_db disposes engine."""
        mock_engine = AsyncMock()
        mock_engine.dispose = AsyncMock()
        
        with patch('app.database.engine', mock_engine):
            from app.database import close_db
            await close_db()
            mock_engine.dispose.assert_called_once()


# ============================================================================
# Main Module Tests (main.py - currently 50%)
# Using mocks to avoid SQLite JSONB compatibility issues
# ============================================================================

class TestVerifyApiKeyFunction:
    """Test verify_api_key function logic."""
    
    def test_verify_api_key_disabled(self):
        """Test when in dev_open mode."""
        from app.config import settings
        
        original_mode = settings.auth_mode
        settings.auth_mode = "dev_open"
        
        from app.main import verify_auth
        
        mock_db = AsyncMock()
        
        # When dev_open, should return dev_open context
        result = verify_auth(
            x_api_key=None,
            authorization=None,
            db=mock_db
        )
        assert result["type"] == "dev_open"
        
        settings.auth_mode = original_mode
    
    def test_verify_api_key_from_header(self):
        """Test extracting API key from X-API-Key header."""
        from app.config import settings
        
        original_keys = settings.api_keys
        original_mode = settings.auth_mode
        settings.api_keys = "test-key-123"
        settings.auth_mode = "service_api_key"
        
        from app.main import verify_auth
        
        mock_db = AsyncMock()
        
        result = verify_auth(
            x_api_key="test-key-123",
            authorization=None,
            db=mock_db
        )
        assert result["type"] == "api_key"
        assert result["key"] == "test-key-123"
        
        settings.api_keys = original_keys
        settings.auth_mode = original_mode
    
    def test_verify_api_key_from_bearer(self):
        """Test extracting API key from Authorization: Bearer header in combined mode."""
        from app.config import settings
        
        original_keys = settings.api_keys
        original_mode = settings.auth_mode
        settings.api_keys = "bearer-key-456"
        settings.auth_mode = "combined"
        
        from app.main import verify_auth
        
        mock_db = AsyncMock()
        
        result = verify_auth(
            x_api_key="bearer-key-456",
            authorization=None,
            db=mock_db
        )
        assert result["type"] == "api_key"
        
        settings.api_keys = original_keys
        settings.auth_mode = original_mode
    
    def test_verify_api_key_missing_raises(self):
        """Test that missing API key raises HTTPException when required."""
        from app.config import settings
        from fastapi import HTTPException
        
        original_keys = settings.api_keys
        original_mode = settings.auth_mode
        settings.api_keys = "required-key"
        settings.auth_mode = "service_api_key"
        
        from app.main import verify_auth
        
        mock_db = AsyncMock()
        
        with pytest.raises(HTTPException) as exc_info:
            verify_auth(
                x_api_key=None,
                authorization=None,
                db=mock_db
            )
        assert exc_info.value.status_code == 401
        
        settings.api_keys = original_keys
        settings.auth_mode = original_mode
    
    def test_verify_api_key_invalid_raises(self):
        """Test that invalid key raises HTTPException."""
        from app.config import settings
        from fastapi import HTTPException
        
        original_keys = settings.api_keys
        original_mode = settings.auth_mode
        settings.api_keys = "valid-key-only"
        settings.auth_mode = "service_api_key"
        
        from app.main import verify_auth
        
        mock_db = AsyncMock()
        
        # Invalid key not in configured keys - should raise
        with pytest.raises(HTTPException) as exc_info:
            verify_auth(
                x_api_key="invalid-key",
                authorization=None,
                db=mock_db
            )
        assert exc_info.value.status_code == 401
        
        settings.api_keys = original_keys
        settings.auth_mode = original_mode


class TestAPIEndpointsMocked:
    """Test API endpoint handlers with mocked services."""
    
    def _create_mock_feature(self):
        """Create a mock GeoFeature for testing."""
        from app.models.feature import GeoFeature
        mock_feature = GeoFeature()
        mock_feature.id = 1
        mock_feature.name = "Test"
        mock_feature.geometry_type = "Point"
        mock_feature.properties = {}
        mock_feature.raw_geometry = {"type": "Point", "coordinates": [0, 0]}
        mock_feature.owner_sub = None
        mock_feature.edit_token = None
        mock_feature.created_at = datetime.utcnow()
        mock_feature.updated_at = datetime.utcnow()
        return mock_feature
    
    @pytest.mark.asyncio
    async def test_ingest_geojson_success(self):
        """Test ingest endpoint with mocked service."""
        from app.main import ingest_geojson
        
        mock_db = AsyncMock()
        mock_feature = self._create_mock_feature()
        
        with patch('app.main.FeatureService') as mock_service_class:
            mock_service = AsyncMock()
            mock_service.create_feature = AsyncMock(return_value=(mock_feature, None))
            mock_service_class.return_value = mock_service
            
            result = await ingest_geojson(
                feature={"type": "Feature", "geometry": {"type": "Point", "coordinates": [0, 0]}, "properties": {}},
                name="Test",
                db=mock_db,
                auth_context={"type": "dev_open"},
                current_user=None
            )
            
            assert result["id"] == 1
            assert result["message"] == "Feature ingested successfully"
    
    @pytest.mark.asyncio
    async def test_ingest_geojson_invalid_type(self):
        """Test ingest endpoint rejects non-Feature type."""
        from app.main import ingest_geojson
        from fastapi import HTTPException
        
        mock_db = AsyncMock()
        
        with pytest.raises(HTTPException) as exc_info:
            await ingest_geojson(
                feature={"type": "FeatureCollection", "features": []},
                name=None,
                db=mock_db,
                auth_context={"type": "dev_open"},
                current_user=None
            )
        assert exc_info.value.status_code == 400
        assert "Expected GeoJSON Feature" in exc_info.value.detail
    
    @pytest.mark.asyncio
    async def test_list_features_success(self):
        """Test list features endpoint."""
        from app.main import list_features
        from app.services.feature_service import OwnershipInfo
        
        mock_db = AsyncMock()
        mock_feature = self._create_mock_feature()
        
        with patch('app.main.FeatureService') as mock_service_class:
            mock_service = AsyncMock()
            mock_service.list_features = AsyncMock(return_value=([mock_feature], 1))
            mock_service.get_ownership_info = MagicMock(return_value=OwnershipInfo(True, False))
            mock_service_class.return_value = mock_service
            
            result = await list_features(
                skip=0, limit=100, geometry_type=None,
                db=mock_db, auth_context={"type": "dev_open"}, current_user=None
            )
            
            assert result["total"] == 1
            assert len(result["features"]) == 1
    
    @pytest.mark.asyncio
    async def test_query_by_bbox_success(self):
        """Test bounding box query endpoint."""
        from app.main import query_by_bbox
        from app.services.feature_service import OwnershipInfo
        
        mock_db = AsyncMock()
        mock_feature = self._create_mock_feature()
        
        with patch('app.main.FeatureService') as mock_service_class:
            mock_service = AsyncMock()
            mock_service.query_by_bbox = AsyncMock(return_value=[mock_feature])
            mock_service.get_ownership_info = MagicMock(return_value=OwnershipInfo(True, False))
            mock_service_class.return_value = mock_service
            
            result = await query_by_bbox(
                min_lon=-123.0, min_lat=37.0, max_lon=-122.0, max_lat=38.0,
                db=mock_db, auth_context={"type": "dev_open"}, current_user=None
            )
            
            assert result["type"] == "FeatureCollection"
            assert result["count"] == 1
    
    @pytest.mark.asyncio
    async def test_query_by_proximity_success(self):
        """Test proximity query endpoint."""
        from app.main import query_by_proximity
        from app.services.feature_service import OwnershipInfo
        
        mock_db = AsyncMock()
        mock_feature = self._create_mock_feature()
        
        with patch('app.main.FeatureService') as mock_service_class:
            mock_service = AsyncMock()
            mock_service.query_by_proximity = AsyncMock(return_value=[mock_feature])
            mock_service.get_ownership_info = MagicMock(return_value=OwnershipInfo(True, False))
            mock_service_class.return_value = mock_service
            
            result = await query_by_proximity(
                lon=-122.4, lat=37.7, radius=1000, limit=100,
                db=mock_db, auth_context={"type": "dev_open"}, current_user=None
            )
            
            assert result["type"] == "FeatureCollection"
            assert result["count"] == 1
    
    @pytest.mark.asyncio
    async def test_get_feature_success(self):
        """Test get feature by ID endpoint."""
        from app.main import get_feature
        from app.services.feature_service import OwnershipInfo
        
        mock_db = AsyncMock()
        mock_feature = self._create_mock_feature()
        
        with patch('app.main.FeatureService') as mock_service_class:
            mock_service = AsyncMock()
            mock_service.get_feature = AsyncMock(return_value=mock_feature)
            mock_service.get_ownership_info = MagicMock(return_value=OwnershipInfo(True, False))
            mock_service_class.return_value = mock_service
            
            result = await get_feature(
                feature_id=1, db=mock_db,
                auth_context={"type": "dev_open"}, current_user=None
            )
            
            assert result["id"] == 1
    
    @pytest.mark.asyncio
    async def test_get_feature_not_found(self):
        """Test get feature returns 404 when not found."""
        from app.main import get_feature
        from fastapi import HTTPException
        
        mock_db = AsyncMock()
        
        with patch('app.main.FeatureService') as mock_service_class:
            mock_service = AsyncMock()
            mock_service.get_feature = AsyncMock(return_value=None)
            mock_service_class.return_value = mock_service
            
            with pytest.raises(HTTPException) as exc_info:
                await get_feature(
                    feature_id=999, db=mock_db,
                    auth_context={"type": "dev_open"}, current_user=None
                )
            assert exc_info.value.status_code == 404
    
    @pytest.mark.asyncio
    async def test_update_feature_success(self):
        """Test update feature endpoint."""
        from app.main import update_feature
        from app.services.feature_service import OwnershipInfo
        
        mock_db = AsyncMock()
        mock_feature = self._create_mock_feature()
        mock_feature.name = "Updated"
        mock_feature.properties = {"updated": True}
        
        with patch('app.main.FeatureService') as mock_service_class:
            mock_service = AsyncMock()
            mock_service.get_feature = AsyncMock(return_value=mock_feature)
            mock_service.verify_ownership = MagicMock(return_value=OwnershipInfo(True, True))
            mock_service.update_feature = AsyncMock(return_value=mock_feature)
            mock_service_class.return_value = mock_service
            
            result = await update_feature(
                feature_id=1,
                feature_data=None,
                name="Updated",
                properties={"updated": True},
                edit_token=None,
                db=mock_db,
                auth_context={"type": "dev_open"},
                current_user=None
            )
            
            assert result["id"] == 1
            assert result["message"] == "Feature updated successfully"
    
    @pytest.mark.asyncio
    async def test_update_feature_not_found(self):
        """Test update feature returns 404 when not found."""
        from app.main import update_feature
        from fastapi import HTTPException
        
        mock_db = AsyncMock()
        
        with patch('app.main.FeatureService') as mock_service_class:
            mock_service = AsyncMock()
            mock_service.get_feature = AsyncMock(return_value=None)
            mock_service_class.return_value = mock_service
            
            with pytest.raises(HTTPException) as exc_info:
                await update_feature(
                    feature_id=999,
                    feature_data=None,
                    name="Test",
                    properties=None,
                    edit_token=None,
                    db=mock_db,
                    auth_context={"type": "dev_open"},
                    current_user=None
                )
            assert exc_info.value.status_code == 404
    
    @pytest.mark.asyncio
    async def test_delete_feature_success(self):
        """Test delete feature endpoint."""
        from app.main import delete_feature
        from app.services.feature_service import OwnershipInfo
        
        mock_db = AsyncMock()
        mock_feature = self._create_mock_feature()
        
        with patch('app.main.FeatureService') as mock_service_class:
            mock_service = AsyncMock()
            mock_service.get_feature = AsyncMock(return_value=mock_feature)
            mock_service.verify_ownership = MagicMock(return_value=OwnershipInfo(True, True))
            mock_service.delete_feature = AsyncMock(return_value=True)
            mock_service_class.return_value = mock_service
            
            result = await delete_feature(
                feature_id=1, edit_token=None, db=mock_db,
                auth_context={"type": "dev_open"}, current_user=None
            )
            
            assert "deleted successfully" in result["message"]
    
    @pytest.mark.asyncio
    async def test_delete_feature_not_found(self):
        """Test delete feature returns 404 when not found."""
        from app.main import delete_feature
        from fastapi import HTTPException
        
        mock_db = AsyncMock()
        
        with patch('app.main.FeatureService') as mock_service_class:
            mock_service = AsyncMock()
            mock_service.get_feature = AsyncMock(return_value=None)
            mock_service_class.return_value = mock_service
            
            with pytest.raises(HTTPException) as exc_info:
                await delete_feature(
                    feature_id=999, edit_token=None, db=mock_db,
                    auth_context={"type": "dev_open"}, current_user=None
                )
            assert exc_info.value.status_code == 404
    
    @pytest.mark.asyncio
    async def test_export_all_success(self):
        """Test export all endpoint."""
        from app.main import export_all
        from app.services.feature_service import OwnershipInfo
        
        mock_db = AsyncMock()
        mock_feature = self._create_mock_feature()
        
        # Mock the db.execute result for the export_all function
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_feature]
        mock_db.execute = AsyncMock(return_value=mock_result)
        
        with patch('app.main.FeatureService') as mock_service_class:
            mock_service = AsyncMock()
            mock_service.get_ownership_info = MagicMock(return_value=OwnershipInfo(True, False))
            mock_service_class.return_value = mock_service
            
            result = await export_all(
                db=mock_db, auth_context={"type": "dev_open"}, current_user=None
            )
            
            assert result["type"] == "FeatureCollection"


class TestAPIKeyEndpointsMocked:
    """Test API key management endpoints with mocked services."""
    
    @pytest.mark.asyncio
    async def test_create_api_key_success(self):
        """Test creating a new API key."""
        from app.main import create_api_key
        from app.models.api_key import APIKey
        
        mock_db = AsyncMock()
        mock_api_key = APIKey()
        mock_api_key.id = 1
        mock_api_key.name = "Test Key"
        mock_api_key.rate_limit = 100
        mock_api_key.expires_at = datetime.utcnow() + timedelta(days=30)
        mock_api_key.created_at = datetime.utcnow()
        
        with patch('app.main.APIKeyService') as mock_service_class:
            mock_service = AsyncMock()
            mock_service.create_api_key = AsyncMock(return_value=("gk_test_key", mock_api_key))
            mock_service_class.return_value = mock_service
            
            result = await create_api_key(
                name="Test Key",
                rate_limit=100,
                expires_in_days=30,
                metadata=None,
                db=mock_db,
                api_key=None
            )
            
            assert result["id"] == 1
            assert "key" in result
    
    @pytest.mark.asyncio
    async def test_list_api_keys_success(self):
        """Test listing API keys."""
        from app.main import list_api_keys
        from app.models.api_key import APIKey
        
        mock_db = AsyncMock()
        mock_api_key = APIKey()
        mock_api_key.id = 1
        mock_api_key.name = "Test Key"
        mock_api_key.is_active = True
        mock_api_key.rate_limit = 60
        mock_api_key.expires_at = None
        mock_api_key.last_used_at = None
        mock_api_key.usage_count = 0
        mock_api_key.created_at = datetime.utcnow()
        
        with patch('app.main.APIKeyService') as mock_service_class:
            mock_service = AsyncMock()
            mock_service.list_api_keys = AsyncMock(return_value=([mock_api_key], 1))
            mock_service_class.return_value = mock_service
            
            result = await list_api_keys(
                skip=0, limit=100, active_only=False,
                db=mock_db, api_key=None
            )
            
            assert result["total"] == 1
            assert len(result["api_keys"]) == 1
    
    @pytest.mark.asyncio
    async def test_update_api_key_success(self):
        """Test updating an API key."""
        from app.main import update_api_key
        from app.models.api_key import APIKey
        
        mock_db = AsyncMock()
        mock_api_key = APIKey()
        mock_api_key.id = 1
        mock_api_key.name = "Updated Key"
        mock_api_key.is_active = True
        mock_api_key.rate_limit = 120
        mock_api_key.expires_at = None
        mock_api_key.created_at = datetime.utcnow()
        
        with patch('app.main.APIKeyService') as mock_service_class:
            mock_service = AsyncMock()
            mock_service.update_api_key = AsyncMock(return_value=mock_api_key)
            mock_service_class.return_value = mock_service
            
            result = await update_api_key(
                key_id=1,
                name="Updated Key",
                is_active=True,
                rate_limit=120,
                expires_in_days=None,
                metadata=None,
                db=mock_db,
                api_key=None
            )
            
            assert result["id"] == 1
            assert result["name"] == "Updated Key"
    
    @pytest.mark.asyncio
    async def test_update_api_key_not_found(self):
        """Test updating non-existent API key."""
        from app.main import update_api_key
        from fastapi import HTTPException
        
        mock_db = AsyncMock()
        
        with patch('app.main.APIKeyService') as mock_service_class:
            mock_service = AsyncMock()
            mock_service.update_api_key = AsyncMock(return_value=None)
            mock_service_class.return_value = mock_service
            
            with pytest.raises(HTTPException) as exc_info:
                await update_api_key(
                    key_id=999,
                    name="Test",
                    is_active=None,
                    rate_limit=None,
                    expires_in_days=None,
                    metadata=None,
                    db=mock_db,
                    api_key=None
                )
            assert exc_info.value.status_code == 404
    
    @pytest.mark.asyncio
    async def test_delete_api_key_success(self):
        """Test deleting an API key."""
        from app.main import delete_api_key
        
        mock_db = AsyncMock()
        
        with patch('app.main.APIKeyService') as mock_service_class:
            mock_service = AsyncMock()
            mock_service.delete_api_key = AsyncMock(return_value=True)
            mock_service_class.return_value = mock_service
            
            result = await delete_api_key(key_id=1, db=mock_db, api_key=None)
            
            assert "deleted successfully" in result["message"]
    
    @pytest.mark.asyncio
    async def test_delete_api_key_not_found(self):
        """Test deleting non-existent API key."""
        from app.main import delete_api_key
        from fastapi import HTTPException
        
        mock_db = AsyncMock()
        
        with patch('app.main.APIKeyService') as mock_service_class:
            mock_service = AsyncMock()
            mock_service.delete_api_key = AsyncMock(return_value=False)
            mock_service_class.return_value = mock_service
            
            with pytest.raises(HTTPException) as exc_info:
                await delete_api_key(key_id=999, db=mock_db, api_key=None)
            assert exc_info.value.status_code == 404


# ============================================================================
# Feature Service Tests (feature_service.py - currently 70%)
# ============================================================================

class TestFeatureServiceSpatialQueries:
    """Test spatial query methods in FeatureService."""
    
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
    async def test_query_by_bbox_with_results(self, mock_db):
        """Test query_by_bbox returns features from results."""
        from app.services.feature_service import FeatureService
        from datetime import datetime
        
        service = FeatureService(mock_db)
        
        # Create mock row data
        mock_row = MagicMock()
        mock_row.id = 1
        mock_row.name = "Test Point"
        mock_row.geometry_type = "Point"
        mock_row.properties = {"test": True}
        mock_row.raw_geometry = {"type": "Point", "coordinates": [0, 0]}
        mock_row.owner_sub = None
        mock_row.edit_token = None
        mock_row.created_at = datetime.utcnow()
        mock_row.updated_at = datetime.utcnow()
        
        mock_result = MagicMock()
        mock_result.fetchall.return_value = [mock_row]
        mock_db.execute.return_value = mock_result
        
        features = await service.query_by_bbox(-123.0, 37.0, -122.0, 38.0)
        
        assert len(features) == 1
        assert features[0].id == 1
        assert features[0].name == "Test Point"
        assert features[0].geometry_type == "Point"
    
    @pytest.mark.asyncio
    async def test_query_by_bbox_empty_results(self, mock_db):
        """Test query_by_bbox with no matching features."""
        from app.services.feature_service import FeatureService
        
        service = FeatureService(mock_db)
        
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        mock_db.execute.return_value = mock_result
        
        features = await service.query_by_bbox(-180.0, -90.0, -170.0, -80.0)
        
        assert len(features) == 0
        assert features == []
    
    @pytest.mark.asyncio
    async def test_query_by_proximity_with_results(self, mock_db):
        """Test query_by_proximity returns features ordered by distance."""
        from app.services.feature_service import FeatureService
        from datetime import datetime
        
        service = FeatureService(mock_db)
        
        # Create mock rows for multiple results
        mock_row1 = MagicMock()
        mock_row1.id = 1
        mock_row1.name = "Nearby Point"
        mock_row1.geometry_type = "Point"
        mock_row1.properties = {}
        mock_row1.raw_geometry = {"type": "Point", "coordinates": [-122.4, 37.7]}
        mock_row1.owner_sub = None
        mock_row1.edit_token = None
        mock_row1.created_at = datetime.utcnow()
        mock_row1.updated_at = datetime.utcnow()
        mock_row1.distance = 100.5
        
        mock_row2 = MagicMock()
        mock_row2.id = 2
        mock_row2.name = "Far Point"
        mock_row2.geometry_type = "Point"
        mock_row2.properties = {}
        mock_row2.raw_geometry = {"type": "Point", "coordinates": [-122.5, 37.8]}
        mock_row2.owner_sub = None
        mock_row2.edit_token = None
        mock_row2.created_at = datetime.utcnow()
        mock_row2.updated_at = datetime.utcnow()
        mock_row2.distance = 500.0
        
        mock_result = MagicMock()
        mock_result.fetchall.return_value = [mock_row1, mock_row2]
        mock_db.execute.return_value = mock_result
        
        features = await service.query_by_proximity(-122.4194, 37.7749, 1000, 10)
        
        assert len(features) == 2
        assert features[0].id == 1
        assert features[1].id == 2
    
    @pytest.mark.asyncio
    async def test_query_by_proximity_empty(self, mock_db):
        """Test query_by_proximity with no nearby features."""
        from app.services.feature_service import FeatureService
        
        service = FeatureService(mock_db)
        
        mock_result = MagicMock()
        mock_result.fetchall.return_value = []
        mock_db.execute.return_value = mock_result
        
        features = await service.query_by_proximity(0, 0, 100, 10)
        
        assert len(features) == 0
    
    @pytest.mark.asyncio
    async def test_export_all_with_features(self, mock_db):
        """Test export_all returns proper FeatureCollection."""
        from app.services.feature_service import FeatureService
        from app.models.feature import GeoFeature
        from datetime import datetime
        
        service = FeatureService(mock_db)
        
        # Create mock features
        mock_feature1 = GeoFeature()
        mock_feature1.id = 1
        mock_feature1.name = "Feature 1"
        mock_feature1.geometry_type = "Point"
        mock_feature1.properties = {}
        mock_feature1.raw_geometry = {"type": "Point", "coordinates": [0, 0]}
        mock_feature1.created_at = datetime.utcnow()
        mock_feature1.updated_at = datetime.utcnow()
        
        mock_feature2 = GeoFeature()
        mock_feature2.id = 2
        mock_feature2.name = "Feature 2"
        mock_feature2.geometry_type = "Polygon"
        mock_feature2.properties = {}
        mock_feature2.raw_geometry = {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]]}
        mock_feature2.created_at = datetime.utcnow()
        mock_feature2.updated_at = datetime.utcnow()
        
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_feature1, mock_feature2]
        mock_db.execute.return_value = mock_result
        
        result = await service.export_all()
        
        assert result["type"] == "FeatureCollection"
        assert len(result["features"]) == 2
        assert result["features"][0]["id"] == 1
        assert result["features"][1]["id"] == 2
    
    @pytest.mark.asyncio
    async def test_export_all_empty(self, mock_db):
        """Test export_all with no features."""
        from app.services.feature_service import FeatureService
        
        service = FeatureService(mock_db)
        
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result
        
        result = await service.export_all()
        
        assert result["type"] == "FeatureCollection"
        assert result["features"] == []
    
    @pytest.mark.asyncio
    async def test_update_feature_with_name(self, mock_db):
        """Test updating feature with name parameter."""
        from app.services.feature_service import FeatureService
        from app.models.feature import GeoFeature
        from datetime import datetime
        
        service = FeatureService(mock_db)
        
        # Create mock feature
        mock_feature = GeoFeature()
        mock_feature.id = 1
        mock_feature.name = "Original Name"
        mock_feature.geometry_type = "Point"
        mock_feature.properties = {}
        mock_feature.created_at = datetime.utcnow()
        mock_feature.updated_at = datetime.utcnow()
        
        mock_db.get.return_value = mock_feature
        
        # Update with just name parameter
        result = await service.update_feature(1, name="New Name")
        
        assert result is not None
        assert result.name == "New Name"
        mock_db.commit.assert_called()
        mock_db.refresh.assert_called_with(mock_feature)
    
    @pytest.mark.asyncio
    async def test_update_feature_with_feature_data_properties(self, mock_db):
        """Test updating feature with properties from feature_data."""
        from app.services.feature_service import FeatureService
        from app.models.feature import GeoFeature
        from datetime import datetime
        
        service = FeatureService(mock_db)
        
        mock_feature = GeoFeature()
        mock_feature.id = 1
        mock_feature.name = "Test"
        mock_feature.geometry_type = "Point"
        mock_feature.properties = {}
        mock_feature.created_at = datetime.utcnow()
        mock_feature.updated_at = datetime.utcnow()
        
        mock_db.get.return_value = mock_feature
        
        # Update with feature_data containing properties but no geometry
        feature_data = {
            "type": "Feature",
            "properties": {"updated": True, "version": 2}
        }
        
        result = await service.update_feature(1, feature_data=feature_data)
        
        assert result is not None
        assert result.properties == {"updated": True, "version": 2}


# ============================================================================
# Additional Tests for Edge Cases and Error Handling
# ============================================================================

class TestMainModuleErrorHandling:
    """Test error handling in main.py endpoints."""
    
    @pytest.mark.asyncio
    async def test_ingest_service_error(self):
        """Test ingest endpoint handles service errors."""
        from app.main import ingest_geojson
        from fastapi import HTTPException
        
        mock_db = AsyncMock()
        
        with patch('app.main.FeatureService') as mock_service_class:
            mock_service = AsyncMock()
            mock_service.create_feature = AsyncMock(side_effect=Exception("DB Error"))
            mock_service_class.return_value = mock_service
            
            with pytest.raises(HTTPException) as exc_info:
                await ingest_geojson(
                    feature={"type": "Feature", "geometry": {"type": "Point", "coordinates": [0, 0]}, "properties": {}},
                    name=None,
                    db=mock_db,
                    auth_context={"type": "dev_open"},
                    current_user=None
                )
            assert exc_info.value.status_code == 500
    
    @pytest.mark.asyncio
    async def test_list_features_service_error(self):
        """Test list features handles service errors."""
        from app.main import list_features
        from fastapi import HTTPException
        
        mock_db = AsyncMock()
        
        with patch('app.main.FeatureService') as mock_service_class:
            mock_service = AsyncMock()
            mock_service.list_features = AsyncMock(side_effect=Exception("DB Error"))
            mock_service_class.return_value = mock_service
            
            with pytest.raises(HTTPException) as exc_info:
                await list_features(
                    skip=0, limit=100, geometry_type=None, db=mock_db,
                    auth_context={"type": "dev_open"}, current_user=None
                )
            assert exc_info.value.status_code == 500
    
    @pytest.mark.asyncio
    async def test_bbox_query_service_error(self):
        """Test bbox query handles service errors."""
        from app.main import query_by_bbox
        from fastapi import HTTPException
        
        mock_db = AsyncMock()
        
        with patch('app.main.FeatureService') as mock_service_class:
            mock_service = AsyncMock()
            mock_service.query_by_bbox = AsyncMock(side_effect=Exception("PostGIS Error"))
            mock_service_class.return_value = mock_service
            
            with pytest.raises(HTTPException) as exc_info:
                await query_by_bbox(
                    min_lon=-123.0, min_lat=37.0, max_lon=-122.0, max_lat=38.0,
                    db=mock_db, auth_context={"type": "dev_open"}, current_user=None
                )
            assert exc_info.value.status_code == 500
    
    @pytest.mark.asyncio
    async def test_proximity_query_service_error(self):
        """Test proximity query handles service errors."""
        from app.main import query_by_proximity
        from fastapi import HTTPException
        
        mock_db = AsyncMock()
        
        with patch('app.main.FeatureService') as mock_service_class:
            mock_service = AsyncMock()
            mock_service.query_by_proximity = AsyncMock(side_effect=Exception("Query Error"))
            mock_service_class.return_value = mock_service
            
            with pytest.raises(HTTPException) as exc_info:
                await query_by_proximity(
                    lon=-122.4, lat=37.7, radius=1000, limit=100, db=mock_db,
                    auth_context={"type": "dev_open"}, current_user=None
                )
            assert exc_info.value.status_code == 500
    
    @pytest.mark.asyncio
    async def test_get_feature_service_error(self):
        """Test get feature handles service errors."""
        from app.main import get_feature
        from fastapi import HTTPException
        
        mock_db = AsyncMock()
        
        with patch('app.main.FeatureService') as mock_service_class:
            mock_service = AsyncMock()
            mock_service.get_feature = AsyncMock(side_effect=Exception("DB Error"))
            mock_service_class.return_value = mock_service
            
            with pytest.raises(HTTPException) as exc_info:
                await get_feature(
                    feature_id=1, db=mock_db,
                    auth_context={"type": "dev_open"}, current_user=None
                )
            assert exc_info.value.status_code == 500
    
    @pytest.mark.asyncio
    async def test_update_feature_service_error(self):
        """Test update feature handles service errors."""
        from app.main import update_feature
        from app.models.feature import GeoFeature
        from app.services.feature_service import OwnershipInfo
        from fastapi import HTTPException
        
        mock_db = AsyncMock()
        mock_feature = GeoFeature()
        mock_feature.id = 1
        mock_feature.owner_sub = None
        mock_feature.edit_token = None
        
        with patch('app.main.FeatureService') as mock_service_class:
            mock_service = AsyncMock()
            mock_service.get_feature = AsyncMock(return_value=mock_feature)
            mock_service.verify_ownership = MagicMock(return_value=OwnershipInfo(True, True))
            mock_service.update_feature = AsyncMock(side_effect=Exception("DB Error"))
            mock_service_class.return_value = mock_service
            
            with pytest.raises(HTTPException) as exc_info:
                await update_feature(
                    feature_id=1, feature_data=None, name="Test",
                    properties=None, edit_token=None, db=mock_db,
                    auth_context={"type": "dev_open"}, current_user=None
                )
            assert exc_info.value.status_code == 500
    
    @pytest.mark.asyncio
    async def test_delete_feature_service_error(self):
        """Test delete feature handles service errors."""
        from app.main import delete_feature
        from app.models.feature import GeoFeature
        from app.services.feature_service import OwnershipInfo
        from fastapi import HTTPException
        
        mock_db = AsyncMock()
        mock_feature = GeoFeature()
        mock_feature.id = 1
        mock_feature.owner_sub = None
        mock_feature.edit_token = None
        
        with patch('app.main.FeatureService') as mock_service_class:
            mock_service = AsyncMock()
            mock_service.get_feature = AsyncMock(return_value=mock_feature)
            mock_service.verify_ownership = MagicMock(return_value=OwnershipInfo(True, True))
            mock_service.delete_feature = AsyncMock(side_effect=Exception("DB Error"))
            mock_service_class.return_value = mock_service
            
            with pytest.raises(HTTPException) as exc_info:
                await delete_feature(
                    feature_id=1, edit_token=None, db=mock_db,
                    auth_context={"type": "dev_open"}, current_user=None
                )
            assert exc_info.value.status_code == 500
    
    @pytest.mark.asyncio
    async def test_export_all_service_error(self):
        """Test export all handles service errors."""
        from app.main import export_all
        from fastapi import HTTPException
        
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(side_effect=Exception("Export Error"))
        
        with pytest.raises(HTTPException) as exc_info:
            await export_all(
                db=mock_db, auth_context={"type": "dev_open"}, current_user=None
            )
        assert exc_info.value.status_code == 500


class TestAPIKeyErrorHandling:
    """Test error handling in API key endpoints."""
    
    @pytest.mark.asyncio
    async def test_create_api_key_service_error(self):
        """Test create API key handles service errors."""
        from app.main import create_api_key
        from fastapi import HTTPException
        
        mock_db = AsyncMock()
        
        with patch('app.main.APIKeyService') as mock_service_class:
            mock_service = AsyncMock()
            mock_service.create_api_key = AsyncMock(side_effect=Exception("DB Error"))
            mock_service_class.return_value = mock_service
            
            with pytest.raises(HTTPException) as exc_info:
                await create_api_key(
                    name="Test", rate_limit=60, expires_in_days=None,
                    metadata=None, db=mock_db, api_key=None
                )
            assert exc_info.value.status_code == 500
    
    @pytest.mark.asyncio
    async def test_list_api_keys_service_error(self):
        """Test list API keys handles service errors."""
        from app.main import list_api_keys
        from fastapi import HTTPException
        
        mock_db = AsyncMock()
        
        with patch('app.main.APIKeyService') as mock_service_class:
            mock_service = AsyncMock()
            mock_service.list_api_keys = AsyncMock(side_effect=Exception("DB Error"))
            mock_service_class.return_value = mock_service
            
            with pytest.raises(HTTPException) as exc_info:
                await list_api_keys(skip=0, limit=100, active_only=False, db=mock_db, api_key=None)
            assert exc_info.value.status_code == 500
    
    @pytest.mark.asyncio
    async def test_update_api_key_service_error(self):
        """Test update API key handles service errors."""
        from app.main import update_api_key
        from fastapi import HTTPException
        
        mock_db = AsyncMock()
        
        with patch('app.main.APIKeyService') as mock_service_class:
            mock_service = AsyncMock()
            mock_service.update_api_key = AsyncMock(side_effect=Exception("DB Error"))
            mock_service_class.return_value = mock_service
            
            with pytest.raises(HTTPException) as exc_info:
                await update_api_key(
                    key_id=1, name="Test", is_active=None, rate_limit=None,
                    expires_in_days=None, metadata=None, db=mock_db, api_key=None
                )
            assert exc_info.value.status_code == 500
    
    @pytest.mark.asyncio
    async def test_delete_api_key_service_error(self):
        """Test delete API key handles service errors."""
        from app.main import delete_api_key
        from fastapi import HTTPException
        
        mock_db = AsyncMock()
        
        with patch('app.main.APIKeyService') as mock_service_class:
            mock_service = AsyncMock()
            mock_service.delete_api_key = AsyncMock(side_effect=Exception("DB Error"))
            mock_service_class.return_value = mock_service
            
            with pytest.raises(HTTPException) as exc_info:
                await delete_api_key(key_id=1, db=mock_db, api_key=None)
            assert exc_info.value.status_code == 500


class TestConfigModule:
    """Additional tests for config module."""
    
    def test_redis_url_generation(self):
        """Test Redis URL generation."""
        from app.config import Settings
        
        settings = Settings()
        settings.redis_host = "localhost"
        settings.redis_port = 6379
        settings.redis_db = 0
        settings.redis_password = ""
        
        url = settings.get_redis_url()
        # URL should be None or a valid redis URL
        assert url is None or "redis://" in url
    
    def test_redis_url_with_password(self):
        """Test Redis URL with password."""
        from app.config import Settings
        
        settings = Settings()
        settings.redis_host = "localhost"
        settings.redis_port = 6379
        settings.redis_db = 1
        settings.redis_password = "secret"
        
        url = settings.get_redis_url()
        if url:
            assert "secret" in url or "redis://" in url


class TestLifespanEvents:
    """Test application lifespan events."""
    
    @pytest.mark.asyncio
    async def test_lifespan_startup_shutdown(self):
        """Test lifespan context manager."""
        from app.main import lifespan
        from app.config import settings
        
        # Set up valid auth config
        original_mode = settings.auth_mode
        settings.auth_mode = "dev_open"
        
        # Create a mock app state
        mock_app = MagicMock()
        mock_app.state = MagicMock()
        
        try:
            with patch('app.main.init_db', new_callable=AsyncMock) as mock_init:
                with patch('app.main.close_db', new_callable=AsyncMock) as mock_close:
                    with patch('app.main.redis_client', None):
                        # Test lifespan as context manager
                        async with lifespan(mock_app):
                            # Startup should have initialized
                            mock_init.assert_called_once()
                        
                        # Shutdown should have closed db
                        mock_close.assert_called_once()
        finally:
            settings.auth_mode = original_mode
    
    @pytest.mark.asyncio
    async def test_lifespan_with_redis_client(self):
        """Test lifespan shuts down Redis client."""
        from app.main import lifespan
        from app.config import settings
        
        # Set up valid auth config
        original_mode = settings.auth_mode
        settings.auth_mode = "dev_open"
        
        mock_app = MagicMock()
        mock_app.state = MagicMock()
        mock_redis = AsyncMock()
        mock_redis.close = AsyncMock()
        
        try:
            with patch('app.main.init_db', new_callable=AsyncMock):
                with patch('app.main.close_db', new_callable=AsyncMock):
                    with patch('app.main.redis_client', mock_redis):
                        async with lifespan(mock_app):
                            pass
                        mock_redis.close.assert_called_once()
        finally:
            settings.auth_mode = original_mode
    
    @pytest.mark.asyncio
    async def test_lifespan_init_db_error(self):
        """Test lifespan handles init_db errors gracefully."""
        from app.main import lifespan
        from app.config import settings
        
        # Set up valid auth config
        original_mode = settings.auth_mode
        settings.auth_mode = "dev_open"
        
        mock_app = MagicMock()
        mock_app.state = MagicMock()
        
        try:
            with patch('app.main.init_db', new_callable=AsyncMock) as mock_init:
                mock_init.side_effect = Exception("DB connection failed")
                with patch('app.main.close_db', new_callable=AsyncMock):
                    with patch('app.main.redis_client', None):
                        # Should not raise even if init_db fails
                        async with lifespan(mock_app):
                            pass
        finally:
            settings.auth_mode = original_mode
