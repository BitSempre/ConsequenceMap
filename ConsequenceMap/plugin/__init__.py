"""ConsequenceMap - Decision Intelligence for AI Agents.

The Hermes plugin entry point. The host calls :func:`register` with a
``PluginContext``; the five hooks and the command palette entry are
registered there.

The package under ``consequence_map/`` is the implementation. This
module is only the adapter: it wires the host's context to the
package and does nothing else.
"""
from __future__ import annotations

import logging
import os
import sys
from typing import Any

logger = logging.getLogger(__name__)

#: The plugin folder, so the package can be imported whether the plugin
#: was installed as a directory or imported in place.
_PLUGIN_ROOT = os.path.dirname(os.path.abspath(__file__))
#: The project root: the folder that holds the ``consequence_map``
#: package. The plugin may live inside it (``<root>/plugin``) or beside
#: it (``<root>/../plugin``), so both are considered.
_PROJECT_ROOT = os.path.dirname(_PLUGIN_ROOT)
#: The directories that may hold the ``consequence_map`` package. What
#: goes on ``sys.path`` is the **directory that contains** the package,
#: not the package itself.
_PACKAGE_PARENTS = (
    # Installed layout: the package sits inside the plugin folder.
    _PLUGIN_ROOT,
    # Development layout: the plugin folder sits inside the project
    # root, and the package is a sibling of the plugin folder.
    _PROJECT_ROOT,
    os.path.dirname(_PROJECT_ROOT),
)


def _ensure_importable() -> None:
    """Make the package importable without installing it.

    The directory that holds the ``consequence_map`` package is put on
    ``sys.path``. The plugin works from a checkout and from an
    installed folder, without either arrangement needing a path edit.
    """
    for parent in _PACKAGE_PARENTS:
        package = os.path.join(parent, "consequence_map")
        if os.path.isdir(package) and parent not in sys.path:
            sys.path.insert(0, parent)
            return


def register(ctx: Any) -> None:
    """Register the five hooks and the command.

    The host calls this once, with its plugin context. A failure here
    must not take the host down: the plugin logs and returns.
    """
    _ensure_importable()
    try:
        from consequence_map.hooks import register as register_hooks
        from consequence_map.hooks import (
            RepositoryAuthorizationSink,
            HookState,
        )

        # Injete o provedor do Hermes para que as inserções usem a mesma conexão
        # que o host cria através do sqlite_util.transaction.
        try:
            from hermes_cli.sqlite_util import transaction as hermes_transaction
            def hermes_provider(path):
                return hermes_transaction(provider=path)
            db_module.set_connection_provider(hermes_provider)
        except Exception:
            logger.warning(
                "ConsequenceMap: não foi possível injetar o provedor do Hermes",
                exc_info=True,
            )
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
            HookState.STATE.sink = RepositoryAuthorizationSink(repository)
        except Exception:
            logger.warning(
                "ConsequenceMap: the database is unavailable; the "
                "authorization will not be recorded",
                exc_info=True,
            )

        register_hooks(ctx)
        logger.info("ConsequenceMap: registered")
    except Exception:
        logger.exception("ConsequenceMap: registration failed")
