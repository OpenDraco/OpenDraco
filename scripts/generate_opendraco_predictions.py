import argparse
import json
import logging
from typing import Any

from opendraco.core.workflow.runner import run as run_opendraco_workflow
from opendraco.exceptions.errors import OllamaMemoryError
# Re-exported for backward compatibility with callers still using
# `from scripts.generate_opendraco_predictions import load_instances`.
# Real home is `opendraco.utils.instances` so the reproduce-this-run notebooks
# (generated under ~/Downloads, no `scripts/` access) can import it via pip.
from opendraco.utils.instances import load_instances  # noqa: F401
from opendraco.utils.weave_init import init_weave  # noqa: F401  # pyright: ignore[reportUnusedImport]

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def run_opendraco(instance: dict[str, Any], config: str = "") -> str:
    return run_opendraco_workflow(instance, config=config)


def build_predictions(
    instances_path: str,
    output_path: str,
    config: str = "",
    limit: int | None = None,
) -> int:
    instances = load_instances(instances_path, limit)
    logger.info("Loaded %d instances from %s", len(instances), instances_path)

    count = 0
    with open(output_path, "w") as out:
        for item in instances:
            instance_id: str = item["instance_id"]
            logger.info("Processing %s", instance_id)
            try:
                patch = run_opendraco(item, config=config)
            except OllamaMemoryError as exc:
                logger.error("Ollama out of memory - aborting run: %s", exc)
                break  # model can't load; no point trying remaining instances
            except Exception as exc:
                logger.error("run_opendraco failed on %s: %s", instance_id, exc)
                patch = ""
            pred = {
                "instance_id": instance_id,
                "model_patch": patch,
                "model_name_or_path": "opendraco",
                # Forward subset/split so the Evaluation page can partition
                # and run the harness against the right HuggingFace dataset.
                "subset": item.get("subset", "lite"),
                "split":  item.get("split", "dev"),
            }
            out.write(json.dumps(pred) + "\n")
            out.flush()  # make each prediction visible in the file immediately
            count += 1

    return count


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--instances",
        default="swebench_instances.jsonl",
        help="Path to JSONL file produced by generate_swebench_instances.py",
    )
    parser.add_argument("--output", default="opendraco_predictions.jsonl")
    parser.add_argument(
        "--config",
        default="",
        help=(
            "Unified config to run. Either a stem resolved against "
            "opendraco/config/predefined/<stem>.json (built-ins like 'chain', "
            "'star', 'tree', 'cycle', 'hybrid'), opendraco/config/loaded/"
            "<stem>.json (UI-imported, e.g. 'multi-chain'), or "
            "opendraco/config/<stem>.json (legacy flat root). An absolute or "
            "relative path to a config JSON also works."
        ),
    )
    parser.add_argument("--limit", type=int, default=None,
                        help="Process only the first N instances (smoke test)")
    args = parser.parse_args()

    # init_weave() TODO uncomment this if wanna run weave
    logger.info(
        "Generating predictions from %s (config=%s, limit=%s)",
        args.instances, args.config, args.limit,
    )
    total = build_predictions(args.instances, args.output, args.config, args.limit)
    logger.info("Generated %d predictions → %s", total, args.output)


if __name__ == "__main__":
    main()
