"""
Pytest configuration and fixtures for testing.

Supports two modes:
1. Unit tests: Use SQLite in-memory (fast, no external dependencies, mocked PostGIS operations)
2. Integration tests: Use PostgreSQL/PostGIS (requires docker-compose.test.yml)

Run unit tests:     pytest tests/ -m "not integration"
Run integration:    TEST_MODE=integration pytest tests/test_postgis_integration.py -v
Run all:            pytest tests/
"""
import os
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import declarative_base
from sqlalchemy import text
from fastapi.testclient import TestClient
from httpx import AsyncClient, ASGITransport
from typing import AsyncGenerator

# Ensure app startup validation passes in unit tests (before app is imported)
os.environ.setdefault("AUTH_MODE", "dev_open")
os.environ.setdefault("ENV", "development")
os.environ.setdefault("RATE_LIMIT", "10000")

# Determine test mode based on environment variable
TEST_MODE = os.environ.get("TEST_MODE", "unit")  # "unit" or "integration"
TEST_DB_HOST = os.environ.get("TEST_DB_HOST", "localhost")
TEST_DB_PORT = os.environ.get("TEST_DB_PORT", "5433")
TEST_DB_NAME = os.environ.get("TEST_DB_NAME", "geojson_test")
TEST_DB_USER = os.environ.get("TEST_DB_USER", "postgres")
TEST_DB_PASSWORD = os.environ.get("TEST_DB_PASSWORD", "postgres")

# Integration test database URL (PostgreSQL/PostGIS)
INTEGRATION_DATABASE_URL = (
    f"postgresql+asyncpg://{TEST_DB_USER}:{TEST_DB_PASSWORD}"
    f"@{TEST_DB_HOST}:{TEST_DB_PORT}/{TEST_DB_NAME}"
)

# Unit test database URL (SQLite in-memory)
UNIT_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line("markers", "integration: Integration tests requiring PostGIS database")
    config.addinivalue_line("markers", "unit: Unit tests that can run without external dependencies")


def pytest_collection_modifyitems(config, items):
    """Auto-skip integration tests if TEST_MODE is unit and vice versa."""
    skip_integration = pytest.mark.skip(reason="TEST_MODE is 'unit', skipping integration tests")
    skip_unit = pytest.mark.skip(reason="TEST_MODE is 'integration', skipping unit tests")
    
    for item in items:
        if TEST_MODE == "unit" and "integration" in item.keywords:
            item.add_marker(skip_integration)
        elif TEST_MODE == "integration" and "unit" in item.keywords and "integration" not in item.keywords:
            item.add_marker(skip_unit)


# ============================================================================
# Integration Test Fixtures (PostgreSQL/PostGIS)
# ============================================================================

def _check_db_available():
    """Check if integration database is available."""
    import socket
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        result = sock.connect_ex((TEST_DB_HOST, int(TEST_DB_PORT)))
        sock.close()
        return result == 0
    except Exception:
        return False


@pytest.fixture
async def integration_engine():
    """Create PostgreSQL engine for integration tests."""
    if not _check_db_available():
        pytest.skip(f"Integration database not available at {TEST_DB_HOST}:{TEST_DB_PORT}")
    
    engine = create_async_engine(
        INTEGRATION_DATABASE_URL,
        echo=False,
        pool_pre_ping=True,
    )
    yield engine
    await engine.dispose()


@pytest.fixture
async def clean_db(integration_engine):
    """Clean database tables before integration tests."""
    async with integration_engine.begin() as conn:
        # Delete all test data (but keep schema)
        await conn.execute(text("DELETE FROM fines_ledger"))
        await conn.execute(text("DELETE FROM geo_features"))
        await conn.execute(text("DELETE FROM api_keys"))
        # Reset sequences
        await conn.execute(text("ALTER SEQUENCE geo_features_id_seq RESTART WITH 1"))
        await conn.execute(text("ALTER SEQUENCE api_keys_id_seq RESTART WITH 1"))
        await conn.execute(text("ALTER SEQUENCE fines_ledger_id_seq RESTART WITH 1"))
    yield


