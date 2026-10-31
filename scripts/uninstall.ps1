# CrossChat uninstaller. Run Uninstall.cmd (in the CrossChat folder or the Start menu).
param([switch]$Quiet)
$ErrorActionPreference = 'Stop'

$App = Join-Path $env:LOCALAPPDATA 'CrossChat'
$Menu = Join-Path ([Environment]::GetFolderPath('Programs')) 'CrossChat'

Write-Host ''
Write-Host '  Uninstall CrossChat' -ForegroundColor White
if (-not $Quiet) {
    $sure = Read-Host 'Remove CrossChat from this PC? (y/n)'
    if ($sure -notmatch '^[yY]') { Write-Host 'Nothing was changed.'; exit 0 }
}

Get-CimInstance Win32_Process -Filter "Name like 'python%'" | Where-Object { $_.CommandLine -and $_.CommandLine -like "*$App\*" -and $_.CommandLine -like '*hub*.py*' } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }

$keep = Join-Path ([Environment]::GetFolderPath('MyDocuments')) 'CrossChat backup'
$mine = @('config.json', 'themes') | ForEach-Object { Join-Path $App $_ } | Where-Object { Test-Path $_ }
if ($mine) {
    $save = if ($Quiet) { 'y' } else { Read-Host "Keep your settings and themes in `"$keep`"? (y/n) [y]" }
    if ($save -notmatch '^[nN]') {
        New-Item -ItemType Directory -Force $keep | Out-Null
        foreach ($item in $mine) { Copy-Item $item $keep -Recurse -Force }
        Write-Host "Kept in $keep"
    }
}

if (Test-Path $Menu) { Remove-Item $Menu -Recurse -Force }
# This script runs from inside the folder it removes, so the last step happens after it ends.
Start-Process -WindowStyle Hidden cmd.exe -ArgumentList "/c timeout /t 2 >nul & rmdir /s /q `"$App`""

Write-Host ''
Write-Host 'CrossChat is removed. Two things only you can remove:' -ForegroundColor Green
Write-Host '  - OBS: Tools > Scripts, select crosschat.lua, press the minus button.'
Write-Host '  - Chrome or Edge: the extensions page, CrossChat, Remove.'
