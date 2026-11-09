"""ConsequenceMap - Decision Intelligence for AI Agents.

Phase 2A: domain model and storage layer.

The package is importable without Hermes on the path. The single Hermes
dependency is in `storage/db.py`, imported lazily inside a function, behind
an injectable connection-provider seam (MC1/R01).
"""

__version__ = "0.2.0-phase2a"

SCHEMA_VERSION = 1
