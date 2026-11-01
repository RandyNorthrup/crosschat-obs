# CrossChat installer. Run Install.cmd (it starts this). Safe to run again: it updates CrossChat and keeps your
# settings and themes.
#
#   -Quiet   ask nothing: keep the existing settings, or start from the defaults
param([switch]$Quiet)
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version 2

$Source = Split-Path -Parent $PSScriptRoot
$App = Join-Path $env:LOCALAPPDATA 'CrossChat'
$Menu = Join-Path ([Environment]::GetFolderPath('Programs')) 'CrossChat'
$Version = (Select-String -Path (Join-Path $Source 'hub\hub.py') -Pattern '^VERSION = "(.+)"').Matches[0].Groups[1].Value

function Say($text, $colour = 'Gray') { Write-Host $text -ForegroundColor $colour }
function Step($text) { Write-Host ''; Write-Host "== $text" -ForegroundColor Cyan }
function Ask($question, $default = '') {
    if ($Quiet) { return $default }
    $hint = if ($default) { " [$default]" } else { '' }
    $answer = Read-Host "$question$hint"
    if ([string]::IsNullOrWhiteSpace($answer)) { return $default }
    return $answer.Trim()
}
function Yes($question, $default = $true) {
    $answer = Ask "$question (y/n)" $(if ($default) { 'y' } else { 'n' })
    return $answer -match '^[yY]'
}

# A Python 3.10 or newer: the command and the arguments that run it, or $null.
function Find-Python {
    $candidates = @(
        @{ Exe = 'py'; Args = @('-3') },
        @{ Exe = 'python'; Args = @() },
        @{ Exe = (Join-Path $env:LOCALAPPDATA 'Programs\Python\Launcher\py.exe'); Args = @('-3') }
    )
    foreach ($c in $candidates) {
        try {
            # No double quotes in the code: Windows PowerShell 5.1 drops them on the way to a program.
            $out = & $c.Exe @($c.Args + @('-c', 'import sys; print(sys.version.split()[0]); sys.exit(sys.version_info < (3, 10))')) 2>$null
            if ($LASTEXITCODE -eq 0 -and $out) { return @{ Exe = $c.Exe; Args = $c.Args; Version = "$out".Trim() } }
        } catch { }
    }
    return $null
}

Write-Host ''
Write-Host "  CrossChat $Version installer" -ForegroundColor White
Write-Host '  Every stream chat in one window, on-stream chat widgets, and X Live started with OBS.'
Say "  Installs to $App"

# ---- Python -----------------------------------------------------------------------------------------------
Step 'Python'
$python = Find-Python
if (-not $python) {
    Say 'CrossChat needs Python 3.10 or newer, and this PC has none.' Yellow
    $winget = Get-Command winget -ErrorAction SilentlyContinue
    if ($winget -and -not $Quiet -and (Yes 'Install Python 3.14 for your Windows account now with winget?')) {
        & winget install -e --id Python.Python.3.14 --scope user --accept-package-agreements --accept-source-agreements
        $env:Path = [Environment]::GetEnvironmentVariable('Path', 'User') + ';' + [Environment]::GetEnvironmentVariable('Path', 'Machine')
        $python = Find-Python
    }
    if (-not $python) {
        Say 'Install Python from https://www.python.org/downloads/ (tick "Add python.exe to PATH"), then run Install.cmd again.' Red
        exit 1
    }
}
Say "Python $($python.Version) found."

# ---- files ------------------------------------------------------------------------------------------------
Step 'Copying CrossChat'
# OBS starts the hub as ...\CrossChat\obs\..\hub\hub.py, so match the folder and the file separately.
$restartFor = $null
Get-CimInstance Win32_Process -Filter "Name like 'python%'" | Where-Object { $_.CommandLine -and $_.CommandLine -like "*$App\*" -and $_.CommandLine -like '*hub.py*' -and $_.CommandLine -notlike '*--demo*' } | ForEach-Object {
    Say 'Stopping the running CrossChat hub (it starts again at the end).'
    if ($_.CommandLine -match '--obs-pid (\d+)') { $restartFor = $_.CommandLine }
    Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue      # the venv launcher and its child: one may be gone already
}
New-Item -ItemType Directory -Force $App | Out-Null
foreach ($folder in 'extension', 'hub', 'obs') {
    & robocopy (Join-Path $Source $folder) (Join-Path $App $folder) /MIR /XD __pycache__ /NFL /NDL /NJH /NJS /NP | Out-Null
    if ($LASTEXITCODE -ge 8) { Say "Copying $folder failed (robocopy $LASTEXITCODE)." Red; exit 1 }
}
foreach ($file in 'config.example.json', 'README.md', 'CHANGELOG.md', 'LICENSE', 'THIRD_PARTY_NOTICES.md', 'Uninstall.cmd') {
    $from = Join-Path $Source $file
    if (Test-Path $from) { Copy-Item $from $App -Force }
}
New-Item -ItemType Directory -Force (Join-Path $App 'scripts') | Out-Null
Copy-Item (Join-Path $Source 'scripts\uninstall.ps1') (Join-Path $App 'scripts') -Force
Get-ChildItem $App -Recurse -File | Unblock-File
Say 'Done.'

