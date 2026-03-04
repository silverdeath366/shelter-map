"""
Database model for API key lifecycle management.
"""
from sqlalchemy import Column, Integer, String, DateTime, Boolean, Text
from sqlalchemy.sql import func
from app.database import Base
from datetime import datetime, timedelta
import secrets


class APIKey(Base):
    """Model for API key lifecycle management."""
    
    __tablename__ = "api_keys"
    
    id = Column(Integer, primary_key=True, index=True)
    key_hash = Column(String(255), unique=True, nullable=False, index=True)  # Hashed API key
    name = Column(String(255), nullable=True)  # Human-readable name/description
    is_active = Column(Boolean, default=True, nullable=False, index=True)
    rate_limit = Column(Integer, default=60, nullable=False)  # Requests per minute
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=True)  # Optional expiration
    last_used_at = Column(DateTime(timezone=True), nullable=True)
    usage_count = Column(Integer, default=0, nullable=False)
    key_metadata = Column("metadata", Text, nullable=True)  # JSON string for additional metadata
    
    def is_expired(self) -> bool:
        """Check if API key has expired."""
        if not self.expires_at:
            return False
        return datetime.utcnow() > self.expires_at.replace(tzinfo=None)
    
    def is_valid(self) -> bool:
        """Check if API key is valid (active and not expired)."""
        return self.is_active and not self.is_expired()
    
    @staticmethod
    def generate_key() -> str:
        """Generate a new secure API key."""
        return f"gk_{secrets.token_urlsafe(32)}"
    
    def __repr__(self):
        return f"<APIKey(id={self.id}, name={self.name}, active={self.is_active})>"

