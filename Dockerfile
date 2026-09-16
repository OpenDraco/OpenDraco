# ============================================================================
#  OpenDraco container image — two targets, one file.
#
#    web  : nginx serving the built Angular frontend on :4200
#    api  : the FastAPI backend + the opendraco package on :8000
#
#  Port 4200 is not arbitrary: api/server.py pins the CORS origin to
#  http://localhost:4200, and app/src/app/services/api.service.ts pins the
#  API base to http://localhost:8000/api. Publishing those two host ports
#  means the browser reaches both exactly as it does in a local dev setup,
#  with no source change.
#
#  Build both:   docker compose build
# ============================================================================

# ── build the frontend ──────────────────────────────────────────────────────
FROM node:22-alpine AS web-build
WORKDIR /src
# package files first so `npm ci` is cached independently of source edits
COPY app/package.json app/package-lock.json ./
RUN npm ci
COPY app/ ./
RUN npm run build

# ── target: web ─────────────────────────────────────────────────────────────
FROM nginx:alpine AS web
COPY docker/nginx.conf /etc/nginx/conf.d/default.conf
# Angular's application builder emits dist/<project>/browser
COPY --from=web-build /src/dist/app/browser /usr/share/nginx/html
EXPOSE 4200

# ── target: api ─────────────────────────────────────────────────────────────
FROM python:3.12-slim AS api
ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Sibling-service default, reaching the compose `ollama` container rather than
# the host. Image ENV is the lowest-precedence layer, so an OLLAMA_BASE_URL in
# opendraco/.env (loaded via the compose `env_file`) overrides it — point that
# at a remote Ollama and this value is ignored.
ENV OLLAMA_BASE_URL=http://ollama:11434
# git: the clone-apply-test evaluator clones instance repos, and the
# instances endpoint resolves HEAD with `git ls-remote`.
RUN apt-get update \
 && apt-get install -y --no-install-recommends git ca-certificates \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /opendraco

# Dependency layer: only the metadata and the package itself, so editing
# api/ or scripts/ does not re-resolve the dependency tree. On Linux this
# also picks up `swebench`, which pyproject excludes on win32.
COPY pyproject.toml README.md ./
COPY opendraco/ ./opendraco/
RUN pip install -e .

# The SWE-bench harness drives the daemon through docker-py (a dependency of
# `swebench`, so already installed), but run_swebench_evaluation.py also shells
# out to the `docker` CLI to clear stale sweb.eval.* containers between runs.
# The client binary only — it is inert until a daemon socket is mounted, which
# only docker-compose.swebench.yml does.
COPY --from=docker:cli /usr/local/bin/docker /usr/local/bin/docker

COPY api/ ./api/
COPY scripts/ ./scripts/

EXPOSE 8000
CMD ["python", "-m", "uvicorn", "api.server:app", "--host", "0.0.0.0", "--port", "8000"]
