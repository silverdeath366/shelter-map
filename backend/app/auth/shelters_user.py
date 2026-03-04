"""
Dependency for /v1/shelters: returns a CognitoUser for ownership/display.
When AUTH_MODE=dev_open (or API key), returns a fake user so Phase 1 verification works without JWT.
"""
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from app.auth.cognito import CognitoUser, verify_cognito_token
from app.auth.verify import verify_auth

http_bearer = HTTPBearer(auto_error=False)


async def get_shelters_user(
    auth_context: dict = Depends(verify_auth),
    credentials: HTTPAuthorizationCredentials | None = Depends(http_bearer),
) -> CognitoUser:
    """
    Return current user for shelter routes.
    - dev_open or api_key: return fake user (so /v1/shelters works without JWT in Phase 1).
    - jwt: use payload from verify_auth (simple JWT) or verify Cognito token.
    """
    if auth_context.get("type") == "dev_open":
        return CognitoUser(sub="dev-open", email=None)
    if auth_context.get("type") == "api_key":
        return CognitoUser(sub="api-key", email=None)

    # JWT path: prefer Cognito if Bearer token present, else use payload from verify_auth
    if credentials:
        payload = await verify_cognito_token(credentials.credentials)
        if payload:
            return CognitoUser(
                sub=payload.get("sub") or "unknown",
                email=payload.get("email"),
            )

    payload = auth_context.get("payload") if auth_context.get("type") == "jwt" else None
    if payload:
        return CognitoUser(
            sub=payload.get("sub") or "unknown",
            email=payload.get("email"),
        )

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authorization required. Provide Bearer token for shelter access.",
        headers={"WWW-Authenticate": "Bearer"},
    )
