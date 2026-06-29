#!/bin/bash
# ============================================================
#  Cleo Turbo — one-time setup for this Mac
#  Installs Node + a Python backend environment, then wires up
#  the project so the Dock app (Cleo Turbo.app) can run it.
#  Safe to re-run. Double-click to start.
# ============================================================

cd "$(dirname "$0")" || { echo "Cannot find project folder"; exit 1; }
REPO="$(pwd)"
echo "Project: $REPO"
echo

step() { echo; echo "==> $1"; }

# --- 1. Homebrew ---------------------------------------------------
step "Checking for Homebrew (package manager)"
if ! command -v brew >/dev/null 2>&1; then
  # Common install location for Apple Silicon; load it if present.
  if [ -x /opt/homebrew/bin/brew ]; then
    eval "$(/opt/homebrew/bin/brew shellenv)"
  elif [ -x /usr/local/bin/brew ]; then
    eval "$(/usr/local/bin/brew shellenv)"
  fi
fi
if ! command -v brew >/dev/null 2>&1; then
  echo "Homebrew is not installed. Installing it now."
  echo "You will be asked for your Mac login password (typing is hidden)."
  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)" || {
    echo "Homebrew install failed. Re-run this file once it's resolved."; exit 1; }
  # Load brew for the rest of this script.
  if [ -x /opt/homebrew/bin/brew ]; then eval "$(/opt/homebrew/bin/brew shellenv)"; fi
  if [ -x /usr/local/bin/brew ]; then eval "$(/usr/local/bin/brew shellenv)"; fi
fi
echo "Homebrew: $(command -v brew)"

# Make sure future Terminal sessions can find brew-installed tools.
BREW_LINE='eval "$('"$(command -v brew)"' shellenv)"'
if ! grep -qF "$BREW_LINE" "$HOME/.zprofile" 2>/dev/null; then
  echo "$BREW_LINE" >> "$HOME/.zprofile"
  echo "Added Homebrew to ~/.zprofile (so npm/python are on PATH next time)."
fi

# --- 2. Node + Python ---------------------------------------------
step "Installing Node and Python 3.12 (skips anything already present)"
brew install node python@3.12 || { echo "brew install failed"; exit 1; }
echo "node: $(command -v node)  ($(node -v 2>/dev/null))"
echo "npm:  $(command -v npm)   ($(npm -v 2>/dev/null))"

PYBIN="$(brew --prefix)/bin/python3.12"
[ -x "$PYBIN" ] || PYBIN="python3.12"
echo "python: $PYBIN  ($($PYBIN --version 2>/dev/null))"

# --- 3. Python virtual environment --------------------------------
step "Creating the backend environment (.venv) and installing dependencies"
if [ ! -d "$REPO/.venv" ]; then
  "$PYBIN" -m venv "$REPO/.venv" || { echo "venv creation failed"; exit 1; }
fi
"$REPO/.venv/bin/python" -m pip install --upgrade pip
"$REPO/.venv/bin/python" -m pip install -r "$REPO/requirements.txt" || {
  echo "pip install failed"; exit 1; }
echo "Backend dependencies installed."

# --- 4. Frontend dependencies (clean reinstall) -------------------
step "Installing frontend dependencies (rebuilding for this Mac)"
# node_modules copied from the old Mac may be the wrong CPU architecture,
# so remove and reinstall against the lockfile.
cd "$REPO/frontend" || { echo "no frontend folder"; exit 1; }
rm -rf node_modules
if [ -f package-lock.json ]; then npm ci || npm install; else npm install; fi
cd "$REPO" || exit 1
echo "Frontend dependencies installed."

# --- Done ----------------------------------------------------------
echo
echo "============================================================"
echo " Setup complete."
echo " You can now start the app with the Cleo Turbo Dock icon,"
echo " or by double-clicking start-cleo.command."
echo "============================================================"
echo
read -n 1 -s -r -p "Press any key to close this window."
echo
