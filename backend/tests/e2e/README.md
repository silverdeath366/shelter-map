# E2E Test Interface

## Simple HTML Test Page

This is a **minimal fullstack** test interface for the GeoJSON Ingestion API.

### Purpose

- ✅ **DevOps Testing**: Quick way to test API endpoints
- ✅ **API Validation**: Verify uploads and health checks work
- ✅ **No Build Required**: Just open the HTML file in a browser
- ✅ **No Dependencies**: Pure HTML/CSS/JavaScript

### Usage

1. **Start port-forward** (if not already running):
   ```bash
   kubectl port-forward svc/geojson-ingestion-service 3000:80
   ```

2. **Open the HTML file**:
   ```bash
   # Option 1: Open directly in browser
   open tests/e2e/api-test.html
   
   # Option 2: Serve with Python
   cd tests/e2e
   python3 -m http.server 8080
   # Then open http://localhost:8080/api-test.html
   ```

3. **Configure**:
   - Set API URL (default: http://localhost:3000)
   - Set API Key (saved in localStorage)

4. **Test**:
   - Click "Test /healthz" to check service health
   - Select a GeoJSON file and click "Upload File"
   - View results in the output area

### Features

- ✅ Health check testing
- ✅ File upload testing
- ✅ Real-time status indicator
- ✅ Statistics display
- ✅ Error handling
- ✅ Configuration persistence (localStorage)
- ✅ Clean, modern UI

### Files

- `api-test.html` - Main test interface
- `README.md` - This file

### Notes

- This is a **simple HTML file** - no frameworks, no build process
- Perfect for **DevOps testing** and **API validation**
- Can be used for **demo purposes**
- Configuration is saved in browser localStorage

---

**Purpose**: DevOps Testing Tool
**Complexity**: Minimal (Simple HTML)
**Dependencies**: None

