@echo off
title InsureDesk Agent
echo ============================================
echo   InsureDesk v1.0.0 — Insurance Agent Desktop
echo ============================================
echo.

REM Set paths
set APP_DIR=%~dp0
set DATA_DIR=%USERPROFILE%\.insuredesk

REM Create user data directory
if not exist "%DATA_DIR%" mkdir "%DATA_DIR%"
if not exist "%DATA_DIR%\logs" mkdir "%DATA_DIR%\logs"
if not exist "%DATA_DIR%\profiles" mkdir "%DATA_DIR%\profiles"
if not exist "%DATA_DIR%\config" mkdir "%DATA_DIR%\config"

REM Copy default config if not exists
if not exist "%DATA_DIR%\config\agent.yaml" (
    if exist "%APP_DIR%config\agent.yaml" (
        copy "%APP_DIR%config\agent.yaml" "%DATA_DIR%\config\agent.yaml"
    )
)

REM Install Playwright browser (first run only)
if not exist "%APP_DIR%browser\chrome-win" (
    echo [First run] Installing browser...
    "%APP_DIR%\InsureDesk-CLI.exe" --install-browser
)

echo Starting InsureDesk...
start "" "%APP_DIR%\InsureDesk.exe"

echo.
echo InsureDesk is running in the background.
echo Close the desktop window to stop.
echo.
echo Data directory: %DATA_DIR%
echo Logs: %DATA_DIR%\logs\