# ---- private Python environment ---------------------------------------------------------------------------
Step 'Setting up CrossChat''s Python packages'
$venvPython = Join-Path $App '.venv\Scripts\python.exe'
$healthy = $false
if (Test-Path $venvPython) {
    & $venvPython -c 'import sys' 2>$null
    $healthy = $LASTEXITCODE -eq 0
}
if (-not $healthy) {
    & $python.Exe @($python.Args + @('-m', 'venv', '--clear', (Join-Path $App '.venv')))
    if ($LASTEXITCODE -ne 0) { Say 'Could not create the Python environment.' Red; exit 1 }
}
# exact versions with their checksums: pip refuses anything that doesn't match what was tested
& $venvPython -m pip install --disable-pip-version-check --no-warn-script-location -q --require-hashes -r (Join-Path $App 'hub\requirements.lock')
if ($LASTEXITCODE -ne 0) { Say 'Installing the Python packages failed (see above). Check the internet connection and run Install.cmd again.' Red; exit 1 }
Say 'Done.'

# ---- privacy ----------------------------------------------------------------------------------------------
Step 'Privacy'
Say 'CrossChat runs only on this PC. It has no server, no account and no telemetry.'
Say 'It connects only to the chat platforms you set up, and, unless you turn them off, to 7TV, BetterTTV and'
Say 'FrankerFaceZ for emote pictures (they get your Twitch channel''s public id).'
Say 'Every connection and what it sends: https://github.com/RandyNorthrup/crosschat-obs/blob/main/SECURITY.md#what-leaves-your-pc'

# ---- your channels ----------------------------------------------------------------------------------------
Step 'Your channels'
$config = Join-Path $App 'config.json'
if (Test-Path $config) {
    Say "Keeping your settings in $config"
} else {
    Say 'Which channels does your stream go to? Paste a name or a link; leave empty to skip.'
    $env:CROSSCHAT_TWITCH = Ask 'Twitch channel'
    $env:CROSSCHAT_YOUTUBE = Ask 'YouTube channel (@handle or link)'
    $env:CROSSCHAT_KICK = Ask 'Kick channel'
    $env:CROSSCHAT_TIKTOK = Ask 'TikTok @name (if you go LIVE on TikTok)'
    $env:CROSSCHAT_FACEBOOK = if (Yes 'Do you go live on Facebook?' $false) { '1' } else { '0' }
    $env:CROSSCHAT_INSTAGRAM = if (Yes 'Do you go live on Instagram from OBS (Create, then Live video, on instagram.com)?' $false) { '1' } else { '0' }
    $env:CROSSCHAT_X = if (Yes 'Do you stream to X (it needs X Premium and Live Studio)?' $false) { '1' } else { '0' }
    $env:CROSSCHAT_EMOTES = if (Yes 'Show 7TV, BetterTTV and FrankerFaceZ emotes (asks those services for your channel''s emotes)?') { '1' } else { '0' }
    if ($env:CROSSCHAT_X -eq '1') {
        $env:CROSSCHAT_X_AUTO = if (Yes 'Go live on X by itself whenever OBS starts streaming?') { '1' } else { '0' }
        $env:CROSSCHAT_X_SOURCE = Ask 'Name of the source in X Live Studio that OBS streams to' 'OBS'
        $env:CROSSCHAT_X_TITLE = Ask 'Title for your X livestreams' 'Live now'
    }
    & $venvPython (Join-Path $App 'hub\setup_config.py') config (Join-Path $App 'config.example.json') $config
    if ($LASTEXITCODE -ne 0) { Say 'Could not write config.json.' Red; exit 1 }
    Say "Saved to $config (edit it any time; restart OBS afterwards)."
}

# ---- OBS ----------------------------------------------------------------------------------------------------
Step 'OBS Studio'
$obsExe = Join-Path $env:ProgramFiles 'obs-studio\bin\64bit\obs64.exe'
if (Test-Path $obsExe) { Say "OBS Studio $((Get-Item $obsExe).VersionInfo.ProductVersion) found." } else { Say 'OBS Studio was not found in Program Files (fine if you use a portable OBS).' Yellow }
$obsRunning = [bool](Get-Process obs64 -ErrorAction SilentlyContinue)
$ws = Join-Path $env:APPDATA 'obs-studio\plugin_config\obs-websocket\config.json'
$wsOn = $false
if (Test-Path $ws) { try { $wsOn = [bool]((Get-Content $ws -Raw | ConvertFrom-Json).server_enabled) } catch { } }
if ($wsOn) {
    Say 'OBS''s WebSocket server is on. CrossChat reads its port and password from OBS by itself.'
} elseif ($obsRunning) {
    Say 'OBS''s WebSocket server is off. In OBS: Tools > WebSocket Server Settings > tick "Enable WebSocket server" > OK.' Yellow
} elseif (Yes 'CrossChat follows OBS through its WebSocket server, which is off. Turn it on now?') {
    & $venvPython (Join-Path $App 'hub\setup_config.py') websocket $ws
    Say 'Turned on (with a password; CrossChat reads it from OBS).'
} else {
    Say 'Later, in OBS: Tools > WebSocket Server Settings > tick "Enable WebSocket server".' Yellow
}

