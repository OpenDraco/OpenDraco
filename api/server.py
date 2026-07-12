"""FastAPI entrypoint. Slim host module — every route lives in a
page-scoped router under `api/routers/` (see `routers/__init__.py` for
the map). Shared path constants + helpers live in `api/common.py`."""
from __future__ import annotations

# Repo root on sys.path BEFORE the first `from api …` import so this
# module loads cleanly under any uvicorn `--app-dir` choice (start_api
# launchers pass the repo root explicitly; this is a safety net for
# any other entry point that imports api.server bare).
import sys as _sys
from pathlib import Path as _Path
_REPO_ROOT = _Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in _sys.path:
    _sys.path.insert(0, str(_REPO_ROOT))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Import common BEFORE the routers so its module body (load_dotenv,
# sys.path push, mkdirs) runs first.
from api import common  # noqa: F401  # pyright: ignore[reportUnusedImport]

from api.routers import (
    common as common_router,
    evaluation as evaluation_router,
    inference as inference_router,
    instances as instances_router,
    results as results_router,
    topology as topology_router,
)

app = FastAPI(title="EvoMas API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:4200"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(common_router.router)
app.include_router(topology_router.router)
app.include_router(instances_router.router)
app.include_router(inference_router.router)
app.include_router(evaluation_router.router)
app.include_router(results_router.router)


if __name__ == "__main__":
    import sys
    from pathlib import Path
    import uvicorn
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    uvicorn.run("api.server:app", host="0.0.0.0", port=8000, reload=False)
