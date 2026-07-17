import logging
import os
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_INITIALIZED: bool = False


def init_weave(project: str = "swe-bench") -> Optional[object]:
    global _INITIALIZED
    if _INITIALIZED:
        return None

    env_path: Path = Path(__file__).resolve().parents[1] / ".env"
    if env_path.exists():
        try:
            from dotenv import load_dotenv

            load_dotenv(env_path, override=False)
        except ImportError:
            for line in env_path.read_text().splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                value = value.strip().strip("'\"")
                os.environ.setdefault(key.strip(), value)

    api_key: Optional[str] = os.environ.get("WANDB_API_KEY")
    if not api_key:
        logger.warning("WANDB_API_KEY not set; weave tracing disabled")
        _INITIALIZED = True
        return None

    try:
        import weave  # type: ignore

        client = weave.init(project)
        _INITIALIZED = True
        logger.info("weave initialized for project %s", project)
        return client
    except Exception as exc:
        logger.warning("weave initialization failed: %s", exc)
        _INITIALIZED = True
        return None
