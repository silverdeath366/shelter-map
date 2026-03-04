"""
Service layer for API key lifecycle management.
"""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from app.models.api_key import APIKey
import hashlib
import secrets
import json
import logging

logger = logging.getLogger(__name__)


class APIKeyService:
    """Service for managing API key lifecycle."""
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    def _hash_key(self, key: str) -> str:
        """Hash an API key for storage."""
        return hashlib.sha256(key.encode()).hexdigest()
    
    def _verify_key(self, key: str, key_hash: str) -> bool:
        """Verify an API key against its hash."""
        return self._hash_key(key) == key_hash
    
    async def create_api_key(
        self,
        name: Optional[str] = None,
        rate_limit: int = 60,
        expires_in_days: Optional[int] = None,
        metadata: Optional[dict] = None
    ) -> tuple[str, APIKey]:
        """
        Create a new API key.
        
        Args:
            name: Human-readable name for the key
            rate_limit: Requests per minute limit
            expires_in_days: Optional expiration in days
            metadata: Optional metadata dictionary
        
        Returns:
            Tuple of (plain_text_key, APIKey instance)
        """
        # Generate new key
        plain_key = APIKey.generate_key()
        key_hash = self._hash_key(plain_key)
        
        # Calculate expiration
        expires_at = None
        if expires_in_days:
            expires_at = datetime.utcnow() + timedelta(days=expires_in_days)
        
        # Create API key record
        api_key = APIKey(
            key_hash=key_hash,
            name=name or f"API Key {datetime.utcnow().isoformat()}",
            rate_limit=rate_limit,
            expires_at=expires_at,
            key_metadata=json.dumps(metadata) if metadata else None,
        )
        
        self.db.add(api_key)
        await self.db.commit()
        await self.db.refresh(api_key)
        
        logger.info(f"Created API key: {api_key.id} ({api_key.name})")
        
        return plain_key, api_key
    
    async def verify_api_key(self, key: str) -> Optional[APIKey]:
        """
        Verify an API key and return the APIKey instance if valid.
        
        Args:
            key: Plain text API key to verify
        
        Returns:
            APIKey instance if valid, None otherwise
        """
        key_hash = self._hash_key(key)
        
        result = await self.db.execute(
            select(APIKey).where(APIKey.key_hash == key_hash)
        )
        api_key = result.scalar_one_or_none()
        
        if not api_key:
            return None
        
        # Check if key is valid
        if not api_key.is_valid():
            return None
        
        # Update last used timestamp
        api_key.last_used_at = datetime.utcnow()
        api_key.usage_count += 1
        await self.db.commit()
        
        return api_key
    
    async def get_api_key(self, key_id: int) -> Optional[APIKey]:
        """Get an API key by ID."""
        return await self.db.get(APIKey, key_id)
    
    async def list_api_keys(
        self,
        skip: int = 0,
        limit: int = 100,
        active_only: bool = False
    ) -> tuple[List[APIKey], int]:
        """
        List API keys with pagination.
        
        Returns:
            Tuple of (api_keys list, total count)
        """
        query = select(APIKey)
        count_query = select(func.count(APIKey.id))
        
        if active_only:
            query = query.where(APIKey.is_active == True)
            count_query = count_query.where(APIKey.is_active == True)
        
        # Get total count
        total_result = await self.db.execute(count_query)
        total = total_result.scalar()
        
        # Get paginated results
        query = query.offset(skip).limit(limit).order_by(APIKey.created_at.desc())
        result = await self.db.execute(query)
        api_keys = result.scalars().all()
        
        return list(api_keys), total
    
    async def update_api_key(
        self,
        key_id: int,
        name: Optional[str] = None,
        is_active: Optional[bool] = None,
        rate_limit: Optional[int] = None,
        expires_in_days: Optional[int] = None,
        metadata: Optional[dict] = None
    ) -> Optional[APIKey]:
        """
        Update an API key.
        
        Args:
            key_id: ID of API key to update
            name: Optional new name
            is_active: Optional active status
            rate_limit: Optional new rate limit
            expires_in_days: Optional new expiration (days from now)
            metadata: Optional new metadata
        
        Returns:
            Updated APIKey or None if not found
        """
        api_key = await self.db.get(APIKey, key_id)
        if not api_key:
            return None
        
        if name is not None:
            api_key.name = name
        
        if is_active is not None:
            api_key.is_active = is_active
        
        if rate_limit is not None:
            api_key.rate_limit = rate_limit
        
        if expires_in_days is not None:
            if expires_in_days == 0:
                api_key.expires_at = None
            else:
                api_key.expires_at = datetime.utcnow() + timedelta(days=expires_in_days)
        
        if metadata is not None:
            api_key.key_metadata = json.dumps(metadata)
        
        await self.db.commit()
        await self.db.refresh(api_key)
        
        return api_key
    
    async def delete_api_key(self, key_id: int) -> bool:
        """
        Delete (deactivate) an API key.
        
        Args:
            key_id: ID of API key to delete
        
        Returns:
            True if deleted, False if not found
        """
        api_key = await self.db.get(APIKey, key_id)
        if not api_key:
            return False
        
        # Soft delete by deactivating
        api_key.is_active = False
        await self.db.commit()
        
        return True
    
    async def revoke_api_key(self, key_id: int) -> bool:
        """Alias for delete_api_key (soft delete by deactivating)."""
        return await self.delete_api_key(key_id)

