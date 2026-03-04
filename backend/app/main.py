"""
Main FastAPI application for GeoJSON Ingestion Service.
"""
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional

from fastapi import Body, Depends, FastAPI, Header, HTTPException, Query, status
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

import structlog

from app.config import AuthMode, settings
from app.database import close_db, get_db, init_db
from app.logging_config import setup_logging

# Configure JSON structured logging (stdout, LOG_LEVEL env, stack trace on errors)
setup_logging(settings.log_level)

log = structlog.get_logger(__name__)
from app.services.feature_service import FeatureService, OwnershipError, OwnershipInfo, resolve_feature_photo_urls
from app.services.api_key_service import APIKeyService
from app.services.rate_limiter import RateLimiter, rate_limiter
from app.middleware import (
    SecurityHeadersMiddleware,
    RateLimitMiddleware,
    RequestLoggingMiddleware,
    CityGuardSafetyMiddleware,
    setup_cors
)
from app.auth.cognito import get_current_user, get_current_user_optional, CognitoUser
from app.auth.verify import verify_auth
from app.services.s3_upload_service import get_s3_upload_service, S3UploadError
from app.routers import cityguard, health, shelters

# Initialize Redis client if enabled
redis_client = None
if settings.redis_enabled and settings.redis_host:
    try:
        import redis.asyncio as redis
        redis_client = redis.from_url(
            settings.get_redis_url() or f"redis://{settings.redis_host}:{settings.redis_port}/{settings.redis_db}",
            decode_responses=True
        )
        log.info("Redis client initialized for distributed rate limiting")
    except ImportError:
        log.warning("Redis package not installed", hint="pip install redis")
        redis_client = None
    except Exception as e:
        log.warning("Failed to initialize Redis client, using in-memory fallback", error=str(e))
        redis_client = None
else:
    log.info("Using in-memory rate limiting", redis_enabled=False)

# Initialize rate limiter at module level so it can be used by middleware
# (middleware must be added before app starts, not during lifespan)
rate_limiter_instance = RateLimiter(
    redis_client=redis_client,
    requests_per_minute=settings.rate_limit
)


def _log_auth_mode_startup():
    """
    Log authentication mode configuration at startup.
    
    STRICT AUTH MODE:
    - Validates configuration before allowing startup
    - Fails fast if security requirements are not met
    - Logs clear warnings for dev_open mode
    """
    auth_mode = settings.get_auth_mode()
    env = settings.env
    is_production = settings.is_production()
    
    log.info(
        "auth_startup_validation",
        env=env.upper(),
        auth_mode=auth_mode.value,
        description=settings.get_auth_mode_description(),
    )

    # STRICT: Validate configuration - fail fast on security issues
    is_valid, error_msg = settings.validate_auth_config()
    if not is_valid:
        log.error("auth_startup_blocked", error=error_msg)
        raise RuntimeError(f"STRICT AUTH: {error_msg}")

    # CRITICAL WARNING for dev_open mode
    if auth_mode == AuthMode.DEV_OPEN:
        log.warning(
            "auth_mode_dev_open",
            message="ALL REQUESTS ALLOWED WITHOUT AUTHENTICATION - development only",
            env=env,
            hint="For production use AUTH_MODE=service_api_key or combined",
        )

    # Log strict enforcement details
    api_keys_count = len(settings.get_api_keys_list()) if auth_mode in (AuthMode.SERVICE_API_KEY, AuthMode.COMBINED) else 0
    log.info(
        "auth_enforcement",
        auth_mode=auth_mode.value,
        api_keys_configured=api_keys_count,
        cognito_configured=settings.is_cognito_configured(),
    )
    log.info("auth_validation_success")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    # Startup
    log.info("Starting GeoJSON Ingestion Service")
    
    # Log and validate authentication mode
    _log_auth_mode_startup()
    
    # Store rate limiter in app state for access by middleware and routes
    app.state.rate_limiter = rate_limiter_instance
    
    # Initialize database
    try:
        await init_db()
        log.info("Database initialized successfully")
    except Exception as e:
        log.error("Database initialization failed", error=str(e), exc_info=True)
        # Don't fail startup, but log the error
    
    yield

    # Shutdown
    log.info("Shutting down GeoJSON Ingestion Service")
    await close_db()
    if redis_client:
        await redis_client.close()


