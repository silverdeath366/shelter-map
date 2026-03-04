"""
Phase 5: CityGuard ping integration tests.

Automated test that:
1. Inserts a temporary test polygon (restricted zone)
2. Sends ping inside zone -> asserts violation true
3. Sends ping outside zone -> asserts violation false
4. DB is cleaned after test via conftest clean_db fixture

Uses existing integration test framework (integration_client, clean_db).
No external services: runs against test PostGIS DB only.

Run with: TEST_MODE=integration pytest tests/test_cityguard_integration.py -v
Or: ./run-integration-tests.sh
"""
import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine


# Polygon in SF area: box lon -122.5..-122.4, lat 37.7..37.8 (GeoJSON is [lon, lat])
# Point inside: lon=-122.45, lat=37.75
# Point outside: lon=0, lat=0
RESTRICTED_ZONE_POLYGON = {
    "type": "Feature",
    "geometry": {
        "type": "Polygon",
        "coordinates": [[
            [-122.5, 37.7],
            [-122.4, 37.7],
            [-122.4, 37.8],
            [-122.5, 37.8],
            [-122.5, 37.7],
        ]],
    },
    "properties": {
        "name": "Phase5 Test Restricted Zone",
        "type": "restricted_zone",
    },
}

POINT_INSIDE = {"lat": 37.75, "lon": -122.45}
POINT_OUTSIDE = {"lat": 0.0, "lon": 0.0}


@pytest.mark.integration
class TestCityGuardPingIntegration:
    """Integration tests for CityGuard pings: zone containment and violation flag."""

    async def test_ping_inside_then_outside_restricted_zone(
        self,
        integration_client: AsyncClient,
    ) -> None:
        """
        1. Insert temporary test polygon (restricted_zone).
        2. Ping inside -> assert violation true.
        3. Ping outside -> assert violation false.
        DB is cleaned before (and after) test by clean_db fixture.
        """
        # 1. Insert temporary restricted zone via ingest (same DB as pings)
        ingest_resp = await integration_client.post("/v1/ingest", json=RESTRICTED_ZONE_POLYGON)
        assert ingest_resp.status_code == 201, (
            f"Expected 201 from ingest, got {ingest_resp.status_code}: {ingest_resp.text}"
        )

        # 2. Ping inside polygon -> must return violation true
        ping_inside = await integration_client.post(
            "/v1/cityguard/pings",
            json={
                "scooter_id": "test-scooter-1",
                "lat": POINT_INSIDE["lat"],
                "lon": POINT_INSIDE["lon"],
            },
        )
        assert ping_inside.status_code == 200, (
            f"Expected 200 from pings, got {ping_inside.status_code}: {ping_inside.text}"
        )
        data_inside = ping_inside.json()
        assert data_inside.get("violation") is True, (
            f"Expected violation=true for point inside zone, got: {data_inside}"
        )
        assert data_inside.get("zone") is not None, "Expected zone name in response"

        # 3. Ping outside polygon -> must return violation false
        ping_outside = await integration_client.post(
            "/v1/cityguard/pings",
            json={
                "scooter_id": "test-scooter-1",
                "lat": POINT_OUTSIDE["lat"],
                "lon": POINT_OUTSIDE["lon"],
            },
        )
        assert ping_outside.status_code == 200, (
            f"Expected 200 from pings, got {ping_outside.status_code}: {ping_outside.text}"
        )
        data_outside = ping_outside.json()
        assert data_outside.get("violation") is False, (
            f"Expected violation=false for point outside zone, got: {data_outside}"
        )

        # clean_db runs before each test and clears geo_features + fines_ledger; no extra cleanup needed
        # (next test gets a clean DB from the fixture)

    async def test_spam_same_ping_only_one_row_in_fines_ledger(
        self,
        integration_client: AsyncClient,
        integration_engine: AsyncEngine,
    ) -> None:
        """
        Spam the same ping (scooter_id + lat + lon) many times; only one row must be inserted
        (duplicate detection within 5 seconds).
        """
        # 1. Insert temporary restricted zone
        ingest_resp = await integration_client.post("/v1/ingest", json=RESTRICTED_ZONE_POLYGON)
        assert ingest_resp.status_code == 201, (
            f"Expected 201 from ingest, got {ingest_resp.status_code}: {ingest_resp.text}"
        )

        # 2. Spam same ping (inside zone) many times
        payload = {
            "scooter_id": "spam-scooter",
            "lat": POINT_INSIDE["lat"],
            "lon": POINT_INSIDE["lon"],
        }
        n = 15
        for _ in range(n):
            resp = await integration_client.post("/v1/cityguard/pings", json=payload)
            assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
            assert resp.json().get("violation") is True

        # 3. Assert only one row in fines_ledger
        async with integration_engine.begin() as conn:
            result = await conn.execute(text("SELECT COUNT(*) FROM fines_ledger"))
            count = result.scalar()
        assert count == 1, (
            f"Expected exactly 1 row in fines_ledger after spamming same ping {n} times, got {count}"
        )
