@echo off
setlocal
title Sidekick
cd /d "%~dp0"
echo.
echo Starting Sidekick...
echo.

if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" "scripts\launch.py" %*
    goto finished
)
where py >nul 2>nul
if not errorlevel 1 (
    py -3 "scripts\launch.py" %*
    goto finished
)
where python >nul 2>nul
if not errorlevel 1 (
    python "scripts\launch.py" %*
    goto finished
)
echo Python is needed for the first launch.
echo Install Python 3.11 or newer from https://www.python.org/downloads/windows/
echo Then double-click this file again.
echo.
pause
exit /b 1

:finished
set "sidekickExit=%errorlevel%"
if not "%sidekickExit%"=="0" (
    echo.
    echo Sidekick could not start. Read the message above, then try again.
    echo First launch needs internet, Python 3.11+ and Node.js LTS.
    echo Python: https://www.python.org/downloads/windows/
    echo Node.js: https://nodejs.org/en/download
    echo.
    pause
)
exit /b %sidekickExit%
