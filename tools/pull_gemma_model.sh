#!/usr/bin/env bash
set -euo pipefail
: "${OLLAMA_MODEL:=gemma4:12b}"
ollama pull "$OLLAMA_MODEL"
ollama show "$OLLAMA_MODEL" | sed -n '1,80p'
