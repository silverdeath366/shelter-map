#!/usr/bin/env python3
"""
Build a complete Petah Tikva shelter CSV: use geocoded lat/lon when available,
otherwise use fallback coordinates (city center + jitter) so every shelter
appears on the map with at least an approximate location.

Reads:
  - data/petahtikva.csv (original, tab-separated, no header)
  - data/petahtikva_geocoded.csv (geocoded subset with lat, lon)

Writes:
  - data/petahtikva_full.csv (all rows with lat, lon; compatible with load_petah_tikva_sync.py)

Fallback: Petah Tikva center (32.09, 34.89) + small jitter per row so pins don't stack.
"""
import csv
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parent.parent
ORIGINAL = APP_ROOT / "data" / "petahtikva.csv"
GEOCODED = APP_ROOT / "data" / "petahtikva_geocoded.csv"
OUTPUT = APP_ROOT / "data" / "petahtikva_full.csv"

# Petah Tikva approximate center (WGS84)
PT_CENTER_LAT = 32.09
PT_CENTER_LON = 34.89
# Jitter step so fallback pins spread (about 200m)
JITTER = 0.002


def load_tsv(path: Path) -> list[list[str]]:
    rows = []
    with open(path, "r", encoding="utf-8", newline="") as f:
        for line in f:
            line = line.rstrip("\n\r")
            if not line.strip():
                continue
            rows.append([p.strip() for p in line.split("\t")])
    return rows


def load_geocoded(path: Path) -> list[dict]:
    with open(path, "r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def main() -> int:
    if not ORIGINAL.exists():
        print(f"Missing: {ORIGINAL}", file=__import__("sys").stderr)
        return 1
    if not GEOCODED.exists():
        print(f"Missing: {GEOCODED}. Run geocode_petah_tikva.py first.", file=__import__("sys").stderr)
        return 1

    orig = load_tsv(ORIGINAL)
    geocoded_list = load_geocoded(GEOCODED)

    # Map: normalised (neighbourhood, street) -> geocoded row
    def norm(s: str) -> str:
        return (s or "").strip()

    by_key = {}
    for g in geocoded_list:
        addr = norm(g.get("address") or "")
        if not addr or not g.get("lat") or not g.get("lon"):
            continue
        street_part = addr.split(",")[0].strip() if "," in addr else addr
        neighbourhood = norm(g.get("neighbourhood") or "")
        key = (neighbourhood, street_part)
        by_key[key] = g

    def find_geocoded(neighbourhood: str, street: str) -> dict | None:
        n, s = norm(neighbourhood), norm(street)
        if (n, s) in by_key:
            return by_key[(n, s)]
        for (nk, sk), row in by_key.items():
            if nk == n and sk and (s == sk or s.startswith(sk) or sk in s):
                return row
        return None

    fieldnames = [
        "name", "address", "lat", "lon", "capacity", "accessibility",
        "neighbourhood", "type", "shelter_type", "notes", "number", "sub_area", "status", "source"
    ]
    out_rows = []
    used_geocoded = 0
    fallback_count = 0

    for i, row in enumerate(orig):
        while len(row) < 8:
            row.append("")
        neighbourhood, street, type_, shelter_type, notes, number, sub_area, status = (
            row[0], row[1], row[2], row[3], row[4], row[5], row[6], row[7]
        )
        street = street.strip()
        if not street:
            continue

        g = find_geocoded(neighbourhood, street)
        use_fallback = True
        if g and g.get("lat") and g.get("lon"):
            try:
                lat = float(str(g["lat"]).replace(",", "."))
                lon = float(str(g["lon"]).replace(",", "."))
                use_fallback = False
                used_geocoded += 1
            except ValueError:
                pass
        if use_fallback:
            j = fallback_count
            lat = PT_CENTER_LAT + (j % 10) * JITTER - JITTER * 5
            lon = PT_CENTER_LON + (j // 10) * JITTER - JITTER * 3
            fallback_count += 1
            address = f"{street}, Petah Tikva, Israel"
            name = f"Petah Tikva {neighbourhood or 'Shelter'} {number or street}".strip()
            source = "fallback"
        else:
            address = (g.get("address") or f"{street}, Petah Tikva, Israel").strip()
            name = (g.get("name") or f"Petah Tikva {neighbourhood or 'Shelter'} {number or street}").strip()
            source = "geocoded"

        out_rows.append({
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
            "source": source,
        })

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(out_rows)

    print(f"Wrote {OUTPUT}: {len(out_rows)} shelters ({used_geocoded} geocoded, {fallback_count} fallback).")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
