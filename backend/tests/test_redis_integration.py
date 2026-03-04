"""
Tests for Redis integration and distributed rate limiting.
These tests verify Redis connectivity and rate limiting behavior.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.services.rate_limiter import RateLimiter


@pytest.mark.asyncio
async def test_rate_limiter_with_redis():
    """Test rate limiter with Redis backend."""
    # Mock Redis client
    mock_redis = AsyncMock()
    mock_redis.get.return_value = "5"
    mock_redis.incr.return_value = 6
    mock_redis.expire.return_value = True
    
    limiter = RateLimiter(redis_client=mock_redis, requests_per_minute=60)
    
    # Test rate limit check
    allowed, remaining = await limiter.check_rate_limit("test-key")
    
    assert allowed is True
    assert remaining >= 0
    assert mock_redis.get.called or mock_redis.incr.called


@pytest.mark.asyncio
async def test_rate_limiter_fallback_to_memory():
    """Test that rate limiter falls back to memory if Redis fails."""
    # Mock Redis client that raises an error
    mock_redis = AsyncMock()
    mock_redis.get.side_effect = Exception("Redis connection failed")
    
    limiter = RateLimiter(redis_client=mock_redis, requests_per_minute=60)
    
    # Should fall back to in-memory rate limiting
    allowed, remaining = await limiter.check_rate_limit("test-key")
    
    assert allowed is True
    assert remaining >= 0


@pytest.mark.asyncio
async def test_rate_limiter_memory_only():
    """Test rate limiter with in-memory backend only."""
    limiter = RateLimiter(redis_client=None, requests_per_minute=60)
    
    # Test rate limit check
    allowed, remaining = await limiter.check_rate_limit("test-key")
    
    assert allowed is True
    assert remaining >= 0


@pytest.mark.asyncio
async def test_rate_limiter_exceeds_limit():
    """Test rate limiter when limit is exceeded."""
    limiter = RateLimiter(redis_client=None, requests_per_minute=2)
    
    # Make requests up to limit
    for _ in range(2):
        allowed, remaining = await limiter.check_rate_limit("test-key")
        assert allowed is True
    
    # Next request should be rate limited
    allowed, remaining = await limiter.check_rate_limit("test-key")
    assert allowed is False
    assert remaining == 0


@pytest.mark.asyncio
async def test_rate_limiter_different_keys():
    """Test that rate limiting is per-key."""
    limiter = RateLimiter(redis_client=None, requests_per_minute=2)
    
    # Use up limit for key1
    await limiter.check_rate_limit("key1")
    await limiter.check_rate_limit("key1")
    allowed, _ = await limiter.check_rate_limit("key1")
    assert allowed is False
    
    # key2 should still have full limit
    allowed, remaining = await limiter.check_rate_limit("key2")
    assert allowed is True
    assert remaining > 0
