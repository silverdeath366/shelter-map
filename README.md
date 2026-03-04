# Shelter Map

Standalone copy of the GeoJSON/CityGuard map app for use as a **shelter map**: show shelter locations, details, and let users find the closest shelter and navigate (e.g. open in Google Maps).

## Structure

- **`backend/`** – FastAPI + Postgres/PostGIS API (from geojson-ingestion). GeoJSON CRUD, bbox/nearby queries, JWT + API key auth, CityGuard-style zones/violations endpoints.
- **`frontend/`** – Mapbox GL JS map (from cityguard-dashboard). Single-page app: enter Mapbox token + API URL, then view zones/points on the map.

## Quick start

### Backend

```bash
cd backend
cp env.example .env   # set DB, auth, etc.
python -m venv .venv && source .venv/bin/activate  # or: .venv\Scripts\activate on Windows
pip install -r requirements.txt
# Run Postgres (e.g. docker-compose up -d), then:
uvicorn app.main:app --reload --port 8005
```

See `backend/README.md` for full setup (DB, migrations, Cognito, etc.).

### Frontend

Open `frontend/index.html` in a browser (or serve the folder with any static server). On first load you’ll be asked for:

- **Mapbox access token** – from [Mapbox](https://account.mapbox.com/)
- **API base URL** – e.g. `http://localhost:8005` for local backend

Then the map loads and polls the API for zones/violations/active (or you can point it at shelter/features endpoints).

## Using for shelters

- Store shelters as **GeoJSON features** (Points) with e.g. `properties.type = 'shelter'`, plus capacity, address, etc.
- **Map**: use `GET /v1/features/bbox` or a dedicated shelters endpoint to feed the map.
- **Closest**: `GET /v1/features/nearby?lon=&lat=&radius=&limit=` returns features ordered by distance; first = closest.
- **Navigate**: add a “Open in Google Maps” link using `https://www.google.com/maps/dir/?api=1&destination=lat,lon`.

### Loading shelters from a CSV

To turn a spreadsheet (e.g. `Records.csv`) into pins on the map with info popups:

1. **CSV with coordinates** – The script expects columns for name, address, capacity, accessibility, and latitude/longitude (Hebrew headers like `קואורדינטות ציר x` / `קורדינטות ציר y` are supported).
2. From the **backend** directory (with venv activated and DB running):

   ```bash
   python scripts/load_shelters_from_csv.py path/to/Records.csv
   ```

   On WSL, if the file is in Windows Downloads:

   ```bash
   python scripts/load_shelters_from_csv.py /mnt/c/Users/TOSHIBA/Downloads/Records.csv
   ```

3. Open the frontend map and log in; shelters appear as green circles. Click a pin to see name, address, capacity, accessibility and a "Navigate" link.

### Test in Jerusalem (no CSV needed)

To try the map and **Find Closest Shelter** in Jerusalem without loading a CSV:

```bash
cd backend
.venv/bin/python scripts/seed_jerusalem_shelters.py
```

Then open the frontend with **`?test=jerusalem`** (e.g. `http://localhost:8080/index.html?test=jerusalem`). You’ll be placed in Jerusalem; green dots are shelters, and **Find Closest Shelter** will highlight the nearest one and show distance.

If you see no shelters in another area, either load shelter data for that region (e.g. CSV) or run the seed script and use `?test=jerusalem`. If shelters from a CSV appear in the wrong place (e.g. ocean), the CSV may use x=lon / y=lat instead of the script’s default; see the comment in `load_shelters_from_csv.py` about column mapping.

### Phase 1 — Verify shelters loaded

With the backend running (e.g. `uvicorn app.main:app --reload --port 8005`) and shelters loaded:

1. **List shelters**  
   Open or curl:
   - `http://localhost:8005/v1/shelters`  
   You should get a large JSON list (`features` + `total`).

2. **Nearby**  
   - `http://localhost:8005/v1/shelters/nearby?lon=35.21&lat=31.78&radius=2000&limit=5`  
   You should get a `FeatureCollection` with each feature having `distance_m` and `properties.name` (e.g. shelter name and distance in meters).

**Auth:** For quick verification use `AUTH_MODE=dev_open` and `ENV=development` in `.env` (no headers). Otherwise send `X-API-Key: YOUR_KEY` or `Authorization: Bearer <JWT>`.

Optional script (from `backend/`):

```bash
# With dev_open (no API_KEY needed)
./scripts/verify_shelters_phase1.sh

# With API key
API_KEY=your-secret-api-key ./scripts/verify_shelters_phase1.sh
```

## Origin

Copied from **devops-sandbox**:

- `apps/geojson-ingestion` → `backend/`
- `apps/cityguard-dashboard` → `frontend/`

You can adapt the frontend to shelters (login, shelter layer, closest + navigate) and keep or simplify the backend (e.g. add a `/shelters` filter).
