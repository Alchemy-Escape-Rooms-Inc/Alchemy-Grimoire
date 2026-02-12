@echo off
REM ================================================================
REM  Alchemy Grimoire — Daily Regeneration Script
REM  Run this manually or via Windows Task Scheduler
REM ================================================================

echo.
echo ============================================
echo  ALCHEMY GRIMOIRE - Daily Regeneration
echo  %date% %time%
echo ============================================
echo.

REM --- Set your paths here ---
SET SCRIPT_DIR=%~dp0
SET PYTHON_PATH=python

REM --- Load environment from .env file ---
if exist "%SCRIPT_DIR%.env" (
    for /f "usebackq tokens=1,2 delims==" %%a in ("%SCRIPT_DIR%.env") do (
        REM Skip comments and empty lines
        echo %%a | findstr /r "^#" >nul || (
            if not "%%a"=="" if not "%%b"=="" set "%%a=%%b"
        )
    )
)

REM --- Check requirements ---
%PYTHON_PATH% --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found. Install from https://python.org
    echo Make sure to check "Add Python to PATH" during installation.
    pause
    exit /b 1
)

REM --- Install/upgrade dependencies ---
echo Installing dependencies...
%PYTHON_PATH% -m pip install --quiet --upgrade anthropic gitpython 2>nul

REM --- Run the regeneration ---
echo Starting Grimoire regeneration...
%PYTHON_PATH% "%SCRIPT_DIR%regenerate_grimoire.py" %*

if errorlevel 1 (
    echo.
    echo ERROR: Grimoire regeneration failed!
    echo Check the output above for details.
    echo.
    REM Log error for Task Scheduler
    echo %date% %time% - FAILED >> "%SCRIPT_DIR%grimoire_log.txt"
    exit /b 1
) else (
    echo.
    echo SUCCESS: Grimoire updated!
    echo %date% %time% - SUCCESS >> "%SCRIPT_DIR%grimoire_log.txt"
)

exit /b 0
