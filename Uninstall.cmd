@echo off
rem Removes CrossChat. It runs scripts\uninstall.ps1.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\uninstall.ps1" %*
echo.
pause
