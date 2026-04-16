#!/bin/bash
# Full RT pipeline: extract → classify → normalize → resolve → compile → rebuild
# Runs everything unattended, logs to /tmp/rt_full_pipeline.log
set -e

# Use script directory to find project root
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

cd "$SCRIPT_DIR"

echo "=== STAGE 1: Extract + Assemble ==="
echo "$(date): Starting extract+assemble..."
python3 run_pipeline.py
echo "$(date): Extract+assemble done."
echo ""

echo "=== STAGE 2: Classifier ==="
echo "$(date): Starting classifier..."
python3 run_classifier.py
echo "$(date): Classifier done."
echo ""

echo "=== STAGE 3-5: run_all.py (normalize → resolve_v2 → compile → rebuild) ==="
echo "$(date): Starting run_all.py orchestrator..."
cd "$PROJECT_ROOT"
python3 engines/rt/run_all.py
echo "$(date): Full pipeline complete!"
echo ""

echo "=== FINAL COUNTS ==="
python3 -c "
import sqlite3
conn = sqlite3.connect('data/cleo.db')
for t in ['properties','transactions','contacts','groups','pois','gw_assessments','gw_sales_history']:
    try:
        n = conn.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0]
        print(f'  {t}: {n:,}')
    except: pass
conn.close()
"
echo ""
echo "$(date): ALL DONE!"
