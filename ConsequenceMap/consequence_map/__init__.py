"""Compatibility entry point for the ``consequence_map`` package.

The canonical implementation lives **exclusively** in
``plugin/consequence_map/``.  This module is the root-level
compatibility shim that keeps the separate ``consequence_guard``
package (and any code importing ``consequence_map`` from the
repository root) working after the package was relocated into the
plugin folder.

Mechanism
---------
The canonical package's real ``__init__.py`` is executed **exactly
once** for this module via ``importlib``.  The module's ``__file__``,
``__spec__`` and ``__path__`` are re-pointed at the canonical
implementation so that:

* ``consequence_map.__version__`` and ``consequence_map.SCHEMA_VERSION``
  (defined by the real initializer) are preserved;
* submodule imports such as ``consequence_map.core.canonical``
  resolve into ``plugin/consequence_map/``;
* no second copy of the package is ever loaded;
* no ``sys.path`` entry is added or modified.

If the canonical package is missing, the shim fails loudly with an
``ImportError``.  It never falls back to another checkout or
filesystem location.
"""
from __future__ import annotations

import importlib.util as _ilu
import os as _os
import sys as _sys

#: This file lives at the repository root; the canonical package lives
#: in the sibling ``plugin/consequence_map`` folder.
_HERE = _os.path.dirname(_os.path.abspath(__file__))
_IMPL_DIR = _os.path.normpath(
    _os.path.join(_os.path.dirname(_HERE), "plugin", "consequence_map")
)
_INIT = _os.path.join(_IMPL_DIR, "__init__.py")

if not _os.path.isfile(_INIT):
    raise ImportError(
        "consequence_map compatibility shim: the canonical package was not "
        f"found at {_IMPL_DIR!r}. The implementation lives exclusively in "
        "plugin/consequence_map/; this shim does not fall back to any other "
        "location."
    )

_spec = _ilu.spec_from_file_location(
    __name__, _INIT, submodule_search_locations=[_IMPL_DIR]
)
if _spec is None or _spec.loader is None:
    raise ImportError(
        "consequence_map compatibility shim: could not build a package "
        f"specification for {_INIT!r}"
    )

# Re-point the module's identity at the canonical implementation so the
# package origin, resource resolution and submodule search all refer to
# plugin/consequence_map/ - not to this stub file.
__spec__ = _spec
__file__ = _INIT
__loader__ = _spec.loader
__path__ = [_IMPL_DIR]

# Execute the real package initializer exactly once, in this module's
# namespace.  Repeated imports hit the sys.modules cache and never
# re-execute this body.
_spec.loader.exec_module(_sys.modules[__name__])
