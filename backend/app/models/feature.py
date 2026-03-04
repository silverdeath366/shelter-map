"""
Database model for GeoJSON features.
"""
from sqlalchemy import Column, Integer, String, DateTime, JSON
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func
from sqlalchemy.types import UserDefinedType
from app.database import Base
import json


class Geometry(UserDefinedType):
    """PostGIS Geometry type for SQLAlchemy."""
    
    def get_col_spec(self):
        return "GEOMETRY(GEOMETRY, 4326)"


class GeoFeature(Base):
    """Model representing a GeoJSON feature stored in PostgreSQL/PostGIS."""
    
    __tablename__ = "geo_features"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=True, index=True)
    geometry_type = Column(String(50), nullable=True, index=True)
    geom = Column(Geometry, nullable=False)  # PostGIS geometry
    properties = Column(JSONB, nullable=True)  # Feature properties as JSONB
    raw_geometry = Column(JSONB, nullable=True)  # Original GeoJSON geometry
    owner_sub = Column(String(255), nullable=True, index=True)  # Cognito user sub for JWT-based ownership
    edit_token = Column(String(255), nullable=True, index=True)  # Legacy edit token for anonymous edits
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    
    def to_geojson(self) -> dict:
        """Convert database record to GeoJSON Feature format."""
        # Handle raw_geometry - might be dict, string, or None
        geometry = {}
        if self.raw_geometry:
            if isinstance(self.raw_geometry, str):
                geometry = json.loads(self.raw_geometry)
            elif isinstance(self.raw_geometry, dict):
                geometry = self.raw_geometry
        
        return {
            "type": "Feature",
            "id": self.id,
            "geometry": geometry,
            "properties": {
                **(self.properties if isinstance(self.properties, dict) else {}),
                "name": self.name,
                "geometry_type": self.geometry_type,
                "created_at": self.created_at.isoformat() if self.created_at else None,
                "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            }
        }
    
    def __repr__(self):
        return f"<GeoFeature(id={self.id}, name={self.name}, type={self.geometry_type})>"

