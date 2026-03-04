"""
Service layer for GeoJSON feature operations.
Handles CRUD operations and spatial queries.
"""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from sqlalchemy.sql import text
from typing import List, Optional, Dict, Any, Tuple
from app.models.feature import GeoFeature
import geojson
import json
import logging
import secrets

logger = logging.getLogger(__name__)


def is_s3_photo_key(url: Optional[str]) -> bool:
    """Check if a URL is an S3 photo key (not a full URL or base64)."""
    if not url:
        return False
    # S3 keys: find-my-dog/ (authenticated) or reports/anonymous/ (Phase 2 anonymous)
    return (
        (url.startswith("find-my-dog/") or url.startswith("reports/anonymous/"))
        and not url.startswith("http://")
        and not url.startswith("https://")
        and not url.startswith("data:")
    )


def resolve_s3_photo_url(photo_url: Optional[str]) -> Optional[str]:
    """
    Resolve an S3 photo key to a presigned GET URL.
    
    If the photo_url is an S3 key (e.g., "find-my-dog/user123/abc.jpg"),
    generate a presigned GET URL. Otherwise, return the URL as-is
    (for base64 data URLs or legacy HTTP URLs).
    """
    if not photo_url:
        return photo_url
    
    if not is_s3_photo_key(photo_url):
        # Already a full URL (base64 or http), return as-is
        return photo_url
    
    try:
        # Import here to avoid circular dependency
        from app.services.s3_upload_service import get_s3_upload_service, S3UploadError
        
        s3_service = get_s3_upload_service()
        if not s3_service.is_configured:
            logger.warning(f"S3 not configured, cannot resolve key: {photo_url[:50]}...")
            return photo_url
        
        # Generate presigned GET URL (24-hour expiry for display)
        presigned_url = s3_service.get_presigned_get_url(photo_url)
        return presigned_url
    except Exception as e:
        logger.error(f"Failed to resolve S3 key to URL: {e}")
        # Return the original key if resolution fails
        return photo_url


def resolve_feature_photo_urls(feature_json: Dict[str, Any]) -> Dict[str, Any]:
    """
    Resolve S3 photo keys in feature properties to presigned URLs.
    
    This should be called after to_geojson() to ensure photo URLs
    are accessible to clients.
    """
    properties = feature_json.get("properties", {})
    
    if "photoUrl" in properties:
        properties["photoUrl"] = resolve_s3_photo_url(properties.get("photoUrl"))
    
    return feature_json


class OwnershipError(Exception):
    """Raised when an ownership check fails."""
    pass


class OwnershipInfo:
    """Ownership information for a feature."""
    
    def __init__(
        self,
        is_legacy_owner: bool,
        is_owner: bool,
        owner_sub: Optional[str] = None
    ):
        self.is_legacy_owner = is_legacy_owner
        self.is_owner = is_owner
        self.owner_sub = owner_sub
    
    def to_dict(self, include_owner_sub: bool = False) -> Dict[str, Any]:
        """Convert to dictionary for API response."""
        result = {"isLegacyOwner": self.is_legacy_owner}
        if include_owner_sub and self.owner_sub and self.is_owner:
            result["ownerSub"] = self.owner_sub
        return result


