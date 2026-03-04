"""
Rate limiting service with support for both in-memory and Redis backends.
Falls back to in-memory if Redis is not available.
"""
from typing import Optional
from datetime import datetime, timedelta
import time
import hashlib
import logging
from collections import defaultdict
from threading import Lock

logger = logging.getLogger(__name__)


class RateLimiter:
    """
    Rate limiter that supports both in-memory and Redis backends.
    Automatically falls back to in-memory if Redis is unavailable.
    """
    
    def __init__(self, redis_client: Optional[object] = None, requests_per_minute: int = 60):
        """
        Initialize rate limiter.
        
        Args:
            redis_client: Optional Redis client (redis.Redis or redis.asyncio.Redis)
            requests_per_minute: Rate limit (requests per minute)
        """
        self.redis_client = redis_client
        self.requests_per_minute = requests_per_minute
        self.window_seconds = 60
        
        # In-memory fallback storage
        self._memory_store: dict[str, list[float]] = defaultdict(list)
        self._memory_lock = Lock()
        self._cleanup_interval = 300  # Clean up old entries every 5 minutes
        self._last_cleanup = time.time()
    
    def _get_key(self, identifier: str) -> str:
        """Generate Redis key for rate limiting."""
        window = int(time.time() // self.window_seconds)
        return f"ratelimit:{identifier}:{window}"
    
    def _cleanup_memory_store(self):
        """Clean up old entries from memory store."""
        current_time = time.time()
        if current_time - self._last_cleanup < self._cleanup_interval:
            return
        
        cutoff_time = current_time - (self.window_seconds * 2)  # Keep 2 windows
        
        with self._memory_lock:
            keys_to_remove = []
            for key, timestamps in self._memory_store.items():
                # Filter out old timestamps
                self._memory_store[key] = [ts for ts in timestamps if ts > cutoff_time]
                if not self._memory_store[key]:
                    keys_to_remove.append(key)
            
            for key in keys_to_remove:
                del self._memory_store[key]
        
        self._last_cleanup = current_time
    
    async def _check_redis(self, identifier: str) -> tuple[bool, int]:
        """
        Check rate limit using Redis backend.
        Returns (is_allowed, remaining_requests).
        """
        if not self.redis_client:
            return True, self.requests_per_minute
        
        try:
            key = self._get_key(identifier)
            current_count = await self.redis_client.get(key)
            
            if current_count is None:
                # First request in this window
                await self.redis_client.setex(key, self.window_seconds, 1)
                return True, self.requests_per_minute - 1
            else:
                current_count = int(current_count)
                if current_count >= self.requests_per_minute:
                    return False, 0
                
                # Increment counter
                await self.redis_client.incr(key)
                return True, self.requests_per_minute - current_count - 1
                
        except Exception as e:
            logger.warning(f"Redis rate limit check failed, falling back to memory: {e}")
            return await self._check_memory(identifier)
    
    async def _check_memory(self, identifier: str) -> tuple[bool, int]:
        """
        Check rate limit using in-memory backend.
        Returns (is_allowed, remaining_requests).
        """
        self._cleanup_memory_store()
        current_time = time.time()
        window_start = current_time - self.window_seconds
        
        with self._memory_lock:
            timestamps = self._memory_store[identifier]
            # Remove timestamps outside current window
            timestamps[:] = [ts for ts in timestamps if ts > window_start]
            
            if len(timestamps) >= self.requests_per_minute:
                return False, 0
            
            # Add current request
            timestamps.append(current_time)
            remaining = self.requests_per_minute - len(timestamps)
            return True, remaining
    
    async def check_rate_limit(self, identifier: str) -> tuple[bool, int]:
        """
        Check if request is within rate limit.
        
        Args:
            identifier: Unique identifier (IP address, API key, etc.)
        
        Returns:
            Tuple of (is_allowed, remaining_requests)
        """
        if self.redis_client:
            return await self._check_redis(identifier)
        else:
            return await self._check_memory(identifier)
    
    async def reset_rate_limit(self, identifier: str):
        """Reset rate limit for an identifier (useful for testing/admin)."""
        if self.redis_client:
            try:
                key = self._get_key(identifier)
                await self.redis_client.delete(key)
            except Exception as e:
                logger.warning(f"Failed to reset Redis rate limit: {e}")
        else:
            with self._memory_lock:
                if identifier in self._memory_store:
                    del self._memory_store[identifier]


# Global rate limiter instance (will be initialized in main.py)
rate_limiter: Optional[RateLimiter] = None

