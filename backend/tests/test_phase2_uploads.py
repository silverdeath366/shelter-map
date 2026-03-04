"""
Phase 2 acceptance tests: presign and confirm endpoints.

Backend logic:
- Presign returns valid PUT URL shape.
- Confirm accepts valid metadata; rejects invalid prefix and oversized.
"""
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from fastapi.testclient import TestClient


@pytest.fixture
def client_uploads(upload_only_session):
    """Client for upload endpoints (no JWT required in Phase 2). Uses DB with only report_images."""
    from app.main import app
    from app.database import get_db

    async def override_get_db():
        yield upload_only_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.mark.unit
class TestPresignEndpoint:
    """1️⃣ Presign endpoint returns a valid PUT URL."""

    @patch("app.main.get_s3_upload_service")
    def test_presign_returns_valid_put_url_shape(self, mock_get_s3, client_uploads: TestClient):
        mock_svc = MagicMock()
        mock_svc.is_configured = True
        mock_svc.create_presigned_upload_anonymous = AsyncMock(
            return_value=MagicMock(
                upload_url="https://s3.us-east-1.amazonaws.com/bucket/reports/anonymous/abc.jpg?X-Amz-...",
                photo_key="reports/anonymous/abc.jpg",
                get_url="https://s3.us-east-1.amazonaws.com/bucket/reports/anonymous/abc.jpg?X-Amz-...",
                expires_in=600,
            )
        )
        mock_get_s3.return_value = mock_svc

        r = client_uploads.post(
            "/v1/uploads/presign",
            json={"content_type": "image/jpeg", "file_size": 1024},
        )
        assert r.status_code == 200
        data = r.json()
        assert "uploadUrl" in data
        assert data["uploadUrl"].startswith("https://")
        assert "objectKey" in data
        assert data["objectKey"].startswith("reports/anonymous/")
        assert "getUrl" in data
        assert "expiresIn" in data
        assert data["publicReadStrategy"] == "presigned"

    @patch("app.main.get_s3_upload_service")
    def test_presign_when_s3_not_configured_returns_503(self, mock_get_s3, client_uploads: TestClient):
        mock_svc = MagicMock()
        mock_svc.is_configured = False
        mock_get_s3.return_value = mock_svc

        r = client_uploads.post(
            "/v1/uploads/presign",
            json={"content_type": "image/jpeg", "file_size": 1024},
        )
        assert r.status_code == 503

    @patch("app.main.get_s3_upload_service")
    def test_presign_rejects_invalid_content_type(self, mock_get_s3, client_uploads: TestClient):
        from app.services.s3_upload_service import S3UploadError
        mock_svc = MagicMock()
        mock_svc.is_configured = True
        mock_svc.create_presigned_upload_anonymous = AsyncMock(side_effect=S3UploadError("Invalid content type"))
        mock_get_s3.return_value = mock_svc

        r = client_uploads.post(
            "/v1/uploads/presign",
            json={"content_type": "image/gif", "file_size": 1024},
        )
        assert r.status_code == 400


@pytest.mark.unit
class TestConfirmEndpoint:
    """1️⃣ Confirm: accepts valid metadata; rejects invalid prefix or oversized."""

    def test_confirm_accepts_valid_metadata(self, client_uploads: TestClient):
        r = client_uploads.post(
            "/v1/uploads/confirm",
            json={
                "s3_key": "reports/anonymous/550e8400-e29b-41d4-a716-446655440000.jpg",
                "content_type": "image/jpeg",
                "size_bytes": 1024,
            },
        )
        assert r.status_code == 201
        data = r.json()
        assert data.get("ok") is True
        assert "reports/anonymous/" in data.get("s3_key", "")

    def test_confirm_rejects_invalid_prefix(self, client_uploads: TestClient):
        r = client_uploads.post(
            "/v1/uploads/confirm",
            json={
                "s3_key": "find-my-dog/user123/photo.jpg",
                "content_type": "image/jpeg",
                "size_bytes": 1024,
            },
        )
        assert r.status_code == 400
        assert "must start with" in r.json().get("detail", "").lower() or "invalid" in r.json().get("detail", "").lower()

    def test_confirm_rejects_zero_size(self, client_uploads: TestClient):
        r = client_uploads.post(
            "/v1/uploads/confirm",
            json={
                "s3_key": "reports/anonymous/550e8400-e29b-41d4-a716-446655440000.jpg",
                "content_type": "image/jpeg",
                "size_bytes": 0,
            },
        )
        assert r.status_code == 400

    def test_confirm_rejects_oversized(self, client_uploads: TestClient):
        # Default max 5MB = 5*1024*1024
        r = client_uploads.post(
            "/v1/uploads/confirm",
            json={
                "s3_key": "reports/anonymous/550e8400-e29b-41d4-a716-446655440000.jpg",
                "content_type": "image/jpeg",
                "size_bytes": 6 * 1024 * 1024,
            },
        )
        assert r.status_code == 400
        assert "size" in r.json().get("detail", "").lower() or "max" in r.json().get("detail", "").lower()

    def test_confirm_rejects_invalid_content_type(self, client_uploads: TestClient):
        r = client_uploads.post(
            "/v1/uploads/confirm",
            json={
                "s3_key": "reports/anonymous/550e8400-e29b-41d4-a716-446655440000.jpg",
                "content_type": "image/gif",
                "size_bytes": 1024,
            },
        )
        assert r.status_code == 400
