#!/usr/bin/env python3
"""
Phase 1: Zone Loader.
Reads restricted_zones.geojson and inserts each polygon feature into geo_features
with type=restricted_zone, geometry SRID 4326.
Uses existing app database connection (app.database).
"""
import asyncio
import json
import os
import sys
from pathlib import Path

# Add app root to path and cwd so app.config and app.database resolve
APP_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP_ROOT))
os.chdir(APP_ROOT)

from sqlalchemy import text

from app.database import AsyncSessionLocal


# GeoJSON file path: same directory as this script
GEOJSON_PATH = Path(__file__).resolve().parent / "restricted_zones.geojson"


def load_geojson(path: Path) -> dict:
    """Load and parse GeoJSON file."""
    if not path.exists():
        raise FileNotFoundError(f"GeoJSON file not found: {path}")
    data = json.loads(path.read_text())
    if data.get("type") != "FeatureCollection" or "features" not in data:
        raise ValueError("Expected GeoJSON FeatureCollection with 'features' array")
    return data


def is_polygon_geometry(geom: dict) -> bool:
    """Return True if geometry is Polygon or MultiPolygon."""
    t = (geom or {}).get("type")
    return t in ("Polygon", "MultiPolygon")


async def main() -> int:
    geojson_path = GEOJSON_PATH
    if len(sys.argv) > 1:
        geojson_path = Path(sys.argv[1]).resolve()

    try:
        data = load_geojson(geojson_path)
    except (FileNotFoundError, ValueError) as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    features = [f for f in data["features"] if is_polygon_geometry(f.get("geometry"))]
    if not features:
        print("No polygon features found in GeoJSON.", file=sys.stderr)
        return 0

    inserted = 0
    async with AsyncSessionLocal() as session:
        try:
            await session.execute(
                text("DELETE FROM geo_features WHERE properties->>'type' = 'restricted_zone'")
            )
            for feature in features:
                geom = feature.get("geometry")
                props = feature.get("properties") or {}
                name = (props.get("name:en") or props.get("name") or "zone").strip() or "zone"
                geometry_type = "polygon"
                # Properties JSONB must include type=restricted_zone
                properties = {**props, "type": "restricted_zone"}
                geom_json = json.dumps(geom)
                raw_geometry = geom_json
                properties_json = json.dumps(properties)

                await session.execute(
                    text("""
                        INSERT INTO geo_features (name, geometry_type, geom, properties, raw_geometry)
                        VALUES (
                            :name,
                            :geometry_type,
                            ST_SetSRID(ST_GeomFromGeoJSON(:geom_json), 4326),
                            CAST(:properties AS jsonb),
                            CAST(:raw_geometry AS jsonb)
                        )
                    """),
                    {
                        "name": name,
                        "geometry_type": geometry_type,
                        "geom_json": geom_json,
                        "properties": properties_json,
                        "raw_geometry": raw_geometry,
                    },
                )
                inserted += 1
                print(f"  Inserted: {name}")
            await session.commit()
        except Exception as e:
            await session.rollback()
            err = str(e)
            if "Connect" in err or "111" in err or "connection" in err.lower():
                print(
                    "Error: Cannot connect to PostgreSQL. Is the database running?\n"
                    "  Local: start it with e.g. docker-compose up -d db\n"
                    "  Set DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD (or .env) if needed.",
                    file=sys.stderr,
                )
            else:
                print(f"Error inserting features: {e}", file=sys.stderr)
            return 1

    print(f"Done. Inserted {inserted} zone(s).")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
