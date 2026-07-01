#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
python3 tools/ai_infer_stub.py --host 0.0.0.0 --port 8090
