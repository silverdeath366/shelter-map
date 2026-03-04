# CityGuard Dashboard

Minimal single-page map for CityGuard: restricted zones, violations, and safe scooters.

- **Restricted zones** → red polygons  
- **Violations** → red dots  
- **Safe scooters** → green dots  

Data refreshes every 2 seconds from the CityGuard API.

## Setup

1. **Mapbox token**  
   Use a Mapbox access token (e.g. from Mapbox account).  
   Before opening the page, set in the console or inject when serving:
   - `window.MAPBOX_ACCESS_TOKEN = 'pk....'`

2. **API base**  
   If the dashboard is not served from the same origin as the API:
   - `window.CITYGUARD_API_BASE = 'https://your-api-host'`

3. **API key** (if CityGuard uses API key auth):
   - `window.CITYGUARD_API_KEY = 'your-key'`

## Running locally

Serve the folder (e.g. `python3 -m http.server 8080` in `apps/cityguard-dashboard/`), then open the page and in the browser console run:

```js
window.MAPBOX_ACCESS_TOKEN = 'YOUR_MAPBOX_TOKEN';
location.reload();
```

Or use `env.example` and a small server that injects the token into the HTML.

## API endpoints (geojson-ingestion)

- `GET /cityguard/zones` – GeoJSON FeatureCollection of restricted zones  
- `GET /cityguard/violations` – list of violation records (lat, lon, scooter_id, zone_name)  
- `GET /cityguard/active` – list of safe scooter positions (last non-violation pings)  

All are mounted under `/cityguard` for ingress; auth same as CityGuard (API key or dev_open).
