@echo off
setlocal
set "HERE=%~dp0"

where py >nul 2>&1
if errorlevel 1 (
  echo Python launcher "py" was not found.
  echo.
  echo Install Python 3 from https://www.python.org/downloads/
  echo During setup, enable:
  echo   - Add python.exe to PATH
  echo   - py launcher
  echo Do not use the Microsoft Store Python stub.
  echo.
  pause
  exit /b 1
)

pushd "%HERE%"
if errorlevel 1 (
  echo Failed to open "%HERE%"
  echo CMD cannot use a UNC path as the working directory without pushd.
  pause
  exit /b 1
)

echo Starting Audio Library from %CD%
echo Python: 
py -3 --version
echo.
py -3 "%HERE%server.py"
set ERR=%ERRORLEVEL%
if not %ERR%==0 (
  echo.
  echo py -3 failed with exit code %ERR%.
  echo Install Python 3 from python.org and ensure "py -3" works.
  echo Do not use the Microsoft Store python stub.
)
popd
pause
exit /b %ERR%
