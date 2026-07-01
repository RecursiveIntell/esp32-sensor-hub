#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
python3 tools/sensor_receiver.py --host 0.0.0.0 --port 8088
