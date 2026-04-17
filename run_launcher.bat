@echo off
setlocal

set "ROOT=%~dp0"
set "PYTHON=%ROOT%venv\Scripts\python.exe"
set "MAIN=%ROOT%main.py"
set "PYSIDE6_DIR=%ROOT%venv\Lib\site-packages\PySide6"

set "PYTHONHOME="
set "PYTHONPATH="
set "VIRTUAL_ENV="
set "PYTHONNOUSERSITE=1"
set "QT_PLUGIN_PATH=%PYSIDE6_DIR%\plugins"
set "QT_MULTIMEDIA_PREFERRED_PLUGINS=windows"
set "OPENCV_IO_ENABLE_OPENEXR=1"

if not exist "%PYTHON%" goto missing_python
if not exist "%MAIN%" goto missing_main

"%PYTHON%" -c "import sys" >nul 2>&1
if errorlevel 1 goto broken_venv

echo [INFO] Launching Skyforge...
echo -----------------------------
"%PYTHON%" "%MAIN%"
set "EXITCODE=%ERRORLEVEL%"
if not "%EXITCODE%"=="0" (
  echo [ERROR] Launcher exited with code %EXITCODE%
  pause
)
exit /b %EXITCODE%

:missing_python
echo [ERROR] Python venv not found: %PYTHON%
echo Run setup.bat first.
pause
exit /b 1

:missing_main
echo [ERROR] main.py not found: %MAIN%
pause
exit /b 1

:broken_venv
echo [ERROR] Python venv is broken and cannot start Python.
echo Re-run setup.bat to rebuild the environment.
pause
exit /b 1
