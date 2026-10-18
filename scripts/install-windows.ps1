# Per-user setup (no admin): venv, Startup shortcut for the server, 07:00 daily task.
param([int]$Port = 8095, [string]$Time = "07:00")
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $root
if (-not (Test-Path ".venv\Scripts\python.exe")) { python -m venv .venv }
& .venv\Scripts\python.exe -m pip install -q --upgrade pip
& .venv\Scripts\python.exe -m pip install -q -r requirements.txt
# Resident server via Startup folder
$startup = [Environment]::GetFolderPath("Startup")
$lnk = Join-Path $startup "Tailor-feed server.lnk"
$ws = New-Object -ComObject WScript.Shell
$s = $ws.CreateShortcut($lnk)
$s.TargetPath = "$env:WINDIR\System32\wscript.exe"
$s.Arguments = "`"$root\scripts\start-server.vbs`""
$s.WorkingDirectory = $root
$s.Save()
# Daily pipeline task (current user, runs only when logged on => no password/admin needed)
$act = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$root\run_daily.ps1`"" -WorkingDirectory $root
$trg = New-ScheduledTaskTrigger -Daily -At $Time
$set = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Hours 1)
$pr = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName "Tailor-feed daily refresh" -Action $act -Trigger $trg -Settings $set -Principal $pr -Force | Out-Null
Write-Host "Installed: $lnk ; task 'Tailor-feed daily refresh' at $Time"
