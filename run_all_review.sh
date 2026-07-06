#!/usr/bin/env bash
# macOS / Linux equivalent of run_all_review.bat.
# Runs the spreadsheet review and automatically resumes (skipping any file that
# crashes a native library) until every folder is processed.
set -uo pipefail
cd "$(dirname "$0")"

if [ $# -lt 3 ]; then
  echo "Usage: ./run_all_review.sh \"workbook.xlsx\" ./passports ./passports_output"
  exit 2
fi

WB="$1"; FOLDERS="$2"; OUT="$3"
source .venv/bin/activate

echo "=== Initial run ==="
python run_sheet_review.py --workbook "$WB" --folders-root "$FOLDERS" --output-root "$OUT" --config config.example.json
code=$?

attempts=0
while [ "$code" -ne 0 ] && [ "$attempts" -lt 80 ]; do
  attempts=$((attempts + 1))
  echo "=== Resume attempt $attempts (previous exit $code) ==="
  python run_sheet_review.py --workbook "$WB" --folders-root "$FOLDERS" --output-root "$OUT" --config config.example.json --resume
  code=$?
done

if [ "$code" -eq 0 ]; then
  echo "=== All folders processed. ==="
else
  echo "=== Stopped after $attempts attempts (exit $code); check the output folder. ==="
fi
