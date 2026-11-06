@echo off
REM ============================================================
REM  InsaneVoice - one-time setup for Windows
REM  Creates venv, installs deps, clones engines, gets models.
REM ============================================================
setlocal
cd /d "%~dp0\.."

echo.
echo  InsaneVoice setup
echo  =================
echo.

REM ---- python check ----
where python >nul 2>nul
if errorlevel 1 (
  echo [x] Python not found in PATH. Install Python 3.10+ from python.org
  pause & exit /b 1
)

REM ---- ffmpeg check ----
where ffmpeg >nul 2>nul
if errorlevel 1 (
  echo [!] ffmpeg not found. Install it:  winget install Gyan.FFmpeg
  echo     then re-open this terminal and run setup again.
  pause & exit /b 1
)

REM ---- venv ----
if not exist ".venv\Scripts\python.exe" (
  echo [1/5] Creating virtual environment...
  python -m venv .venv || (echo [x] venv failed & pause & exit /b 1)
) else (
  echo [1/5] Virtual environment exists - ok.
)
set PY=.venv\Scripts\python.exe

echo [2/5] Installing PyTorch (CPU)...
%PY% -m pip show torch >nul 2>nul || %PY% -m pip install torch --index-url https://download.pytorch.org/whl/cpu

echo [3/5] Installing dependencies...
%PY% -m pip install -q -r requirements.txt

echo [4/5] Fetching engine sources (OpenVoice + MeloTTS)...
if not exist "third_party\OpenVoice" git clone --depth 1 https://github.com/myshell-ai/OpenVoice.git third_party\OpenVoice
if not exist "third_party\MeloTTS" git clone --depth 1 https://github.com/myshell-ai/MeloTTS.git third_party\MeloTTS

echo [5/5] Patching MeloTTS + downloading models (~330 MB)...
%PY% scripts\patch_melotts.py
%PY% scripts\download_models.py
if errorlevel 1 (
  echo [x] Model download failed - check your internet and run:
  echo     %PY% scripts\download_models.py
  pause & exit /b 1
)

echo.
echo  Setup complete!  Run scripts\start_windows.bat to launch.
echo.
pause
