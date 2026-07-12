"""Per-page FastAPI routers for the EvoMas API.

Each module here defines a `router = APIRouter()` and decorates its
endpoints with full `/api/...` paths (no prefix), so URLs stay
byte-for-byte identical to the pre-split monolith. `api/server.py`
imports each module and calls `app.include_router(...)` once per
module. Module boundaries match the frontend pages:

  common      — /api/health (the navbar's API-online indicator)
  topology    — /api/configs/*, /api/models/*, /api/tools, /api/agent-*
  instances   — /api/instances/*
  inference   — /api/inference/*
  evaluation  — /api/evaluation/*, /api/predictions, /api/predictions/inspect
  results     — /api/results/*

Cross-router helpers + path constants live in `api/common.py`.
"""
