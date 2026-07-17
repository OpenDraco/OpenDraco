"""OpenDraco package marker. Required so the package takes precedence over the
sibling `opendraco.py` shim in import resolution (pytest discovery would
otherwise pick up the shim and break `import opendraco.tests.test_config`)."""