class FeatureService:
    """Service for managing GeoJSON features."""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def create_feature(
        self, 
        feature_data: dict, 
        name: Optional[str] = None,
        owner_sub: Optional[str] = None,
        generate_edit_token: bool = False
    ) -> Tuple[GeoFeature, Optional[str]]:
        """
        Create a new GeoJSON feature.
        
        Args:
            feature_data: GeoJSON Feature object
            name: Optional name for the feature
            owner_sub: Optional Cognito user sub for JWT-based ownership
            generate_edit_token: If True, generate an edit token for legacy access
        
        Returns:
            Tuple of (Created GeoFeature instance, edit_token if generated)
        """
        geometry = feature_data.get("geometry", {})
        properties = feature_data.get("properties", {})
        geometry_type = geometry.get("type", "Unknown")
        
        # Extract name from properties if not provided
        if not name:
            name = properties.get("name") or properties.get("id")
        
        # Generate edit token if requested (for legacy support when not using JWT)
        edit_token = None
        if generate_edit_token and not owner_sub:
            edit_token = secrets.token_urlsafe(32)
        
        # Convert GeoJSON geometry to PostGIS geometry using ST_GeomFromGeoJSON
        geom_json = json.dumps(geometry)
        
        # Create feature using raw SQL for PostGIS functions
        result = await self.db.execute(
            text("""
                INSERT INTO geo_features (name, geometry_type, geom, properties, raw_geometry, owner_sub, edit_token)
                VALUES (:name, :geometry_type, ST_GeomFromGeoJSON(:geom_json), :properties, :raw_geometry, :owner_sub, :edit_token)
                RETURNING id, name, geometry_type, created_at, updated_at
            """),
            {
                "name": name,
                "geometry_type": geometry_type,
                "geom_json": geom_json,
                "properties": json.dumps(properties),
                "raw_geometry": json.dumps(geometry),
                "owner_sub": owner_sub,
                "edit_token": edit_token,
            }
        )
        
        row = result.fetchone()
        await self.db.commit()
        
        # Fetch the complete record
        feature = await self.db.get(GeoFeature, row.id)
        return feature, edit_token
    
    async def get_feature(self, feature_id: int) -> Optional[GeoFeature]:
        """Get a feature by ID."""
        return await self.db.get(GeoFeature, feature_id)
    
    def get_ownership_info(
        self,
        feature: GeoFeature,
        current_user_sub: Optional[str] = None,
        edit_token: Optional[str] = None
    ) -> OwnershipInfo:
        """
        Get ownership information for a feature.
        
        Args:
            feature: The GeoFeature to check
            current_user_sub: The current user's Cognito sub (if authenticated via JWT)
            edit_token: The edit token provided (if using legacy access)
        
        Returns:
            OwnershipInfo with ownership details
        """
        is_legacy = feature.owner_sub is None
        is_owner = False
        
        if is_legacy:
            # Legacy feature - check edit token if provided
            if edit_token and feature.edit_token:
                is_owner = secrets.compare_digest(edit_token, feature.edit_token)
        else:
            # JWT-owned feature - check user sub
            if current_user_sub:
                is_owner = feature.owner_sub == current_user_sub
        
        return OwnershipInfo(
            is_legacy_owner=is_legacy,
            is_owner=is_owner,
            owner_sub=feature.owner_sub if is_owner else None
        )
    
    def verify_ownership(
        self,
        feature: GeoFeature,
        current_user_sub: Optional[str] = None,
        edit_token: Optional[str] = None
    ) -> OwnershipInfo:
        """
        Verify ownership of a feature for update/delete operations.
        
        Args:
            feature: The GeoFeature to check
            current_user_sub: The current user's Cognito sub (if authenticated via JWT)
            edit_token: The edit token provided (if using legacy access)
        
        Returns:
            OwnershipInfo if authorized
        
        Raises:
            OwnershipError if not authorized
        """
        ownership = self.get_ownership_info(feature, current_user_sub, edit_token)
        
        if feature.owner_sub is not None:
            # JWT-owned feature - require matching JWT
            if not current_user_sub:
                raise OwnershipError("This feature requires JWT authentication for modifications")
            if not ownership.is_owner:
                raise OwnershipError("You do not own this feature")
        else:
            # Legacy feature - require edit token if one exists
            if feature.edit_token:
                if not edit_token:
                    raise OwnershipError("Edit token required for this feature")
                if not ownership.is_owner:
                    raise OwnershipError("Invalid edit token")
            # If no edit_token on feature, allow (truly legacy open feature)
        
        return ownership
    
    async def update_feature(
        self, 
        feature_id: int, 
        feature_data: Optional[dict] = None,
        name: Optional[str] = None,
        properties: Optional[dict] = None
    ) -> Optional[GeoFeature]:
        """
        Update an existing GeoJSON feature.
        
        Args:
            feature_id: ID of feature to update
            feature_data: Optional complete GeoJSON Feature object
            name: Optional name to update
            properties: Optional properties to update
        
        Returns:
            Updated GeoFeature or None if not found
        """
        feature = await self.db.get(GeoFeature, feature_id)
        if not feature:
            return None
        
        # Update geometry if provided in feature_data
        if feature_data and "geometry" in feature_data:
            geometry = feature_data["geometry"]
            geom_json = json.dumps(geometry)
            
            await self.db.execute(
                text("""
                    UPDATE geo_features 
                    SET geom = ST_GeomFromGeoJSON(:geom_json),
                        raw_geometry = :raw_geometry,
                        geometry_type = :geometry_type
                    WHERE id = :id
                """),
                {
                    "id": feature_id,
                    "geom_json": geom_json,
                    "raw_geometry": json.dumps(geometry),
                    "geometry_type": geometry.get("type", feature.geometry_type),
                }
            )
        
        # Update name if provided
        if name is not None:
            feature.name = name
        
        # Update properties if provided
        if properties is not None:
            feature.properties = properties
        elif feature_data and "properties" in feature_data:
            feature.properties = feature_data["properties"]
        
        await self.db.commit()
        await self.db.refresh(feature)
        return feature
    
    async def delete_feature(self, feature_id: int) -> bool:
        """
        Delete a feature by ID.
        
        Returns:
            True if deleted, False if not found
        """
        feature = await self.db.get(GeoFeature, feature_id)
        if not feature:
            return False
        
        await self.db.delete(feature)
        await self.db.commit()
        return True
    
    async def list_features(
        self, 
        skip: int = 0, 
        limit: int = 100,
        geometry_type: Optional[str] = None
    ) -> tuple[List[GeoFeature], int]:
        """
        List features with pagination.
        
        Returns:
            Tuple of (features list, total count)
        """
        query = select(GeoFeature)
        count_query = select(func.count(GeoFeature.id))
        
        if geometry_type:
            query = query.where(GeoFeature.geometry_type == geometry_type)
            count_query = count_query.where(GeoFeature.geometry_type == geometry_type)
        
        # Get total count
        total_result = await self.db.execute(count_query)
        total = total_result.scalar()
        
        # Get paginated results
        query = query.offset(skip).limit(limit).order_by(GeoFeature.created_at.desc())
        result = await self.db.execute(query)
        features = result.scalars().all()
        
        return list(features), total
    
    async def query_by_bbox(
        self, 
        min_lon: float, 
        min_lat: float, 
        max_lon: float, 
        max_lat: float
    ) -> List[GeoFeature]:
        """
        Query features within a bounding box.
        
        Args:
            min_lon: Minimum longitude
            min_lat: Minimum latitude
            max_lon: Maximum longitude
            max_lat: Maximum latitude
        
        Returns:
            List of features within bounding box
        """
        # Create bounding box polygon
        bbox_geom = f"""
            ST_MakeEnvelope(
                {min_lon}, {min_lat},
                {max_lon}, {max_lat},
                4326
            )
        """
        
        result = await self.db.execute(
            text(f"""
                SELECT id, name, geometry_type, properties, raw_geometry, owner_sub, edit_token, created_at, updated_at
                FROM geo_features
                WHERE ST_Intersects(geom, {bbox_geom})
                ORDER BY created_at DESC
            """)
        )
        
        rows = result.fetchall()
        features = []
        for row in rows:
            feature = GeoFeature()
            feature.id = row.id
            feature.name = row.name
            feature.geometry_type = row.geometry_type
            feature.properties = row.properties
            feature.raw_geometry = row.raw_geometry
            feature.owner_sub = row.owner_sub
            feature.edit_token = row.edit_token
            feature.created_at = row.created_at
            feature.updated_at = row.updated_at
            features.append(feature)
        
        return features
    
    async def query_by_proximity(
        self, 
        lon: float, 
        lat: float, 
        radius_meters: float = 1000,
        limit: int = 100
    ) -> List[GeoFeature]:
        """
        Query features near a point.
        
        Args:
            lon: Longitude
            lat: Latitude
            radius_meters: Search radius in meters
            limit: Maximum number of results
        
        Returns:
            List of features ordered by distance
        """
        result = await self.db.execute(
            text("""
                SELECT id, name, geometry_type, properties, raw_geometry, owner_sub, edit_token, created_at, updated_at,
                       ST_Distance(
                           geom::geography,
                           ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography
                       ) AS distance
                FROM geo_features
                WHERE ST_DWithin(
                    geom::geography,
                    ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography,
                    :radius
                )
                ORDER BY distance
                LIMIT :limit
            """),
            {
                "lon": lon,
                "lat": lat,
                "radius": radius_meters,
                "limit": limit,
            }
        )
        
        rows = result.fetchall()
        features = []
        for row in rows:
            feature = GeoFeature()
            feature.id = row.id
            feature.name = row.name
            feature.geometry_type = row.geometry_type
            feature.properties = row.properties
            feature.raw_geometry = row.raw_geometry
            feature.owner_sub = row.owner_sub
            feature.edit_token = row.edit_token
            feature.created_at = row.created_at
            feature.updated_at = row.updated_at
            features.append(feature)
        
        return features

    # --- Shelter-specific queries (features where properties->>'type' = 'shelter') ---

    SHELTER_TYPE_FILTER = "properties->>'type' = 'shelter'"

    async def list_shelters(
        self,
        skip: int = 0,
        limit: int = 100,
    ) -> Tuple[List[GeoFeature], int]:
        """
        List shelters with pagination (features where properties->>'type' = 'shelter').
        Returns (features list, total count).
        """
        shelter_filter = GeoFeature.properties["type"].astext == "shelter"
        count_result = await self.db.execute(
            select(func.count(GeoFeature.id)).where(shelter_filter)
        )
        total = count_result.scalar() or 0
        result = await self.db.execute(
            select(GeoFeature)
            .where(shelter_filter)
            .order_by(GeoFeature.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        features = list(result.scalars().all())
        return features, total

    async def query_shelters_by_bbox(
        self,
        min_lon: float,
        min_lat: float,
        max_lon: float,
        max_lat: float,
    ) -> List[GeoFeature]:
        """Query shelters within a bounding box (same spatial logic as query_by_bbox)."""
        bbox_geom = f"""
            ST_MakeEnvelope(
                {min_lon}, {min_lat},
                {max_lon}, {max_lat},
                4326
            )
        """
        result = await self.db.execute(
            text(f"""
                SELECT id, name, geometry_type, properties, raw_geometry, owner_sub, edit_token, created_at, updated_at
                FROM geo_features
                WHERE ST_Intersects(geom, {bbox_geom})
                  AND {self.SHELTER_TYPE_FILTER}
                ORDER BY created_at DESC
            """)
        )
        rows = result.fetchall()
        return [self._row_to_feature(row) for row in rows]

    async def query_shelters_nearby(
        self,
        lon: float,
        lat: float,
        radius_meters: float = 1000,
        limit: int = 100,
    ) -> List[Tuple[GeoFeature, float]]:
        """
        Query shelters near a point. Ordered by ST_Distance.
        Returns list of (GeoFeature, distance_m).
        """
        result = await self.db.execute(
            text("""
                SELECT id, name, geometry_type, properties, raw_geometry, owner_sub, edit_token, created_at, updated_at,
                       ST_Distance(
                           geom::geography,
                           ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography
                       ) AS distance
                FROM geo_features
                WHERE ST_DWithin(
                    geom::geography,
                    ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography,
                    :radius
                )
                  AND """ + self.SHELTER_TYPE_FILTER + """
                ORDER BY distance
                LIMIT :limit
            """),
            {
                "lon": lon,
                "lat": lat,
                "radius": radius_meters,
                "limit": limit,
            },
        )
        rows = result.fetchall()
        out = []
        for row in rows:
            feature = self._row_to_feature(row)
            distance_m = float(getattr(row, "distance", 0))
            out.append((feature, distance_m))
        return out

    def _row_to_feature(self, row) -> GeoFeature:
        """Build a GeoFeature from a result row (with id, name, geometry_type, etc.)."""
        feature = GeoFeature()
        feature.id = row.id
        feature.name = row.name
        feature.geometry_type = row.geometry_type
        feature.properties = row.properties
        feature.raw_geometry = row.raw_geometry
        feature.owner_sub = row.owner_sub
        feature.edit_token = row.edit_token
        feature.created_at = row.created_at
        feature.updated_at = row.updated_at
        return feature

    async def get_shelter(self, feature_id: int) -> Optional[GeoFeature]:
        """Get a feature by ID if it is a shelter; otherwise return None."""
        feature = await self.get_feature(feature_id)
        if not feature or not isinstance(feature.properties, dict):
            return None
        if feature.properties.get("type") != "shelter":
            return None
        return feature
    
    async def export_all(self) -> dict:
        """
        Export all features as a GeoJSON FeatureCollection.
        
        Returns:
            GeoJSON FeatureCollection
        """
        result = await self.db.execute(
            select(GeoFeature).order_by(GeoFeature.created_at.desc())
        )
        features = result.scalars().all()
        
        return {
            "type": "FeatureCollection",
            "features": [feature.to_geojson() for feature in features]
        }

