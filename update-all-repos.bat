@echo off
:: ============================================
:: Daily Repo Update - Runs at 6:00 AM
:: Pulls latest for ALL repos in the Repos folder
:: ============================================

set REPOS_DIR=C:\Users\joshu\Repos
set LOG_FILE=%REPOS_DIR%\update-log.txt

echo ======================================== >> "%LOG_FILE%"
echo Repo Update - %date% %time% >> "%LOG_FILE%"
echo ======================================== >> "%LOG_FILE%"

:: Loop through every folder in Repos that contains a .git directory
for /d %%D in ("%REPOS_DIR%\*") do (
    if exist "%%D\.git" (
        echo Updating: %%~nxD >> "%LOG_FILE%"
        cd /d "%%D"
        git pull origin main >> "%LOG_FILE%" 2>&1
        if %ERRORLEVEL% NEQ 0 (
            echo   FAILED: %%~nxD >> "%LOG_FILE%"
        ) else (
            echo   OK: %%~nxD >> "%LOG_FILE%"
        )
        echo. >> "%LOG_FILE%"
    )
)

echo Update complete. >> "%LOG_FILE%"
echo. >> "%LOG_FILE%"
