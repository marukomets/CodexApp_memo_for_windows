param(
    [string]$AppExe = "dist\\CodexHandoffSetup.exe",
    [string]$BackgroundDir = "build-assets\\background-dist\\CodexHandoffBackground",
    [switch]$NoRestart
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$appSource = (Resolve-Path (Join-Path $repoRoot $AppExe)).Path
$backgroundSource = (Resolve-Path (Join-Path $repoRoot $BackgroundDir)).Path

$localRoot = Join-Path $env:LOCALAPPDATA "CodexHandoff"
$backgroundRoot = Join-Path $localRoot "background"
$backupRoot = Join-Path $env:TEMP ("CodexHandoff-backup-" + (Get-Date -Format "yyyyMMdd-HHmmss"))

$managedTargets = @(
    (Join-Path $localRoot "CodexHandoff.exe"),
    (Join-Path $backgroundRoot "CodexHandoffBackground.exe")
)

$runningManaged = Get-CimInstance Win32_Process |
    Where-Object { $_.ExecutablePath -and ($managedTargets -contains $_.ExecutablePath) }

if ($runningManaged) {
    $runningManaged | ForEach-Object {
        Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
    }
    Start-Sleep -Milliseconds 500
}

if (Test-Path $localRoot) {
    New-Item -ItemType Directory -Path $backupRoot -Force | Out-Null
    Copy-Item (Join-Path $localRoot "*") $backupRoot -Recurse -Force
}

New-Item -ItemType Directory -Path $localRoot -Force | Out-Null
Copy-Item $appSource (Join-Path $localRoot "CodexHandoff.exe") -Force

if (Test-Path $backgroundRoot) {
    Remove-Item $backgroundRoot -Recurse -Force
}
New-Item -ItemType Directory -Path $backgroundRoot -Force | Out-Null
Copy-Item (Join-Path $backgroundSource "*") $backgroundRoot -Recurse -Force

$backgroundExe = Join-Path $backgroundRoot "CodexHandoffBackground.exe"
if (-not $NoRestart -and (Test-Path $backgroundExe)) {
    Start-Process -FilePath $backgroundExe | Out-Null
}

Write-Output "backup=$backupRoot"
Write-Output "app=$(Join-Path $localRoot 'CodexHandoff.exe')"
Write-Output "background=$backgroundExe"
