#Requires -RunAsAdministrator
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot

$targetDir = 'C:\AristocratServer'
$targetExe = Join-Path $targetDir 'ServerLisa.exe'
$expectedVersion = (Get-Content (Join-Path $PSScriptRoot 'SERVER_VERSION.txt') -Raw).Trim()

& (Join-Path $PSScriptRoot 'build_server.ps1')
if ($LASTEXITCODE -ne 0) { throw 'Сборка ServerLisa завершилась ошибкой' }
$sourceDir = Join-Path $PSScriptRoot 'outputs\server_to_install'
if (-not (Test-Path (Join-Path $sourceDir 'ServerLisa.exe'))) {
    throw 'Новая сборка ServerLisa.exe не найдена'
}

# Останавливаем только ServerLisa; данные, отчёты и обновления не трогаем.
Get-CimInstance Win32_Process -Filter "Name = 'ServerLisa.exe'" | ForEach-Object {
    Stop-Process -Id $_.ProcessId -Force -ErrorAction Stop
    Wait-Process -Id $_.ProcessId -Timeout 10 -ErrorAction SilentlyContinue
}
New-Item -ItemType Directory -Path $targetDir -Force | Out-Null
Get-ChildItem -LiteralPath $sourceDir -File | ForEach-Object {
    Copy-Item -LiteralPath $_.FullName -Destination $targetDir -Force
}

$backup = [System.Collections.Generic.List[object]]::new()
$backupPath = Join-Path $targetDir ('autostart_backup_' + (Get-Date -Format 'yyyyMMdd_HHmmss') + '.json')
$saveBackup = {
    ConvertTo-Json -InputObject $backup.ToArray() -Depth 5 |
        Set-Content -LiteralPath $backupPath -Encoding UTF8
}
& $saveBackup
$runKeys = @(
    'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run',
    'HKLM:\Software\Microsoft\Windows\CurrentVersion\Run',
    'HKLM:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Run'
)
foreach ($key in $runKeys) {
    if (-not (Test-Path $key)) { continue }
    $regKey = Get-Item $key
    foreach ($name in $regKey.GetValueNames()) {
        $value = [string]$regKey.GetValue($name)
        if ($value -notmatch '(?i)ServerLisa(?:\.exe)?') { continue }
        $backup.Add(@{ type = 'Run'; path = $key; name = $name; value = $value })
        & $saveBackup
        Remove-ItemProperty -Path $key -Name $name -ErrorAction Stop
    }
}

$startupDirs = @(
    (Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs\Startup'),
    (Join-Path $env:ProgramData 'Microsoft\Windows\Start Menu\Programs\Startup')
)
$shell = New-Object -ComObject WScript.Shell
foreach ($dir in $startupDirs) {
    if (-not (Test-Path $dir)) { continue }
    Get-ChildItem -LiteralPath $dir -Filter '*.lnk' -File | ForEach-Object {
        $shortcut = $shell.CreateShortcut($_.FullName)
        if (($shortcut.TargetPath + ' ' + $shortcut.Arguments) -match '(?i)ServerLisa(?:\.exe)?') {
            $disabled = $_.FullName + '.disabled'
            if (Test-Path $disabled) { throw "Уже существует $disabled; проверь старый автозапуск" }
            $backup.Add(@{ type = 'Shortcut'; path = $_.FullName; disabled = $disabled })
            & $saveBackup
            Move-Item -LiteralPath $_.FullName -Destination $disabled
        }
    }
}

foreach ($task in Get-ScheduledTask) {
    $actions = ($task.Actions | ForEach-Object { $_.Execute + ' ' + $_.Arguments }) -join ' '
    if ($actions -notmatch '(?i)ServerLisa(?:\.exe)?') { continue }
    if ($task.TaskName -eq 'ServerLisa' -and $task.TaskPath -eq '\') { continue }
    $backup.Add(@{ type = 'Task'; name = $task.TaskName; path = $task.TaskPath })
    & $saveBackup
    Disable-ScheduledTask -InputObject $task | Out-Null
}

$userId = "$env:USERDOMAIN\$env:USERNAME"
$action = New-ScheduledTaskAction -Execute $targetExe -WorkingDirectory $targetDir
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $userId
$principal = New-ScheduledTaskPrincipal -UserId $userId -LogonType Interactive -RunLevel Highest
$settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Seconds 0)
Register-ScheduledTask -TaskName 'ServerLisa' -TaskPath '\' -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Force | Out-Null

Start-Process -FilePath $targetExe -WorkingDirectory $targetDir
$actual = $null
for ($i = 0; $i -lt 30; $i++) {
    try {
        $actual = (Invoke-RestMethod -Uri 'http://127.0.0.1:8000/ping' -TimeoutSec 2).version
        if ($actual) { break }
    } catch { Start-Sleep -Milliseconds 500 }
}
if ($actual -ne $expectedVersion) {
    throw "Запущена версия '$actual' вместо '$expectedVersion'. Проверь, кто занимает порт 8000."
}
Write-Host "Установлен и запущен ServerLisa $actual. После входа в Windows стартует $targetExe"
Write-Host "Сведения о старом автозапуске: $backupPath"
