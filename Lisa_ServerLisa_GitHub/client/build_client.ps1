$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$pythonPath = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
$iconPath = Join-Path $PSScriptRoot "1.ico"

if (-not (Test-Path $iconPath)) {
    throw "Icon was not found: $iconPath"
}

if (-not (Test-Path $pythonPath)) {
    $pyLauncher = Get-Command py -ErrorAction SilentlyContinue
    if ($pyLauncher) {
        & py -m venv .venv
    }
    else {
        $pythonLauncher = Get-Command python -ErrorAction SilentlyContinue
        if (-not $pythonLauncher) {
            throw "Python was not found. Install Python 3.12+ and enable Add Python to PATH."
        }
        & python -m venv .venv
    }
}

if (-not (Test-Path $pythonPath)) {
    throw "Virtual environment was not created: $pythonPath"
}

& $pythonPath -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw "pip upgrade failed" }

& $pythonPath -m pip install -r requirements_client.txt
if ($LASTEXITCODE -ne 0) { throw "Dependency installation failed" }

$clientArgs = @(
    "-m", "PyInstaller",
    "--noconfirm", "--clean", "--onefile", "--windowed",
    "--name", "Lisa",
    "--icon", "1.ico",
    "--add-data", "1.ico;.",
    "--add-data", "fox_app.png;."
)

$clientArgs += "client_entry.py"
& $pythonPath @clientArgs
if ($LASTEXITCODE -ne 0) { throw "Lisa.exe build failed" }

& $pythonPath -m PyInstaller `
    --noconfirm `
    --clean `
    --onefile `
    --windowed `
    --name Updater `
    --icon "1.ico" `
    client_updater.py
if ($LASTEXITCODE -ne 0) { throw "Updater.exe build failed" }

$usersOutput = Join-Path $PSScriptRoot "outputs\client_to_users"
$serverOutput = Join-Path $PSScriptRoot "outputs\update_to_server"
New-Item -ItemType Directory -Force -Path $usersOutput | Out-Null
New-Item -ItemType Directory -Force -Path $serverOutput | Out-Null

Copy-Item -Force "dist\Lisa.exe" $usersOutput
Copy-Item -Force "dist\Updater.exe" $usersOutput
Copy-Item -Force "1.ico" $usersOutput

& $pythonPath prepare_update.py `
    --exe "dist\Lisa.exe" `
    --output $serverOutput
if ($LASTEXITCODE -ne 0) { throw "Update package preparation failed" }

Write-Host ""
Write-Host "BUILD COMPLETE: Lisa Client 4.1.14"
Write-Host "Initial installation files: $usersOutput"
Write-Host "Copy update files to C:\AristocratServer\updates: $serverOutput"
