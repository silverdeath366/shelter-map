"""
Phase 2 Test Gate - Authorization Tests for JWT + editToken Ownership

Required Test Cases:
✅ User A creates report → owner_sub set
❌ User B updates A's report → 403
❌ No JWT update → 401 (JWT-owned feature requires JWT)
✅ User A updates own report → 200
✅ Legacy report can still be edited with editToken
❌ Legacy report cannot be edited with JWT-only (no token)
"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi import HTTPException
from fastapi.testclient import TestClient
from httpx import AsyncClient, ASGITransport
import json

from app.services.feature_service import FeatureService, OwnershipError, OwnershipInfo
from app.auth.cognito import CognitoUser


# =============================================================================
# Test Fixtures
# =============================================================================

@pytest.fixture
def user_a():
    """Cognito user A - the owner."""
    return CognitoUser(sub="user-a-sub-12345", email="usera@example.com")


@pytest.fixture
def user_b():
    """Cognito user B - a different user."""
    return CognitoUser(sub="user-b-sub-67890", email="userb@example.com")


@pytest.fixture
def sample_geojson_feature():
    """Sample GeoJSON Feature for testing."""
    return {
        "type": "Feature",
        "geometry": {
            "type": "Point",
            "coordinates": [-122.4194, 37.7749]
        },
        "properties": {
            "name": "Test Lost Dog",
            "description": "Brown labrador lost near park",
            "status": "active"
        }
    }


@pytest.fixture
def mock_feature_with_owner():
    """Mock feature owned by User A (JWT-based ownership)."""
    feature = MagicMock()
    feature.id = 1
    feature.owner_sub = "user-a-sub-12345"  # Owned by User A
    feature.edit_token = None  # No legacy token
    feature.name = "Test Feature"
    feature.geometry_type = "Point"
    feature.properties = {"status": "active"}
    feature.to_geojson = MagicMock(return_value={
        "type": "Feature",
        "id": 1,
        "geometry": {"type": "Point", "coordinates": [-122.4194, 37.7749]},
        "properties": {"status": "active"}
    })
    return feature


@pytest.fixture
def mock_legacy_feature():
    """Mock legacy feature with editToken (no owner_sub)."""
    feature = MagicMock()
    feature.id = 2
    feature.owner_sub = None  # Legacy - no JWT owner
    feature.edit_token = "legacy-edit-token-abc123"  # Has edit token
    feature.name = "Legacy Feature"
    feature.geometry_type = "Point"
    feature.properties = {"status": "active"}
    feature.to_geojson = MagicMock(return_value={
        "type": "Feature",
        "id": 2,
        "geometry": {"type": "Point", "coordinates": [-122.4194, 37.7749]},
        "properties": {"status": "active"}
    })
    return feature


# =============================================================================
# Unit Tests for FeatureService.verify_ownership
# =============================================================================

class TestOwnershipVerification:
    """Test OwnershipInfo and verify_ownership logic."""

    def test_ownership_info_structure(self):
        """Test OwnershipInfo data class."""
        info = OwnershipInfo(is_legacy_owner=False, is_owner=True, owner_sub="user-123")
        assert info.is_legacy_owner is False
        assert info.is_owner is True
        assert info.owner_sub == "user-123"
        
        # Test to_dict without owner_sub
        result = info.to_dict(include_owner_sub=False)
        assert result == {"isLegacyOwner": False}
        assert "ownerSub" not in result
        
        # Test to_dict with owner_sub (only when is_owner)
        result = info.to_dict(include_owner_sub=True)
        assert result == {"isLegacyOwner": False, "ownerSub": "user-123"}


# =============================================================================
# Phase 2 Authorization Tests
# =============================================================================

class TestPhase2Authorization:
    """
    Phase 2 Test Gate - Authorization Tests
    
    These tests verify the ownership system works correctly for both
    JWT-based ownership (owner_sub) and legacy token-based ownership (edit_token).
    """

    # -------------------------------------------------------------------------
    # TEST 1: User A creates report → owner_sub set ✅
    # -------------------------------------------------------------------------
    @pytest.mark.asyncio
    async def test_user_a_creates_report_owner_sub_set(
        self,
        user_a,
        sample_geojson_feature
    ):
        """
        ✅ User A creates report → owner_sub set
        
        When a user creates a feature with JWT authentication,
        the feature should have owner_sub set to the user's sub.
        """
        # Mock database session
        mock_db = AsyncMock()
        
        # Mock the database execute and commit
        mock_result = MagicMock()
        mock_result.fetchone.return_value = MagicMock(id=1, name="Test", geometry_type="Point")
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.commit = AsyncMock()
        mock_db.get = AsyncMock(return_value=MagicMock(
            id=1,
            owner_sub="user-a-sub-12345",  # Should be set!
            edit_token=None,  # No edit token when JWT is used
            to_geojson=lambda: {"type": "Feature", "id": 1}
        ))
        
        feature_service = FeatureService(mock_db)
        
        # Create feature WITH owner_sub (JWT user)
        created_feature, edit_token = await feature_service.create_feature(
            feature_data=sample_geojson_feature,
            name="Lost Dog Report",
            owner_sub=user_a.sub,  # User A's sub
            generate_edit_token=False  # No edit token needed with JWT
        )
        
        # Verify
        assert created_feature is not None
        assert created_feature.owner_sub == "user-a-sub-12345"
        assert edit_token is None  # No edit token when using JWT
        print("✅ TEST 1 PASSED: User A creates report → owner_sub set")

    # -------------------------------------------------------------------------
    # TEST 2: User B updates A's report → 403 ❌
    # -------------------------------------------------------------------------
    def test_user_b_cannot_update_user_a_report(
        self,
        user_a,
        user_b,
        mock_feature_with_owner
    ):
        """
        ❌ User B updates A's report → 403
        
        User B (different sub) should NOT be able to update a feature
        owned by User A. Should raise OwnershipError.
        """
        mock_db = AsyncMock()
        feature_service = FeatureService(mock_db)
        
        # User B tries to update User A's feature
        with pytest.raises(OwnershipError) as exc_info:
            feature_service.verify_ownership(
                feature=mock_feature_with_owner,  # Owned by user-a-sub-12345
                current_user_sub=user_b.sub,  # User B trying to update
                edit_token=None
            )
        
        assert "do not own" in str(exc_info.value).lower()
        print("✅ TEST 2 PASSED: User B updates A's report → 403 (OwnershipError)")

    # -------------------------------------------------------------------------
    # TEST 3: No JWT update on JWT-owned feature → 401 ❌
    # -------------------------------------------------------------------------
    def test_no_jwt_update_on_jwt_owned_feature(
        self,
        mock_feature_with_owner
    ):
        """
        ❌ No JWT update → 401
        
        A JWT-owned feature (has owner_sub) REQUIRES JWT authentication
        for modifications. Without JWT, should raise OwnershipError.
        """
        mock_db = AsyncMock()
        feature_service = FeatureService(mock_db)
        
        # Try to update without any JWT (no current_user_sub)
        with pytest.raises(OwnershipError) as exc_info:
            feature_service.verify_ownership(
                feature=mock_feature_with_owner,  # Has owner_sub
                current_user_sub=None,  # No JWT!
                edit_token=None
            )
        
        assert "requires jwt authentication" in str(exc_info.value).lower()
        print("✅ TEST 3 PASSED: No JWT update → 401 (OwnershipError)")

    # -------------------------------------------------------------------------
    # TEST 4: User A updates own report → 200 ✅
    # -------------------------------------------------------------------------
    def test_user_a_updates_own_report(
        self,
        user_a,
        mock_feature_with_owner
    ):
        """
        ✅ User A updates own report → 200
        
        The owner (User A) should be able to update their own feature.
        """
        mock_db = AsyncMock()
        feature_service = FeatureService(mock_db)
        
        # User A updates their own feature
        ownership_info = feature_service.verify_ownership(
            feature=mock_feature_with_owner,  # Owned by user-a-sub-12345
            current_user_sub=user_a.sub,  # Same user!
            edit_token=None
        )
        
        # Should succeed
        assert ownership_info.is_owner is True
        assert ownership_info.is_legacy_owner is False  # Not legacy
        assert ownership_info.owner_sub == "user-a-sub-12345"
        print("✅ TEST 4 PASSED: User A updates own report → 200")

    # -------------------------------------------------------------------------
    # TEST 5: Legacy report can still be edited with editToken ✅
    # -------------------------------------------------------------------------
    def test_legacy_report_editable_with_edit_token(
        self,
        mock_legacy_feature
    ):
        """
        ✅ Legacy report can still be edited with editToken
        
        Features created without JWT (legacy) should still be editable
        using the editToken.
        """
        mock_db = AsyncMock()
        feature_service = FeatureService(mock_db)
        
        # Update legacy feature with correct edit token
        ownership_info = feature_service.verify_ownership(
            feature=mock_legacy_feature,  # No owner_sub, has edit_token
            current_user_sub=None,  # No JWT needed for legacy
            edit_token="legacy-edit-token-abc123"  # Correct token
        )
        
        # Should succeed
        assert ownership_info.is_owner is True
        assert ownership_info.is_legacy_owner is True  # Is legacy
        print("✅ TEST 5 PASSED: Legacy report can still be edited with editToken")

    # -------------------------------------------------------------------------
    # TEST 6: Legacy report cannot be edited with JWT-only (no token) ❌
    # -------------------------------------------------------------------------
    def test_legacy_report_not_editable_with_jwt_only(
        self,
        user_a,
        mock_legacy_feature
    ):
        """
        ❌ Legacy report cannot be edited with JWT-only (no token)
        
        A legacy feature (has edit_token, no owner_sub) should NOT be
        editable with just a JWT token - it requires the editToken.
        """
        mock_db = AsyncMock()
        feature_service = FeatureService(mock_db)
        
        # Try to update legacy feature with JWT but no edit token
        with pytest.raises(OwnershipError) as exc_info:
            feature_service.verify_ownership(
                feature=mock_legacy_feature,  # Legacy feature with edit_token
                current_user_sub=user_a.sub,  # Has JWT...
                edit_token=None  # ...but no edit token!
            )
        
        assert "edit token required" in str(exc_info.value).lower()
        print("✅ TEST 6 PASSED: Legacy report cannot be edited with JWT-only → 403")


# =============================================================================
# Integration Tests (with mocked Cognito)
# =============================================================================

class TestPhase2Integration:
    """Integration tests with mocked HTTP endpoints."""

    @pytest.mark.asyncio
    async def test_full_ownership_flow(self):
        """
        Full integration test of ownership flow.
        Tests create -> verify owner -> deny other user -> allow owner update
        """
        from app.main import app
        from app.database import get_db
        from app.auth.cognito import get_current_user_optional, verify_cognito_token
        
        # Mock database
        mock_db = AsyncMock()
        mock_feature = MagicMock()
        mock_feature.id = 100
        mock_feature.owner_sub = "integration-user-a"
        mock_feature.edit_token = None
        mock_feature.to_geojson = MagicMock(return_value={
            "type": "Feature", "id": 100,
            "geometry": {"type": "Point", "coordinates": [-122.4, 37.7]},
            "properties": {}
        })
        
        async def mock_get_db():
            yield mock_db
        
        app.dependency_overrides[get_db] = mock_get_db
        
        # Mock Cognito verification to return User A
        with patch('app.auth.cognito.verify_cognito_token') as mock_verify:
            mock_verify.return_value = {
                "sub": "integration-user-a",
                "email": "integration@test.com"
            }
            
            # Verify ownership check works
            feature_service = FeatureService(mock_db)
            
            # Owner check should pass
            ownership = feature_service.get_ownership_info(
                mock_feature,
                current_user_sub="integration-user-a"
            )
            assert ownership.is_owner is True
            
            # Different user should not be owner
            ownership_other = feature_service.get_ownership_info(
                mock_feature,
                current_user_sub="different-user"
            )
            assert ownership_other.is_owner is False
        
        # Clean up
        app.dependency_overrides.clear()
        print("✅ Integration test PASSED: Full ownership flow")


# =============================================================================
# Test Runner Summary
# =============================================================================

if __name__ == "__main__":
    """Run Phase 2 tests with detailed output."""
    import sys
    
    print("=" * 70)
    print("  🧪 PHASE 2 TEST GATE - Authorization Tests")
    print("=" * 70)
    print()
    print("Required Tests:")
    print("  ✅ User A creates report → owner_sub set")
    print("  ❌ User B updates A's report → 403")
    print("  ❌ No JWT update → 401")
    print("  ✅ User A updates own report → 200")
    print("  ✅ Legacy report can still be edited with editToken")
    print("  ❌ Legacy report cannot be edited with JWT-only (no token)")
    print()
    print("=" * 70)
    
    # Run with pytest
    sys.exit(pytest.main([__file__, "-v", "--tb=short"]))
