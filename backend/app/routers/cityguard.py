"""
CityGuard API router – GPS ping ingestion and related endpoints.
Separate from GeoJSON feature endpoints.
Auth is applied at mount time in main (dependencies=[Depends(verify_auth)]).
On DB failure: log error, return 503, process must NOT crash (Gate 6).
"""
import json
import logging
import time
from collections import OrderedDict
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, HTTPException, status
from prometheus_client import Counter, Histogram
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import SQLAlchemyError
from typing import Any, Dict, List, Optional

from app.config import settings
from app.database import get_db

router = APIRouter()
logger = logging.getLogger(__name__)

# In-memory store of last known position for scooters that are NOT in violation (safe/active).
# Updated on each non-violation ping; capped at 500 entries (FIFO).
# Each entry has last_updated (epoch sec) so GET /active can filter by TTL (green dots stay 60s).
ACTIVE_SCOOTERS_MAX = 500
ACTIVE_TTL_SECONDS = 10
_active_scooters: Dict[str, Dict[str, Any]] = OrderedDict()

cityguard_requests_total = Counter("cityguard_requests_total", "Total CityGuard ping requests")
cityguard_violations_total = Counter("cityguard_violations_total", "Total CityGuard violations")
cityguard_query_duration_seconds = Histogram(
    "cityguard_query_duration_seconds",
    "CityGuard query duration in seconds",
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
)


class GpsPingRequest(BaseModel):
    """Request body for POST /v1/cityguard/pings."""

    scooter_id: str = Field(..., min_length=1, description="Scooter identifier")
    lat: float = Field(..., ge=-90.0, le=90.0, description="Latitude (-90 to 90)")
    lon: float = Field(..., ge=-180.0, le=180.0, description="Longitude (-180 to 180)")
    ts: str | None = Field(None, description="Optional timestamp string")


class GpsPingResponse(BaseModel):
    """Response for POST /v1/cityguard/pings."""

    status: str = "ok"
    violation: bool = False
    zone: Optional[str] = None


@router.post("/pings", response_model=GpsPingResponse, response_model_exclude_none=True)
async def create_ping(
    body: GpsPingRequest,
    db: AsyncSession = Depends(get_db),
) -> GpsPingResponse:
    """
    Ingest a GPS ping for a scooter. Checks if point is inside a restricted zone;
    if so, records violation in fines_ledger and returns violation details.

    - **scooter_id**: Required scooter identifier
    - **lat**: Latitude, must be between -90 and 90
    - **lon**: Longitude, must be between -180 and 180
    - **ts**: Optional timestamp string

    Returns violation=true and zone name if inside restricted zone, else violation=false.
    """
    cityguard_requests_total.inc()
    # Validated integer from config only (1–300s). Literal in SQL for SET: many DB drivers
    # do not support bound parameters for SET statement_timeout.
    _timeout_s = max(1, min(300, int(settings.cityguard_db_statement_timeout_s)))
    dialect_name = ""
    try:
        bind = db.get_bind()
        dialect_name = bind.dialect.name if bind else ""
    except Exception:
        pass
    try:
        if dialect_name == "postgresql":
            # Parameterized: set_config supports bind params; no string interpolation. is_local=false = session scope.
            await db.execute(
                text("SELECT set_config('statement_timeout', :t, false)"),
                {"t": f"{_timeout_s}s"},
            )
        with cityguard_query_duration_seconds.time():
            # Parameterized: only :lon/:lat bound (no user string in SQL). Semgrep: safe use of text().
            query = text("""
                SELECT id, name
                FROM geo_features
                WHERE properties->>'type' = 'restricted_zone'
                AND ST_Contains(
                    geom,
                    ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)
                )
                LIMIT 1
            """)
            result = await db.execute(query, {"lon": body.lon, "lat": body.lat})
            row = result.fetchone()

            if row:
                zone_id, zone_name = row
                params = {
                    "scooter_id": body.scooter_id,
                    "lat": body.lat,
                    "lon": body.lon,
                    "zone_feature_id": zone_id,
                    "zone_name": zone_name or "",
                }
                ins = await db.execute(
                    text("""
                        INSERT INTO fines_ledger (scooter_id, lat, lon, zone_feature_id, zone_name)
                        SELECT :scooter_id, :lat, :lon, :zone_feature_id, :zone_name
                        WHERE NOT EXISTS (
                            SELECT 1 FROM fines_ledger
                            WHERE scooter_id = :scooter_id
                              AND lat = :lat AND lon = :lon
                              AND created_at > NOW() - INTERVAL '5 seconds'
                        )
                    """),
                    params,
                )
                if ins.rowcount:
                    cityguard_violations_total.inc()
                return GpsPingResponse(status="ok", violation=True, zone=zone_name or "")

        # Non-violation: update active (safe) scooter position for dashboard
        _active_scooters[body.scooter_id] = {
            "scooter_id": body.scooter_id,
            "lat": body.lat,
            "lon": body.lon,
            "ts": body.ts or "",
            "last_updated": time.time(),
        }
        if len(_active_scooters) > ACTIVE_SCOOTERS_MAX:
            for _ in range(len(_active_scooters) - ACTIVE_SCOOTERS_MAX):
                _active_scooters.popitem(last=False)
        return GpsPingResponse(status="ok", violation=False)
    except SQLAlchemyError as e:
        logger.error("CityGuard database error (Gate 6: do not crash): %s", e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database temporarily unavailable",
        )
    except Exception as e:
        logger.error("CityGuard unexpected error (Gate 6: do not crash): %s", e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service temporarily unavailable",
        )
    finally:
        if dialect_name == "postgresql":
            try:
                await db.execute(text("RESET statement_timeout"))
            except Exception:
                pass


