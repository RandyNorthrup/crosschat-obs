# Builds the release download: dist\CrossChat-<version>-windows.zip and its .sha256 file.
#   pwsh scripts/package.ps1
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$Version = (Select-String -Path (Join-Path $Root 'hub\hub.py') -Pattern '^VERSION = "(.+)"').Matches[0].Groups[1].Value
$Manifest = (Get-Content (Join-Path $Root 'extension\manifest.json') -Raw | ConvertFrom-Json).version
$Lua = (Select-String -Path (Join-Path $Root 'obs\crosschat.lua') -Pattern '^local VERSION = "(.+)"').Matches[0].Groups[1].Value
if ($Manifest -ne $Version -or $Lua -ne $Version) { throw "Versions differ: hub $Version, extension $Manifest, OBS script $Lua" }

$Name = "CrossChat-$Version-windows"
$Dist = Join-Path $Root 'dist'
$Stage = Join-Path $Dist $Name
if (Test-Path $Stage) { Remove-Item $Stage -Recurse -Force }
New-Item -ItemType Directory -Force $Stage | Out-Null

foreach ($folder in 'extension', 'hub', 'obs') {
    Copy-Item (Join-Path $Root $folder) $Stage -Recurse
}
New-Item -ItemType Directory -Force (Join-Path $Stage 'scripts'), (Join-Path $Stage 'docs') | Out-Null
Copy-Item (Join-Path $Root 'scripts\install.ps1'), (Join-Path $Root 'scripts\uninstall.ps1') (Join-Path $Stage 'scripts')
Copy-Item (Join-Path $Root 'docs\THEMES.md'), (Join-Path $Root 'docs\COMPANION.md') (Join-Path $Stage 'docs')
foreach ($file in 'Install.cmd', 'Uninstall.cmd', 'config.example.json', 'README.md', 'CHANGELOG.md', 'LICENSE', 'THIRD_PARTY_NOTICES.md') {
    Copy-Item (Join-Path $Root $file) $Stage
}
Get-ChildItem $Stage -Recurse -Directory -Filter '__pycache__' | Remove-Item -Recurse -Force

$Zip = Join-Path $Dist "$Name.zip"
if (Test-Path $Zip) { Remove-Item $Zip -Force }
Compress-Archive -Path (Join-Path $Stage '*') -DestinationPath $Zip
$Hash = (Get-FileHash $Zip -Algorithm SHA256).Hash.ToLower()
Set-Content -Path "$Zip.sha256" -Value "$Hash  $Name.zip" -NoNewline -Encoding ascii
Remove-Item $Stage -Recurse -Force
Write-Host "$Zip"
Write-Host "sha256 $Hash"
