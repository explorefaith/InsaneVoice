#!/usr/bin/env bash
# InsaneVoice - one-time setup for macOS / Linux
set -e
cd "$(dirname "$0")/.."

echo ""
echo " InsaneVoice setup"
echo " ================="
echo ""

command -v python3 >/dev/null || { echo "[x] python3 not found"; exit 1; }
command -v ffmpeg >/dev/null || { echo "[x] ffmpeg not found - install it first (brew install ffmpeg / apt install ffmpeg)"; exit 1; }

if [ ! -x ".venv/bin/python" ]; then
  echo "[1/5] Creating virtual environment..."
  python3 -m venv .venv
else
  echo "[1/5] Virtual environment exists - ok."
fi
PY=.venv/bin/python

echo "[2/5] Installing PyTorch (CPU)..."
$PY -m pip show torch >/dev/null 2>&1 || $PY -m pip install torch --index-url https://download.pytorch.org/whl/cpu

echo "[3/5] Installing dependencies..."
$PY -m pip install -q -r requirements.txt

echo "[4/5] Fetching engine sources..."
[ -d third_party/OpenVoice ] || git clone --depth 1 https://github.com/myshell-ai/OpenVoice.git third_party/OpenVoice
[ -d third_party/MeloTTS ]   || git clone --depth 1 https://github.com/myshell-ai/MeloTTS.git third_party/MeloTTS

echo "[5/5] Patching MeloTTS + downloading models (~330 MB)..."
$PY scripts/patch_melotts.py
$PY scripts/download_models.py

echo ""
echo " Setup complete!  Run scripts/start.sh to launch."
