#!/usr/bin/env bash
# Linux / macOS counterpart of install.ps1.
# Behaviour mirrors the PowerShell script: non-destructive venv reuse,
# `pip install -e "."`, regenerated requirements.txt lockfile, and
# an idempotent `evomas` function appended to the user's shell rc.
set -euo pipefail

REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# Venv lives in the user's home (`~/.evomas-venv`) so the repo stays
# free of build artefacts and the same env can be shared across multiple
# checkouts of the repo. start_api.sh + the rc-function appended below
# both reference the same path.
VENV_DIR="$HOME/.evomas-venv"
PYTHON_EVOMAS="$VENV_DIR/bin/python"
EVOMAS_EXE="$VENV_DIR/bin/evomas"

# Prefer python3 over python (Linux/macOS convention).
PYTHON_BIN="$(command -v python3 || command -v python || true)"
if [ -z "$PYTHON_BIN" ]; then
    echo "[install] python3 not found -- install Python 3.10+ first" >&2
    echo "        https://www.python.org/downloads/  (3.12.6 is the dev baseline)" >&2
    exit 1
fi

test_cli() {
    local name="$1"; local hint="$2"
    if command -v "$name" >/dev/null 2>&1; then
        echo "[install] found $name -> $(command -v "$name")"
        return 0
    fi
    echo "[install] missing prerequisite: $name"
    echo "        $hint"
    return 1
}

# ── 1. Prerequisite checks ────────────────────────────────────────────────────
echo "[install] checking prerequisites"
echo "[install] python -> $PYTHON_BIN"
ollama_ok=0; test_cli ollama "Install Ollama from https://ollama.com/download." && ollama_ok=1 || true
docker_ok=0; test_cli docker "Install Docker (Desktop on macOS) from https://www.docker.com/products/docker-desktop/ (required for default 'evomas run evaluation --local')." && docker_ok=1 || true
npm_ok=0;    test_cli npm    "Install Node.js 18+ from https://nodejs.org/ (needed for the Angular frontend)." && npm_ok=1 || true

# Only python is mandatory (the check above aborts if it's missing). Ollama,
# Docker and Node are feature-gated -- warn and continue so an inference-only
# or CLI-only install still succeeds.
[ "$ollama_ok" = 0 ] && echo "[install] continuing without ollama -- only needed for local models; 'evomas ollama *' + ollama/* agents will fail until you install it."
[ "$docker_ok" = 0 ] && echo "[install] continuing without docker -- only needed for local SWE-bench eval; 'evomas run evaluation' (default --local) will fail; pass --remote to use sb-cli instead."
[ "$npm_ok" = 0 ]    && echo "[install] continuing without npm -- only needed for the Angular frontend; 'evomas web' will fail until you install Node.js."

# ── 2. Ensure the venv exists ────────────────────────────────────────────────
# Non-destructive: never delete an existing venv. If something is broken,
# remove it yourself (`rm -rf "$VENV_DIR"`) and re-run setup -- see the
# troubleshooting section in README.md.
if [ -d "$VENV_DIR" ]; then
    echo "[install] reusing existing venv at $VENV_DIR (pass through pip resolves any drift)"
else
    echo "[install] creating venv at $VENV_DIR"
    "$PYTHON_BIN" -m venv "$VENV_DIR"
fi

echo "[install] upgrading pip + wheel"
"$PYTHON_EVOMAS" -m pip install --upgrade pip wheel

# ── 3. Install the project ───────────────────────────────────────────────────
# `-e "."` reads pyproject.toml; deps are pinned there and an `evomas`
# console script is registered against `evomas.cli:main`.
echo "[install] installing evomas (editable) + dependencies + dev extras"
"$PYTHON_EVOMAS" -m pip install -e ".[dev]"

# Snapshot exact resolved versions to requirements.txt for reproducibility /
# recovery if a downstream package ships a breaking release. pyproject.toml
# stays the canonical input; this file is a regenerated lockfile.
echo "[install] freezing pinned versions to requirements.txt"
"$PYTHON_EVOMAS" -m pip freeze > "$REPO_ROOT/requirements.txt"

