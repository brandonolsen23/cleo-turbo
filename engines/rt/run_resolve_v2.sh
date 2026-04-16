#!/bin/bash
# Full resolve_v2 run — launches as background process with logging.
#
# Usage:
#   ./engines/rt/run_resolve_v2.sh                    # resume (skip already done)
#   ./engines/rt/run_resolve_v2.sh --reprocess         # redo all 155K
#   ./engines/rt/run_resolve_v2.sh --reprocess-unresolved  # redo only failed
#
# Monitor:
#   tail -f /tmp/resolve_v2.log
#   # or check progress:
#   grep -c '"method"' engines/rt/pipeline/parcel_links/*.json | tail -1

set -e
cd "$(dirname "$0")/../.."

LOG="/tmp/resolve_v2.log"
PIDFILE="/tmp/resolve_v2.pid"

# Check if already running
if [ -f "$PIDFILE" ]; then
    PID=$(cat "$PIDFILE")
    if kill -0 "$PID" 2>/dev/null; then
        echo "resolve_v2 is already running (PID $PID)"
        echo "Monitor: tail -f $LOG"
        exit 1
    fi
fi

echo "Starting resolve_v2 with args: $@"
echo "Log: $LOG"

# Use unbuffered Python output so log is readable in real-time
PYTHONUNBUFFERED=1 python3 -c "
import sys
sys.path.insert(0, '.')
sys.path.insert(0, 'engines/rt')
from parcel_resolver.resolve_v2 import run
run($( [ "$1" = "--reprocess" ] && echo "reprocess=True" || ([ "$1" = "--reprocess-unresolved" ] && echo "reprocess_unresolved=True" || echo "") ))
" > "$LOG" 2>&1 &

PID=$!
echo "$PID" > "$PIDFILE"
echo "Started PID $PID"
echo "Monitor: tail -f $LOG"

# Clean up PID file when process ends
(wait $PID 2>/dev/null; rm -f "$PIDFILE") &
