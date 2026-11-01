# Builds dist\CrossChat-Setup-<version>.exe (and its .sha256): CrossChat with its own Python, as one setup program
# made with NSIS. Every download is pinned and checked against its published checksum before use.
#   pwsh installer/build.ps1
#
# What goes in: CrossChat's files as they are installed, plus python.org's Windows embeddable Python with CrossChat's
# packages from hub\requirements.lock (exact versions, SHA-256 checked by pip, wheels only). Nothing is installed on
# the build machine: NSIS runs from its zip, and pip only downloads into the bundle (--target).
param([string]$Work = (Join-Path ([IO.Path]::GetTempPath()) 'crosschat-installer'))
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version 2

$Root = Split-Path -Parent $PSScriptRoot

# ---- pinned downloads ---------------------------------------------------------------------------------------
$PythonVersion = '3.14.10'
$PythonTag = '314'
$Python = @{
    Url    = "https://www.python.org/ftp/python/$PythonVersion/python-$PythonVersion-embed-amd64.zip"
    Sha256 = '90905e64a840557d8c1bc4f5b74db3d7ee85e3ffb217611cac1c7813acea4159'   # published on python.org's 3.14.10 release page
}
$NsisVersion = '3.13'
$Nsis = @{
    Url    = "https://downloads.sourceforge.net/project/nsis/NSIS%203/$NsisVersion/nsis-$NsisVersion.zip"
    Sha256 = 'ba63dffc4410ee89193e1cb5a41989991bd77c61068da17e3156d136b7b0b3d8'
    Md5    = '530e3623c077cba879ed2ae6e13be362'                                     # published by SourceForge for this file
}

function Get-Pinned($item, $name) {
    $downloads = Join-Path $Work 'downloads'
    New-Item -ItemType Directory -Force $downloads | Out-Null
    $file = Join-Path $downloads $name
    for ($try = 1; -not ((Test-Path $file) -and (Get-FileHash $file -Algorithm SHA256).Hash -eq $item.Sha256); $try++) {
        if ($try -gt 3) { throw "$name does not match its pinned SHA-256 after 3 downloads; not using it" }
        if (Test-Path $file) { Remove-Item $file -Force }
        & curl.exe -fsSL --retry 3 -A 'crosschat-build' -o $file $item.Url
        if ($LASTEXITCODE -ne 0) { Start-Sleep -Seconds (2 * $try) }
    }
    if ($item.ContainsKey('Md5') -and (Get-FileHash $file -Algorithm MD5).Hash -ne $item.Md5) { throw "$name does not match its published MD5" }
    Write-Host "checked $name"
    return $file
}

# ---- versions agree -----------------------------------------------------------------------------------------
$Version = (Select-String -Path (Join-Path $Root 'hub\hub.py') -Pattern '^VERSION = "(.+)"').Matches[0].Groups[1].Value
$Manifest = (Get-Content (Join-Path $Root 'extension\manifest.json') -Raw | ConvertFrom-Json).version
$Lua = (Select-String -Path (Join-Path $Root 'obs\crosschat.lua') -Pattern '^local VERSION = "(.+)"').Matches[0].Groups[1].Value
if ($Manifest -ne $Version -or $Lua -ne $Version) { throw "Versions differ: hub $Version, extension $Manifest, OBS script $Lua" }

# ---- the files, laid out as installed -----------------------------------------------------------------------
$Stage = Join-Path $Work 'stage'
if (Test-Path $Stage) { Remove-Item $Stage -Recurse -Force }
New-Item -ItemType Directory -Force $Stage, (Join-Path $Stage 'docs'), (Join-Path $Stage 'installer') | Out-Null
foreach ($folder in 'extension', 'hub', 'obs') { Copy-Item (Join-Path $Root $folder) $Stage -Recurse }
Get-ChildItem $Stage -Recurse -Directory -Filter '__pycache__' | Remove-Item -Recurse -Force
foreach ($doc in 'THEMES.md', 'COMPANION.md', 'API.md', 'INSTALLER.md') { Copy-Item (Join-Path $Root "docs\$doc") (Join-Path $Stage 'docs') }
Copy-Item (Join-Path $PSScriptRoot 'first-steps.html') (Join-Path $Stage 'docs')
Copy-Item (Join-Path $PSScriptRoot 'steps.ps1'), (Join-Path $PSScriptRoot 'privacy.txt') (Join-Path $Stage 'installer')
foreach ($file in 'config.example.json', 'README.md', 'CHANGELOG.md', 'LICENSE', 'THIRD_PARTY_NOTICES.md', 'SECURITY.md') {
    Copy-Item (Join-Path $Root $file) $Stage
}

# ---- CrossChat's own Python -----------------------------------------------------------------------------------
$Py = Join-Path $Stage 'python'
Expand-Archive (Get-Pinned $Python "python-$PythonVersion-embed-amd64.zip") $Py
# The embeddable Python only looks where its ._pth file says: its own files, the packages, and the hub's folder
# (so hub.py finds its own modules). No user site-packages, no PYTHONPATH: nothing else on the PC can change it.
Set-Content -Path (Join-Path $Py "python$PythonTag._pth") -Encoding ascii -Value @(
    "python$PythonTag.zip", '.', 'Lib\site-packages', '..\hub'
)
$Packages = Join-Path $Py 'Lib\site-packages'
& python -m pip install --disable-pip-version-check --no-warn-script-location --quiet --no-compile `
    --require-hashes --only-binary=:all: --platform win_amd64 --python-version $PythonVersion --implementation cp --abi "cp$PythonTag" `
    --target $Packages -r (Join-Path $Root 'hub\requirements.lock')
if ($LASTEXITCODE -ne 0) { throw 'pip could not fetch the pinned packages' }
Get-ChildItem $Packages -Directory -Filter 'bin' | Remove-Item -Recurse -Force
& (Join-Path $Py 'python.exe') -c 'import sys, ssl, ctypes, asyncio, sqlite3, requests, websockets, hub, devices; print(sys.version.split()[0])'
if ($LASTEXITCODE -ne 0) { throw 'the bundled Python cannot run CrossChat' }
& (Join-Path $Py 'python.exe') -m compileall -q $Packages | Out-Null

# ---- the setup program ----------------------------------------------------------------------------------------
$NsisDir = Join-Path $Work "nsis-$NsisVersion"
if (-not (Test-Path (Join-Path $NsisDir 'makensis.exe'))) { Expand-Archive (Get-Pinned $Nsis "nsis-$NsisVersion.zip") $Work -Force }
$Dist = Join-Path $Root 'dist'
New-Item -ItemType Directory -Force $Dist | Out-Null
$Name = "CrossChat-Setup-$Version.exe"
$Out = Join-Path $Dist $Name
& (Join-Path $NsisDir 'makensis.exe') /V2 /INPUTCHARSET UTF8 "/DVERSION=$Version" "/DSTAGE=$Stage" "/DOUTFILE=$Out" (Join-Path $PSScriptRoot 'crosschat.nsi')
if ($LASTEXITCODE -ne 0) { throw 'makensis failed' }
$Hash = (Get-FileHash $Out -Algorithm SHA256).Hash.ToLower()
Set-Content -Path "$Out.sha256" -Value "$Hash  $Name" -NoNewline -Encoding ascii
Write-Host $Out
Write-Host ("{0:N1} MB, sha256 {1}" -f ((Get-Item $Out).Length / 1MB), $Hash)
