@echo off
cd /d "%~dp0"
where py >nul 2>&1
if errorlevel 1 (
  echo Install Python 3.14 x64 from https://www.python.org/downloads/windows/
  echo Or use the ready Windows ZIP: no Python required.
  pause
  exit /b 1
)
py -3.14 -m venv .venv
if errorlevel 1 goto error
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto error
echo Setup complete. Run Start.cmd.
pause
exit /b 0
:error
echo Setup failed. Please copy the error above when reporting a problem.
pause
exit /b 1
