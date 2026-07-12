import pytest

from evomas.config.loader import load_config
from evomas.exceptions.errors import ConfigError


# ── unified config ────────────────────────────────────────────────────────────
# The chain/state/topology-shape tests that used to live here loaded
# `chain` config from `evomas/config/loaded/`, which is the user-upload
# directory and may be empty on a fresh checkout. Dropped them so the
# suite doesn't depend on optional on-disk content. Predefined-config
# coverage is exercised by the agent-type variant tests
# (`test_variant_tool_coverage.py`) and by the integration matrix.

def test_load_unknown_config_raises() -> None:
    with pytest.raises(ConfigError):
        load_config("does_not_exist")
