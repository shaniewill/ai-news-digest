# Launcher invoked by Windows Task Scheduler to run the daily digest.
# Usage:
#   .\scripts\run-daily.ps1            # normal daily run
#   .\scripts\run-daily.ps1 -DryRun    # skip vault write (smoke test)
#
# Does:
#   1. cd to project root
#   2. load .env into the process environment (so ANTHROPIC_API_KEY is set)
#   3. run `uv run python -m src.main daily`
#   4. append timestamped output to data/cron.log

[CmdletBinding()]
param(
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

$projectRoot = Split-Path $PSScriptRoot -Parent
Set-Location $projectRoot

# Ensure log dir exists
$logDir = Join-Path $projectRoot "data"
if (-not (Test-Path $logDir)) {
    New-Item -ItemType Directory -Path $logDir | Out-Null
}
$logFile = Join-Path $logDir "cron.log"

function Write-Log {
    param([string]$Message)
    $ts = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
    Add-Content -Path $logFile -Value "[$ts] $Message" -Encoding utf8
}

Write-Host "run-daily: started (DryRun=$DryRun). Output goes to data/cron.log — may take 3-8 min." -ForegroundColor Cyan
Write-Log "----- run-daily start (DryRun=$DryRun) -----"

# Load .env (KEY=VALUE per line, # for comments, optional quotes)
$envFile = Join-Path $projectRoot ".env"
if (Test-Path $envFile) {
    foreach ($line in Get-Content $envFile -Encoding utf8) {
        $trimmed = $line.Trim()
        if ($trimmed -eq "" -or $trimmed.StartsWith("#")) { continue }
        $eq = $trimmed.IndexOf("=")
        if ($eq -lt 1) { continue }
        $k = $trimmed.Substring(0, $eq).Trim()
        $v = $trimmed.Substring($eq + 1).Trim().Trim('"').Trim("'")
        Set-Item -Path "Env:$k" -Value $v
    }
} else {
    Write-Log "WARN: .env not found at $envFile"
}

if (-not $env:ANTHROPIC_API_KEY) {
    Write-Log "ERROR: ANTHROPIC_API_KEY not set after loading .env. Aborting."
    exit 1
}

$args = @("run", "python", "-m", "src.main", "daily")
if ($DryRun) { $args += "--dry-run" }

Write-Log "exec: uv $($args -join ' ')"

# Capture stdout+stderr to the log
try {
    $output = & uv @args 2>&1
    $exit = $LASTEXITCODE
    foreach ($line in $output) {
        Add-Content -Path $logFile -Value "    $line" -Encoding utf8
    }
    Write-Log "----- run-daily end (exit=$exit) -----"
    if ($exit -eq 0) {
        Write-Host "run-daily: done (exit=0). See data/cron.log and Obsidian AI_news/Daily/" -ForegroundColor Green
    } else {
        Write-Host "run-daily: failed (exit=$exit). See data/cron.log" -ForegroundColor Red
    }
    exit $exit
}
catch {
    Write-Log "EXCEPTION: $($_.Exception.Message)"
    Write-Host "run-daily: EXCEPTION — $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
