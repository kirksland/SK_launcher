@echo off
setlocal

set "ROOT=%~dp0"
set "PYTHON_CMD=python"
set "VENV_PY=%ROOT%venv\Scripts\python.exe"
set "REQ_FILE=%ROOT%requirements.txt"

echo [INFO] Skyforge setup
echo.

if not exist "%REQ_FILE%" (
  echo [ERROR] Missing requirements.txt
  pause
  exit /b 1
)

where %PYTHON_CMD% >nul 2>&1
if errorlevel 1 (
  if exist "%LocalAppData%\Programs\Python\Python313\python.exe" (
    set "PYTHON_PATH=%LocalAppData%\Programs\Python\Python313\python.exe"
    goto :python_found
  )
  if exist "%LocalAppData%\Programs\Python\Python312\python.exe" (
    set "PYTHON_PATH=%LocalAppData%\Programs\Python\Python312\python.exe"
    goto :python_found
  )
  if exist "%LocalAppData%\Programs\Python\Python311\python.exe" (
    set "PYTHON_PATH=%LocalAppData%\Programs\Python\Python311\python.exe"
    goto :python_found
  )
  echo [ERROR] Python not found.
  echo Install Python 3.11+ from python.org and check "Add python.exe to PATH".
  pause
  exit /b 1
)

for /f "delims=" %%P in ('where %PYTHON_CMD%') do (
  set "PYTHON_PATH=%%P"
  goto :python_found
)

:python_found
echo [INFO] Python: %PYTHON_PATH%
echo %PYTHON_PATH% | find /I "WindowsApps" >nul
if not errorlevel 1 (
  echo [ERROR] Windows Store Python alias detected.
  echo Install Python from python.org and re-run setup.bat.
  pause
  exit /b 1
)

"%PYTHON_PATH%" -V
if errorlevel 1 (
  echo [ERROR] Python command failed.
  pause
  exit /b 1
)

echo [INFO] Creating virtual environment...
"%PYTHON_PATH%" -m venv "%ROOT%venv"
if errorlevel 1 goto venv_fallback

echo [INFO] Upgrading pip...
"%VENV_PY%" -m pip install --upgrade pip
if errorlevel 1 (
  echo [ERROR] Failed to upgrade pip.
  pause
  exit /b 1
)

echo [INFO] Installing dependencies...
"%VENV_PY%" -m pip install -r "%REQ_FILE%"
if errorlevel 1 (
  echo [ERROR] Failed to install dependencies.
  pause
  exit /b 1
)

echo.
echo [OK] Setup complete.
echo Run run_launcher.bat to start Skyforge.
pause
exit /b 0

:venv_fallback
echo [WARN] venv failed during ensurepip. Trying fallback...
"%PYTHON_PATH%" -m venv --without-pip "%ROOT%venv"
if errorlevel 1 (
  echo [ERROR] Failed to create venv.
  echo Close Skyforge and retry.
  pause
  exit /b 1
)
"%PYTHON_PATH%" -m pip --python "%VENV_PY%" install pip setuptools wheel
if errorlevel 1 (
  echo [ERROR] Failed to bootstrap pip in venv.
  pause
  exit /b 1
)

echo [INFO] Installing dependencies...
"%VENV_PY%" -m pip install -r "%REQ_FILE%"
if errorlevel 1 (
  echo [ERROR] Failed to install dependencies.
  pause
  exit /b 1
)

echo.
echo [OK] Setup complete.
echo Run run_launcher.bat to start Skyforge.
pause
exit /b 0
