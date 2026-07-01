#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
. .venv/bin/activate
ENV_NAME="${1:-esp32dev}"
PORT="${2:-}"
if [[ -n "$PORT" ]]; then
  pio run -e "$ENV_NAME" -t upload --upload-port "$PORT"
else
  pio run -e "$ENV_NAME" -t upload
fi
