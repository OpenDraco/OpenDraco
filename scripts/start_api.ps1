# `$PSScriptRoot` now points at `scripts/`; the API server lives at the
# repo root, so step up one directory before resolving sibling paths.
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

$apiEnvFile    = Join-Path $RepoRoot "api\.env"
$evomasEnvFile = Join-Path $RepoRoot "evomas\.env"
$apiHost = "0.0.0.0"
$apiPort = "8000"

# Parse one .env file into a hashtable. Returns `@{}` if the file is
# missing. Quote-stripping mirrors what python-dotenv does inside the
# server, so the values shown here match what the API actually reads.
function Read-EnvFile {
    param([string]$Path)
    $bag = [ordered]@{}
    if (-not (Test-Path $Path)) { return $bag }
    foreach ($line in Get-Content $Path) {
        $trim = $line.Trim()
        if (-not $trim -or $trim.StartsWith("#")) { continue }
        $kv = $trim -split "=", 2
        if ($kv.Length -ne 2) { continue }
        $bag[$kv[0].Trim()] = $kv[1].Trim().Trim('"').Trim("'")
    }
    return $bag
}

# Mask values that look like API keys / tokens so they don't end up in
# scrollback or screenshots. Anything else is printed verbatim.
function Format-EnvValue {
    param([string]$Key, [string]$Value)
    if ($Key -match "(?i)(api[_-]?key|secret|token|password)") {
        if ($Value.Length -gt 8) {
            return ($Value.Substring(0, 6) + "***(" + $Value.Length + " chars)")
        }
        return "***"
    }
    return $Value
}

# Print both .env files plus a "Effective" column showing which value
# wins after `load_dotenv(override=False)` runs in evomas/paths.py —
# shell-set env vars take precedence over .env values, so a stale
# `$env:RESULTS_DIR=...` in the launching shell quietly beats the file.
$evomasEnv = Read-EnvFile $evomasEnvFile
$apiEnv    = Read-EnvFile $apiEnvFile

# Surface API_HOST/API_PORT for the uvicorn launch line. api/.env wins
# over evomas/.env on collisions, matching the python-side merge order.
if ($apiEnv.Contains("API_HOST")) { $apiHost = $apiEnv["API_HOST"] }
elseif ($evomasEnv.Contains("API_HOST")) { $apiHost = $evomasEnv["API_HOST"] }
if ($apiEnv.Contains("API_PORT")) { $apiPort = $apiEnv["API_PORT"] }
elseif ($evomasEnv.Contains("API_PORT")) { $apiPort = $evomasEnv["API_PORT"] }

Write-Host ""
Write-Host "=== Env from evomas/.env ===" -ForegroundColor Cyan
if ($evomasEnv.Count -eq 0) {
    Write-Host "  (file missing or empty)"
} else {
    foreach ($k in $evomasEnv.Keys) {
        Write-Host ("  {0,-26} = {1}" -f $k, (Format-EnvValue -Key $k -Value $evomasEnv[$k]))
    }
}

Write-Host ""
Write-Host "=== Env from api/.env ===" -ForegroundColor Cyan
if ($apiEnv.Count -eq 0) {
    Write-Host "  (file missing or empty)"
} else {
    foreach ($k in $apiEnv.Keys) {
        Write-Host ("  {0,-26} = {1}" -f $k, (Format-EnvValue -Key $k -Value $apiEnv[$k]))
    }
}

