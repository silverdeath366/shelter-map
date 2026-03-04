#!/usr/bin/env python3
"""
Load shelter records from a CSV file into geo_features as pins on the map.

What is CSV? It's a spreadsheet saved as a text file (e.g. Excel "Save as CSV",
or a downloaded Records.csv). Each row = one shelter, columns = name, address,
coordinates, etc.

Supports:
- CSV with existing coordinates (e.g. "קואורדינטות ציר x", "קורדינטות ציר y" or lat/lon columns).
- Optional geocoding for address-only CSVs (requires geopy).

Usage:
  python scripts/load_shelters_from_csv.py [path/to/Records.csv]

If no path is given, uses backend/scripts/data/Records.csv or backend/data/Records.csv.

File in Windows Downloads (use this path from WSL/Linux):
  python scripts/load_shelters_from_csv.py /mnt/c/Users/TOSHIBA/Downloads/Records.csv
"""
import asyncio
import csv
import json
import os
import sys
from pathlib import Path

# Add app root to path
APP_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP_ROOT))
os.chdir(APP_ROOT)

from sqlalchemy import text

from app.database import AsyncSessionLocal


# Column name variants (strip + lower for matching)
# First match wins. Order: Hebrew / your CSV headers, then English.
ADDRESS_KEYS = [
    "כתובות למפה", "כתובת", "address", "Address", "full_address", "location",
]
NAME_KEYS = [
    "מספר מקלט", "שם השכונה", "קטגוריה", "name", "Name", "title", "shelter",
]
CAPACITY_KEYS = ["מס' נפשות", "capacity", "Capacity", "people", "נפשות"]
ACCESSIBILITY_KEYS = ["נגישות", "accessibility", "Accessibility"]
# Latitude / longitude. GeoJSON is [lon, lat]. Israeli CSVs: often "ציר x" = lat, "ציר y" = lon.
# If your pins appear in the wrong place (e.g. ocean), your CSV may use x=lon, y=lat — swap the column mapping or use columns named "lat"/"lon" explicitly.
LAT_KEYS = ["קואורדינטות ציר x", "lat", "Lat", "latitude", "Latitude", "y"]
LON_KEYS = ["קורדינטות ציר y", "lon", "Lon", "lng", "longitude", "Longitude", "x"]


def normalize_header(h: str) -> str:
    return (h.strip() or "").strip('"\'')


def find_column(row: dict, keys: list) -> str | None:
    """Return value for first key that exists in row (normalized header match)."""
    for k in keys:
        k_norm = normalize_header(k)
        for header, value in row.items():
            if normalize_header(header) == k_norm:
                v = (value or "").strip()
                if v:
                    return v
    return None


def find_column_key(headers: list, keys: list) -> str | None:
    """Return first header that matches one of keys (normalized)."""
    normalized = [normalize_header(h) for h in headers]
    for k in keys:
        k2 = k.strip()
        for i, h in enumerate(normalized):
            if h == k2:
                return headers[i]
    return None


def load_csv(path: Path, encoding: str = "utf-8-sig") -> list[dict]:
    """Load CSV into list of dicts (first row = headers)."""
    with open(path, "r", encoding=encoding, newline="") as f:
        reader = csv.DictReader(f)
        return list(reader)


