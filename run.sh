#!/usr/bin/env bash
# LexiGraph app runner.
# Creates/activates a venv, installs deps, checks .env, and starts the API.
#
# Usage:
#   ./run.sh            # install (first run) + start server on :8000
#   ./run.sh --no-install   # skip pip install (faster restarts)
set -euo pipefail

cd "$(dirname "$0")"

VENV=".venv"
PY="${PYTHON:-python3}"
HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8000}"
DO_INSTALL=1
[[ "${1:-}" == "--no-install" ]] && DO_INSTALL=0

# 1. Virtualenv
if [[ ! -d "$VENV" ]]; then
  echo "==> Creating virtualenv ($VENV)"
  "$PY" -m venv "$VENV"
fi
# shellcheck disable=SC1091
source "$VENV/bin/activate"

# 2. Dependencies (prefer the pinned lockfile for reproducibility)
if [[ "$DO_INSTALL" == "1" ]]; then
  echo "==> Installing dependencies"
  pip install -q --upgrade pip
  if [[ -f requirements.lock.txt ]]; then
    pip install -q -r requirements.lock.txt
  else
    pip install -q -r requirements.txt
  fi
fi

# 3. Config check
if [[ ! -f .env ]]; then
  echo "!! No .env found. Copy the template and fill in your keys:"
  echo "     cp .env.example .env"
  echo "   See the README (\"Getting the API keys\") for where to get each one."
  exit 1
fi

# 4. Launch
echo "==> Starting LexiGraph on http://$HOST:$PORT  (docs at /docs)"
exec uvicorn app.main:app --host "$HOST" --port "$PORT" --reload
