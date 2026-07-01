#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
: "${OLLAMA_MODEL:=gemma4:12b}"
: "${OLLAMA_URL:=http://127.0.0.1:11434}"
python3 tools/ai_infer_gemma_ollama.py --host 0.0.0.0 --port 8090 --model "$OLLAMA_MODEL" --ollama-url "$OLLAMA_URL"