# ── 3b. Register the venv as a Jupyter kernel ────────────────────────────────
# The "reproduce-this-run" notebook exported from the Results page sets
# `kernelspec.name = "evomas"` so opening it in Jupyter / VSCode auto-picks
# this interpreter without the user having to hunt through the kernel
# dropdown. `ipykernel` itself ships via the pip install above; this
# step just publishes the kernelspec under the user's Jupyter data dir
# (idempotent -- safe to re-run).
echo "[install] registering 'evomas' Jupyter kernel"
"$PYTHON_EVOMAS" -m ipykernel install --user --name evomas \
    --display-name "Python 3 (EvoMas)" >/dev/null 2>&1 || \
    echo "[install] warning: ipykernel registration failed (notebooks will fall back to a generic Python 3 kernel)"

# ── 4. Install npm deps for the Angular frontend ─────────────────────────────
# Without this, `npx ng serve` (invoked by `evomas web` / start_frontend.sh)
# resolves `ng` against the global npm registry, fetches a wrong package,
# and exits with "could not determine executable to run". Running `npm
# install` populates app/node_modules so npx finds the Angular CLI locally.
if [ "$npm_ok" = 1 ]; then
    echo "[install] installing app/ npm dependencies (Angular CLI + project deps)"
    (cd "$REPO_ROOT/app" && npm install --no-audit --no-fund)
else
    echo "[install] skipping npm install -- node/npm not available."
fi

# ── 5. Shell-rc evomas function ──────────────────────────────────────────────
# pip install -e . registers `evomas` inside the venv's bin/. To call it
# from anywhere without activating the venv, append a function to the
# user's shell rc that delegates to the venv binary.
detect_shell_rc() {
    case "${SHELL:-}" in
        */zsh)  echo "$HOME/.zshrc" ;;
        */bash) [ -f "$HOME/.bashrc" ] && echo "$HOME/.bashrc" || echo "$HOME/.bash_profile" ;;
        */fish) echo "$HOME/.config/fish/config.fish" ;;
        *)      echo "$HOME/.profile" ;;
    esac
}

RC_PATH="$(detect_shell_rc)"
MARKER="# >>> evomas-cli >>>"
END_MARKER="# <<< evomas-cli <<<"

mkdir -p "$(dirname "$RC_PATH")"
[ ! -f "$RC_PATH" ] && touch "$RC_PATH"

# Strip any previous block between markers (re-runs replace, never stack).
# Substring match (`index() > 0`), not `$0 == s`, because earlier versions of
# this script appended without a leading newline -- if the rc file didn't
# end with a newline the start marker got concatenated onto the existing
# last line (e.g. `. ~/.bashrc-extras# >>> evomas-cli >>>`). The robust
# pass below preserves any text before the start marker on its line and
# any text after the end marker on its line, so even a malformed previous
# injection is cleaned up correctly.
if grep -qF "$MARKER" "$RC_PATH"; then
    echo "[install] refreshing existing evomas function in $RC_PATH"
    awk -v s="$MARKER" -v e="$END_MARKER" '
        BEGIN { skip = 0 }
        {
            spos = index($0, s)
            if (spos > 0) {
                if (!skip && spos > 1) print substr($0, 1, spos - 1)
                skip = 1
                next
            }
            if (skip) {
                epos = index($0, e)
                if (epos > 0) {
                    skip = 0
                    rest = substr($0, epos + length(e))
                    if (rest != "") print rest
                }
                next
            }
            print
        }
    ' "$RC_PATH" > "$RC_PATH.tmp" && mv "$RC_PATH.tmp" "$RC_PATH"
fi

# Ensure the rc file ends with a newline so the heredoc below appends on a
# fresh line instead of being concatenated onto an existing one.
if [ -s "$RC_PATH" ] && [ -n "$(tail -c1 "$RC_PATH")" ]; then
    printf '\n' >> "$RC_PATH"
fi

