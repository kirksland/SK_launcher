@echo off
setlocal

set "ROOT=%~dp0"
set "PYTHON=%ROOT%venv\Scripts\python.exe"
set "PYTHONW=%ROOT%venv\Scripts\pythonw.exe"
set "MAIN=%ROOT%main.py"
set "PYSIDE6_DIR=%ROOT%venv\Lib\site-packages\PySide6"
set "QT_PLUGIN_PATH=%PYSIDE6_DIR%\plugins"
set "QT_MULTIMEDIA_PREFERRED_PLUGINS=windows"
set "PATH=%PYSIDE6_DIR%;%PATH%"

if not exist "%PYTHON%" (
  echo [ERROR] Python venv not found: %PYTHON%
  echo Please create the venv or update this path.
  pause
  exit /b 1
)

echo [INFO] Launching...
start "" "%PYTHONW%" "%MAIN%"
exit /b 0
