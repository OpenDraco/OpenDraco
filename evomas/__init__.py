"""EvoMas package marker. Required so the package takes precedence over the
sibling `evomas.py` shim in import resolution (pytest discovery would
otherwise pick up the shim and break `import evomas.tests.test_config`)."""
