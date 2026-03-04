# Test Suite for GeoJSON Ingestion Service

This directory contains comprehensive tests for the GeoJSON Ingestion Service.

## Test Structure

- `test_main.py` - Unit tests for FastAPI endpoints
- `test_services.py` - Unit tests for service layer
- `test_rate_limiter.py` - Tests for rate limiting functionality
- `test_integration.py` - Integration tests for end-to-end functionality
- `test_redis_integration.py` - Tests for Redis integration
- `conftest.py` - Pytest configuration and fixtures
- `e2e/` - End-to-end test interface (HTML)

## Running Tests

### Run All Tests

```bash
cd services/geojson-ingestion
./run-tests.sh
```

Or manually:

```bash
pytest tests/ -v
```

### Run Specific Test Files

```bash
# Unit tests only
pytest tests/test_main.py tests/test_services.py -v

# Integration tests
pytest tests/test_integration.py -v

# Rate limiter tests
pytest tests/test_rate_limiter.py -v
```

### Run with Coverage

```bash
pytest tests/ --cov=app --cov-report=html
```

## Test Categories

### Unit Tests

Tests individual components in isolation with mocked dependencies:
- `test_main.py` - API endpoint tests
- `test_services.py` - Service layer tests
- `test_rate_limiter.py` - Rate limiter tests

### Integration Tests

Tests that verify end-to-end functionality:
- `test_integration.py` - Full API workflow tests
- `test_redis_integration.py` - Redis connectivity tests

### E2E Tests

Manual testing interface:
- `e2e/api-test.html` - Browser-based test interface

## Test Features

### Offline Testing

All tests run **offline** without requiring:
- AWS services
- Kubernetes cluster
- Redis server
- PostgreSQL database

Tests use:
- In-memory SQLite for database operations
- Mocked Redis client
- Mocked AWS services

### Test Coverage

- ✅ Health check endpoints
- ✅ Feature CRUD operations
- ✅ Spatial queries (bbox, proximity)
- ✅ API key management
- ✅ Authentication and authorization (feature endpoints require JWT; tests override `get_current_user`)
- ✅ Rate limiting
- ✅ Error handling
- ✅ Input validation

## Writing New Tests

### Test Structure

```python
import pytest
from fastapi.testclient import TestClient

def test_example(client: TestClient):
    """Test description."""
    response = client.get("/endpoint")
    assert response.status_code == 200
```

### Using Fixtures

```python
def test_with_fixture(client: TestClient, sample_feature, sample_api_key):
    # Feature endpoints require JWT; client fixture overrides get_current_user with a mock user
    response = client.post(
        "/v1/ingest",
        json=sample_feature,
        headers={"X-API-Key": sample_api_key}
    )
    assert response.status_code == 201
```

### Mocking Dependencies

```python
from unittest.mock import AsyncMock, patch

@pytest.mark.asyncio
async def test_with_mock():
    mock_db = AsyncMock()
    # Use mock_db in your test
```

## Continuous Integration

Tests are designed to run in CI/CD pipelines:
- No external dependencies
- Fast execution
- Deterministic results
- Clear error messages

## Troubleshooting

### Tests Failing

1. Check that all dependencies are installed:
   ```bash
   pip install -r requirements-dev.txt
   ```

2. Verify pytest is installed:
   ```bash
   pytest --version
   ```

3. Run tests with verbose output:
   ```bash
   pytest tests/ -v -s
   ```

### Database Errors

Tests use in-memory SQLite. If you see database errors:
- Check that SQLAlchemy is properly configured
- Verify that models are imported correctly
- Check conftest.py for database setup

### Import Errors

If you see import errors:
- Ensure you're running tests from the project root
- Check that PYTHONPATH includes the project directory
- Verify all dependencies are installed
