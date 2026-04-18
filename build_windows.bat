@echo off
setlocal

set "ROOT=%~dp0"
set "PYTHON=%ROOT%venv\Scripts\python.exe"
set "SPEC=%ROOT%skyforge_launcher.spec"
set "BUILD_REQ=%ROOT%requirements-build.txt"

if not exist "%PYTHON%" (
  echo [ERROR] Python venv not found: %PYTHON%
  echo Run setup.bat first.
  pause
  exit /b 1
)

if not exist "%SPEC%" (
  echo [ERROR] Missing spec file: %SPEC%
  pause
  exit /b 1
)

echo [INFO] Checking pip in build venv...
"%PYTHON%" -m pip --version >nul 2>&1
if errorlevel 1 goto bootstrap_pip
goto install_build_deps

:bootstrap_pip
echo [WARN] pip missing in venv. Bootstrapping...
"%PYTHON%" -m ensurepip --upgrade >nul 2>&1
if errorlevel 1 (
  echo [WARN] ensurepip failed. Trying fallback bootstrap...
  python -m pip --python "%PYTHON%" install pip setuptools wheel
  if errorlevel 1 (
    echo [ERROR] Failed to bootstrap pip in venv.
    pause
    exit /b 1
  )
)

:install_build_deps
echo [INFO] Installing build dependencies...
"%PYTHON%" -m pip install -r "%BUILD_REQ%"
if errorlevel 1 (
  echo [ERROR] Failed to install build dependencies.
  pause
  exit /b 1
)

echo [INFO] Building SkyforgeLauncher with PyInstaller...
"%PYTHON%" -m PyInstaller --noconfirm --clean "%SPEC%"
if errorlevel 1 (
  echo [ERROR] Build failed.
  pause
  exit /b 1
)

echo.
echo [OK] Build complete.
echo Output: %ROOT%dist\SkyforgeLauncher
pause
exit /b 0
