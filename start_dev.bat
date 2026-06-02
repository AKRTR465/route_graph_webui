@echo off
setlocal

set "ROOT=%~dp0"
set "SRC_DIR=%ROOT%src"
set "FRONTEND_DIR=%ROOT%webui_frontend"

if not defined ROUTE_GRAPH_WEBUI_HOST set "ROUTE_GRAPH_WEBUI_HOST=127.0.0.1"
if not defined ROUTE_GRAPH_WEBUI_PORT set "ROUTE_GRAPH_WEBUI_PORT=8000"
if not defined ROUTE_GRAPH_WEBUI_VITE_HOST set "ROUTE_GRAPH_WEBUI_VITE_HOST=127.0.0.1"
set "BROWSER_HOST=%ROUTE_GRAPH_WEBUI_HOST%"
if "%BROWSER_HOST%"=="0.0.0.0" set "BROWSER_HOST=127.0.0.1"
set "BACKEND_HEALTH_URL=http://%BROWSER_HOST%:%ROUTE_GRAPH_WEBUI_PORT%/api/health"
set "FRONTEND_URL=http://%ROUTE_GRAPH_WEBUI_VITE_HOST%:5173"
if "%ROUTE_GRAPH_WEBUI_VITE_HOST%"=="0.0.0.0" set "FRONTEND_URL=http://127.0.0.1:5173"

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
where node >nul 2>&1
if errorlevel 1 (
  echo Node.js was not found. Install Node.js or add node to PATH.
  exit /b 1
)
where npm >nul 2>&1
if errorlevel 1 (
  echo npm was not found. Install npm or add it to PATH.
  exit /b 1
)

if not defined ROUTE_GRAPH_WEBUI_DATA_DIR (
  set "ROUTE_GRAPH_WEBUI_DATA_DIR=%ROOT%data"
)
if not defined VITE_API_BASE (
  set "VITE_API_BASE=http://%BROWSER_HOST%:%ROUTE_GRAPH_WEBUI_PORT%"
)

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ports = @([int]'%ROUTE_GRAPH_WEBUI_PORT%', 5173);" ^
  "foreach ($port in $ports) {" ^
  "  $listeners = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue;" ^
  "  if ($listeners) { Write-Host ('Port {0} is already in use. Stop the existing process or change the port.' -f $port); exit 1 }" ^
  "}" ^
  "exit 0"
if errorlevel 1 exit /b 1

echo Backend bind: %ROUTE_GRAPH_WEBUI_HOST%:%ROUTE_GRAPH_WEBUI_PORT%
echo Data directory: "%ROUTE_GRAPH_WEBUI_DATA_DIR%"
start "route_graph_api" cmd /k "cd /d ""%ROOT%"" && ""%PYTHON_EXE%"" -m uvicorn route_graph_webui.backend.server:app --reload --host %ROUTE_GRAPH_WEBUI_HOST% --port %ROUTE_GRAPH_WEBUI_PORT%"

echo Waiting for backend readiness: %BACKEND_HEALTH_URL%
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$deadline = (Get-Date).AddSeconds(30);" ^
  "while ((Get-Date) -lt $deadline) {" ^
  "  try {" ^
  "    $response = Invoke-WebRequest -UseBasicParsing '%BACKEND_HEALTH_URL%' -TimeoutSec 2;" ^
  "    if ($response.StatusCode -eq 200) { exit 0 }" ^
  "  } catch {}" ^
  "  Start-Sleep -Milliseconds 500" ^
  "}" ^
  "exit 1"

if errorlevel 1 (
  echo Backend did not become ready within 30 seconds. Starting frontend anyway.
) else (
  echo Backend is ready.
)

start "route_graph_webui_frontend" cmd /k "cd /d ""%FRONTEND_DIR%"" && npm run dev"

echo Waiting for frontend readiness: %FRONTEND_URL%
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$deadline = (Get-Date).AddSeconds(30);" ^
  "while ((Get-Date) -lt $deadline) {" ^
  "  try {" ^
  "    $response = Invoke-WebRequest -UseBasicParsing '%FRONTEND_URL%' -TimeoutSec 2;" ^
  "    if ($response.StatusCode -eq 200) { exit 0 }" ^
  "  } catch {}" ^
  "  Start-Sleep -Milliseconds 500" ^
  "}" ^
  "exit 1"

if errorlevel 1 (
  echo Frontend did not become ready within 30 seconds. Please open %FRONTEND_URL% manually.
) else (
  echo Frontend is ready. Opening browser...
  start "" %FRONTEND_URL%
)

endlocal
