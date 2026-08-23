@echo off
echo ======================================
echo MyManageRH Root CA Installation
echo ======================================

set CERT=certs\root_ca.crt

if not exist %CERT% (
    echo ❌ Root CA not found at %CERT%
    pause
    exit /b 1
)

echo Installing Root CA into Trusted Root Store...
certutil -addstore Root %CERT%

if %errorlevel% neq 0 (
    echo ❌ Installation failed
    echo 👉 Try running as Administrator
    pause
    exit /b 1
)

echo.
echo ✅ Root CA installed successfully
echo 👉 Signatures will now appear as TRUSTED in Adobe

pause
