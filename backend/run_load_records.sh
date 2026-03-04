#!/bin/bash
# Load shelters from Records.csv
# 1) Put Records.csv in backend/data/ (drag from your PC into Cursor's backend/data folder)
# 2) Run:  ./run_load_records.sh   or:  .venv/bin/python scripts/load_shelters_from_csv.py data/Records.csv

cd "$(dirname "$0")"
CSV="data/Records.csv"
if [ ! -f "$CSV" ]; then
  echo "Records.csv not found in backend/data/"
  echo ""
  echo "Do this:"
  echo "  1. On your PC, open  C:\\Users\\TOSHIBA\\Downloads\\  and find Records.csv"
  echo "  2. In Cursor, in the left sidebar open folder  backend  then  data"
  echo "  3. Drag  Records.csv  from Downloads and drop it onto the  data  folder"
  echo "  4. Run again:  ./run_load_records.sh"
  echo ""
  exit 1
fi
.venv/bin/python scripts/load_shelters_from_csv.py "$CSV"
