#!/bin/bash
# Cleo Turbo launcher. Backend (.venv) + frontend in interactive Terminal shells.
# NOTE: forces NODE_ENV=development for the frontend (shell sets it to production globally).
/usr/bin/osascript <<'OSA'
tell application "Terminal"
    activate
    do script "cd '/Users/brandonolsen/Library/CloudStorage/OneDrive-CanadianCommercial/03_Admin/06_Operations [SOPs, Mind Maps, Software Logins, Business Planning]/00_Cleo Operating System/cleo-turbo' && clear && echo 'Cleo Backend -> http://localhost:8099' && if [ -x './.venv/bin/python' ]; then ./.venv/bin/python -m uvicorn cleo.web.app:app --reload --port 8099; else echo 'No .venv found — run setup-cleo.command first.'; fi"
    delay 0.6
    do script "cd '/Users/brandonolsen/Library/CloudStorage/OneDrive-CanadianCommercial/03_Admin/06_Operations [SOPs, Mind Maps, Software Logins, Business Planning]/00_Cleo Operating System/cleo-turbo/frontend' && export NODE_ENV=development && clear && echo 'Cleo Frontend -> http://localhost:5174' && npm run dev"
end tell
OSA
sleep 6
open "http://localhost:5174"
