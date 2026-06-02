@echo off
setlocal

set "ROOT=%~dp0"
set "SRC_DIR=%ROOT%src"
set "FRONTEND_INDEX=%ROOT%webui_frontend\dist\index.html"

if not defined ROUTE_GRAPH_WEBUI_HOST set "ROUTE_GRAPH_WEBUI_HOST=127.0.0.1"
if not defined ROUTE_GRAPH_WEBUI_PORT set "ROUTE_GRAPH_WEBUI_PORT=8000"
set "BROWSER_HOST=%ROUTE_GRAPH_WEBUI_HOST%"
if "%BROWSER_HOST%"=="0.0.0.0" set "BROWSER_HOST=127.0.0.1"
set "BACKEND_HEALTH_URL=http://%BROWSER_HOST%:%ROUTE_GRAPH_WEBUI_PORT%/api/health"
set "APP_URL=http://%BROWSER_HOST%:%ROUTE_GRAPH_WEBUI_PORT%/"

if defined ROUTE_GRAPH_WEBUI_PYTHON (
  set "PYTHON_EXE=%ROUTE_GRAPH_WEBUI_PYTHON%"
) else (
  set "PYTHON_EXE=python"
)

"%PYTHON_EXE%" --version >nul 2>&1
if errorlevel 1 (
  echo Python was not found. Set ROUTE_GRAPH_WEBUI_PYTHON or add python to PATH.
  exit /b 1
)

if defined PYTHONPATH (
  set "PYTHONPATH=%SRC_DIR%;%PYTHONPATH%"
) else (
  set "PYTHONPATH=%SRC_DIR%"
)

if not defined ROUTE_GRAPH_WEBUI_DATA_DIR (
  if defined LOCALAPPDATA (
    set "ROUTE_GRAPH_WEBUI_DATA_DIR=%LOCALAPPDATA%\RouteGraphWebUI\data"
  ) else if defined APPDATA (
    set "ROUTE_GRAPH_WEBUI_DATA_DIR=%APPDATA%\RouteGraphWebUI\data"
  ) else (
    set "ROUTE_GRAPH_WEBUI_DATA_DIR=%ROOT%data"
  )
)
set "ROUTE_GRAPH_WEBUI_RELEASE=1"

if not exist "%FRONTEND_INDEX%" (
  echo Frontend build was not found: "%FRONTEND_INDEX%"
  echo Run "npm --prefix webui_frontend run build" before running start.bat.
  exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$port = [int]'%ROUTE_GRAPH_WEBUI_PORT%';" ^
  "$listeners = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue;" ^
  "if ($listeners) { Write-Host ('Port {0} is already in use. Set ROUTE_GRAPH_WEBUI_PORT or stop the existing process.' -f $port); exit 1 }" ^
  "exit 0"
if errorlevel 1 exit /b 1

echo Backend bind: %ROUTE_GRAPH_WEBUI_HOST%:%ROUTE_GRAPH_WEBUI_PORT%
echo Data directory: "%ROUTE_GRAPH_WEBUI_DATA_DIR%"
start "route_graph_api" cmd /k "cd /d ""%ROOT%"" && ""%PYTHON_EXE%"" -m uvicorn route_graph_webui.backend.server:app --host %ROUTE_GRAPH_WEBUI_HOST% --port %ROUTE_GRAPH_WEBUI_PORT%"

echo Waiting for backend readiness: %BACKEND_HEALTH_URL%
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$deadline = (Get-Date).AddSeconds(30);" ^
  "while ((Get-Date) -lt $deadline) {" ^
  "  try {" ^
  "    $response = Invoke-WebRequest -UseBasicParsing '%BACKEND_HEALTH_URL%' -TimeoutSec 2;" ^
  "    if ($response.StatusCode -eq 200) {" ^
  "      $health = $response.Content | ConvertFrom-Json;" ^
  "      if ($health.data_dir.writable -eq $true) { exit 0 }" ^
  "    }" ^
  "  } catch {}" ^
  "  Start-Sleep -Milliseconds 500" ^
  "}" ^
  "exit 1"

if errorlevel 1 (
  echo Backend did not become ready within 30 seconds.
  echo Open %APP_URL% manually after resolving the backend error.
  exit /b 1
) else (
  echo Backend is ready. Opening browser...
  start "" %APP_URL%
)

endlocal
