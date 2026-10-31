@echo off
rem CrossChat installer: double-click this file. It runs scripts\install.ps1.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\install.ps1" %*
echo.
pause
