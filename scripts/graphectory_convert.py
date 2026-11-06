"""Convert existing OpenDraco runs into the local Graphectory Viewer.

usage: python scripts/graphectory_convert.py [<run.ndjson> ...]

Run it from the repo root with OpenDraco's venv (see
docs/graphectory_local.md). Without arguments it converts every log in
opendraco/logs/inference_logs/. Each run is written into the Viewer's data
folder (<RESULTS_DIR>/graphectory/<run_id>/); with GRAPHECTORY_URL set the
Viewer is then reloaded so it lists them. New runs do not need this: the api
publishes each one when it ends, and the Results page's "Analyze in
Graphectory" publishes the selected one.

Exits 1 when a log was skipped (unreadable, or a run with no agent activity).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from opendraco.paths import BASE_DIR, bootstrap  # noqa: E402
from opendraco.utils import graphectory  # noqa: E402


def main() -> int:
    bootstrap()  # loads opendraco/.env (GRAPHECTORY_URL)
    logs = [Path(a) for a in sys.argv[1:]] or sorted(
        (BASE_DIR / "opendraco" / "logs" / "inference_logs").glob("*.ndjson"))
    failed = 0
    for log_path in logs:
        run_id = graphectory.safe_run_id(
            log_path.name.removesuffix(".ndjson").removeprefix("prediction-"))
        try:
            state, records = graphectory.convert_run(run_id, log_path.read_bytes(), run_id)
        except (OSError, graphectory.GraphectoryError) as exc:
            print(f"skip {log_path.name}: {exc}", file=sys.stderr)
            failed += 1
            continue
        session = graphectory.write_session(graphectory.DATA_DIR, run_id, state, records)
        print(f"{run_id}: {len(records)} records -> {session}")

    viewer_url = graphectory.graphectory_base_url()
    if viewer_url:
        try:
            graphectory.reload_viewer(viewer_url)
            print(f"reloaded the Viewer at {viewer_url}")
        except graphectory.GraphectoryError as exc:
            print(f"could not reload the Viewer: {exc}", file=sys.stderr)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