@router.get("/zones")
async def get_zones(db: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    """Return restricted zones as a GeoJSON FeatureCollection for dashboard visualization."""
    try:
        result = await db.execute(
            text("""
                SELECT id, name, raw_geometry
                FROM geo_features
                WHERE properties->>'type' = 'restricted_zone'
                AND raw_geometry IS NOT NULL
            """),
        )
        rows = result.fetchall()
        features: List[Dict[str, Any]] = []
        for row in rows:
            feat_id, name, raw_geom = row
            if not raw_geom:
                continue
            geom = raw_geom if isinstance(raw_geom, dict) else json.loads(raw_geom) if isinstance(raw_geom, str) else raw_geom
            features.append({
                "type": "Feature",
                "id": feat_id,
                "properties": {"name": name or ""},
                "geometry": geom,
            })
        return {"type": "FeatureCollection", "features": features}
    except SQLAlchemyError as e:
        logger.error("CityGuard zones query error: %s", e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database temporarily unavailable",
        )


# Only show violations from the last N minutes so the map doesn't turn solid red.
VIOLATIONS_WINDOW_MINUTES = 5
VIOLATIONS_LIMIT = 200


@router.get("/violations")
async def get_violations(db: AsyncSession = Depends(get_db)) -> List[Dict[str, Any]]:
    """Return recent violations from fines_ledger for dashboard (red dots).
    Only last VIOLATIONS_WINDOW_MINUTES so old dots drop off and the zone stays visible."""
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=VIOLATIONS_WINDOW_MINUTES)
        result = await db.execute(
            text("""
                SELECT scooter_id, lat, lon, zone_name, created_at
                FROM fines_ledger
                WHERE created_at > :cutoff
                ORDER BY created_at DESC
                LIMIT :lim
            """),
            {"cutoff": cutoff, "lim": VIOLATIONS_LIMIT},
        )
        rows = result.fetchall()
        return [
            {
                "scooter_id": r.scooter_id or "",
                "lat": float(r.lat),
                "lon": float(r.lon),
                "zone_name": r.zone_name or "",
                "created_at": r.created_at.isoformat() if r.created_at else "",
            }
            for r in rows
        ]
    except SQLAlchemyError as e:
        logger.error("CityGuard violations query error: %s", e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database temporarily unavailable",
        )


@router.get("/active")
async def get_active() -> List[Dict[str, Any]]:
    """Return last known positions of scooters that are not in violation (safe scooters, green dots).
    Only returns entries updated in the last ACTIVE_TTL_SECONDS so green dots stay visible for a bit."""
    now = time.time()
    cutoff = now - ACTIVE_TTL_SECONDS
    out = []
    for v in _active_scooters.values():
        if v.get("last_updated", 0) >= cutoff:
            out.append({k: v[k] for k in ("scooter_id", "lat", "lon", "ts") if k in v})
    return out
