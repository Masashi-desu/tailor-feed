# Daily entrypoint for Windows (Task Scheduler). Logs to logs\run_daily.log
$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot
$py = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) { $py = "python" }
New-Item -ItemType Directory -Force -Path (Join-Path $PSScriptRoot "logs") | Out-Null
$log = Join-Path $PSScriptRoot "logs\run_daily.log"
$env:PYTHONIOENCODING = "utf-8"; $env:PYTHONUTF8 = "1"
& $py (Join-Path $PSScriptRoot "run_daily.py") *>> $log
exit $LASTEXITCODE
