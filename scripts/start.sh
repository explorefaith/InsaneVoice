#!/usr/bin/env bash
# InsaneVoice - start the local server
cd "$(dirname "$0")/.."
[ -x ".venv/bin/python" ] || { echo "Run scripts/setup.sh first."; exit 1; }
( sleep 2 && open "http://127.0.0.1:8177" 2>/dev/null || xdg-open "http://127.0.0.1:8177" 2>/dev/null ) &
.venv/bin/python -W ignore -m uvicorn main:app --host 127.0.0.1 --port 8177 --app-dir backend
