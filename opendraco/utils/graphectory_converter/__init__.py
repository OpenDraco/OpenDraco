"""Framework trajectory → single super-agent Claude-wire session for Graphectory.

From https://github.com/OpenDraco/graphectory-opendraco (commit 4582cee,
`app/converter/`), included in OpenDraco so nothing extra is installed;
`opendraco.utils.graphectory` uses it to publish runs into the Viewer.

Dispatch lives in :mod:`registry`; each framework self-registers from its own
module under :mod:`adapters` (imported here to trigger discovery). ``SUPPORTED``
is therefore exactly the adapter modules this branch ships.
"""

from . import adapters as _adapters  # noqa: F401  (import triggers registration)
from .registry import ADAPTERS, ConvertError, run_to_session

__all__ = ["ConvertError", "run_to_session", "SUPPORTED"]

SUPPORTED = tuple(sorted(ADAPTERS))
