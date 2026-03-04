"""
Shelter-specific API: features where properties->>'type' = 'shelter'.
Reuses spatial logic from the features API; does not modify /v1/features.
"""
from typing import Any, Dict, List

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.cognito import CognitoUser
from app.auth.shelters_user import get_shelters_user
from app.database import get_db
from app.services.feature_service import (
    FeatureService,
    resolve_feature_photo_urls,
)

log = structlog.get_logger(__name__)

router = APIRouter(tags=["shelters"])


@router.get("")
async def list_shelters(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
    current_user: CognitoUser = Depends(get_shelters_user),
):
    """
    List shelters (features with properties.type = 'shelter') with pagination.
    Same auth as /v1/features. Response shape matches list features.
    """
    try:
        feature_service = FeatureService(db)
        features, total = await feature_service.list_shelters(skip=skip, limit=limit)
        current_user_sub = current_user.sub
        feature_list = []
        for f in features:
            feature_json = resolve_feature_photo_urls(f.to_geojson())
            ownership_info = feature_service.get_ownership_info(f, current_user_sub)
            feature_json["ownership"] = ownership_info.to_dict(
                include_owner_sub=ownership_info.is_owner
            )
            feature_list.append(feature_json)
        return {
            "features": feature_list,
            "total": total,
            "skip": skip,
            "limit": limit,
        }
    except Exception as e:
        log.error("list_shelters_error", error=str(e), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list shelters: {str(e)}",
        )


@router.get("/bbox")
async def shelters_bbox(
    min_lon: float = Query(..., description="Minimum longitude"),
    min_lat: float = Query(..., description="Minimum latitude"),
    max_lon: float = Query(..., description="Maximum longitude"),
    max_lat: float = Query(..., description="Maximum latitude"),
    db: AsyncSession = Depends(get_db),
    current_user: CognitoUser = Depends(get_shelters_user),
):
    """Query shelters within a bounding box. Same spatial logic as /v1/features/bbox."""
    try:
        feature_service = FeatureService(db)
        features = await feature_service.query_shelters_by_bbox(
            min_lon, min_lat, max_lon, max_lat
        )
        current_user_sub = current_user.sub
        feature_list = []
        for f in features:
            feature_json = resolve_feature_photo_urls(f.to_geojson())
            ownership_info = feature_service.get_ownership_info(f, current_user_sub)
            feature_json["ownership"] = ownership_info.to_dict(
                include_owner_sub=ownership_info.is_owner
            )
            feature_list.append(feature_json)
        return {
            "type": "FeatureCollection",
            "features": feature_list,
            "count": len(features),
        }
    except Exception as e:
        log.error("shelters_bbox_error", error=str(e), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to query shelters: {str(e)}",
        )


@router.get("/nearby")
async def shelters_nearby(
    lon: float = Query(..., description="Longitude"),
    lat: float = Query(..., description="Latitude"),
    radius: float = Query(1000, description="Radius in meters", ge=1),
    limit: int = Query(100, description="Maximum results", ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
    current_user: CognitoUser = Depends(get_shelters_user),
):
    """
    Query shelters near a point. Ordered by distance (ST_Distance).
    Returns each feature with distance_m in the response.
    """
    try:
        feature_service = FeatureService(db)
        pairs = await feature_service.query_shelters_nearby(
            lon=lon, lat=lat, radius_meters=radius, limit=limit
        )
        current_user_sub = current_user.sub
        feature_list: List[Dict[str, Any]] = []
        for f, distance_m in pairs:
            feature_json = resolve_feature_photo_urls(f.to_geojson())
            ownership_info = feature_service.get_ownership_info(f, current_user_sub)
            feature_json["ownership"] = ownership_info.to_dict(
                include_owner_sub=ownership_info.is_owner
            )
            feature_json["distance_m"] = round(distance_m, 2)
            feature_list.append(feature_json)
        return {
            "type": "FeatureCollection",
            "features": feature_list,
            "count": len(feature_list),
        }
    except Exception as e:
        log.error("shelters_nearby_error", error=str(e), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to query shelters: {str(e)}",
        )


@router.get("/{shelter_id}")
async def get_shelter(
    shelter_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: CognitoUser = Depends(get_shelters_user),
):
    """Get a shelter by ID. 404 if not found or not a shelter (properties.type != 'shelter')."""
    try:
        feature_service = FeatureService(db)
        feature = await feature_service.get_shelter(shelter_id)
        if not feature:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Shelter {shelter_id} not found",
            )
        current_user_sub = current_user.sub
        ownership_info = feature_service.get_ownership_info(feature, current_user_sub)
        response = resolve_feature_photo_urls(feature.to_geojson())
        response["ownership"] = ownership_info.to_dict(
            include_owner_sub=ownership_info.is_owner
        )
        return response
    except HTTPException:
        raise
    except Exception as e:
        log.error("get_shelter_error", error=str(e), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get shelter: {str(e)}",
        )
