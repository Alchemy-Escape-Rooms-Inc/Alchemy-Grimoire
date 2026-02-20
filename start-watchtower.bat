@echo off
:: ============================================
:: WatchTower v2 - Startup Script
:: Pulls latest from GitHub, then launches app
:: ============================================

title WatchTower v2

set REPO_PATH=C:\Users\joshu\Repos\Alchemy-Grimoire

echo.
echo ========================================
echo   WatchTower v2 - Starting Up
echo   %date% %time%
echo ========================================
echo.

:: Pull latest code from GitHub
echo [1/2] Pulling latest from GitHub...
cd /d "%REPO_PATH%"
git pull origin main
if %ERRORLEVEL% NEQ 0 (
    echo WARNING: Git pull failed. Running with local version.
) else (
    echo Git pull successful.
)

echo.

:: Start WatchTower
echo [2/2] Launching WatchTower...
cd /d "%REPO_PATH%\watchtower-v2"
python app.py

:: If WatchTower crashes, keep window open so you can see the error
echo.
echo ========================================
echo   WatchTower has stopped.
echo   Press any key to close this window.
echo ========================================
pause >nul
