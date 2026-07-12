$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

$RepoRoot = $PSScriptRoot
# Venv lives in the user's home (`~\.evomas-venv`) so the repo stays
# free of build artefacts and the same env can be shared across multiple
# checkouts of the repo. start_api.ps1 + the $PROFILE wrapper appended
# at the end of this script both reference the same path.
$VenvDir  = Join-Path $HOME ".evomas-venv"
$PythonEvomas = Join-Path $VenvDir "Scripts\python.exe"
$EvomasExe    = Join-Path $VenvDir "Scripts\evomas.exe"

function Test-Cli($name, $hint) {
    $found = Get-Command $name -ErrorAction SilentlyContinue
    if (-not $found) {
        Write-Host "[install] missing prerequisite: $name" -ForegroundColor Yellow
        Write-Host "        $hint"
        return $false
    }
    Write-Host "[install] found $name -> $($found.Source)"
    return $true
}

function Test-Wsl {
    # wsl.exe ships with Windows even when no distro is installed, so a bare
    # Get-Command check isn't enough -- probe that a distro actually runs.
    $found = Get-Command wsl -ErrorAction SilentlyContinue
    if (-not $found) {
        Write-Host "[install] missing prerequisite: wsl2" -ForegroundColor Yellow
        Write-Host "        Install WSL2 from https://learn.microsoft.com/windows/wsl/install (needed for local SWE-bench eval on Windows)."
        return $false
    }
    try {
        & wsl.exe -e true 2>$null | Out-Null
        if ($LASTEXITCODE -eq 0) {
            Write-Host "[install] found wsl2 -> $($found.Source)"
            return $true
        }
    } catch { }
    Write-Host "[install] wsl present but no runnable distro" -ForegroundColor Yellow
    Write-Host "        Install a distro (e.g. 'wsl --install -d Ubuntu') -- needed for local SWE-bench eval on Windows."
    return $false
}

# --- 1. Prerequisite checks --------------------------------------------------
Write-Host "[install] checking prerequisites" -ForegroundColor Cyan
$pythonOk = Test-Cli "python" "Install Python 3.12+ from https://www.python.org/downloads/ (Python 3.12.6 is the dev baseline)."
$ollamaOk = Test-Cli "ollama" "Install Ollama from https://ollama.com/download (only needed for local models)."
$dockerOk = Test-Cli "docker" "Install Docker Desktop from https://www.docker.com/products/docker-desktop/ (needed for local SWE-bench eval)."
$npmOk    = Test-Cli "npm"    "Install Node.js 18+ from https://nodejs.org/ (needed for the Angular frontend)."
$wslOk    = Test-Wsl

# Only python is mandatory. Ollama, Docker, Node and WSL2 are feature-gated --
# warn and continue so an inference-only or CLI-only install still succeeds.
if (-not $pythonOk) {
    Write-Host "[install] python is mandatory; aborting." -ForegroundColor Red
    exit 1
}
if (-not $ollamaOk) {
    Write-Host "[install] continuing without ollama -- only needed for local models; `evomas ollama *` + ollama/* agents will fail until you install it."
}
if (-not $dockerOk) {
    Write-Host "[install] continuing without docker -- only needed for local SWE-bench eval; `evomas run evaluation` (default --local) will fail; pass --remote to use sb-cli instead."
}
if (-not $npmOk) {
    Write-Host "[install] continuing without npm -- only needed for the Angular frontend; `evomas web` will fail until you install Node.js."
}
if (-not $wslOk) {
    Write-Host "[install] continuing without WSL2 -- only needed for local SWE-bench eval on Windows ('evomas run evaluation --local')."
}

# --- 2. Ensure the venv exists -----------------------------------------------
# `install.ps1` is non-destructive: we never delete an existing venv, since
# that wipes any in-flight work or manually-installed extras. If something
# in the venv is broken, the user should remove it themselves and rerun
# setup -- see the troubleshooting section in README.md.
if (Test-Path $VenvDir) {
    Write-Host "[install] reusing existing venv at $VenvDir (pass through pip resolves any drift)" -ForegroundColor Cyan
} else {
    Write-Host "[install] creating venv at $VenvDir" -ForegroundColor Cyan
    python -m venv $VenvDir
}

Write-Host "[install] upgrading pip + wheel" -ForegroundColor Cyan
& $PythonEvomas -m pip install --upgrade pip wheel

