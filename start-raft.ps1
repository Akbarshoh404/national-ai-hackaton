<#
.SYNOPSIS
  Start the Raft backend on this machine (local hosting).

.DESCRIPTION
  Checks the virtualenv, .env and the local model (Ollama), then runs the API in this window with all
  background workers enabled in backend\.env (Telegram listener, extractor, decisions, bot).
  Logs are also written to backend\logs\raft-YYYYMMDD.log. Stop with Ctrl+C.

.PARAMETER Lan
  Listen on all interfaces (0.0.0.0) so phones/laptops on the same network can reach it. Default: 127.0.0.1 only.

.PARAMETER Port
  Port to listen on (default: PORT from .env, else 8000).

.PARAMETER NoExtractor
  Do not start the extractor worker (pending Telegram posts stay pending).

.EXAMPLE
  .\start-raft.ps1
  .\start-raft.ps1 -Lan
  .\start-raft.ps1 -NoExtractor
#>
param(
    [switch]$Lan,
    [int]$Port = 0,
    [switch]$NoExtractor
)

$ErrorActionPreference = "Stop"
$backend = Join-Path $PSScriptRoot "backend"
$python = Join-Path $backend ".venv\Scripts\python.exe"

if (-not (Test-Path $python)) {
    Write-Host "No virtualenv found. Create it once:" -ForegroundColor Yellow
    Write-Host "  cd backend; python -m venv .venv; .venv\Scripts\pip install -r requirements-dev.txt"
    exit 1
}
if (-not (Test-Path (Join-Path $backend ".env"))) {
    Write-Host "backend\.env is missing. Copy backend\.env.example to backend\.env and fill it in." -ForegroundColor Yellow
    exit 1
}

# Local model check (extraction falls back to Gemini / rules if it is not running)
try {
    $tags = Invoke-RestMethod -Uri "http://127.0.0.1:11434/api/tags" -TimeoutSec 3
    $names = $tags.models | ForEach-Object { $_.name }
    if ($names -contains "qwen2.5:3b") { Write-Host "Ollama: qwen2.5:3b ready" -ForegroundColor Green }
    else { Write-Host "Ollama is running but qwen2.5:3b is not pulled: ollama pull qwen2.5:3b" -ForegroundColor Yellow }
} catch {
    Write-Host "Ollama not reachable on :11434 - extraction will use Gemini / the rule parser" -ForegroundColor Yellow
}

$env:HOST = if ($Lan) { "0.0.0.0" } else { "127.0.0.1" }
if ($Port -gt 0) { $env:PORT = "$Port" }
if ($NoExtractor) { $env:WORKERS_EXTRACTOR = "false" }

# Resolve the port the same way the app does: -Port, then $env:PORT, then PORT in backend\.env, else 8000.
$effectivePort = 8000
if ($Port -gt 0) { $effectivePort = $Port }
elseif ($env:PORT) { $effectivePort = [int]$env:PORT }
else {
    $line = Get-Content (Join-Path $backend ".env") | Where-Object { $_ -match '^\s*PORT\s*=\s*(\d+)' } | Select-Object -First 1
    if ($line -and $line -match '(\d+)') { $effectivePort = [int]$Matches[1] }
}

# Refuse to start a second copy: it could not bind the port anyway.
$busy = Get-NetTCPConnection -LocalPort $effectivePort -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
if ($busy) {
    $owner = Get-Process -Id $busy.OwningProcess -ErrorAction SilentlyContinue
    Write-Host "Port $effectivePort is already in use by process $($busy.OwningProcess) ($($owner.ProcessName))." -ForegroundColor Red
    Write-Host "Raft is probably already running: open http://127.0.0.1:$effectivePort/docs"
    Write-Host "To restart it, stop that process first:  Stop-Process -Id $($busy.OwningProcess)"
    Write-Host "Or start on another port:                 .\start-raft.ps1 -Port 9000"
    exit 1
}

$logDir = Join-Path $backend "logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$log = Join-Path $logDir ("raft-" + (Get-Date -Format "yyyyMMdd") + ".log")

Write-Host "Starting Raft on $($env:HOST):$effectivePort  (Swagger: http://127.0.0.1:$effectivePort/docs)  log: $log" -ForegroundColor Cyan
if (-not $NoExtractor) {
    Write-Host "The extractor worker will process pending Telegram posts in the background (use -NoExtractor to hold them)."
}

Push-Location $backend
try {
    # uvicorn logs to stderr; let cmd merge the streams so PowerShell sees plain text, not error records.
    # Write the log as UTF-8 (Tee-Object in Windows PowerShell 5 would write UTF-16).
    $ErrorActionPreference = "Continue"
    # FileShare.ReadWrite: the log can be tailed (or held by another tool) without crashing the start.
    $stream = [System.IO.FileStream]::new($log, [System.IO.FileMode]::Append, [System.IO.FileAccess]::Write,
        [System.IO.FileShare]::ReadWrite)
    $writer = [System.IO.StreamWriter]::new($stream, [System.Text.UTF8Encoding]::new($false))
    $writer.AutoFlush = $true
    try {
        cmd /c "`"$python`" -m app.main 2>&1" | ForEach-Object { $_; $writer.WriteLine($_) }
    } finally {
        $writer.Dispose()
    }
} finally {
    Pop-Location
}