# Append fresh block. Fish uses different function syntax; everything else
# is POSIX-ish.
if [[ "$RC_PATH" == *fish* ]]; then
    cat >> "$RC_PATH" <<EOF
$MARKER
function evomas
    "$EVOMAS_EXE" \$argv
end
$END_MARKER
EOF
else
    cat >> "$RC_PATH" <<EOF
$MARKER
evomas() {
    "$EVOMAS_EXE" "\$@"
}
$END_MARKER
EOF
fi
echo "[install] appended evomas function to $RC_PATH"

# ── 6. Set up the SWE-bench harness (local evaluation only) ──────────────────
# `evomas run evaluation` defaults to --local, which drives the official
# SWE-bench Docker harness. That harness is NOT a pip dependency; it lives in a
# sibling clone at <repo>/SWE-bench with its own venv. It's only usable when
# Docker is present (the harness runs each instance in a container), so we gate
# the whole clone+build behind the Docker check -- no point setting it up on a
# box that can't run it.
SWEBENCH_DIR="$REPO_ROOT/SWE-bench"
if [ "$docker_ok" = 0 ]; then
    echo "[install] skipping SWE-bench harness setup -- local eval needs Docker."
    echo "          Install Docker and rerun install.sh (or set it up manually -- see README 'SWE-bench harness')."
else
    # Clone (idempotent -- skipped if the dir already exists).
    if [ -d "$SWEBENCH_DIR" ]; then
        echo "[install] SWE-bench clone already present at $SWEBENCH_DIR (leaving as-is)"
    else
        echo "[install] cloning SWE-bench harness into $SWEBENCH_DIR"
        git clone https://github.com/SWE-bench/SWE-bench.git "$SWEBENCH_DIR" || \
            echo "[install] warning: SWE-bench clone failed -- 'evomas run evaluation --local' will not work until you clone it manually."
    fi
    # Build the harness venv (idempotent -- skipped if already built).
    if [ -d "$SWEBENCH_DIR" ]; then
        if [ -x "$SWEBENCH_DIR/venv/bin/python" ]; then
            echo "[install] SWE-bench venv already built at $SWEBENCH_DIR/venv (leaving as-is)"
        else
            echo "[install] building SWE-bench harness venv at $SWEBENCH_DIR/venv"
            if "$PYTHON_BIN" -m venv "$SWEBENCH_DIR/venv" && \
               "$SWEBENCH_DIR/venv/bin/pip" install -e "$SWEBENCH_DIR"; then
                echo "[install] SWE-bench harness venv ready"
            else
                echo "[install] warning: SWE-bench venv build failed -- build it manually before local eval:"
                echo "          cd SWE-bench && python3 -m venv venv && source venv/bin/activate && pip install -e ."
            fi
        fi
    fi
fi

# ── 7. .env scaffolding ──────────────────────────────────────────────────────
# Copy the example env files into place (non-destructive: never clobber an
# existing .env). Fill in OLLAMA_BASE_URL etc. afterwards -- see README.
if [ ! -f "$REPO_ROOT/evomas/.env" ]; then
    cp "$REPO_ROOT/evomas/.env.example" "$REPO_ROOT/evomas/.env"
    echo "[install] created evomas/.env from evomas/.env.example -- fill in OLLAMA_BASE_URL"
else
    echo "[install] evomas/.env already exists (leaving as-is)"
fi
if [ ! -f "$REPO_ROOT/api/.env" ]; then
    cp "$REPO_ROOT/api/.env.example" "$REPO_ROOT/api/.env"
    echo "[install] created api/.env from api/.env.example"
else
    echo "[install] api/.env already exists (leaving as-is)"
fi

echo
echo "[install] done."
echo "        Source your rc (\`source $RC_PATH\`) or open a new terminal, then:"
echo
echo "          evomas --help                                  # uses the venv via the rc function"
echo
echo "        For interactive dev work (running pytest, importing evomas modules, etc.)"
echo "        activate the venv directly:"
echo
echo "          source $VENV_DIR/bin/activate                  # then \`python\`, \`pytest\`, \`pip\` target the venv"
echo "          deactivate                                     # leaves the venv"