# --- 3. Install the project --------------------------------------------------
# `-e .` reads pyproject.toml; deps are pinned there and an `evomas` console
# script is registered against `evomas.cli:main`. No more hand-maintained
# `pip install langchain langgraph ...` list.
Write-Host "[install] installing evomas (editable) + dependencies + dev extras" -ForegroundColor Cyan
& $PythonEvomas -m pip install -e ".[dev]"

# Snapshot exact resolved versions to requirements.txt for reproducibility /
# recovery if a downstream package ships a breaking release. pyproject.toml
# stays the canonical input; this file is a regenerated lockfile.
Write-Host "[install] freezing pinned versions to requirements.txt" -ForegroundColor Cyan
& $PythonEvomas -m pip freeze | Out-File -Encoding utf8 (Join-Path $RepoRoot "requirements.txt")

# --- 3b. Register the venv as a Jupyter kernel ------------------------------
# The "reproduce-this-run" notebook exported from the Results page sets
# `kernelspec.name = "evomas"` so opening it in Jupyter / VSCode auto-picks
# this interpreter without the user having to hunt through the kernel
# dropdown. `ipykernel` itself ships via the pip install above; this
# step just publishes the kernelspec under the user's Jupyter data dir
# (idempotent -- safe to re-run).
Write-Host "[install] registering 'evomas' Jupyter kernel" -ForegroundColor Cyan
& $PythonEvomas -m ipykernel install --user --name evomas `
    --display-name "Python 3 (EvoMas)" 2>&1 | Out-Null

# --- 4. Install npm deps for the Angular frontend ---------------------------
# Without this, `npx ng serve` (invoked by `evomas web` / start_frontend.ps1)
# resolves `ng` against the global npm registry, fetches the wrong package,
# and exits with "could not determine executable to run". `npm install`
# populates app\node_modules so npx finds the Angular CLI locally.
if ($npmOk) {
    Write-Host "[install] installing app\ npm dependencies (Angular CLI + project deps)" -ForegroundColor Cyan
    Push-Location (Join-Path $RepoRoot "app")
    try {
        npm install --no-audit --no-fund
    } finally {
        Pop-Location
    }
} else {
    Write-Host "[install] skipping npm install -- node/npm not available." -ForegroundColor Yellow
}

# --- 5. PowerShell $PROFILE wrapper -----------------------------------------
# pip install -e . registers `evomas.exe` inside the venv. To call it from
# anywhere without activating the venv first, append a function to the
# user's PowerShell profile that delegates to the venv's exe.
$ProfilePath = $PROFILE
$ProfileDir  = Split-Path -Parent $ProfilePath
if (-not (Test-Path $ProfileDir)) { New-Item -ItemType Directory -Path $ProfileDir -Force | Out-Null }
if (-not (Test-Path $ProfilePath)) { New-Item -ItemType File -Path $ProfilePath -Force | Out-Null }

$Marker = "# >>> evomas-cli >>>"
$EndMarker = "# <<< evomas-cli <<<"
$existing = Get-Content $ProfilePath -Raw -ErrorAction SilentlyContinue
if ($existing -and $existing.Contains($Marker)) {
    Write-Host "[install] refreshing existing evomas function in $ProfilePath" -ForegroundColor Cyan
    $pattern = "(?ms)" + [regex]::Escape($Marker) + ".*?" + [regex]::Escape($EndMarker)
    $existing = [regex]::Replace($existing, $pattern, "").TrimEnd() + "`r`n"
    Set-Content -Path $ProfilePath -Value $existing -Encoding utf8
}

$Block = @"
$Marker
function evomas {
    & "$EvomasExe" @args
}
$EndMarker
"@
Add-Content -Path $ProfilePath -Value $Block -Encoding utf8
Write-Host "[install] appended evomas function to $ProfilePath" -ForegroundColor Green

# --- 6. Set up the SWE-bench harness (local evaluation only) -----------------
# `evomas run evaluation` defaults to --local, which drives the official
# SWE-bench Docker harness. That harness is NOT a pip dependency; it lives in a
# sibling clone at <repo>\SWE-bench with its own venv. It's POSIX-only and needs
# Docker to run, so on Windows it requires BOTH Docker and WSL2 -- we gate the
# whole clone+build behind those two checks and skip it otherwise.
$SwebenchDir = Join-Path $RepoRoot "SWE-bench"
# POSIX venv layout: the venv is Linux-built (inside WSL), so python lives at venv/bin/.
$SwebenchVenvPython = Join-Path $SwebenchDir "venv\bin\python"
if (-not ($dockerOk -and $wslOk)) {
    $missing = @()
    if (-not $dockerOk) { $missing += "Docker" }
    if (-not $wslOk)    { $missing += "WSL2" }
    Write-Host "[install] skipping SWE-bench harness setup -- local eval on Windows needs $($missing -join ' + ')." -ForegroundColor Yellow
    Write-Host "          Install the missing piece and rerun install.ps1 (or set it up manually -- see README 'SWE-bench harness')."
} else {
    # Clone (idempotent -- skipped if the dir already exists).
    if (Test-Path $SwebenchDir) {
        Write-Host "[install] SWE-bench clone already present at $SwebenchDir (leaving as-is)" -ForegroundColor Cyan
    } else {
        Write-Host "[install] cloning SWE-bench harness into $SwebenchDir" -ForegroundColor Cyan
        git clone https://github.com/SWE-bench/SWE-bench.git $SwebenchDir
        if ($LASTEXITCODE -ne 0) {
            Write-Host "[install] warning: SWE-bench clone failed -- 'evomas run evaluation --local' will not work until you clone it manually." -ForegroundColor Yellow
        }
    }
    # Build the harness venv inside WSL (idempotent -- skipped if already built).
    if (Test-Path $SwebenchDir) {
        if (Test-Path $SwebenchVenvPython) {
            Write-Host "[install] SWE-bench venv already built at $SwebenchDir\venv (leaving as-is)" -ForegroundColor Cyan
        } else {
            Write-Host "[install] building SWE-bench harness venv inside WSL (POSIX-only)" -ForegroundColor Cyan
            $WslPath = (& wsl.exe wslpath -a "$SwebenchDir").Trim()
            & wsl.exe bash -lc "cd '$WslPath' && python3 -m venv venv && ./venv/bin/pip install -e ."
            if ($LASTEXITCODE -eq 0 -and (Test-Path $SwebenchVenvPython)) {
                Write-Host "[install] SWE-bench harness venv ready" -ForegroundColor Green
            } else {
                Write-Host "[install] warning: SWE-bench venv build failed (WSL may be missing python3-venv) -- build it manually:" -ForegroundColor Yellow
                Write-Host "          wsl  # then: cd SWE-bench && python3 -m venv venv && source venv/bin/activate && pip install -e ."
            }
        }
    }
}

# --- 7. .env scaffolding -----------------------------------------------------
# Copy the example env files into place (non-destructive: never clobber an
# existing .env). Fill in OLLAMA_BASE_URL etc. afterwards -- see README.
$EvomasEnv = Join-Path $RepoRoot "evomas\.env"
if (-not (Test-Path $EvomasEnv)) {
    Copy-Item (Join-Path $RepoRoot "evomas\.env.example") $EvomasEnv
    Write-Host "[install] created evomas\.env from evomas\.env.example -- fill in OLLAMA_BASE_URL" -ForegroundColor Green
} else {
    Write-Host "[install] evomas\.env already exists (leaving as-is)" -ForegroundColor Cyan
}
$ApiEnv = Join-Path $RepoRoot "api\.env"
if (-not (Test-Path $ApiEnv)) {
    Copy-Item (Join-Path $RepoRoot "api\.env.example") $ApiEnv
    Write-Host "[install] created api\.env from api\.env.example" -ForegroundColor Green
} else {
    Write-Host "[install] api\.env already exists (leaving as-is)" -ForegroundColor Cyan
}

Write-Host ""
Write-Host "[install] done." -ForegroundColor Green
Write-Host "        Open a fresh PowerShell window so the new \$PROFILE function loads, then:"
Write-Host ""
Write-Host "          evomas --help                                  # uses the venv automatically via the profile function"
Write-Host ""
Write-Host "        For interactive dev work (running pytest, importing evomas modules, etc.)"
Write-Host "        activate the venv directly:"
Write-Host ""
Write-Host "          & `"$VenvDir\Scripts\Activate.ps1`"             # then `python`, `pytest`, `pip` target the venv"
Write-Host "          deactivate                                     # leaves the venv"
