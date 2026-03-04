"""
Middleware for security, rate limiting, logging, and CORS.
Supports Redis-based distributed rate limiting with in-memory fallback.
"""
import asyncio
import time
import uuid
from typing import Callable, Optional

from fastapi import Request, status
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

import structlog

from app.config import settings
from app.services.rate_limiter import rate_limiter

# CityGuard path prefix (not environment-specific)
CITYGUARD_PREFIX = "/v1/cityguard"

log = structlog.get_logger()


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add security headers to all responses."""
    
    async def dispatch(self, request: Request, call_next: Callable):
        response = await call_next(request)
        
        # Security headers
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["Content-Security-Policy"] = "default-src 'self'"
        
        return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Rate limiting middleware with Redis support and in-memory fallback."""
    
    def __init__(self, app, rate_limiter_instance):
        super().__init__(app)
        self.rate_limiter = rate_limiter_instance
    
    async def dispatch(self, request: Request, call_next: Callable):
        # Skip rate limiting for health checks and metrics
        if request.url.path in ["/healthz", "/health/live", "/health/ready", "/metrics", "/docs", "/openapi.json", "/redoc"]:
            return await call_next(request)
        
        # Get identifier (IP address or API key)
        identifier = self._get_identifier(request)
        
        # Check rate limit
        is_allowed, remaining = await self.rate_limiter.check_rate_limit(identifier)
        
        if not is_allowed:
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={
                    "error": "Rate limit exceeded",
                    "message": f"Rate limit of {self.rate_limiter.requests_per_minute} requests per minute exceeded"
                },
                headers={
                    "X-RateLimit-Limit": str(self.rate_limiter.requests_per_minute),
                    "X-RateLimit-Remaining": "0",
                    "Retry-After": "60"
                }
            )
        
        # Add rate limit headers
        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(self.rate_limiter.requests_per_minute)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        
        return response
    
    def _get_identifier(self, request: Request) -> str:
        """Get identifier for rate limiting (IP address or API key)."""
        # Try to get API key from header
        api_key = request.headers.get("X-API-Key") or request.headers.get("Authorization")
        if api_key:
            api_key = api_key.replace("Bearer ", "").strip()
            if api_key:
                return "apikey:" + api_key  # nosemgrep: python.flask.security.audit.directly-returned-format-string
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            ip = forwarded_for.split(",")[0].strip()
        else:
            ip = request.client.host if request.client else "unknown"
        safe = "".join(c for c in ip if c in "0123456789.:abcdefABCDEF[]") or "unknown"
        return "ip:" + safe  # nosemgrep: python.flask.security.audit.directly-returned-format-string


class CityGuardSafetyMiddleware(BaseHTTPMiddleware):
    """
    Production safety limits for CityGuard endpoints only.
    Timeouts and limits come from config (env: CITYGUARD_REQUEST_TIMEOUT_S,
    CITYGUARD_MAX_BODY_BYTES).
    """

    async def dispatch(self, request: Request, call_next: Callable):
        if not request.url.path.startswith(CITYGUARD_PREFIX):
            return await call_next(request)

        max_body = settings.cityguard_max_body_bytes
        timeout_s = settings.cityguard_request_timeout_s

        # Enforce max body size when Content-Length is present
        content_length = request.headers.get("content-length")
        if content_length is not None:
            try:
                if int(content_length) > max_body:
                    return JSONResponse(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        content={
                            "error": "Request entity too large",
                            "message": f"Request body must not exceed {max_body} bytes",
                        },
                    )
            except ValueError:
                pass

        # Enforce request timeout
        try:
            return await asyncio.wait_for(
                call_next(request),
                timeout=timeout_s,
            )
        except asyncio.TimeoutError:
            return JSONResponse(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                content={
                    "error": "Gateway timeout",
                    "message": f"Request did not complete within {timeout_s}s",
                },
            )


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Log all requests as JSON with timestamp, level, method, path, status, duration_ms, request_id."""

    async def dispatch(self, request: Request, call_next: Callable):
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id
        start_time = time.perf_counter()

        try:
            response = await call_next(request)
            duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
            log.info(
                "request",
                method=request.method,
                path=request.url.path,
                status=response.status_code,
                duration_ms=duration_ms,
                request_id=request_id,
            )
            response.headers["X-Request-ID"] = request_id
            response.headers["X-Process-Time"] = str((time.perf_counter() - start_time))
            return response

        except Exception:
            duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
            log.error(
                "request",
                method=request.method,
                path=request.url.path,
                status=500,
                duration_ms=duration_ms,
                request_id=request_id,
                exc_info=True,
            )
            raise


def setup_cors(app):
    """
    Setup CORS middleware with configurable origins.
    
    Configuration via environment variables:
    - CORS_ALLOWED_ORIGINS: Comma-separated list of allowed origins, or "*" for all
    - CORS_ALLOW_CREDENTIALS: Whether to allow credentials (default: true)
    - CORS_ALLOW_METHODS: Comma-separated list of allowed methods
    - CORS_ALLOW_HEADERS: Comma-separated list of allowed headers
    
    Production example:
        CORS_ALLOWED_ORIGINS=https://your-frontend.example.com

    Development example (not recommended for production):
        CORS_ALLOWED_ORIGINS=*
    """
    origins = settings.get_cors_allowed_origins()
    
    # Log CORS configuration at startup
    if origins == ["*"]:
        log.warning(
            "CORS configured to allow all origins",
            message="This is NOT recommended for production. Set CORS_ALLOWED_ORIGINS to your frontend domain.",
        )
    else:
        log.info("CORS configured", allowed_origins=origins)
    
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=settings.cors_allow_credentials,
        allow_methods=settings.get_cors_allow_methods(),
        allow_headers=settings.get_cors_allow_headers(),
    )

