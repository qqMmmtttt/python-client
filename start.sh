#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -ne 3 ]; then
  echo "Usage: $0 <playerId> <host> <port>" >&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLAYER_ID="$1"
HOST="$2"
PORT="$3"
PYTHON_BIN="${PYTHON_BIN:-python3}"

if ! command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
  PYTHON_BIN="python"
fi

exec "${PYTHON_BIN}" "${SCRIPT_DIR}/basic_client.py" \
  --player-id "${PLAYER_ID}" \
  --host "${HOST}" \
  --port "${PORT}"
