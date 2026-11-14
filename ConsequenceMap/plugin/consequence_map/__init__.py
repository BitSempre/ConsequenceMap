"""ConsequenceMap - Decision Intelligence for AI Agents.

Phase 2B: runtime integration.

The package is importable without Hermes on the path. The single Hermes
dependency is in `storage/db.py`, imported lazily inside a function, behind
an injectable connection-provider seam (MC1/R01).

The Phase 2B modules -- `hooks`, `correlation`, `authorization`, `paths` and
`self_exclusion` -- are the only permitted Hermes-import sites, and
`self_exclusion` imports nothing from Hermes at all.
"""

__version__ = "0.3.0-phase2b"

SCHEMA_VERSION = 1
