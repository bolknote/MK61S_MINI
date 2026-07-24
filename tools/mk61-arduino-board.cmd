:; exec "$(dirname "$0")/.mk61-arduino-board/install.sh" "$@"
@echo off
setlocal

where pwsh.exe >nul 2>nul
if errorlevel 1 goto windows_powershell
pwsh.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0.mk61-arduino-board\install.ps1" %*
exit /b %errorlevel%

:windows_powershell
where powershell.exe >nul 2>nul
if errorlevel 1 goto missing_powershell
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0.mk61-arduino-board\install.ps1" %*
exit /b %errorlevel%

:missing_powershell
echo PowerShell 5.1 or newer was not found. 1>&2
exit /b 9009
