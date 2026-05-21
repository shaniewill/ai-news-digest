# Start Claude Code using Claude Pro/Max subscription (OAuth), not Console API billing.
# Usage: .\scripts\start-claude-pro.ps1
# Optional args are passed to claude, e.g. .\scripts\start-claude-pro.ps1 -c

$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

# Project .env is for `uv run python -m src.main daily` only.
# If ANTHROPIC_API_KEY is in the shell, Claude Code prefers API billing over Pro.
Remove-Item Env:ANTHROPIC_API_KEY -ErrorAction SilentlyContinue
Remove-Item Env:ANTHROPIC_AUTH_TOKEN -ErrorAction SilentlyContinue

Write-Host "Starting Claude Code (subscription mode). API key env vars cleared for this session." -ForegroundColor Cyan
Write-Host "If prompted in browser, sign in with your Claude Pro account (claude.ai), NOT Console API billing." -ForegroundColor DarkGray

& claude @args