def row_to_feature(row: dict, headers: list) -> dict | None:
    """
    Convert one CSV row to a GeoJSON Feature for a shelter.
    Returns None if required fields (coordinates or address) are missing.
    """
    lat = find_column(row, LAT_KEYS)
    lon = find_column(row, LON_KEYS)

    # Prefer numeric lat/lon from CSV
    if lat is not None and lon is not None:
        try:
            lat_f = float(lat.replace(",", "."))
            lon_f = float(lon.replace(",", "."))
        except ValueError:
            lat_f = lon_f = None
    else:
        lat_f, lon_f = None, None

    # If we have coordinates, use them (GeoJSON order: lon, lat)
    if lat_f is not None and lon_f is not None:
        lon_f, lat_f = float(lon_f), float(lat_f)
        if abs(lat_f) <= 90 and abs(lon_f) <= 180:
            geometry = {"type": "Point", "coordinates": [lon_f, lat_f]}
        else:
            return None
    else:
        # No coordinates in CSV — would need geocoding (optional, not implemented here)
        return None

    name = find_column(row, NAME_KEYS) or "Shelter"
    address = find_column(row, ADDRESS_KEYS) or ""
    capacity = find_column(row, CAPACITY_KEYS) or ""
    accessibility = find_column(row, ACCESSIBILITY_KEYS) or ""

    # Preserve any extra columns in properties for future popup use
    properties = {
        "type": "shelter",
        "name": name,
        "address": address,
        "capacity": capacity,
        "accessibility": accessibility,
    }
    for h in headers:
        key = normalize_header(h)
        if key and key not in {
            normalize_header(k) for k in (NAME_KEYS + ADDRESS_KEYS + CAPACITY_KEYS + ACCESSIBILITY_KEYS + LAT_KEYS + LON_KEYS)
        }:
            val = (row.get(h) or "").strip()
            if val:
                properties[key] = val

    return {
        "type": "Feature",
        "geometry": geometry,
        "properties": properties,
    }


async def main() -> int:
    if len(sys.argv) > 1:
        csv_path = Path(sys.argv[1]).resolve()
    else:
        for p in [
            APP_ROOT / "scripts" / "data" / "Records.csv",
            APP_ROOT / "data" / "Records.csv",
            APP_ROOT / "data" / "petahtikva_geocoded.csv",
        ]:
            if p.exists():
                csv_path = p
                break
        else:
            print(
                "Usage: python scripts/load_shelters_from_csv.py <path/to/Records.csv>\n"
                "  Or place Records.csv in backend/data/, or run geocode_petah_tikva.py then:\n"
                "  python scripts/load_shelters_from_csv.py data/petahtikva_geocoded.csv",
                file=sys.stderr,
            )
            return 1

    if not csv_path.exists():
        print(f"Error: File not found: {csv_path}", file=sys.stderr)
        return 1

    try:
        rows = load_csv(csv_path)
    except Exception as e:
        print(f"Error reading CSV: {e}", file=sys.stderr)
        return 1

    if not rows:
        print("No rows in CSV.", file=sys.stderr)
        return 0

    headers = list(rows[0].keys())
    features = []
    for row in rows:
        feat = row_to_feature(row, headers)
        if feat:
            features.append(feat)

    if not features:
        print(
            "No rows with valid coordinates. Ensure CSV has latitude/longitude columns.",
            file=sys.stderr,
        )
        return 1

    print(f"Loaded {len(features)} shelter(s) from {csv_path.name}. Inserting into database...")

    async with AsyncSessionLocal() as session:
        try:
            for f in features:
                geom = f["geometry"]
                props = f["properties"]
                name = props.get("name") or "Shelter"
                geom_json = json.dumps(geom)
                properties_json = json.dumps(props)
                await session.execute(
                    text("""
                        INSERT INTO geo_features (name, geometry_type, geom, properties, raw_geometry)
                        VALUES (
                            :name,
                            'Point',
                            ST_SetSRID(ST_GeomFromGeoJSON(:geom_json), 4326),
                            CAST(:properties AS jsonb),
                            CAST(:geom_json AS jsonb)
                        )
                    """),
                    {
                        "name": name,
                        "geom_json": geom_json,
                        "properties": properties_json,
                    },
                )
                print(f"  Inserted: {name}")
            await session.commit()
        except Exception as e:
            await session.rollback()
            err = str(e)
            if "Connect" in err or "111" in err or "connection" in err.lower():
                print(
                    "Error: Cannot connect to PostgreSQL. Is the database running?\n"
                    "  e.g. docker-compose up -d db",
                    file=sys.stderr,
                )
            else:
                print(f"Error inserting: {e}", file=sys.stderr)
            return 1

    print(f"Done. {len(features)} shelter(s) are now on the map.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
