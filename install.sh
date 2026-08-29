#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"
REQUIRED_MODEL="${SHORTS_PIPELINE_OLLAMA_MODEL:-qwen2.5vl:7b}"

fail() { echo "ShortsPipeline installer: $*" >&2; exit 1; }
command -v "$PYTHON_BIN" >/dev/null || fail "Python 3.11+ is required. Set PYTHON_BIN if needed."
"$PYTHON_BIN" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)' || fail "Python 3.11+ is required."

VENV="$ROOT/.venv"
if [[ ! -x "$VENV/bin/python" ]]; then "$PYTHON_BIN" -m venv "$VENV"; fi
"$VENV/bin/python" -m pip install --upgrade pip
"$VENV/bin/python" -m pip install -r "$ROOT/requirements.txt"
"$VENV/bin/python" -m pip install -e "$ROOT"
"$VENV/bin/python" -c "import yt_dlp" || fail "yt-dlp was not installed inside .venv."

for tool in ffmpeg ffprobe; do command -v "$tool" >/dev/null || fail "$tool is required on PATH (Ubuntu: sudo apt-get update && sudo apt-get install -y ffmpeg)."; done
if command -v nvidia-smi >/dev/null; then nvidia-smi --query-gpu=name,driver_version --format=csv,noheader || fail "nvidia-smi could not verify the GPU/CUDA runtime."; else echo "WARNING: nvidia-smi is unavailable; GPU acceleration cannot be verified." >&2; fi
command -v ollama >/dev/null || fail "Ollama is required for VLM/reasoning/evaluation. Install/start it, then run: ollama pull $REQUIRED_MODEL"
ollama list | awk 'NR>1 {print $1}' | grep -Fx "$REQUIRED_MODEL" >/dev/null || fail "Required Ollama model is missing: $REQUIRED_MODEL. Run: ollama pull $REQUIRED_MODEL"

mkdir -p "$ROOT/workspace/downloads" "$ROOT/workspace/tmp"
echo "Installed in $VENV. Activate with: source $VENV/bin/activate"
