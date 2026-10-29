@echo off
net session >nul 2>&1
if errorlevel 1 (
  echo Please right-click this file and choose "Run as administrator".
  pause
  exit /b 1
)

netsh advfirewall firewall show rule name="Farm System Server 5000" >nul 2>&1
if errorlevel 1 (
  netsh advfirewall firewall add rule name="Farm System Server 5000" dir=in action=allow protocol=TCP localport=5000 profile=any
) else (
  netsh advfirewall firewall set rule name="Farm System Server 5000" new enable=yes
)

echo.
echo Firewall rule is ready: TCP 5000 is allowed.
echo Use this only on a trusted office/lab network.
echo.
pause
