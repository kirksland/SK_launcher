@echo off
setlocal

set "ROOT=%~dp0"
set "FRESH_DIR=%ROOT%.tmp"
set "FRESH_SETTINGS=%FRESH_DIR%\fresh_settings.json"

if not exist "%FRESH_DIR%" mkdir "%FRESH_DIR%"

if /I "%~1"=="reset" (
  if exist "%FRESH_SETTINGS%" del "%FRESH_SETTINGS%"
)

set "SKYFORGE_SETTINGS_PATH=%FRESH_SETTINGS%"

echo [INFO] Launching Skyforge in fresh-config test mode
echo [INFO] Settings file: %SKYFORGE_SETTINGS_PATH%
call "%ROOT%run_launcher.bat"
