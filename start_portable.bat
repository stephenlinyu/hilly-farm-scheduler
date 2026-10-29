@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"

if not exist "python\python.exe" (
  echo [错误] 未找到内置 Python：python\python.exe
  echo 请完整解压压缩包后再运行，不要直接在压缩包预览窗口中启动。
  pause
  exit /b 1
)

set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
set "PYTHONDONTWRITEBYTECODE=1"
if not defined FARM_SYSTEM_HOST set "FARM_SYSTEM_HOST=0.0.0.0"
if not defined FARM_SYSTEM_PORT set "FARM_SYSTEM_PORT=5000"
if not defined FARM_DB_DRIVER set "FARM_DB_DRIVER=sqlite"
if not defined JT808_ENABLED set "JT808_ENABLED=1"
if not defined JT808_PORT set "JT808_PORT=8088"

for /f "tokens=2 delims=:" %%i in ('ipconfig ^| findstr /i "IPv4"') do if not defined LAN_IP set LAN_IP=%%i
if defined LAN_IP for /f "tokens=* delims= " %%i in ("%LAN_IP%") do set LAN_IP=%%i

echo.
echo 正在检查并初始化本地数据库...
"python\python.exe" init_local_db.py
if errorlevel 1 (
  echo.
  echo [错误] 数据库初始化失败，请保留本窗口中的错误信息。
  pause
  exit /b 1
)

echo.
echo 农场管理系统正在启动...
echo 本机管理端: http://127.0.0.1:%FARM_SYSTEM_PORT%/login
echo 本机作业端: http://127.0.0.1:%FARM_SYSTEM_PORT%/worker/login
echo 北斗定位器 TCP: 0.0.0.0:%JT808_PORT%
if defined LAN_IP echo 局域网管理端: http://%LAN_IP%:%FARM_SYSTEM_PORT%/login
if defined LAN_IP echo 局域网作业端: http://%LAN_IP%:%FARM_SYSTEM_PORT%/worker/login
echo cpolar 公网访问: 请改用 start_public.bat（网页 HTTP + 定位器 TCP 隧道）
echo 公网启动前请修改默认密码，并确认定位器 TCP 隧道符合实际安全要求。
echo.
echo 使用期间请保持此窗口开启。按 Ctrl+C 可停止服务。
echo.

"python\python.exe" run_server.py
set "SERVER_EXIT=%ERRORLEVEL%"
echo.
echo 服务已停止，退出代码: %SERVER_EXIT%
pause
exit /b %SERVER_EXIT%
