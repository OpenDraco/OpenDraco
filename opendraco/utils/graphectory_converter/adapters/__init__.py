"""Framework adapters.

Importing this package auto-registers every adapter module present (each calls
``registry.register`` at import). The set of supported frameworks is therefore
exactly the adapter modules this branch ships — there is no hand-maintained list
to edit, which is what lets the single-framework branches merge cleanly.
"""

import importlib
import pkgutil

for _mod in pkgutil.iter_modules(__path__):
    if not _mod.name.startswith("_"):
        importlib.import_module(f"{__name__}.{_mod.name}")
