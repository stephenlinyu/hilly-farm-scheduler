@echo off
net session >nul 2>&1
if errorlevel 1 (
  echo Please right-click this file and choose "Run as administrator".
  pause
  exit /b 1
)

netsh advfirewall firewall show rule name="Farm System JT808 8088" >nul 2>&1
if errorlevel 1 (
  netsh advfirewall firewall add rule name="Farm System JT808 8088" dir=in action=allow protocol=TCP localport=8088 profile=any
) else (
  netsh advfirewall firewall set rule name="Farm System JT808 8088" new enable=yes
)

echo.
echo Firewall rule is ready: JT808 TCP 8088 is allowed.
echo Use this only on a trusted network or a controlled tunnel host.
echo.
pause
