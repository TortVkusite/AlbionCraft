@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (
  echo Run Setup.cmd first, or download the ready Windows ZIP.
  pause
  exit /b 1
)
".venv\Scripts\pythonw.exe" -m app.main
