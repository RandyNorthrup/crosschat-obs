@echo off
rem Removes CrossChat. It runs scripts\uninstall.ps1, which removes this file's folder too, so this window waits
rem outside that folder, and the rest of this file is one line (a batch file is read one line at a time as it runs).
set "HERE=%~dp0"
cd /d "%TEMP%"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%HERE%scripts\uninstall.ps1" %* & echo. & pause & exit /b
