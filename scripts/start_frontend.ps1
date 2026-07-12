# `$PSScriptRoot` now points at `scripts/`; the Angular app lives at the
# repo root, so step up one directory before resolving the path.
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$AppDir   = Join-Path $RepoRoot "app"

# Self-heal: if a contributor invokes `evomas web` without running setup
# first (or just `git pull`ed and forgot), `npx ng serve` will fetch the
# wrong `ng` package from npmjs and exit with "could not determine
# executable to run". Install local deps once if node_modules is absent.
if (-not (Test-Path (Join-Path $AppDir "node_modules"))) {
    Write-Host "[start_frontend] app\node_modules missing -- running 'npm install' first" -ForegroundColor Yellow
    Push-Location $AppDir
    try {
        npm install --no-audit --no-fund
    } finally {
        Pop-Location
    }
}

# Pre-flight diagnostic. The frontend doesn't read .env — the API URL
# is hardcoded in `app/src/app/services/api.service.ts`. The two things
# worth surfacing before `ng serve` blocks the terminal: which API URL
# the bundle will dial, and whether that URL answers right now.
$ApiBase = "http://localhost:8000/api"
$apiServiceFile = Join-Path $AppDir "src\app\services\api.service.ts"
if (Test-Path $apiServiceFile) {
    foreach ($line in Get-Content $apiServiceFile) {
        if ($line -match "^const\s+BASE\s*=\s*['""]([^'""]+)['""]") {
            $ApiBase = $matches[1]
            break
        }
    }
}

# Read API_PORT from .env (api/.env wins over evomas/.env). If the
# user bumped the port there, the frontend's baked URL (likely :8000)
# won't follow -- surface that mismatch explicitly.
$apiEnvFileFE    = Join-Path $RepoRoot "api\.env"
$evomasEnvFileFE = Join-Path $RepoRoot "evomas\.env"
$envApiPort = $null
foreach ($f in @($evomasEnvFileFE, $apiEnvFileFE)) {
    if (-not (Test-Path $f)) { continue }
    foreach ($line in Get-Content $f) {
        $trim = $line.Trim()
        if (-not $trim -or $trim.StartsWith("#")) { continue }
        $kv = $trim -split "=", 2
        if ($kv.Length -ne 2) { continue }
        if ($kv[0].Trim() -eq "API_PORT") {
            $envApiPort = $kv[1].Trim().Trim('"').Trim("'")
        }
    }
}
$bakedPort = if ($ApiBase -match ":(\d+)/") { $matches[1] } else { "8000" }

Write-Host ""
Write-Host "=== Frontend launch config ===" -ForegroundColor Cyan
Write-Host ("  app dir          : {0}" -f $AppDir)
Write-Host ("  serving on       : http://localhost:4200")
Write-Host ("  API base (baked) : {0}" -f $ApiBase)
if ($envApiPort -and $envApiPort -ne $bakedPort) {
    Write-Host ("  API_PORT (.env)  : {0} -- DIFFERS from the baked URL ({1})" -f $envApiPort, $bakedPort) -ForegroundColor Yellow
    Write-Host ("                     the frontend will dial :{0}; edit api.service.ts if you want it to follow .env" -f $bakedPort) -ForegroundColor Yellow
}

# Probe the API. Use 127.0.0.1 explicitly (not `localhost`) because on
# Windows the latter resolves to ::1 first; if the API binds IPv4-only
# the v6 leg of the lookup times out and the probe spuriously fails.
# 5s timeout gives uvicorn --reload room to finish its first-request
# bootstrap on a cold start.
$apiOk = $false
$probeUrl = ""
try {
    $tail = ($ApiBase -replace "^https?://[^/]+", "")
    if (-not $tail) { $tail = "/api" }
    $probeUrl = "http://127.0.0.1:" + $bakedPort + ($tail.TrimEnd('/')) + "/health"
    $resp = Invoke-WebRequest -Uri $probeUrl -UseBasicParsing -TimeoutSec 5 -ErrorAction Stop
    if ($resp.StatusCode -eq 200) { $apiOk = $true }
} catch {
    $apiOk = $false
}
if ($apiOk) {
    Write-Host ("  API /health      : OK ({0})" -f $probeUrl) -ForegroundColor Green
} else {
    Write-Host ("  API /health      : UNREACHABLE at {0}" -f $probeUrl) -ForegroundColor Yellow
    Write-Host ("                     start with 'evomas api' or check the port matches the baked URL.") -ForegroundColor Yellow
}
Write-Host ""

# Port-occupancy preflight. Same logic as start_api.ps1: netstat -ano +
# taskkill /F /T (whole-tree) so a stale `ng serve` from a prior session
# can't silently keep :4200 captured.
function Get-PidOnPort {
    param([int]$Port)
    $needle = ":" + $Port
    $lines = & cmd /c ("netstat -ano | findstr LISTENING | findstr " + $needle) 2>$null
    foreach ($line in $lines) {
        $tokens = ($line -split '\s+') | Where-Object { $_ }
        if ($tokens.Count -lt 5) { continue }
        $local = $tokens[1]
        if ($local -match (":" + $Port + "$")) {
            return [int]$tokens[-1]
        }
    }
    return $null
}

$FrontendPort = 4200
$portPid = Get-PidOnPort -Port $FrontendPort
if ($portPid) {
    $p = Get-Process -Id $portPid -ErrorAction SilentlyContinue
    $name = if ($p) { $p.ProcessName } else { "<exited>" }
    Write-Host ""
    Write-Host ("Port " + $FrontendPort + " is already in use (PID " + $portPid + " / " + $name + ").") -ForegroundColor Yellow
    $ans = Read-Host "Kill the existing listener and continue? [y/N]"
    if ($ans -match '^[yY]') {
        & cmd /c ("taskkill /F /T /PID " + $portPid) 2>&1 | Out-Null
        Start-Sleep -Seconds 1
        $still = Get-PidOnPort -Port $FrontendPort
        if ($still) {
            Write-Host ("Could not free port " + $FrontendPort + " (PID " + $still + " still listening). Exiting.") -ForegroundColor Red
            exit 1
        }
        Write-Host ("Port " + $FrontendPort + " freed.") -ForegroundColor Green
    } else {
        Write-Host "Aborted -- port still in use, not launching." -ForegroundColor Yellow
        exit 0
    }
}

Write-Host "Starting EvoMas Angular frontend on http://localhost:4200"
Push-Location $AppDir
try {
    npx ng serve --open
} finally {
    Pop-Location
}
