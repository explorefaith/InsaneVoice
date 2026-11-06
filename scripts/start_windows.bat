@echo off
REM InsaneVoice - start the local server and open the studio
cd /d "%~dp0\.."

if not exist ".venv\Scripts\python.exe" (
  echo Run scripts\setup_windows.bat first.
  pause & exit /b 1
)

start "" http://127.0.0.1:8177
.venv\Scripts\python.exe -W ignore -m uvicorn main:app --host 127.0.0.1 --port 8177 --app-dir backend
