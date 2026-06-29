#!/bin/bash
# Cleo Turbo launcher. Backend (.venv) + frontend in interactive Terminal shells.
# NOTE: forces NODE_ENV=development for the frontend (shell sets it to production globally).
# Self-locating: works wherever this project folder lives.
REPO="$(cd "$(dirname "$0")" && pwd)"
/usr/bin/osascript <<OSA
tell application "Terminal"
    activate
    do script "cd '$REPO' && clear && echo 'Cleo Backend -> http://localhost:8099' && if [ -x './.venv/bin/python' ]; then ./.venv/bin/python -m uvicorn cleo.web.app:app --reload --port 8099; else echo 'No .venv found - run setup-cleo.command first.'; fi"
    delay 0.6
    do script "cd '$REPO/frontend' && export NODE_ENV=development && clear && echo 'Cleo Frontend -> http://localhost:5174' && npm run dev"
end tell
OSA
sleep 6
open "http://localhost:5174"
