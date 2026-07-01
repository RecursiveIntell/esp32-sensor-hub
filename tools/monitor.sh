#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
. .venv/bin/activate
PORT="${1:-/dev/ttyUSB0}"
pio device monitor --port "$PORT" -b 115200
