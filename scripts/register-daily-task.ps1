# Register (or update) the Windows scheduled task that runs the daily digest.
# Usage:
#   .\scripts\register-daily-task.ps1                  # default 08:00 daily
#   .\scripts\register-daily-task.ps1 -At "07:30"      # custom time
#   .\scripts\register-daily-task.ps1 -Unregister      # remove the task
#
# What it sets:
#   - Trigger: daily at $At
#   - StartWhenAvailable: if the PC was off at $At, run as soon as it boots
#   - RestartCount=2 on failure (e.g. transient network)
#   - ExecutionTimeLimit=30 min
#   - Runs as the current user, no elevation needed.

[CmdletBinding()]
param(
    [string]$At = "08:00",
    [string]$TaskName = "AI-news-daily-digest",
    [switch]$Unregister
)

$ErrorActionPreference = "Stop"

if ($Unregister) {
    if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
        Write-Host "Removed task: $TaskName" -ForegroundColor Green
    } else {
        Write-Host "Task not found: $TaskName (nothing to remove)" -ForegroundColor Yellow
    }
    return
}

$projectRoot = Split-Path $PSScriptRoot -Parent
$launcher    = Join-Path $projectRoot "scripts\run-daily.ps1"

if (-not (Test-Path $launcher)) {
    throw "Launcher not found: $launcher"
}

# Use powershell.exe (Windows PowerShell 5.1, which Task Scheduler ships with).
# -NoProfile so it doesn't load the user's profile (faster, more deterministic).
# -ExecutionPolicy Bypass so the script runs even if policy is Restricted.
$action = New-ScheduledTaskAction `
    -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$launcher`"" `
    -WorkingDirectory $projectRoot

$trigger = New-ScheduledTaskTrigger -Daily -At $At

$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -DontStopOnIdleEnd `
    -RestartCount 2 `
    -RestartInterval (New-TimeSpan -Minutes 10) `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 30) `
    -MultipleInstances IgnoreNew

# User-scope task — no admin needed. Runs only when current user is logged in,
# which is fine for a daily script. If you want it to run while logged off,
# add -LogonType S4U and run this script elevated.
$principal = New-ScheduledTaskPrincipal `
    -UserId "$env:USERDOMAIN\$env:USERNAME" `
    -LogonType Interactive `
    -RunLevel Limited

if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
    Set-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings | Out-Null
    Write-Host "Updated task: $TaskName (daily @ $At)" -ForegroundColor Green
} else {
    Register-ScheduledTask -TaskName $TaskName `
        -Action $action -Trigger $trigger -Settings $settings -Principal $principal `
        -Description "AI news digest — runs uv run python -m src.main daily" | Out-Null
    Write-Host "Created task: $TaskName (daily @ $At)" -ForegroundColor Green
}

Write-Host ""
Write-Host "Verify:                Get-ScheduledTask -TaskName $TaskName" -ForegroundColor Cyan
Write-Host "Trigger once now:      Start-ScheduledTask -TaskName $TaskName" -ForegroundColor Cyan
Write-Host "Tail log:              Get-Content data\cron.log -Tail 40 -Wait" -ForegroundColor Cyan
Write-Host "Remove:                .\scripts\register-daily-task.ps1 -Unregister" -ForegroundColor Cyan
