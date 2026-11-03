$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$sourceDirectory = Join-Path $PSScriptRoot "outputs\update_to_server"
$sourceExe = Join-Path $sourceDirectory "Лиса.exe"
$sourceManifest = Join-Path $sourceDirectory "version.json"
$serverDirectory = "C:\AristocratServer\updates"

if (-not (Test-Path $sourceExe)) {
    throw "Build first: $sourceExe was not found."
}
if (-not (Test-Path $sourceManifest)) {
    throw "Build first: $sourceManifest was not found."
}

$manifest = Get-Content -LiteralPath $sourceManifest -Raw -Encoding UTF8 | ConvertFrom-Json
if ([string]$manifest.version -ne "4.1.14") {
    throw "Expected version 4.1.14, found $($manifest.version)."
}
if ([string]::IsNullOrWhiteSpace([string]$manifest.sha256)) {
    throw "SHA256 is empty. Run build_client.ps1 again."
}

New-Item -ItemType Directory -Force -Path $serverDirectory | Out-Null
Copy-Item -LiteralPath $sourceExe -Destination $serverDirectory -Force
Copy-Item -LiteralPath $sourceManifest -Destination $serverDirectory -Force

Write-Host "Transition update 4.1.14 published."
Write-Host "Old clients: http://192.168.0.199:8000/updates/version.json"
Write-Host "New clients: http://192.168.10.75/updates/version.json"