# Create FastAPI app
app = FastAPI(
    title="GeoJSON Ingestion Service",
    description="Production-ready REST API for ingesting, validating, and querying GeoJSON geographic data",
    version="1.0.0",
    lifespan=lifespan
)

# Add middleware (order matters - last added is first executed)
app.add_middleware(GZipMiddleware, minimum_size=1000)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(RateLimitMiddleware, rate_limiter_instance=rate_limiter_instance)
app.add_middleware(CityGuardSafetyMiddleware)
setup_cors(app)


# Health (no auth)
app.include_router(health.router, prefix="/health")

# CityGuard API (GPS pings) – separate from GeoJSON endpoints
app.include_router(
    cityguard.router,
    prefix="/v1/cityguard",
    tags=["cityguard"],
    dependencies=[Depends(verify_auth)],
)
# CityGuard dashboard routes (zones, violations, active) – same API under /cityguard for ingress
app.include_router(
    cityguard.router,
    prefix="/cityguard",
    tags=["cityguard"],
    dependencies=[Depends(verify_auth)],
)
app.include_router(
    shelters.router,
    prefix="/v1/shelters",
    dependencies=[Depends(verify_auth)],
)


# Backward compatibility alias
def verify_api_key(
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    authorization: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db)
) -> Optional[str]:
    """
    Backward compatible API key verification.
    Wraps verify_auth and returns just the API key string for compatibility.
    """
    auth_context = verify_auth(x_api_key, authorization, db)
    if auth_context.get("type") == "api_key":
        return auth_context.get("key")
    return None


# Root – avoid 404 when opening API base URL in browser
@app.get("/")
async def root():
    """Root redirect info. Use API base URL without path in frontend (e.g. http://localhost:8005)."""
    return {
        "service": "geojson-ingestion",
        "docs": "/docs",
        "shelters_bbox": "/v1/shelters/bbox",
        "shelters_nearby": "/v1/shelters/nearby",
    }


# Health check endpoint
@app.get("/healthz")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "geojson-ingestion"}


