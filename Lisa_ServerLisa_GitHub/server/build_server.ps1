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

& $pythonPath -m pip install -r requirements_server.txt
if ($LASTEXITCODE -ne 0) { throw "Dependency installation failed" }

& $pythonPath -m PyInstaller `
    --noconfirm `
    --clean `
    --onefile `
    --console `
    --name ServerLisa `
    --icon "1.ico" `
    --hidden-import "pythoncom" `
    --hidden-import "pywintypes" `
    --collect-submodules "win32com" `
    --collect-all "pywinauto" `
    --collect-all "comtypes" `
    --hidden-import "PIL.ImageGrab" `
    --hidden-import "pyscreeze" `
    --collect-all "PIL" `
    --collect-all "pyscreeze" `
    --collect-all "rapidocr" `
    --collect-all "onnxruntime" `
    --add-data "server\date_from.png;." `
    --add-data "server\date_to.png;." `
    --add-data "server\date_from_anchor.png;." `
    --add-data "server\date_to_anchor.png;." `
    --add-data "server\time_zero_anchor.png;." `
    --add-data "server\get_report.png;." `
    --add-data "server\sigur_get_report.png;." `
    --add-data "server\report_button_text_large.png;." `
    --add-data "server\report_button_text_small.png;." `
    --add-data "server\edge_save.png;." `
    server_entry.py

if ($LASTEXITCODE -ne 0) { throw "ServerLisa.exe build failed" }

$outputDir = Join-Path $PSScriptRoot "outputs\server_to_install"
New-Item -ItemType Directory -Force -Path $outputDir | Out-Null

Copy-Item -Force "dist\ServerLisa.exe" $outputDir
Copy-Item -Force "1.ico" $outputDir
Copy-Item -Force "server\date_from.png" $outputDir
Copy-Item -Force "server\date_to.png" $outputDir
Copy-Item -Force "server\date_from_anchor.png" $outputDir
Copy-Item -Force "server\date_to_anchor.png" $outputDir
Copy-Item -Force "server\time_zero_anchor.png" $outputDir
Copy-Item -Force "server\get_report.png" $outputDir
Copy-Item -Force "server\sigur_get_report.png" $outputDir
Copy-Item -Force "server\report_button_text_large.png" $outputDir
Copy-Item -Force "server\report_button_text_small.png" $outputDir
Copy-Item -Force "server\edge_save.png" $outputDir

Write-Host ""
Write-Host "BUILD COMPLETE"
Write-Host "Copy these files to C:\AristocratServer:"
Write-Host $outputDir
