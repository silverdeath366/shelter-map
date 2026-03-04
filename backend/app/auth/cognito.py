"""
AWS Cognito JWT verification module.

Provides JWT token verification using Cognito JWKS (JSON Web Key Set).
Validates token signature, issuer, audience, and expiration.
"""
import logging
from typing import Optional, Dict, Any
from functools import lru_cache
import time

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
import httpx
from jose import jwt, jwk, JWTError
from jose.utils import base64url_decode

from app.config import settings

logger = logging.getLogger(__name__)

# HTTP Bearer security scheme for OpenAPI docs
http_bearer = HTTPBearer(auto_error=False)


class CognitoUser(BaseModel):
    """User identity extracted from Cognito JWT token."""
    sub: str  # Cognito user unique identifier
    email: Optional[str] = None


class JWKSCache:
    """
    Cache for Cognito JWKS (JSON Web Key Set).
    
    Fetches and caches the public keys used to verify JWT signatures.
    Keys are refreshed after TTL expires.
    """
    
    def __init__(self, ttl_seconds: int = 3600):
        self._keys: Dict[str, Any] = {}
        self._last_fetch: float = 0
        self._ttl = ttl_seconds
    
    def _is_expired(self) -> bool:
        """Check if the cache has expired."""
        return time.time() - self._last_fetch > self._ttl
    
    async def get_key(self, kid: str) -> Optional[Dict[str, Any]]:
        """
        Get a public key by key ID (kid).
        
        Args:
            kid: Key ID from the JWT header
            
        Returns:
            The public key dict, or None if not found
        """
        # Refresh cache if expired or key not found
        if self._is_expired() or kid not in self._keys:
            await self._refresh_keys()
        
        return self._keys.get(kid)
    
    async def _refresh_keys(self) -> None:
        """Fetch and cache JWKS from Cognito."""
        jwks_url = settings.get_cognito_jwks_url()
        
        if not jwks_url:
            logger.error("Cognito JWKS URL not configured")
            return
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(jwks_url, timeout=10.0)
                response.raise_for_status()
                jwks = response.json()
            
            # Index keys by kid for fast lookup
            self._keys = {key["kid"]: key for key in jwks.get("keys", [])}
            self._last_fetch = time.time()
            logger.info(f"Refreshed JWKS cache with {len(self._keys)} keys")
            
        except httpx.HTTPError as e:
            logger.error(f"Failed to fetch JWKS: {e}")
            # Keep existing keys if refresh fails
        except Exception as e:
            logger.error(f"Error processing JWKS: {e}")


# Global JWKS cache instance
_jwks_cache = JWKSCache()


async def verify_cognito_token(token: str) -> Optional[Dict[str, Any]]:
    """
    Verify a Cognito JWT token.
    
    Validates:
    - Token signature using Cognito public keys (JWKS)
    - Token expiration
    - Issuer matches Cognito user pool
    - Audience matches configured client ID
    
    Args:
        token: The JWT token string
        
    Returns:
        Decoded token payload if valid, None otherwise
    """
    if not settings.is_cognito_configured():
        logger.error("Cognito is not configured. Set COGNITO_REGION, COGNITO_USER_POOL_ID, and COGNITO_CLIENT_ID.")
        return None
    
    try:
        # Decode header to get key ID (kid)
        headers = jwt.get_unverified_header(token)
        kid = headers.get("kid")
        
        if not kid:
            logger.warning("JWT token missing 'kid' header")
            return None
        
        # Get the public key for this token
        key = await _jwks_cache.get_key(kid)
        
        if not key:
            logger.warning(f"No matching key found for kid: {kid}")
            return None
        
        # Construct the public key
        public_key = jwk.construct(key)
        
        # Verify and decode the token
        payload = jwt.decode(
            token,
            public_key,
            algorithms=["RS256"],
            issuer=settings.get_cognito_issuer(),
            audience=settings.cognito_client_id,
            options={
                "verify_aud": True,
                "verify_iss": True,
                "verify_exp": True,
            }
        )
        
        return payload
        
    except JWTError as e:
        logger.warning(f"JWT verification failed: {e}")
        return None
    except Exception as e:
        logger.error(f"Error verifying Cognito token: {e}")
        return None


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(http_bearer)
) -> CognitoUser:
    """
    FastAPI dependency to extract and verify the current user from Cognito JWT.
    
    Reads the Authorization header, validates the Bearer token against
    Cognito JWKS, and returns a CognitoUser object with the user's identity.
    
    Usage:
        @app.get("/protected")
        async def protected_route(user: CognitoUser = Depends(get_current_user)):
            return {"sub": user.sub, "email": user.email}
    
    Raises:
        HTTPException: 401 if token is missing, invalid, or expired
    """
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header required. Provide: Authorization: Bearer <token>",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    token = credentials.credentials
    payload = await verify_cognito_token(token)
    
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Extract user identity from token claims
    sub = payload.get("sub")
    email = payload.get("email")
    
    if not sub:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token missing 'sub' claim",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    return CognitoUser(sub=sub, email=email)


async def get_current_user_optional(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(http_bearer)
) -> Optional[CognitoUser]:
    """
    Optional version of get_current_user.
    
    Returns None if no token is provided instead of raising an exception.
    Useful for endpoints that support both authenticated and anonymous access.
    """
    if not credentials:
        return None
    
    token = credentials.credentials
    payload = await verify_cognito_token(token)
    
    if not payload:
        return None
    
    sub = payload.get("sub")
    email = payload.get("email")
    
    if not sub:
        return None
    
    return CognitoUser(sub=sub, email=email)