# Metrics endpoint
@app.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint."""
    from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
    from fastapi.responses import Response
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


# User identity endpoint (Cognito JWT protected)
@app.get("/v1/me")
async def get_me(user: CognitoUser = Depends(get_current_user)):
    """
    Get current user identity from Cognito JWT token.
    
    This endpoint requires a valid Cognito JWT token in the Authorization header.
    Returns the user's Cognito subject (sub) and email claims.
    
    Example:
        curl -H "Authorization: Bearer <cognito_jwt_token>" http://localhost:8091/v1/me
    """
    return {
        "sub": user.sub,
        "email": user.email
    }


# S3 Upload Presign endpoint (Phase 2: no auth; Phase 3 can add JWT via middleware)
@app.post("/v1/uploads/presign")
async def create_presigned_upload(
    content_type: str = Body(..., description="MIME type (image/jpeg, image/png, image/webp)"),
    file_size: int = Body(..., description="File size in bytes"),
    filename: Optional[str] = Body(None, description="Original filename (optional)"),
):
    """
    Generate a presigned URL for uploading an image to S3.
    
    Phase 2: No authentication. Object key format: reports/anonymous/{uuid}.{ext}
    Phase 3: Auth middleware can be added; key can switch to user-specific prefix.
    
    Request body:
    - **content_type**: MIME type (image/jpeg, image/png, image/webp)
    - **file_size**: Expected file size in bytes (max per S3_UPLOAD_MAX_SIZE_MB)
    - **filename**: Optional original filename for metadata
    
    Validation: allowed types and max size (enforced at confirm step as well).
    Presign TTL: 5-10 minutes (configurable via S3_PRESIGN_EXPIRY_SECONDS).
    
    Returns:
    - **uploadUrl**: Presigned PUT URL for direct S3 upload
    - **objectKey**: S3 object key (reports/anonymous/{uuid}.{ext})
    - **getUrl**: Presigned GET URL for retrieval
    - **expiresIn**: URL expiry in seconds
    - **publicReadStrategy**: "presigned"
    
    Example:
        curl -X POST -H "Content-Type: application/json" \\
             -d '{"content_type": "image/jpeg", "file_size": 102400}' \\
             http://localhost:8091/v1/uploads/presign
    """
    try:
        s3_service = get_s3_upload_service()
        if not s3_service.is_configured:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Image upload service not configured",
            )
        result = await s3_service.create_presigned_upload_anonymous(
            content_type=content_type,
            file_size=file_size,
            filename=filename,
        )
        return {
            "uploadUrl": result.upload_url,
            "objectKey": result.photo_key,
            "getUrl": result.get_url,
            "expiresIn": result.expires_in,
            "publicReadStrategy": "presigned",
        }
    except HTTPException:
        raise
    except S3UploadError as e:
        log.warning("s3_validation_error", error=str(e))
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        log.error("presign_error", error=str(e), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate upload URL",
        )


# S3 Upload Confirm endpoint (Phase 2: persist metadata after client uploads to S3)
@app.post("/v1/uploads/confirm", status_code=status.HTTP_201_CREATED)
async def confirm_upload(
    s3_key: str = Body(..., description="S3 object key returned from presign"),
    content_type: str = Body(..., description="MIME type of the uploaded file"),
    size_bytes: int = Body(..., description="Actual file size in bytes"),
    db: AsyncSession = Depends(get_db),
):
    """
    Confirm an upload and persist metadata to report_images.
    
    Validates: key prefix reports/anonymous/, content_type allowed, size <= max.
    No auth in Phase 2; auth middleware can be added in Phase 3.
    """
    prefix = getattr(settings, "s3_upload_anonymous_prefix", "reports/anonymous")
    if not s3_key.startswith(prefix + "/"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid s3_key: must start with {prefix}/",
        )
    allowed = settings.get_s3_allowed_content_types()
    if content_type not in allowed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid content_type. Allowed: {', '.join(allowed)}",
        )
    max_bytes = settings.get_s3_max_size_bytes()
    if size_bytes <= 0 or size_bytes > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"size_bytes must be 1..{max_bytes} (max {settings.s3_upload_max_size_mb}MB)",
        )
    try:
        from sqlalchemy import text
        await db.execute(
            text("""
                INSERT INTO report_images (s3_key, content_type, size_bytes)
                VALUES (:s3_key, :content_type, :size_bytes)
                ON CONFLICT (s3_key) DO UPDATE SET
                    content_type = EXCLUDED.content_type,
                    size_bytes = EXCLUDED.size_bytes
            """),
            {"s3_key": s3_key, "content_type": content_type, "size_bytes": size_bytes},
        )
        # get_db commits on successful exit
        return {"ok": True, "s3_key": s3_key}
    except Exception as e:
        log.error("confirm_upload_error", error=str(e), exc_info=True)
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to confirm upload",
        )


# GeoJSON Feature endpoints
@app.post("/v1/ingest", status_code=status.HTTP_201_CREATED)
async def ingest_geojson(
    feature: Dict[str, Any] = Body(...),
    name: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    auth_context: dict = Depends(verify_auth),  # STRICT: auth always required
    current_user: CognitoUser = Depends(get_current_user),  # JWT REQUIRED - only users can create
):
    """
    Ingest a GeoJSON Feature. Requires JWT (user authentication).
    
    - **feature**: GeoJSON Feature object
    - **name**: Optional name for the feature
    
    Ownership: Feature is owned by the authenticated user (owner_sub = user.sub).
    """
    try:
        # Validate GeoJSON structure
        if feature.get("type") != "Feature":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Expected GeoJSON Feature object"
            )
        
        feature_service = FeatureService(db)
        owner_sub = current_user.sub
        created_feature, edit_token = await feature_service.create_feature(
            feature, name, owner_sub, generate_edit_token=False
        )
        
        # Build response (resolve S3 keys to presigned URLs)
        response = {
            "id": created_feature.id,
            "message": "Feature ingested successfully",
            "feature": resolve_feature_photo_urls(created_feature.to_geojson()),
            "isLegacyOwner": owner_sub is None
        }
        
        response["ownerSub"] = owner_sub
        return response
    except HTTPException:
        raise
    except Exception as e:
        log.error("ingest_feature_error", error=str(e), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to ingest feature: {str(e)}"
        )


@app.get("/v1/files")
async def list_features(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    geometry_type: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    auth_context: dict = Depends(verify_auth),  # STRICT: auth always required
    current_user: CognitoUser = Depends(get_current_user),  # JWT REQUIRED - only users can list
):
    """
    List all features with pagination. Requires JWT (user authentication).
    
    - **skip**: Number of records to skip
    - **limit**: Maximum number of records to return
    - **geometry_type**: Optional filter by geometry type (Point, Polygon, LineString, etc.)
    
    Response includes ownership info for each feature.
    """
    try:
        feature_service = FeatureService(db)
        features, total = await feature_service.list_features(skip, limit, geometry_type)
        
        current_user_sub = current_user.sub
        
        # Build response with ownership info (resolve S3 keys to presigned URLs)
        feature_list = []
        for f in features:
            feature_json = resolve_feature_photo_urls(f.to_geojson())
            ownership_info = feature_service.get_ownership_info(f, current_user_sub)
            feature_json["ownership"] = ownership_info.to_dict(include_owner_sub=ownership_info.is_owner)
            feature_list.append(feature_json)
        
        return {
            "features": feature_list,
            "total": total,
            "skip": skip,
            "limit": limit
        }
    except Exception as e:
        log.error("list_features_error", error=str(e), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list features: {str(e)}"
        )


# NOTE: Specific routes (/bbox, /nearby) MUST be defined before parameterized routes (/{feature_id})
# to avoid FastAPI treating "bbox" or "nearby" as a feature_id parameter

@app.get("/v1/features/bbox")
async def query_by_bbox(
    min_lon: float = Query(..., description="Minimum longitude"),
    min_lat: float = Query(..., description="Minimum latitude"),
    max_lon: float = Query(..., description="Maximum longitude"),
    max_lat: float = Query(..., description="Maximum latitude"),
    db: AsyncSession = Depends(get_db),
    auth_context: dict = Depends(verify_auth),  # STRICT: auth always required
    current_user: CognitoUser = Depends(get_current_user),  # JWT REQUIRED - only users can query
):
    """Query features within a bounding box. Requires JWT (user authentication)."""
    try:
        feature_service = FeatureService(db)
        features = await feature_service.query_by_bbox(min_lon, min_lat, max_lon, max_lat)
        
        current_user_sub = current_user.sub
        
        # Build response with ownership info (resolve S3 keys to presigned URLs)
        feature_list = []
        for f in features:
            feature_json = resolve_feature_photo_urls(f.to_geojson())
            ownership_info = feature_service.get_ownership_info(f, current_user_sub)
            feature_json["ownership"] = ownership_info.to_dict(include_owner_sub=ownership_info.is_owner)
            feature_list.append(feature_json)
        
        return {
            "type": "FeatureCollection",
            "features": feature_list,
            "count": len(features)
        }
    except Exception as e:
        log.error("query_bbox_error", error=str(e), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to query features: {str(e)}"
        )


@app.get("/v1/features/nearby")
async def query_by_proximity(
    lon: float = Query(..., description="Longitude"),
    lat: float = Query(..., description="Latitude"),
    radius: float = Query(1000, description="Radius in meters", ge=1),
    limit: int = Query(100, description="Maximum results", ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
    auth_context: dict = Depends(verify_auth),  # STRICT: auth always required
    current_user: CognitoUser = Depends(get_current_user),  # JWT REQUIRED - only users can query
):
    """Query features near a point. Requires JWT (user authentication)."""
    try:
        feature_service = FeatureService(db)
        features = await feature_service.query_by_proximity(lon, lat, radius, limit)
        
        current_user_sub = current_user.sub
        
        # Build response with ownership info (resolve S3 keys to presigned URLs)
        feature_list = []
        for f in features:
            feature_json = resolve_feature_photo_urls(f.to_geojson())
            ownership_info = feature_service.get_ownership_info(f, current_user_sub)
            feature_json["ownership"] = ownership_info.to_dict(include_owner_sub=ownership_info.is_owner)
            feature_list.append(feature_json)
        
        return {
            "type": "FeatureCollection",
            "features": feature_list,
            "count": len(features)
        }
    except Exception as e:
        log.error("query_proximity_error", error=str(e), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to query features: {str(e)}"
        )


@app.get("/v1/features/{feature_id}")
async def get_feature(
    feature_id: int,
    db: AsyncSession = Depends(get_db),
    auth_context: dict = Depends(verify_auth),  # STRICT: auth always required
    current_user: CognitoUser = Depends(get_current_user),  # JWT REQUIRED - only users can get
):
    """
    Get a feature by ID. Requires JWT (user authentication).
    Response includes ownership info.
    """
    try:
        feature_service = FeatureService(db)
        feature = await feature_service.get_feature(feature_id)
        
        if not feature:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Feature {feature_id} not found"
            )
        
        current_user_sub = current_user.sub
        ownership_info = feature_service.get_ownership_info(feature, current_user_sub)
        
        # Build response with ownership info (resolve S3 keys to presigned URLs)
        response = resolve_feature_photo_urls(feature.to_geojson())
        response["ownership"] = ownership_info.to_dict(include_owner_sub=ownership_info.is_owner)
        
        return response
    except HTTPException:
        raise
    except Exception as e:
        log.error("get_feature_error", error=str(e), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get feature: {str(e)}"
        )


@app.put("/v1/features/{feature_id}")
async def update_feature(
    feature_id: int,
    feature_data: Optional[Dict[str, Any]] = Body(None),
    name: Optional[str] = Body(None),
    properties: Optional[Dict[str, Any]] = Body(None),
    edit_token: Optional[str] = Header(None, alias="X-Edit-Token"),
    db: AsyncSession = Depends(get_db),
    auth_context: dict = Depends(verify_auth),  # STRICT: auth always required
    current_user: CognitoUser = Depends(get_current_user),  # JWT REQUIRED - only users can update
):
    """
    Update an existing feature. Requires JWT (user authentication).
    
    - **feature_id**: ID of feature to update
    - **feature_data**: Optional complete GeoJSON Feature object
    - **name**: Optional name to update
    - **properties**: Optional properties to update
    - **X-Edit-Token**: Required header for legacy features (those without owner_sub)
    
    Authorization: JWT with matching sub, or X-Edit-Token for legacy features.
    """
    try:
        feature_service = FeatureService(db)
        
        # First, get the feature to check ownership
        feature = await feature_service.get_feature(feature_id)
        if not feature:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Feature {feature_id} not found"
            )
        
        current_user_sub = current_user.sub
        try:
            ownership_info = feature_service.verify_ownership(feature, current_user_sub, edit_token)
        except OwnershipError as e:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=str(e)
            )
        
        # Proceed with update
        updated_feature = await feature_service.update_feature(
            feature_id, feature_data, name, properties
        )
        
        return {
            "id": updated_feature.id,
            "message": "Feature updated successfully",
            "feature": resolve_feature_photo_urls(updated_feature.to_geojson()),
            "ownership": ownership_info.to_dict(include_owner_sub=ownership_info.is_owner)
        }
    except HTTPException:
        raise
    except Exception as e:
        log.error("update_feature_error", error=str(e), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update feature: {str(e)}"
        )


@app.delete("/v1/features/{feature_id}")
async def delete_feature(
    feature_id: int,
    edit_token: Optional[str] = Header(None, alias="X-Edit-Token"),
    db: AsyncSession = Depends(get_db),
    auth_context: dict = Depends(verify_auth),  # STRICT: auth always required
    current_user: CognitoUser = Depends(get_current_user),  # JWT REQUIRED - only users can delete
):
    """
    Delete a feature by ID. Requires JWT (user authentication).
    - **X-Edit-Token**: Required header for legacy features (those without owner_sub).
    Authorization: JWT with matching sub, or X-Edit-Token for legacy features.
    """
    try:
        feature_service = FeatureService(db)
        
        # First, get the feature to check ownership
        feature = await feature_service.get_feature(feature_id)
        if not feature:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Feature {feature_id} not found"
            )
        
        current_user_sub = current_user.sub
        try:
            feature_service.verify_ownership(feature, current_user_sub, edit_token)
        except OwnershipError as e:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=str(e)
            )
        
        # Proceed with delete
        deleted = await feature_service.delete_feature(feature_id)
        
        if not deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Feature {feature_id} not found"
            )
        
        return {"message": f"Feature {feature_id} deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        log.error("delete_feature_error", error=str(e), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete feature: {str(e)}"
        )


@app.get("/v1/export")
async def export_all(
    db: AsyncSession = Depends(get_db),
    auth_context: dict = Depends(verify_auth),  # STRICT: auth always required
    current_user: CognitoUser = Depends(get_current_user),  # JWT REQUIRED - only users can export
):
    """
    Export all features as a GeoJSON FeatureCollection. Requires JWT (user authentication).
    Ownership info is included for each feature.
    """
    try:
        feature_service = FeatureService(db)
        
        # Get all features manually to add ownership info
        from sqlalchemy import select
        from app.models.feature import GeoFeature
        
        result = await db.execute(
            select(GeoFeature).order_by(GeoFeature.created_at.desc())
        )
        features = result.scalars().all()
        
        current_user_sub = current_user.sub
        
        # Build feature collection with ownership info (resolve S3 keys to presigned URLs)
        feature_list = []
        for f in features:
            feature_json = resolve_feature_photo_urls(f.to_geojson())
            ownership_info = feature_service.get_ownership_info(f, current_user_sub)
            feature_json["ownership"] = ownership_info.to_dict(include_owner_sub=ownership_info.is_owner)
            feature_list.append(feature_json)
        
        return {
            "type": "FeatureCollection",
            "features": feature_list
        }
    except Exception as e:
        log.error("export_features_error", error=str(e), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to export features: {str(e)}"
        )


# API Key Management endpoints
@app.post("/v1/api-keys", status_code=status.HTTP_201_CREATED)
async def create_api_key(
    name: Optional[str] = Body(None),
    rate_limit: int = Body(60),
    expires_in_days: Optional[int] = Body(None),
    metadata: Optional[Dict[str, Any]] = Body(None),
    db: AsyncSession = Depends(get_db),
    api_key: Optional[str] = Depends(verify_api_key)
):
    """Create a new API key."""
    try:
        api_key_service = APIKeyService(db)
        plain_key, api_key_obj = await api_key_service.create_api_key(
            name, rate_limit, expires_in_days, metadata
        )
        
        return {
            "id": api_key_obj.id,
            "key": plain_key,  # Only returned once!
            "name": api_key_obj.name,
            "rate_limit": api_key_obj.rate_limit,
            "expires_at": api_key_obj.expires_at.isoformat() if api_key_obj.expires_at else None,
            "created_at": api_key_obj.created_at.isoformat(),
            "warning": "Store this key securely. It will not be shown again."
        }
    except Exception as e:
        log.error("create_api_key_error", error=str(e), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create API key: {str(e)}"
        )


@app.get("/v1/api-keys")
async def list_api_keys(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    active_only: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    api_key: Optional[str] = Depends(verify_api_key)
):
    """List API keys."""
    try:
        api_key_service = APIKeyService(db)
        api_keys, total = await api_key_service.list_api_keys(skip, limit, active_only)
        
        return {
            "api_keys": [
                {
                    "id": ak.id,
                    "name": ak.name,
                    "is_active": ak.is_active,
                    "rate_limit": ak.rate_limit,
                    "expires_at": ak.expires_at.isoformat() if ak.expires_at else None,
                    "last_used_at": ak.last_used_at.isoformat() if ak.last_used_at else None,
                    "usage_count": ak.usage_count,
                    "created_at": ak.created_at.isoformat()
                }
                for ak in api_keys
            ],
            "total": total,
            "skip": skip,
            "limit": limit
        }
    except Exception as e:
        log.error("list_api_keys_error", error=str(e), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list API keys: {str(e)}"
        )


@app.put("/v1/api-keys/{key_id}")
async def update_api_key(
    key_id: int,
    name: Optional[str] = Body(None),
    is_active: Optional[bool] = Body(None),
    rate_limit: Optional[int] = Body(None),
    expires_in_days: Optional[int] = Body(None),
    metadata: Optional[Dict[str, Any]] = Body(None),
    db: AsyncSession = Depends(get_db),
    api_key: Optional[str] = Depends(verify_api_key)
):
    """Update an API key."""
    try:
        api_key_service = APIKeyService(db)
        updated_key = await api_key_service.update_api_key(
            key_id, name, is_active, rate_limit, expires_in_days, metadata
        )
        
        if not updated_key:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"API key {key_id} not found"
            )
        
        return {
            "id": updated_key.id,
            "name": updated_key.name,
            "is_active": updated_key.is_active,
            "rate_limit": updated_key.rate_limit,
            "expires_at": updated_key.expires_at.isoformat() if updated_key.expires_at else None,
            "message": "API key updated successfully"
        }
    except HTTPException:
        raise
    except Exception as e:
        log.error("update_api_key_error", error=str(e), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update API key: {str(e)}"
        )


@app.delete("/v1/api-keys/{key_id}")
async def delete_api_key(
    key_id: int,
    db: AsyncSession = Depends(get_db),
    api_key: Optional[str] = Depends(verify_api_key)
):
    """Delete (deactivate) an API key."""
    try:
        api_key_service = APIKeyService(db)
        deleted = await api_key_service.delete_api_key(key_id)
        
        if not deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"API key {key_id} not found"
            )
        
        return {"message": f"API key {key_id} deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        log.error("delete_api_key_error", error=str(e), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete API key: {str(e)}"
        )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.app_host,
        port=settings.app_port,
        log_level=settings.log_level.lower()
    )

