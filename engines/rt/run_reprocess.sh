#!/bin/bash
# Auto-restart wrapper for resolve_v2 --reprocess
# Waits 10 minutes between throttle stops and relaunches automatically.
# Usage: cd ~/cleo-turbo/engines/rt && bash run_reprocess.sh

LOG=~/reprocess.log
WAIT_MINUTES=10

echo "=== Reprocess wrapper started at $(date) ===" | tee -a "$LOG"

while true; do
    echo "" | tee -a "$LOG"
    echo "=== Run starting at $(date) ===" | tee -a "$LOG"

    python3 -u -m parcel_resolver.resolve_v2 --reprocess 2>&1 | tee -a "$LOG"
    EXIT_CODE=${PIPESTATUS[0]}

    # Check if it finished cleanly (all records done)
    if grep -q "Pending:           0" <(tail -20 "$LOG"); then
        echo "" | tee -a "$LOG"
        echo "=== ALL DONE at $(date) ===" | tee -a "$LOG"
        break
    fi

    # Check if it was a throttle stop (exit code 0 but not finished)
    if [ $EXIT_CODE -eq 0 ]; then
        echo "" | tee -a "$LOG"
        echo "=== Throttled. Waiting ${WAIT_MINUTES} minutes before restart... ===" | tee -a "$LOG"
        sleep $(( WAIT_MINUTES * 60 ))
    else
        # Unexpected error or Ctrl+C
        echo "" | tee -a "$LOG"
        echo "=== Stopped with exit code $EXIT_CODE at $(date) ===" | tee -a "$LOG"
        echo "=== Not auto-restarting. Review the log and restart manually. ===" | tee -a "$LOG"
        break
    fi
done
