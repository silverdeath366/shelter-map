#!/usr/bin/env python3
"""
Load Petah Tikva shelters from a CSV (with lat, lon) into geo_features using
a synchronous psycopg2 connection. Use this when the async loader does not
persist to the same DB as the API.

Usage:
  DB_HOST=127.0.0.1 DB_PORT=5435 DB_NAME=geospatial DB_USER=postgres DB_PASSWORD=postgres \
    python scripts/load_petah_tikva_sync.py data/petahtikva_geocoded.csv

Or with defaults from .env: python scripts/load_petah_tikva_sync.py data/petahtikva_geocoded.csv
"""
import csv
import json
import os
import sys
from pathlib import Path

try:
    import psycopg2
    from psycopg2.extras import execute_values
except ImportError:
    print("Install psycopg2: pip install psycopg2-binary", file=sys.stderr)
    sys.exit(1)

APP_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CSV = APP_ROOT / "data" / "petahtikva_geocoded.csv"

# DB from env (same as app when using Docker: host 127.0.0.1, port 5435)
DB_HOST = os.environ.get("DB_HOST", "127.0.0.1")
DB_PORT = int(os.environ.get("DB_PORT", "5435"))
DB_NAME = os.environ.get("DB_NAME", "geospatial")
DB_USER = os.environ.get("DB_USER", "postgres")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "postgres")


def load_csv(path: Path) -> list[dict]:
    with open(path, "r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def main() -> int:
    csv_path = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else DEFAULT_CSV
    if not csv_path.exists():
        print(f"File not found: {csv_path}", file=sys.stderr)
        return 1

    rows = load_csv(csv_path)
    if not rows:
        print("No rows in CSV.", file=sys.stderr)
        return 0

    # Build list of (name, geom_geojson, properties_json) for insert
    to_insert = []
    for r in rows:
        lat_s, lon_s = r.get("lat", "").strip(), r.get("lon", "").strip()
        if not lat_s or not lon_s:
            continue
        try:
            lat = float(lat_s.replace(",", "."))
            lon = float(lon_s.replace(",", "."))
        except ValueError:
            continue
        if abs(lat) > 90 or abs(lon) > 180:
            continue
        name = (r.get("name") or "Shelter").strip() or "Petah Tikva Shelter"
        address = (r.get("address") or "").strip()
        geom = {"type": "Point", "coordinates": [lon, lat]}
        props = {
            "type": "shelter",  # required for /v1/shelters; do not overwrite
            "name": name,
            "address": address,
            "capacity": (r.get("capacity") or "").strip(),
            "accessibility": (r.get("accessibility") or "").strip(),
        }
        for k, v in r.items():
            if k in ("name", "address", "lat", "lon", "capacity", "accessibility", "type"):
                continue
            if v and str(v).strip():
                props[k] = str(v).strip()
        # Store CSV "type" (e.g. ציבורי) as public_type so it doesn't overwrite type=shelter
        if r.get("type") and str(r.get("type")).strip():
            props["public_type"] = str(r.get("type")).strip()
        to_insert.append((name, json.dumps(geom), json.dumps(props)))

    if not to_insert:
        print("No rows with valid lat/lon.", file=sys.stderr)
        return 1

    conn = psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
    )
    conn.autocommit = False
    cur = conn.cursor()

    try:
        # Remove existing Petah Tikva shelters (lon 34–35) so we don't duplicate
        cur.execute("""
            DELETE FROM geo_features
            WHERE properties->>'type' = 'shelter'
              AND ST_XMin(geom::geometry) BETWEEN 34 AND 35
        """)
        deleted = cur.rowcount
        if deleted:
            print(f"Removed {deleted} existing Petah Tikva shelter(s).")
        cur.execute(
            """
            INSERT INTO geo_features (name, geometry_type, geom, properties, raw_geometry)
            SELECT %s, 'Point', ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326), %s::jsonb, %s::jsonb
            """,
            (to_insert[0][0], to_insert[0][1], to_insert[0][2], to_insert[0][1]),
        )
        for name, geom_json, props_json in to_insert[1:]:
            cur.execute(
                """
                INSERT INTO geo_features (name, geometry_type, geom, properties, raw_geometry)
                SELECT %s, 'Point', ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326), %s::jsonb, %s::jsonb
                """,
                (name, geom_json, props_json, geom_json),
            )
        conn.commit()
        print(f"Inserted {len(to_insert)} Petah Tikva shelter(s) into {DB_NAME} at {DB_HOST}:{DB_PORT}")
    except Exception as e:
        conn.rollback()
        print(f"Error: {e}", file=sys.stderr)
        return 1
    finally:
        cur.close()
        conn.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
