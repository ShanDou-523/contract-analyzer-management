@echo off
setlocal

title Contract Analysis Management System
cd /d "%~dp0"

set "APP_URL=http://127.0.0.1:5173"
set "PYTHON_EXE=python_backend\.venv\Scripts\python.exe"

echo [Contract Analyzer] Checking the development environment...

if not exist "package.json" (
    echo [ERROR] package.json was not found next to this script.
    goto :failed
)

where node.exe >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Node.js is not installed or is not available in PATH.
    echo         Install Node.js 20 or newer, then run this script again.
    goto :failed
)

node.exe -e "process.exit(Number(process.versions.node.split('.')[0]) >= 20 ? 0 : 1)"
if errorlevel 1 (
    echo [ERROR] Node.js 20 or newer is required.
    goto :failed
)

where npm.cmd >nul 2>&1
if errorlevel 1 (
    echo [ERROR] npm is not available in PATH.
    goto :failed
)

if not exist "%PYTHON_EXE%" (
    echo [ERROR] Python virtual environment was not found:
    echo         %PYTHON_EXE%
    echo         Follow the setup commands in README.md first.
    goto :failed
)

"%PYTHON_EXE%" -c "import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 11) else 1)"
if errorlevel 1 (
    echo [ERROR] The project virtual environment must use Python 3.11.
    goto :failed
)

if not exist "node_modules\.bin\electron.cmd" goto :missing_node_modules
if not exist "node_modules\.bin\concurrently.cmd" goto :missing_node_modules
if not exist "node_modules\.bin\vite.cmd" goto :missing_node_modules

powershell.exe -NoLogo -NoProfile -Command "$busy = Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue | Where-Object { $_.LocalPort -in 5173, 5768 }; if ($busy) { $busy | ForEach-Object { Write-Host ('[ERROR] Port {0} is already in use by PID {1}.' -f $_.LocalPort, $_.OwningProcess) }; exit 1 }"
if errorlevel 1 (
    echo         Close the existing Contract Analyzer services or free the ports, then retry.
    goto :failed
)

if /i "%~1"=="--check" (
    echo [OK] All startup checks passed.
    exit /b 0
)

echo [Contract Analyzer] Building Electron entry files...
call npm.cmd run build:main
if errorlevel 1 goto :command_failed

call npm.cmd run build:preload
if errorlevel 1 goto :command_failed

set "ELECTRON_RENDERER_URL=%APP_URL%"

echo.
echo [Contract Analyzer] Starting the application...
echo [Contract Analyzer] Renderer: %APP_URL%
echo [Contract Analyzer] Press Ctrl+C in this window to stop all development services.
echo.

call "node_modules\.bin\concurrently.cmd" --kill-others-on-fail --kill-others "npm.cmd run dev:renderer -- --host 127.0.0.1" "node_modules\.bin\electron.cmd ."
set "EXIT_CODE=%ERRORLEVEL%"

if not "%EXIT_CODE%"=="0" (
    echo.
    echo [ERROR] Contract Analyzer stopped with exit code %EXIT_CODE%.
    goto :failed
)

echo.
echo [Contract Analyzer] Application stopped.
exit /b 0

:missing_node_modules
echo [ERROR] Frontend dependencies are missing.
echo         Run npm install in this directory, then run this script again.
goto :failed

:command_failed
echo.
echo [ERROR] A build command failed. Review the output above.

:failed
echo.
if /i "%~1"=="--check" exit /b 1
pause
exit /b 1
