#!/usr/bin/env python3
"""
Read backend/data/petahtikva.csv (tab-separated, no header), geocode each street
address to "Street, Petah Tikva, Israel" using Nominatim (OpenStreetMap), and write
backend/data/petahtikva_geocoded.csv with lat/lon for loading via load_shelters_from_csv.

Columns in petahtikva.csv: neighbourhood, street_address, type, shelter_type, notes, number, sub_area, status

Usage (from backend dir with venv activated):
  python scripts/geocode_petah_tikva.py [path/to/petahtikva.csv]
  python scripts/geocode_petah_tikva.py path/to/petahtikva.csv --limit 5   # test run

Output: backend/data/petahtikva_geocoded.csv (UTF-8, with header).
Nominatim allows 1 request per second; script sleeps 1.1s between requests.
"""
import csv
import sys
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP_ROOT))

# Optional: geopy may not be installed in minimal env
try:
    from geopy.geocoders import Nominatim
    from geopy.extra.rate_limiter import RateLimiter
except ImportError:
    print("Install geopy: pip install geopy", file=sys.stderr)
    sys.exit(1)

DEFAULT_INPUT = APP_ROOT / "data" / "petahtikva.csv"
OUTPUT_CSV = APP_ROOT / "data" / "petahtikva_geocoded.csv"
CITY = "Petah Tikva"
COUNTRY = "Israel"
DELAY_SEC = 1.1  # Nominatim policy: 1 req/sec


def normalize_street(s: str) -> str:
    """Clean street field for geocoding."""
    if not s or not s.strip():
        return ""
    s = s.strip()
    # Remove trailing/leading whitespace
    return s


def build_query(street: str) -> str:
    return f"{street}, {CITY}, {COUNTRY}"


def load_tsv(path: Path, encoding: str = "utf-8") -> list[list[str]]:
    """Load tab-separated file, no header. Each row is list of columns."""
    rows = []
    with open(path, "r", encoding=encoding, newline="") as f:
        for line in f:
            line = line.rstrip("\n\r")
            if not line.strip():
                continue
            parts = line.split("\t")
            rows.append([p.strip() for p in parts])
    return rows


def main() -> int:
    limit = None
    paths = []
    i = 1
    while i < len(sys.argv):
        a = sys.argv[i]
        if a == "--limit":
            i += 1
            if i < len(sys.argv):
                limit = int(sys.argv[i])
        elif a.startswith("--limit="):
            limit = int(a.split("=", 1)[1])
        else:
            paths.append(a)
        i += 1
    input_path = Path(paths[0]).resolve() if paths else DEFAULT_INPUT
    if not input_path.exists():
        print(f"Error: not found: {input_path}", file=sys.stderr)
        return 1

    rows = load_tsv(input_path)
    if limit is not None:
        rows = rows[:limit]
        print(f"Limiting to first {limit} rows (test run).")
    if not rows:
        print("No rows in input.", file=sys.stderr)
        return 0

    # Column indices: 0=neighbourhood, 1=street_address, 2=type, 3=shelter_type, 4=notes, 5=number, 6=sub_area, 7=status
    geolocator = Nominatim(user_agent="shelter-map-petah-tikva")
    geocode = RateLimiter(geolocator.geocode, min_delay_seconds=DELAY_SEC)

    out_path = OUTPUT_CSV
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # Output CSV header compatible with load_shelters_from_csv (LAT_KEYS, LON_KEYS, NAME_KEYS, ADDRESS_KEYS)
    fieldnames = [
        "name",
        "address",
        "lat",
        "lon",
        "capacity",
        "accessibility",
        "neighbourhood",
        "type",
        "shelter_type",
        "notes",
        "number",
        "sub_area",
        "status",
    ]

    seen_queries: dict[str, tuple[float, float]] = {}
    geocoded = 0
    failed = 0

    with open(out_path, "w", encoding="utf-8", newline="") as out:
        writer = csv.DictWriter(out, fieldnames=fieldnames)
        writer.writeheader()

        for i, row in enumerate(rows):
            while len(row) < 8:
                row.append("")
            neighbourhood, street_address, type_, shelter_type, notes, number, sub_area, status = (
                row[0], row[1], row[2], row[3], row[4], row[5], row[6], row[7]
            )
            street = normalize_street(street_address)
            if not street:
                failed += 1
                continue

            query = build_query(street)
            if query in seen_queries:
                lat, lon = seen_queries[query]
            else:
                try:
                    location = geocode(query)
                    if location is None:
                        failed += 1
                        continue
                    lat, lon = location.latitude, location.longitude
                    seen_queries[query] = (lat, lon)
                    geocoded += 1
                except Exception as e:
                    print(f"  Geocode failed for '{query}': {e}", file=sys.stderr)
                    failed += 1
                    continue

            # Name for map: neighbourhood + number or address
            name = f"Petah Tikva {neighbourhood or 'Shelter'} {number or street}".strip()
            address = f"{street}, {CITY}, {COUNTRY}"

            writer.writerow({
                "name": name,
                "address": address,
                "lat": lat,
                "lon": lon,
                "capacity": "",
                "accessibility": "",
                "neighbourhood": neighbourhood,
                "type": type_,
                "shelter_type": shelter_type,
                "notes": notes,
                "number": number,
                "sub_area": sub_area,
                "status": status,
            })

    print(f"Wrote {out_path}. Geocoded: {geocoded}, skipped/failed: {failed}, total rows: {len(rows)}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
