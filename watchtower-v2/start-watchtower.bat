@echo off
:: ============================================
:: WatchTower v2 - Startup Script (LIVE copy)
:: Lives IN the live app folder so it can never resolve to the retired
:: OneDrive copy (the old bat next to that copy launched the wrong app
:: for weeks before it was hardcoded on 2026-07-11).
::
:: Desktop "WatchTower" shortcut points here. Double-click =
::   1. open the dashboard in the browser as soon as port 5000 answers
::   2. run app.py in this window (single-instance guard in app.py makes
::      a second click just open the browser and exit)
:: ============================================

title WatchTower v2

set APP_DIR=C:\Users\Alchemy\Alchemy-Grimoire\watchtower-v2
set DASH_URL=http://localhost:5000/game

cd /d "%APP_DIR%"

if not exist "app.py" (
    echo ERROR: Could not find app.py under:
    echo   %APP_DIR%
    echo.
    pause
    exit /b 1
)

echo.
echo ========================================
echo   WatchTower v2 - Starting Up
echo   %date% %time%
echo ========================================
echo.
echo Launching WatchTower dashboard...
echo   %DASH_URL%
echo.

:: Browser opener rides in the background: poll port 5000 (up to 60s),
:: then open the dashboard. If WatchTower is already up, opens instantly.
start "" /b powershell -NoProfile -WindowStyle Hidden -Command ^
  "for ($i=0; $i -lt 120; $i++) { try { $c = New-Object Net.Sockets.TcpClient; $c.Connect('127.0.0.1', 5000); $c.Close(); Start-Process '%DASH_URL%'; exit } catch { Start-Sleep -Milliseconds 500 } }"

python app.py

echo.
echo ========================================
echo   WatchTower has stopped.
echo   Press any key to close this window.
echo ========================================
pause >nul
