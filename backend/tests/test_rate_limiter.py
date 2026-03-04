"""
Unit tests for rate limiter service.
Tests both in-memory and Redis backends (mocked).
"""
import pytest
from unittest.mock import AsyncMock
from app.services.rate_limiter import RateLimiter


@pytest.mark.asyncio
async def test_rate_limiter_memory():
    """Test in-memory rate limiting."""
    limiter = RateLimiter(redis_client=None, requests_per_minute=5)
    
    identifier = "test-ip-123"
    
    # Make 5 requests (should all pass)
    for i in range(5):
        is_allowed, remaining = await limiter.check_rate_limit(identifier)
        assert is_allowed is True
        assert remaining >= 0
    
    # 6th request should be blocked
    is_allowed, remaining = await limiter.check_rate_limit(identifier)
    assert is_allowed is False
    assert remaining == 0


@pytest.mark.asyncio
async def test_rate_limiter_redis():
    """Test Redis-based rate limiting with mocked Redis."""
    mock_redis = AsyncMock()
    limiter = RateLimiter(redis_client=mock_redis, requests_per_minute=5)
    
    identifier = "test-ip-456"
    
    # Mock Redis responses
    mock_redis.get.return_value = None  # First request
    mock_redis.setex.return_value = True
    
    is_allowed, remaining = await limiter.check_rate_limit(identifier)
    assert is_allowed is True
    assert mock_redis.get.called
    assert mock_redis.setex.called
    
    # Mock subsequent requests
    mock_redis.get.return_value = "3"  # 3 requests already made
    mock_redis.incr.return_value = 4
    
    is_allowed, remaining = await limiter.check_rate_limit(identifier)
    assert is_allowed is True
    assert remaining == 1  # 5 - 4 = 1 remaining
    
    # Mock rate limit exceeded
    mock_redis.get.return_value = "5"
    is_allowed, remaining = await limiter.check_rate_limit(identifier)
    assert is_allowed is False
    assert remaining == 0


@pytest.mark.asyncio
async def test_rate_limiter_redis_fallback():
    """Test that rate limiter falls back to memory if Redis fails."""
    mock_redis = AsyncMock()
    mock_redis.get.side_effect = Exception("Redis connection failed")
    
    limiter = RateLimiter(redis_client=mock_redis, requests_per_minute=5)
    
    identifier = "test-ip-789"
    
    # Should fall back to memory and work
    is_allowed, remaining = await limiter.check_rate_limit(identifier)
    assert is_allowed is True
    assert remaining >= 0


@pytest.mark.asyncio
async def test_rate_limiter_reset():
    """Test resetting rate limit."""
    limiter = RateLimiter(redis_client=None, requests_per_minute=5)
    
    identifier = "test-ip-reset"
    
    # Exceed rate limit
    for _ in range(6):
        await limiter.check_rate_limit(identifier)
    
    # Reset
    await limiter.reset_rate_limit(identifier)
    
    # Should be able to make requests again
    is_allowed, remaining = await limiter.check_rate_limit(identifier)
    assert is_allowed is True

