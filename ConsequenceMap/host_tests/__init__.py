"""Tests that live outside the plugin package.

The package's own import audit requires its tests never to import a
Hermes module. The test that exercises the host's manifest parser
therefore lives here, beside the package rather than inside it.
"""
