# CrossChat uninstaller. Run Uninstall.cmd (in the CrossChat folder or the Start menu).
#   -Quiet   ask nothing: keep a backup of your settings and themes, then remove everything else (chat history too)
# Where things are can be named (setup's steps.ps1 takes -App the same way): a test runs this on folders of its own.
param(
    [switch]$Quiet,
    [string]$App = (Join-Path $env:LOCALAPPDATA 'CrossChat'),
    [string]$Menu = (Join-Path ([Environment]::GetFolderPath('Programs')) 'CrossChat'),
    [string]$KeepIn = (Join-Path ([Environment]::GetFolderPath('MyDocuments')) 'CrossChat backup'),
    [string]$AppsEntry = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\CrossChat'
)
$ErrorActionPreference = 'Stop'
$App = $App.TrimEnd('\')

# CrossChat's programs: python(w).exe running a hub script from this folder (OBS starts it as ...\obs\..\hub\hub.py).
function Hubs {
    @(Get-CimInstance Win32_Process -Filter "Name like 'python%'" | Where-Object {
        $_.CommandLine -and $_.CommandLine.IndexOf($App + '\', [StringComparison]::OrdinalIgnoreCase) -ge 0 -and $_.CommandLine -like '*hub*.py*'
    })
}

function Stop-Hubs {
    # (stopped twice: OBS's script restarts a hub that stops with an error within seconds, unless hub.py is gone)
    for ($round = 0; $round -lt 2; $round++) {
        foreach ($p in Hubs) { Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue }
        if ($round -eq 0) {
            Remove-Item -LiteralPath (Join-Path $App 'hub\hub.py') -Force -ErrorAction SilentlyContinue
        }
        for ($i = 0; $i -lt 40 -and @(Hubs).Count; $i++) { Start-Sleep -Milliseconds 250 }
    }
}

Write-Host ''
Write-Host '  Uninstall CrossChat' -ForegroundColor White
if (-not $Quiet) {
    $sure = Read-Host 'Remove CrossChat from this PC? (y/n)'
    if ($sure -notmatch '^[yY]') { Write-Host 'Nothing was changed.'; exit 0 }
}

Stop-Hubs

$mine = @('config.json', 'themes', 'quick.json', 'filters.json', 'tts.json') | ForEach-Object { Join-Path $App $_ } | Where-Object { Test-Path -LiteralPath $_ }
if ($mine) {
    $save = if ($Quiet) { 'y' } else { Read-Host "Keep your settings and themes in `"$KeepIn`"? (y/n) [y]" }
    if ($save -notmatch '^[nN]') {
        New-Item -ItemType Directory -Force $KeepIn | Out-Null
        foreach ($item in $mine) { Copy-Item -LiteralPath $item $KeepIn -Recurse -Force }
        Write-Host "Kept in $KeepIn"
    }
}
$logs = Join-Path $App 'logs'
if (Test-Path -LiteralPath $logs) {
    $save = if ($Quiet) { 'n' } else { Read-Host 'Keep your chat history there too? (y/n) [y]' }
    if ($save -notmatch '^[nN]') {
        New-Item -ItemType Directory -Force $KeepIn | Out-Null
        Copy-Item -LiteralPath $logs $KeepIn -Recurse -Force
        Write-Host "Chat history kept in $KeepIn"
    } else {
        Write-Host 'Your chat history goes with CrossChat.'
    }
}

if (Test-Path -LiteralPath $Menu) { Remove-Item -LiteralPath $Menu -Recurse -Force }
# The Apps entry, if CrossChat's setup program installed here before
Remove-Item $AppsEntry -Recurse -Force -ErrorAction SilentlyContinue

# This script's own folder goes too: PowerShell has read it whole, and it mustn't sit in the folder it removes.
[Environment]::CurrentDirectory = [IO.Path]::GetTempPath()
Set-Location -LiteralPath ([IO.Path]::GetTempPath())
$trouble = @()
for ($try = 0; $try -lt 20 -and (Test-Path -LiteralPath $App); $try++) {       # a program that has just ended can hold a file a moment longer
    if ($try) { Start-Sleep -Milliseconds 250 }
    Remove-Item -LiteralPath $App -Recurse -Force -ErrorAction SilentlyContinue -ErrorVariable trouble
}

Write-Host ''
if (Test-Path -LiteralPath $App) {
    Write-Host "CrossChat could not be fully removed: $App is still there." -ForegroundColor Red
    if ($trouble) { Write-Host $trouble[0].Exception.Message }
    Write-Host 'Close whatever is using it (OBS, a window open in that folder), then delete the folder.'
    exit 1
}
Write-Host 'CrossChat is removed. Two things only you can remove:' -ForegroundColor Green
Write-Host '  - OBS: Tools > Scripts, select crosschat.lua, press the minus button.'
Write-Host '  - Chrome or Edge: the extensions page, CrossChat, Remove.'
