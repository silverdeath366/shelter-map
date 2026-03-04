# Phase 1 setup — get .env and test shelters

## 1. Get and fill `.env`

From the **backend** directory:

```bash
cp env.example .env
```

Then edit `.env` and set at least these (rest can stay as in `env.example`):

### Option A: Use Docker for Postgres only (easiest)

Start the DB:

```bash
docker compose up -d db
```

In `.env` set:

- `DB_HOST=localhost`
- `DB_PORT=5434`   (host port from docker-compose; container uses 5432)
- `DB_NAME=geospatial`
- `DB_USER=postgres`
- `DB_PASSWORD=postgres`
- `DB_SSLMODE=disable`
- `ENV=development`
- `AUTH_MODE=dev_open`

With `AUTH_MODE=dev_open` you don’t need API keys or JWT for Phase 1.

### Option B: Use existing host Postgres

- `DB_HOST=localhost`
- `DB_PORT=5432` (or your port)
- `DB_NAME=geojson_db` (or your DB name)
- `DB_USER=postgres`
- `DB_PASSWORD=<your password>`
- `DB_SSLMODE=prefer` or `disable`
- `ENV=development`
- `AUTH_MODE=dev_open`

Ensure the database exists and has the schema (run migrations or use the same schema as `init-db.sql`).

---

## 2. Install and run backend

```bash
cd backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8005
```

Leave this running.

---

## 3. Load shelters (if you have a CSV)

In another terminal, from `backend/` with venv activated:

```bash
python scripts/load_shelters_from_csv.py path/to/Records.csv
```

If you don’t have a CSV, the table may be empty and Phase 1 will return empty lists.

---

## 4. What you need to test (Phase 1)

1. **List shelters**  
   Open in browser or curl:
   - **http://localhost:8005/v1/shelters**  
   You should get JSON with `features` and `total` (can be empty if no data).

2. **Nearby**  
   - **http://localhost:8005/v1/shelters/nearby?lon=35.21&lat=31.78&radius=2000&limit=5**  
   You should get a FeatureCollection; each feature can have `distance_m` and `properties.name`.

If both return **200** and valid JSON → backend is ready for Phase 1.

Optional script (from `backend/`):

```bash
./scripts/verify_shelters_phase1.sh
```

With `AUTH_MODE=dev_open` you don’t need to set `API_KEY`.

---

## Summary: minimal `.env` for Phase 1 (Docker DB)

```env
DB_HOST=localhost
DB_PORT=5434
DB_NAME=geospatial
DB_USER=postgres
DB_PASSWORD=postgres
DB_SSLMODE=disable
ENV=development
AUTH_MODE=dev_open
```

Plus any other keys from `env.example` you want (e.g. `LOG_LEVEL=INFO`); the app will start with defaults for the rest.
