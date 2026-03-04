#!/usr/bin/env python3
"""
Insert many shelter points in Jerusalem so you can test the map with ?test=jerusalem
and use "Find Closest Shelter" without loading a CSV.

Run from backend dir (with venv activated and DB running):
  python scripts/seed_jerusalem_shelters.py

Coordinates are WGS84 (lon, lat). Jerusalem center ~ 35.21, 31.78.

Re-running this script only removes shelters with properties.source = 'seed'.
Shelters loaded from CSV (no source or source != 'seed') are kept.
"""
import asyncio
import json
import sys
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP_ROOT))

from sqlalchemy import text

from app.database import AsyncSessionLocal

# WGS84 [lon, lat] – Jerusalem area. Names/addresses are placeholder.
# Grid + named points so the map looks well covered.
def _jerusalem_shelters():
    out = [
        {"name": "Central Jerusalem Shelter 1", "address": "King George St 1", "capacity": "200", "lon": 35.2137, "lat": 31.7683},
        {"name": "Central Jerusalem Shelter 2", "address": "Jaffa Rd 50", "capacity": "150", "lon": 35.2180, "lat": 31.7800},
        {"name": "Jerusalem North Shelter", "address": "Shmuel HaNavi 20", "capacity": "100", "lon": 35.2200, "lat": 31.7900},
        {"name": "Jerusalem South Shelter", "address": "Hebron Rd 100", "capacity": "120", "lon": 35.2080, "lat": 31.7550},
        {"name": "Old City Area Shelter", "address": "Near Damascus Gate", "capacity": "80", "lon": 35.2305, "lat": 31.7815},
    ]
    # Add a grid of shelters across Jerusalem (lon 35.18–35.26, lat 31.74–31.82)
    areas = [
        ("Downtown", "Ben Yehuda", 35.21, 31.78),
        ("Rehavia", "Ramban St", 35.214, 31.775),
        ("Talpiot", "Pierre Koenig", 35.205, 31.752),
        ("Gilo", "Gilo Center", 35.185, 31.738),
        ("French Hill", "HaNassi", 35.235, 31.798),
        ("Har Nof", "Har Nof", 35.178, 31.788),
        ("East Jerusalem", "Salah ad-Din", 35.238, 31.782),
        ("Mamilla", "Mamilla", 35.223, 31.775),
        ("Beit Hanina", "Beit Hanina", 35.205, 31.832),
        ("Givat Ram", "Givat Ram", 35.208, 31.772),
        ("Mount Scopus", "Mount Scopus", 35.242, 31.792),
        ("Baka", "Derech Beit Lechem", 35.218, 31.758),
        ("Arnona", "Derech Hebron", 35.225, 31.752),
        ("Katamon", "HaPalmach", 35.212, 31.765),
        ("Ramat Eshkol", "Ramat Eshkol", 35.228, 31.802),
        ("Sanhedria", "Sanhedria", 35.215, 31.805),
        ("Geula", "Malchei Yisrael", 35.218, 31.788),
        ("Mea Shearim", "Mea Shearim", 35.222, 31.783),
        ("Musrara", "Musrara", 35.227, 31.778),
        ("Nachlaot", "Agripas", 35.217, 31.778),
    ]
    step_lon, step_lat = 0.008, 0.006
    n = 0
    for area_name, street, base_lon, base_lat in areas:
        for di in (-1, 0, 1):
            for dj in (-1, 0, 1):
                lon = round(base_lon + di * step_lon, 5)
                lat = round(base_lat + dj * step_lat, 5)
                if 35.17 <= lon <= 35.27 and 31.73 <= lat <= 31.84:
                    n += 1
                    out.append({
                        "name": f"Shelter {area_name} {n}",
                        "address": f"{street} area",
                        "capacity": str(80 + (n % 120)),
                        "lon": lon,
                        "lat": lat,
                    })
    return out

JERUSALEM_SHELTERS = _jerusalem_shelters()


async def main() -> int:
    async with AsyncSessionLocal() as session:
        try:
            # Remove only our seeded demo data (source=seed), never CSV-loaded shelters
            await session.execute(
                text("""
                    DELETE FROM geo_features
                    WHERE properties->>'type' = 'shelter' AND properties->>'source' = 'seed'
                """)
            )
            await session.commit()
            for s in JERUSALEM_SHELTERS:
                coords = [s["lon"], s["lat"]]
                geom = {"type": "Point", "coordinates": coords}
                props = {
                    "type": "shelter",
                    "source": "seed",
                    "name": s["name"],
                    "address": s["address"],
                    "capacity": s["capacity"],
                    "accessibility": "",
                }
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
                        "name": s["name"],
                        "geom_json": json.dumps(geom),
                        "properties": json.dumps(props),
                    },
                )
                print(f"  Inserted: {s['name']}")
            await session.commit()
        except Exception as e:
            await session.rollback()
            print(f"Error: {e}", file=sys.stderr)
            return 1
    print(f"Done. {len(JERUSALEM_SHELTERS)} Jerusalem shelters seeded. Open the map with ?test=jerusalem")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
