"""The ConsequenceMap Security Guard - the privileged side of the platform.

This package is the part of ConsequenceMap that the AI agent must NOT
be able to influence. It runs under its own identity, in its own
process, with its own protected storage.

The split is deliberate and it is the architecture:

- ``consequence_map`` is the **plugin**: the analysis, the proposals,
  the agent integration. It is stdlib-only, it runs where the agent
  runs, and the agent controls it. It may PROPOSE. It may not decide.
- ``consequence_guard`` is the **service**: the verification, the
  policy, the durable state, the execution. It runs where the agent
  cannot reach. It DECIDES, and it EXECUTES.

Anything that can grant authority belongs here and not in the plugin.
That includes the cryptographic verification: the plugin does not hold
the ability to check a real signature, so it cannot be talked into
accepting a forged one.

The dependency difference is therefore a FEATURE, not an accident: the
plugin stays stdlib-only (constraint C-1) while the guard uses a
maintained cryptographic library. The rule "the agent's side has no
special capability" is preserved precisely because the agent's side
cannot verify a signature.
"""
from __future__ import annotations

__all__ = []
