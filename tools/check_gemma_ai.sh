#!/usr/bin/env bash
set -euo pipefail
: "${OLLAMA_MODEL:=gemma4:12b}"
: "${OLLAMA_URL:=http://127.0.0.1:11434}"

if ! command -v ollama >/dev/null 2>&1; then
  echo "ollama not found" >&2
  exit 1
fi

if ! curl -fsS "$OLLAMA_URL/api/tags" >/dev/null; then
  echo "ollama API is not reachable at $OLLAMA_URL" >&2
  echo "start it with: ollama serve" >&2
  exit 1
fi

if ollama list | awk 'NR>1 {print $1}' | grep -Fx "$OLLAMA_MODEL" >/dev/null; then
  echo "model present: $OLLAMA_MODEL"
else
  echo "model missing: $OLLAMA_MODEL" >&2
  echo "pull on the GTX box with: ollama pull $OLLAMA_MODEL" >&2
  exit 2
fi

curl -s "${AI_ENDPOINT:-http://127.0.0.1:8090/health}" || true
