$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonExe = Join-Path $projectRoot ".venv\Scripts\python.exe"
$managePy = Join-Path $projectRoot "manage.py"

if (!(Test-Path $pythonExe)) {
    Write-Error "Python executable not found: $pythonExe"
}

& $pythonExe $managePy backup_db
Write-Output "Database backup completed"