@pytest.fixture
async def integration_db_session(integration_engine, clean_db) -> AsyncGenerator[AsyncSession, None]:
    """Create a database session for integration tests."""
    async_session = async_sessionmaker(
        integration_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    
    async with async_session() as session:
        yield session


@pytest.fixture
async def integration_client(integration_db_session):
    """Create a test client for integration tests using PostgreSQL."""
    # Import here to avoid circular imports
    from app.main import app, rate_limiter_instance
    from app.database import get_db
    from app.auth.cognito import get_current_user, CognitoUser

    async def override_get_db():
        try:
            yield integration_db_session
            await integration_db_session.commit()
        except Exception:
            await integration_db_session.rollback()
            raise

    async def override_get_current_user():
        return CognitoUser(sub="integration-test-user-sub", email="integration@example.com")

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user

    # Set very high rate limit for testing to avoid 429 errors
    original_rate_limit = rate_limiter_instance.requests_per_minute
    rate_limiter_instance.requests_per_minute = 10000

    # Clear any existing rate limit data
    rate_limiter_instance._memory_store.clear()

    # Use async client for proper async handling
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    # Restore original rate limit
    rate_limiter_instance.requests_per_minute = original_rate_limit
    app.dependency_overrides.clear()


# ============================================================================
# Unit Test Fixtures (SQLite in-memory with mocking)
# ============================================================================

@pytest.fixture
async def unit_engine():
    """Create SQLite engine for unit tests."""
    from app.database import Base
    
    engine = create_async_engine(
        UNIT_DATABASE_URL,
        echo=False,
        connect_args={"check_same_thread": False}
    )
    
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    yield engine
    
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    
    await engine.dispose()


@pytest.fixture
async def unit_db_session(unit_engine) -> AsyncGenerator[AsyncSession, None]:
    """Create a database session for unit tests."""
    async_session = async_sessionmaker(
        unit_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    
    async with async_session() as session:
        yield session


# Phase 2 upload tests: use SQLite with only report_images (no geo_features/JSONB)
REPORT_IMAGES_DDL = """
CREATE TABLE IF NOT EXISTS report_images (
    image_id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    s3_key TEXT NOT NULL UNIQUE,
    content_type TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
)
"""


@pytest.fixture
async def upload_only_engine():
    """SQLite engine with only report_images table (avoids JSONB/PostGIS in Phase 2 tests)."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.execute(text(REPORT_IMAGES_DDL))
    yield engine
    await engine.dispose()


@pytest.fixture
async def upload_only_session(upload_only_engine) -> AsyncGenerator[AsyncSession, None]:
    """Session for Phase 2 upload (presign/confirm) tests."""
    async_session = async_sessionmaker(
        upload_only_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    async with async_session() as session:
        yield session


@pytest.fixture
def mock_cognito_user():
    """Mock CognitoUser for feature endpoints (JWT required in production)."""
    from app.auth.cognito import CognitoUser
    return CognitoUser(sub="test-user-sub-12345", email="test@example.com")


@pytest.fixture
def client(unit_db_session: AsyncSession, mock_cognito_user):
    """Create a test client for unit tests (SQLite backend).
    Overrides get_current_user so feature endpoints receive a mock user (JWT required in app)."""
    from app.main import app
    from app.database import get_db
    from app.auth.cognito import get_current_user

    async def override_get_db():
        yield unit_db_session

    async def override_get_current_user():
        return mock_cognito_user

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()


@pytest.fixture
def client_no_jwt_override(unit_db_session: AsyncSession):
    """Test client without get_current_user override. Use to assert 401 when only API key is sent."""
    from app.main import app
    from app.database import get_db

    async def override_get_db():
        yield unit_db_session

    app.dependency_overrides[get_db] = override_get_db
    # Do NOT override get_current_user - feature endpoints will require JWT

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()


# ============================================================================
# Common Fixtures (used by both unit and integration tests)
# ============================================================================

@pytest.fixture
def mock_redis():
    """Mock Redis client for testing."""
    redis_mock = AsyncMock()
    redis_mock.get = AsyncMock(return_value=None)
    redis_mock.setex = AsyncMock(return_value=True)
    redis_mock.incr = AsyncMock(return_value=1)
    redis_mock.delete = AsyncMock(return_value=1)
    redis_mock.close = AsyncMock()
    return redis_mock


@pytest.fixture
def sample_feature():
    """Sample GeoJSON Point feature for testing."""
    return {
        "type": "Feature",
        "geometry": {
            "type": "Point",
            "coordinates": [-122.4194, 37.7749]  # San Francisco
        },
        "properties": {
            "name": "Test Point",
            "description": "A test point in San Francisco"
        }
    }


@pytest.fixture
def sample_polygon_feature():
    """Sample GeoJSON Polygon feature for testing."""
    return {
        "type": "Feature",
        "geometry": {
            "type": "Polygon",
            "coordinates": [[
                [-122.5, 37.7],
                [-122.4, 37.7],
                [-122.4, 37.8],
                [-122.5, 37.8],
                [-122.5, 37.7]
            ]]
        },
        "properties": {
            "name": "Test Polygon",
            "description": "A test polygon in San Francisco"
        }
    }


@pytest.fixture
def sample_linestring_feature():
    """Sample GeoJSON LineString feature for testing."""
    return {
        "type": "Feature",
        "geometry": {
            "type": "LineString",
            "coordinates": [
                [-122.5, 37.7],
                [-122.4, 37.75],
                [-122.3, 37.8]
            ]
        },
        "properties": {
            "name": "Test LineString",
            "description": "A test linestring"
        }
    }


@pytest.fixture
def sample_feature_collection(sample_feature, sample_polygon_feature):
    """Sample GeoJSON FeatureCollection for testing."""
    return {
        "type": "FeatureCollection",
        "features": [sample_feature, sample_polygon_feature]
    }


@pytest.fixture
def sample_api_key():
    """Sample API key for testing."""
    return "test-api-key-12345"


@pytest.fixture
def valid_api_key():
    """A valid API key that would pass validation."""
    return "gk_test_valid_key_abc123"


@pytest.fixture
def bbox_san_francisco():
    """Bounding box parameters for San Francisco area."""
    return {
        "min_lon": -122.6,
        "min_lat": 37.6,
        "max_lon": -122.2,
        "max_lat": 37.9
    }


@pytest.fixture
def bbox_new_york():
    """Bounding box parameters for New York area (no features expected)."""
    return {
        "min_lon": -74.3,
        "min_lat": 40.5,
        "max_lon": -73.7,
        "max_lat": 40.9
    }
