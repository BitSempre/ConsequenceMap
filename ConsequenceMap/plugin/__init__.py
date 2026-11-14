"""ConsequenceMap - Decision Intelligence for AI Agents.

The Hermes plugin entry point. The host calls :func:`register` with a
``PluginContext``; the five hooks and the command palette entry are
registered there.

The ``consequence_map`` package lives inside the plugin folder.
This module is only the adapter: it wires the host's context to the
package and does nothing else.
"""

from __future__ import annotations

import importlib.util
import logging
import os
import sys
from typing import Any

logger = logging.getLogger(__name__)

#: The plugin root folder - the package lives here.
_PLUGIN_ROOT = os.path.dirname(os.path.abspath(__file__))

#: The consequence_map package root.
_PACKAGE_ROOT = os.path.join(_PLUGIN_ROOT, "consequence_map")

def _load_canonical_package():
    """Load the canonical ``consequence_map`` package via importlib.

    Uses ``importlib.util.spec_from_file_location`` with
    ``submodule_search_locations`` to create a proper package
    specification.  This executes the real package ``__init__.py``
    and registers the module under the canonical name in
    ``sys.modules`` without any ``sys.path`` mutation.

    If the package is already loaded, verifies that it originates
    from the expected canonical location before reusing it.

    Returns the loaded (or existing) package module.

    Raises ``RuntimeError`` if the package cannot be loaded or if
    an existing module originates from an unexpected location that
    cannot be normalised.
    """
    existing = sys.modules.get("consequence_map")
    if existing is not None:
        # Fast path: already canonical.
        pkg_path = getattr(existing, "__path__", None)
        if pkg_path and len(pkg_path) == 1:
            if os.path.realpath(str(pkg_path[0])) == os.path.realpath(_PACKAGE_ROOT):
                return existing
        else:
            pkg_file = getattr(existing, "__file__", None)
            if pkg_file:
                expected_init = os.path.join(_PACKAGE_ROOT, "__init__.py")
                if os.path.realpath(str(pkg_file)) == os.path.realpath(expected_init):
                    return existing
        # Slow path: the root compatibility shim (or another
        # origin) created the package first.  Normalise the single
        # package object onto the canonical implementation so that
        # both entry paths share one package, one origin and no
        # duplicate submodules.  Submodules already loaded through
        # the shim keep their identity; only the package's search
        # locations are re-pointed.
        #
        # The real package initializer was already executed by the
        # module that created this entry (the shim calls
        # spec.loader.exec_module on the same object).  Re-executing
        # it here would run module-level side effects twice, so we
        # only re-point the identity attributes and return.
        #
        # SECURITY: we do not normalise a module whose origin is
        # completely foreign (e.g. a site-packages consequence_map
        # from a different install).  In that case we raise.
        init_file = os.path.join(_PACKAGE_ROOT, "__init__.py")
        if not os.path.isfile(init_file):
            raise RuntimeError(
                f"ConsequenceMap: consequence_map is loaded from "
                f"{getattr(existing, '__file__', 'unknown')!r} but the "
                f"canonical package is missing at {_PACKAGE_ROOT!r}"
            )
        # Check whether the existing module is from the root shim
        # (same origin as canonical, just loaded via a different entry).
        # The shim sets __file__ to _INIT, which equals init_file.
        existing_file = getattr(existing, "__file__", None)
        if existing_file is not None and os.path.realpath(str(existing_file)) == os.path.realpath(init_file):
            # Same origin (shim loaded first) — normalise.
            spec = importlib.util.spec_from_file_location(
                "consequence_map",
                init_file,
                submodule_search_locations=[_PACKAGE_ROOT],
            )
            if spec is None or spec.loader is None:
                raise RuntimeError(
                    "ConsequenceMap: failed to create the canonical package "
                    f"specification for {init_file!r}"
                )
            existing.__spec__ = spec
            existing.__file__ = init_file
            existing.__path__ = [_PACKAGE_ROOT]
            existing.__package__ = "consequence_map"
            return existing
        # Foreign origin — refuse to normalise.
        raise RuntimeError(
            "ConsequenceMap: consequence_map is already loaded from a foreign "
            f"location ({existing_file!r}); expected the root shim or the "
            f"canonical package at {_PACKAGE_ROOT!r}"
        )

    init_file = os.path.join(_PACKAGE_ROOT, "__init__.py")
    if not os.path.isfile(init_file):
        raise RuntimeError(
            f"ConsequenceMap: canonical package not found at {init_file!r}"
        )

    spec = importlib.util.spec_from_file_location(
        "consequence_map",
        init_file,
        submodule_search_locations=[_PACKAGE_ROOT],
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(
            f"ConsequenceMap: failed to create package specification for {init_file!r}"
        )
    module = importlib.util.module_from_spec(spec)
    sys.modules["consequence_map"] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        # Clean up the partial entry so a retry starts fresh.
        sys.modules.pop("consequence_map", None)
        raise
    return module


def register(ctx: Any) -> None:
    """Register the five hooks and the command.

    The host calls this once, with its plugin context.

    A failure here must raise so a broken install shows up in
    ``hermes plugins validate``.
    """
    try:
        _load_canonical_package()

        from consequence_map.hooks import register as register_hooks
        from consequence_map.hooks import (
            RepositoryAuthorizationSink,
            STATE,
        )

        # The connection provider is the package default
        # (`storage.db.hermes_connection_provider`), which uses the public
        # `plugins.plugin_storage.plugin_db` surface. No private Hermes
        # module is imported here.
        # The sink writes to the plugin's own database. If the
        # database cannot be opened, the sink counts the failure and
        # the hooks keep working: a hook must never fail because the
        # storage is unavailable.
        try:
            from consequence_map.storage import db as db_module
            from consequence_map.storage.migrations import apply_migrations
            from consequence_map.storage.repository import Repository

            connection = db_module.connect()
            apply_migrations(connection)
            repository = Repository(connection)
            STATE.sink = RepositoryAuthorizationSink(repository)
        except Exception as exc:
            # Re-raise so the install is clearly broken
            raise RuntimeError(
                "ConsequenceMap: registration failed - could not initialise storage"
            ) from exc

        register_hooks(ctx)
        logger.info("ConsequenceMap: registered")
    except Exception as exc:
        # Re-raise so the install is clearly broken
        raise RuntimeError("ConsequenceMap: registration failed") from exc