# ---- Start menu -------------------------------------------------------------------------------------------
Step 'Start menu'
$pythonw = Join-Path $App '.venv\Scripts\pythonw.exe'
$control = Join-Path $App 'hub\control.py'
$icon = Join-Path $App 'hub\web\crosschat.ico'
New-Item -ItemType Directory -Force $Menu | Out-Null
Get-ChildItem $Menu -Filter '*.lnk' | Remove-Item -Force
$shell = New-Object -ComObject WScript.Shell
function Shortcut($name, $target, $arguments, $description) {
    $link = $shell.CreateShortcut((Join-Path $Menu "$name.lnk"))
    $link.TargetPath = $target
    $link.Arguments = $arguments
    $link.WorkingDirectory = $App
    $link.Description = $description
    if (Test-Path $icon) { $link.IconLocation = $icon }
    $link.Save()
}
Shortcut 'Open chat' $pythonw "`"$control`" show" 'Open the CrossChat window'
Shortcut 'Try the demo' $pythonw "`"$control`" demo" 'CrossChat with a made-up live stream; nothing is posted anywhere'
Shortcut 'Theme Studio' $pythonw "`"$control`" studio" 'Change how chat looks on stream'
Shortcut 'Go live on X' $pythonw "`"$control`" x-live" 'Start the X livestream now'
Shortcut 'Test X (never goes live)' $pythonw "`"$control`" x-dry" 'Fill in the X form without going live'
Shortcut 'Hide featured message' $pythonw "`"$control`" unfeature" 'Take the featured message off the stream'
Shortcut 'CrossChat folder' (Join-Path $env:WINDIR 'explorer.exe') "`"$App`"" 'Settings, themes and the log'
Shortcut 'Uninstall CrossChat' (Join-Path $App 'Uninstall.cmd') '' 'Remove CrossChat'
Say "Start menu > CrossChat"

# ---- the hub that was running for an open OBS: start the updated one in its place ------------------------
if ($restartFor -and $restartFor -match '--obs-pid (\d+)' -and (Get-Process -Id $Matches[1] -ErrorAction SilentlyContinue)) {
    $obsPid = $Matches[1]
    $obsConfig = if ($restartFor -match '--obs-config "([^"]+)"') { $Matches[1] } else { Join-Path $env:APPDATA 'obs-studio' }
    Start-Process (Join-Path $App '.venv\Scripts\pythonw.exe') -WorkingDirectory (Join-Path $App 'hub') `
        -ArgumentList "`"$(Join-Path $App 'hub\hub.py')`" --obs-pid $obsPid --obs-config `"$obsConfig`""
    Say 'Started the updated hub for the OBS that is open.'
}

# ---- the two steps that need you --------------------------------------------------------------------------
$lua = Join-Path $App 'obs\crosschat.lua'
$extension = Join-Path $App 'extension'
Set-Clipboard -Value $lua
Write-Host ''
Write-Host '  Two steps left, about a minute:' -ForegroundColor Green
Write-Host ''
Write-Host '  1. OBS: Tools > Scripts > + and pick this file (its path is on your clipboard):' -ForegroundColor White
Write-Host "       $lua"
Write-Host '  2. Chrome (or Edge): open chrome://extensions (edge://extensions), switch on Developer mode,' -ForegroundColor White
Write-Host '     press "Load unpacked" and pick this folder:'
Write-Host "       $extension"
Write-Host '     (Needed for replying from the chat window and for X. Reading chat and the on-stream widgets work without it.)'
Write-Host ''
Write-Host '  On-stream widgets: in OBS add a Browser Source with one of these addresses:' -ForegroundColor White
Write-Host '       http://127.0.0.1:4466/overlay/chat       450 x 800'
Write-Host '       http://127.0.0.1:4466/overlay/featured   900 x 260'
Write-Host '       http://127.0.0.1:4466/overlay/viewers    600 x 120'
Write-Host '       http://127.0.0.1:4466/overlay/alerts     800 x 300'
Write-Host '  Restyle them in Start menu > CrossChat > Theme Studio.'
Write-Host ''
if ($obsRunning) { Say '  OBS is open: after adding the script, it starts by itself. Already added? Press "Start the hub again" in Tools > Scripts.' Yellow }
if (-not $Quiet -and (Yes 'Open the extension folder now?')) { Start-Process explorer.exe $extension }
Say "CrossChat $Version is installed." Green