Write-Host ""
Write-Host "=== Effective in this shell (shell env wins over .env via override=False) ===" -ForegroundColor Cyan
$allKeys = @($evomasEnv.Keys + $apiEnv.Keys) | Sort-Object -Unique
foreach ($k in $allKeys) {
    $shellVal = [System.Environment]::GetEnvironmentVariable($k, "Process")
    # api/.env wins over evomas/.env on collisions (matches the
    # python-dotenv load order in evomas/paths.py).
    $envVal = if ($apiEnv.Contains($k)) { $apiEnv[$k] } else { $evomasEnv[$k] }
    $envSrc = if ($apiEnv.Contains($k)) { "api/.env" } else { "evomas/.env" }

    # Only flag a genuine override: shell value present AND different
    # from the .env value. The `evomas` CLI imports evomas.paths
    # (which eagerly load_dotenv()'s) before spawning this script, so
    # every .env key is already in the process env by the time we
    # inspect it — that's not a real override and shouldn't warn.
    if ($shellVal -and $shellVal -ne $envVal) {
        $src = "shell"
        $val = $shellVal
        $marker = " <- shell overrides .env!"
        $color = "Yellow"
    } else {
        $src = $envSrc
        $val = $envVal
        $marker = ""
        $color = "Gray"
    }
    Write-Host ("  {0,-26} = {1,-50}  [{2}]{3}" -f $k, (Format-EnvValue -Key $k -Value $val), $src, $marker) `
        -ForegroundColor $color
}
Write-Host ""

# Venv installed by install.ps1 to `~\.evomas-venv` (in the user's home so
# the repo stays free of build artefacts).
$VenvDir = Join-Path $HOME ".evomas-venv"
$Uvicorn = Join-Path $VenvDir "Scripts\uvicorn.exe"
if (-not (Test-Path $Uvicorn)) {
    Write-Host "[start_api] uvicorn not found at $Uvicorn -- run install.ps1 first." -ForegroundColor Red
    exit 1
}

# Port-occupancy preflight. Parses `netstat -ano` because
# `Get-NetTCPConnection` caches stale entries on Windows when a uvicorn
# reloader cycle leaves orphaned multiprocessing children holding the
# socket. taskkill /F /T kills the whole process tree, which is what
# we need when a `uvicorn --reload` setup leaves a parent + worker pair.
function Get-PidOnPort {
    param([int]$Port)
    $needle = ":" + $Port
    $lines = & cmd /c ("netstat -ano | findstr LISTENING | findstr " + $needle) 2>$null
    foreach ($line in $lines) {
        $tokens = ($line -split '\s+') | Where-Object { $_ }
        if ($tokens.Count -lt 5) { continue }
        # Only match an exact :<port> ending on the local address (4th column).
        $local = $tokens[1]
        if ($local -match (":" + $Port + "$")) {
            return [int]$tokens[-1]
        }
    }
    return $null
}

$portPid = Get-PidOnPort -Port ([int]$apiPort)
if ($portPid) {
    $p = Get-Process -Id $portPid -ErrorAction SilentlyContinue
    $name = if ($p) { $p.ProcessName } else { "<exited>" }
    Write-Host ""
    Write-Host ("Port " + $apiPort + " is already in use (PID " + $portPid + " / " + $name + ").") -ForegroundColor Yellow
    $ans = Read-Host "Kill the existing listener and continue? [y/N]"
    if ($ans -match '^[yY]') {
        & cmd /c ("taskkill /F /T /PID " + $portPid) 2>&1 | Out-Null
        Start-Sleep -Seconds 1
        $still = Get-PidOnPort -Port ([int]$apiPort)
        if ($still) {
            Write-Host ("Could not free port " + $apiPort + " (PID " + $still + " still listening). Exiting.") -ForegroundColor Red
            exit 1
        }
        Write-Host ("Port " + $apiPort + " freed.") -ForegroundColor Green
    } else {
        Write-Host "Aborted -- port still in use, not launching." -ForegroundColor Yellow
        exit 0
    }
}
Write-Host "Starting EvoMas API server on http://$($apiHost):$($apiPort)"
# --app-dir points at the repo root (not api\) so `from api import common`
# inside api\server.py finds the `api` package on sys.path.
& $Uvicorn --app-dir "$RepoRoot" api.server:app --host $apiHost --port $apiPort --reload
