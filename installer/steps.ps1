# What CrossChat's setup program does besides copying files. Setup runs it hidden (no console window) through NSIS's
# nsExec, with Windows PowerShell 5.1:
#   -Step stop-hub     stop CrossChat (and the demo) before its files are replaced; note an OBS-started hub to restart
#   -Step obs-status   print on | running | off: OBS's WebSocket server is on; or it's off and OBS is open; or both off
#   -Step finish       a first config.json, OBS's WebSocket server (with -EnableWebSocket), the hub again for an open
#                      OBS, and the OBS script's path on the clipboard
#   -Step uninstall    stop CrossChat; with -Backup, copy your settings and themes to Documents\CrossChat backup
param(
    [Parameter(Mandatory = $true)][ValidateSet('stop-hub', 'obs-status', 'finish', 'uninstall')][string]$Step,
    [string]$App = (Join-Path $env:LOCALAPPDATA 'CrossChat'),
    [switch]$EnableWebSocket,
    [switch]$Backup
)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version 2
$App = $App.TrimEnd('\')
$RestartNote = Join-Path $env:TEMP 'CrossChat-restart.txt'
$WebSocket = Join-Path $env:APPDATA 'obs-studio\plugin_config\obs-websocket\config.json'

# CrossChat's hubs: python(w).exe running hub.py from this folder (OBS starts it as ...\obs\..\hub\hub.py).
function Hubs {
    @(Get-CimInstance Win32_Process -Filter "Name like 'python%'" | Where-Object {
        $_.CommandLine -and $_.CommandLine.IndexOf($App + '\', [StringComparison]::OrdinalIgnoreCase) -ge 0 -and $_.CommandLine -like '*hub.py*'
    })
}

function Stop-Hubs {
    # (stopped twice: OBS's script restarts a hub that stops with an error within seconds, unless hub.py is gone)
    for ($round = 0; $round -lt 2; $round++) {
        foreach ($p in Hubs) { Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue }
        if ($round -eq 0) {
            Remove-Item (Join-Path $App 'hub\hub.py') -Force -ErrorAction SilentlyContinue     # replaced or removed in a moment
        }
        for ($i = 0; $i -lt 40 -and @(Hubs).Count; $i++) { Start-Sleep -Milliseconds 250 }
    }
}

switch ($Step) {
    'stop-hub' {
        $restart = ''
        foreach ($p in Hubs) {
            if ($p.CommandLine -match '--obs-pid (\d+)' -and $p.CommandLine -notmatch '--demo') { $restart = $p.CommandLine }
        }
        Stop-Hubs
        if ($restart) { Set-Content -Path $RestartNote -Value $restart -Encoding UTF8 }
        elseif (Test-Path $RestartNote) { Remove-Item $RestartNote -Force }
    }
    'obs-status' {
        $on = $false
        if (Test-Path $WebSocket) { try { $on = [bool]((Get-Content $WebSocket -Raw | ConvertFrom-Json).server_enabled) } catch { } }
        $state = if ($on) { 'on' } elseif (Get-Process obs64 -ErrorAction SilentlyContinue) { 'running' } else { 'off' }
        [Console]::Out.Write($state)
    }
    'finish' {
        $python = Join-Path $App 'python\python.exe'
        $setup = Join-Path $App 'hub\setup_config.py'
        & $python $setup ensure (Join-Path $App 'config.example.json') (Join-Path $App 'config.json')
        if ($LASTEXITCODE -ne 0) { throw 'could not write config.json' }
        if ($EnableWebSocket) {
            & $python $setup websocket $WebSocket
            if ($LASTEXITCODE -ne 0) { throw "could not turn on OBS's WebSocket server" }
        }
        if (Test-Path $RestartNote) {
            $line = Get-Content $RestartNote -Raw
            Remove-Item $RestartNote -Force
            if ($line -match '--obs-pid (\d+)' -and (Get-Process -Id $Matches[1] -ErrorAction SilentlyContinue)) {
                $obsPid = $Matches[1]
                $obsConfig = if ($line -match '--obs-config "([^"]+)"') { $Matches[1] } else { Join-Path $env:APPDATA 'obs-studio' }
                Start-Process (Join-Path $App 'python\pythonw.exe') -WorkingDirectory (Join-Path $App 'hub') `
                    -ArgumentList "`"$(Join-Path $App 'hub\hub.py')`" --obs-pid $obsPid --obs-config `"$obsConfig`""
            }
        }
        try { Set-Clipboard -Value (Join-Path $App 'obs\crosschat.lua') } catch { }
    }
    'uninstall' {
        Stop-Hubs
        if ($Backup) {
            $keep = Join-Path ([Environment]::GetFolderPath('MyDocuments')) 'CrossChat backup'
            $mine = @('config.json', 'themes', 'quick.json', 'filters.json', 'tts.json') | ForEach-Object { Join-Path $App $_ } | Where-Object { Test-Path $_ }
            if ($mine) {
                New-Item -ItemType Directory -Force $keep | Out-Null
                foreach ($item in $mine) { Copy-Item $item $keep -Recurse -Force }
            }
        }
    }
}
