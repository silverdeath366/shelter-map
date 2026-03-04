"""
Tests for AWS Cognito JWT authentication module.
"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from app.auth.cognito import (
    CognitoUser,
    JWKSCache,
    verify_cognito_token,
    get_current_user,
    get_current_user_optional,
)


class TestCognitoUser:
    """Tests for CognitoUser model."""
    
    def test_cognito_user_with_email(self):
        """Test CognitoUser with both sub and email."""
        user = CognitoUser(sub="abc123", email="user@example.com")
        assert user.sub == "abc123"
        assert user.email == "user@example.com"
    
    def test_cognito_user_without_email(self):
        """Test CognitoUser with only sub (email optional)."""
        user = CognitoUser(sub="abc123")
        assert user.sub == "abc123"
        assert user.email is None
    
    def test_cognito_user_dict_export(self):
        """Test CognitoUser can be exported to dict."""
        user = CognitoUser(sub="abc123", email="user@example.com")
        user_dict = user.model_dump()
        assert user_dict == {"sub": "abc123", "email": "user@example.com"}


class TestJWKSCache:
    """Tests for JWKS caching functionality."""
    
    def test_cache_initialization(self):
        """Test JWKSCache initializes with empty state."""
        cache = JWKSCache(ttl_seconds=3600)
        assert cache._keys == {}
        assert cache._last_fetch == 0
        assert cache._ttl == 3600
    
    def test_cache_expiration_check(self):
        """Test cache expiration logic."""
        cache = JWKSCache(ttl_seconds=3600)
        # Initially expired (last_fetch = 0)
        assert cache._is_expired() is True
    
    @pytest.mark.asyncio
    async def test_cache_get_key_triggers_refresh(self):
        """Test that getting a key triggers refresh when expired."""
        cache = JWKSCache(ttl_seconds=3600)
        
        with patch.object(cache, '_refresh_keys', new_callable=AsyncMock) as mock_refresh:
            await cache.get_key("test-kid")
            mock_refresh.assert_called_once()


class TestVerifyCognitoToken:
    """Tests for token verification function."""
    
    @pytest.mark.asyncio
    async def test_verify_token_not_configured(self):
        """Test verification fails when Cognito not configured."""
        with patch('app.auth.cognito.settings') as mock_settings:
            mock_settings.is_cognito_configured.return_value = False
            
            result = await verify_cognito_token("some.jwt.token")
            assert result is None
    
    @pytest.mark.asyncio
    async def test_verify_token_missing_kid(self):
        """Test verification fails when token missing kid header."""
        with patch('app.auth.cognito.settings') as mock_settings, \
             patch('app.auth.cognito.jwt') as mock_jwt:
            mock_settings.is_cognito_configured.return_value = True
            mock_jwt.get_unverified_header.return_value = {}  # No 'kid'
            
            result = await verify_cognito_token("some.jwt.token")
            assert result is None
    
    @pytest.mark.asyncio
    async def test_verify_token_key_not_found(self):
        """Test verification fails when key not in JWKS."""
        with patch('app.auth.cognito.settings') as mock_settings, \
             patch('app.auth.cognito.jwt') as mock_jwt, \
             patch('app.auth.cognito._jwks_cache') as mock_cache:
            mock_settings.is_cognito_configured.return_value = True
            mock_jwt.get_unverified_header.return_value = {"kid": "unknown-kid"}
            mock_cache.get_key = AsyncMock(return_value=None)
            
            result = await verify_cognito_token("some.jwt.token")
            assert result is None


class TestGetCurrentUser:
    """Tests for get_current_user dependency."""
    
    @pytest.mark.asyncio
    async def test_get_current_user_no_credentials(self):
        """Test raises 401 when no credentials provided."""
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(credentials=None)
        
        assert exc_info.value.status_code == 401
        assert "Authorization header required" in exc_info.value.detail
    
    @pytest.mark.asyncio
    async def test_get_current_user_invalid_token(self):
        """Test raises 401 when token is invalid."""
        credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="invalid.token")
        
        with patch('app.auth.cognito.verify_cognito_token', new_callable=AsyncMock) as mock_verify:
            mock_verify.return_value = None
            
            with pytest.raises(HTTPException) as exc_info:
                await get_current_user(credentials=credentials)
            
            assert exc_info.value.status_code == 401
            assert "Invalid or expired token" in exc_info.value.detail
    
    @pytest.mark.asyncio
    async def test_get_current_user_valid_token(self):
        """Test returns CognitoUser when token is valid."""
        credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="valid.jwt.token")
        
        with patch('app.auth.cognito.verify_cognito_token', new_callable=AsyncMock) as mock_verify:
            mock_verify.return_value = {
                "sub": "user-123",
                "email": "test@example.com"
            }
            
            user = await get_current_user(credentials=credentials)
            
            assert isinstance(user, CognitoUser)
            assert user.sub == "user-123"
            assert user.email == "test@example.com"
    
    @pytest.mark.asyncio
    async def test_get_current_user_missing_sub(self):
        """Test raises 401 when token missing sub claim."""
        credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="valid.jwt.token")
        
        with patch('app.auth.cognito.verify_cognito_token', new_callable=AsyncMock) as mock_verify:
            mock_verify.return_value = {"email": "test@example.com"}  # No 'sub'
            
            with pytest.raises(HTTPException) as exc_info:
                await get_current_user(credentials=credentials)
            
            assert exc_info.value.status_code == 401
            assert "missing 'sub' claim" in exc_info.value.detail


class TestGetCurrentUserOptional:
    """Tests for optional user dependency."""
    
    @pytest.mark.asyncio
    async def test_optional_no_credentials(self):
        """Test returns None when no credentials provided."""
        user = await get_current_user_optional(credentials=None)
        assert user is None
    
    @pytest.mark.asyncio
    async def test_optional_invalid_token(self):
        """Test returns None when token is invalid."""
        credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="invalid.token")
        
        with patch('app.auth.cognito.verify_cognito_token', new_callable=AsyncMock) as mock_verify:
            mock_verify.return_value = None
            
            user = await get_current_user_optional(credentials=credentials)
            assert user is None
    
    @pytest.mark.asyncio
    async def test_optional_valid_token(self):
        """Test returns CognitoUser when token is valid."""
        credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials="valid.jwt.token")
        
        with patch('app.auth.cognito.verify_cognito_token', new_callable=AsyncMock) as mock_verify:
            mock_verify.return_value = {
                "sub": "user-456",
                "email": "optional@example.com"
            }
            
            user = await get_current_user_optional(credentials=credentials)
            
            assert isinstance(user, CognitoUser)
            assert user.sub == "user-456"
            assert user.email == "optional@example.com"
