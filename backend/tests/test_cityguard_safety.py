"""
CityGuard production safety limits: huge payload rejected, DB down fails fast.
"""
import time
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient, ASGITransport

from app.config import settings


class TestCityGuardHugePayloadRejected:
    """Send body > limit → 413 Request Entity Too Large."""

    def test_huge_payload_rejected_413(self, client):
        """POST with body > limit is rejected by middleware before handler."""
        max_body = settings.cityguard_max_body_bytes
        huge = b"x" * (max_body + 100)
        resp = client.post(
            "/v1/cityguard/pings",
            content=huge,
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code == 413, (
            f"Expected 413 for body > {max_body} bytes, got {resp.status_code}: {resp.text}"
        )
        data = resp.json()
        assert "Request entity too large" in data.get("error", "") or "too large" in str(data).lower()
        assert str(max_body) in resp.text

    @pytest.mark.asyncio
    async def test_body_at_limit_accepted(self):
        """POST with body at or under limit is not rejected by middleware (no 413)."""
        from app.main import app
        from app.database import get_db
        from app.auth.cognito import get_current_user
        from app.auth.cognito import CognitoUser

        max_body = settings.cityguard_max_body_bytes
        # Mock session: no SET (dialect != postgresql), SELECT returns no row
        mock_result = MagicMock()
        mock_result.fetchone.return_value = None
        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.get_bind = MagicMock(return_value=MagicMock(dialect=MagicMock(name="sqlite")))
        mock_session.commit = AsyncMock()
        mock_session.rollback = AsyncMock()
        mock_session.close = AsyncMock()

        async def override_get_db():
            yield mock_session

        async def override_get_current_user():
            return CognitoUser(sub="test", email="test@example.com")

        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[get_current_user] = override_get_current_user
        try:
            at_limit = b'{"scooter_id":"x","lat":0,"lon":0}' + b" " * (max_body - 35)
            assert len(at_limit) <= max_body
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                resp = await ac.post(
                    "/v1/cityguard/pings",
                    content=at_limit,
                    headers={"Content-Type": "application/json"},
                )
            assert resp.status_code != 413, f"Body at or under limit should not get 413: {resp.text}"
        finally:
            app.dependency_overrides.clear()


class TestCityGuardDbFailsFast:
    """When DB is dead or errors, request fails fast (no long hang)."""

    @pytest.mark.asyncio
    async def test_db_dead_request_fails_fast(self):
        """When DB raises on first use, request fails quickly (< 1s), not hang."""
        from app.main import app
        from app.database import get_db
        from app.auth.cognito import get_current_user
        from app.auth.cognito import CognitoUser
        from sqlalchemy.exc import OperationalError

        mock_session = AsyncMock()
        mock_session.execute = AsyncMock(
            side_effect=OperationalError("connection refused", None, None)
        )
        mock_session.get_bind = MagicMock(return_value=MagicMock(dialect=MagicMock(name="postgresql")))
        mock_session.commit = AsyncMock()
        mock_session.rollback = AsyncMock()
        mock_session.close = AsyncMock()

        async def override_get_db():
            yield mock_session

        async def override_get_current_user():
            return CognitoUser(sub="test", email="test@example.com")

        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[get_current_user] = override_get_current_user

        try:
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test", timeout=5.0) as ac:
                t0 = time.monotonic()
                try:
                    resp = await ac.post(
                        "/v1/cityguard/pings",
                        json={"scooter_id": "s1", "lat": 0.0, "lon": 0.0},
                    )
                    got_response = True
                except Exception:
                    got_response = False
                    resp = None
                elapsed = time.monotonic() - t0
            assert elapsed < 1.0, (
                f"Request must fail fast when DB is dead, took {elapsed:.2f}s"
            )
            if got_response and resp is not None:
                assert resp.status_code in (500, 503), (
                    f"Expected 5xx when DB errors, got {resp.status_code}: {resp.text}"
                )
        finally:
            app.dependency_overrides.clear()
