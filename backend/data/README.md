# Put your shelter CSV here

Your workspace is on **Ubuntu** (remote). It cannot see your Windows PC’s `C:\Users\TOSHIBA\Downloads\`.

**To load Records.csv:**

1. **Upload the file** into this folder:
   - In Cursor: drag `Records.csv` from your PC into **`backend/data/`** in the file tree, or  
   - Right‑click `backend/data` → Upload / Add file → choose `Records.csv`.

2. **Run the loader** (in the terminal, from the repo root or from `backend`):
   ```bash
   cd backend
   .venv/bin/python scripts/load_shelters_from_csv.py data/Records.csv
   ```

If you put the file directly in `backend/` instead, use:
```bash
.venv/bin/python scripts/load_shelters_from_csv.py Records.csv
```
