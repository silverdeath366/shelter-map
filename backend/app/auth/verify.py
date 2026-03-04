"""
STRICT authentication verification (AUTH_MODE).
Used by main app and by shelters to allow dev_open → fake user for Phase 1 verification.
"""
from typing import Optional

import structlog
from fastapi import Header, HTTPException, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import AuthMode, settings
from app.database import get_db

log = structlog.get_logger(__name__)


def _validate_api_key(api_key: str) -> bool:
    """Validate an API key against configured keys."""
    configured_keys = settings.get_api_keys_list()
    return api_key in configured_keys if configured_keys else False


def _validate_jwt(token: str) -> Optional[dict]:
    """
    Validate a JWT token (HS256 / simple JWT).
    Returns decoded payload if valid, None otherwise.
    """
    if not settings.jwt_secret:
        return None
    try:
        import jwt
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            issuer=settings.jwt_issuer if settings.jwt_issuer else None,
            audience=settings.jwt_audience if settings.jwt_audience else None,
            options={
                "verify_iss": bool(settings.jwt_issuer),
                "verify_aud": bool(settings.jwt_audience),
            }
        )
        return payload
    except jwt.ExpiredSignatureError:
        log.warning("jwt_expired", message="JWT token has expired")
        return None
    except jwt.InvalidTokenError as e:
        log.warning("jwt_invalid", error=str(e))
        return None
    except ImportError:
        log.error("jwt_missing", message="PyJWT package not installed", hint="pip install PyJWT")
        return None


def verify_auth(
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    authorization: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db)
) -> dict:
    """
    STRICT authentication verification based on AUTH_MODE.
    Returns auth context: dev_open | api_key | jwt.
    """
    auth_mode = settings.get_auth_mode()

    if auth_mode == AuthMode.DEV_OPEN:
        if settings.is_production():
            log.critical("security_violation", message="dev_open mode attempted in production")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Service misconfigured: dev_open is FORBIDDEN in production"
            )
        log.debug("dev_open", message="Allowing unauthenticated request")
        return {"type": "dev_open", "auth_mode": "dev_open"}

    api_key = x_api_key
    bearer_token = None
    if authorization and authorization.startswith("Bearer "):
        bearer_token = authorization[7:].strip()

    if auth_mode == AuthMode.SERVICE_API_KEY:
        if not api_key:
            log.warning("auth_rejected", reason="missing X-API-Key header")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="STRICT AUTH: API key required. Provide X-API-Key header.",
                headers={"WWW-Authenticate": "ApiKey"}
            )
        if not _validate_api_key(api_key):
            log.warning("auth_rejected", reason="invalid API key")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="STRICT AUTH: Invalid API key",
                headers={"WWW-Authenticate": "ApiKey"}
            )
        return {"type": "api_key", "key": api_key, "auth_mode": "service_api_key"}

    if auth_mode == AuthMode.USER_JWT:
        if not bearer_token:
            log.warning("auth_rejected", reason="missing Authorization Bearer token")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="STRICT AUTH: JWT token required. Provide Authorization: Bearer <token> header.",
                headers={"WWW-Authenticate": "Bearer"}
            )
        payload = _validate_jwt(bearer_token)
        if not payload:
            log.warning("auth_rejected", reason="invalid or expired JWT token")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="STRICT AUTH: Invalid or expired JWT token",
                headers={"WWW-Authenticate": "Bearer"}
            )
        return {"type": "jwt", "payload": payload, "auth_mode": "user_jwt"}

    if auth_mode == AuthMode.COMBINED:
        if api_key and _validate_api_key(api_key):
            return {"type": "api_key", "key": api_key, "auth_mode": "combined"}
        if bearer_token:
            payload = _validate_jwt(bearer_token)
            if payload:
                return {"type": "jwt", "payload": payload, "auth_mode": "combined"}
        log.warning("auth_rejected", reason="no valid API key or JWT provided")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="STRICT AUTH: Provide valid X-API-Key or Authorization: Bearer <jwt>.",
            headers={"WWW-Authenticate": "Bearer, ApiKey"}
        )

    log.error("auth_error", message=f"Unknown auth mode: {auth_mode}")
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Server configuration error: Unknown authentication mode"
    )
