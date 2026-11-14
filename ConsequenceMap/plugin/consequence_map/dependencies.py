"""The dependency inventory (section 13, LLM-4).

The production dependency inventory is EMPTY: the plugin is stdlib-only.
`pyproject.toml` is not created, and there is no `python_dependencies`
entry to declare.
"""
from __future__ import annotations

#: The production dependencies. EMPTY - the plugin is stdlib-only.
PRODUCTION_DEPENDENCIES: tuple = ()

#: The same inventory in the manifest's shape.
PYTHON_DEPENDENCIES: list = []

#: The minimum Hermes version, as a SemVer floor.
REQUIRES_HERMES = ">=0.22.5"
