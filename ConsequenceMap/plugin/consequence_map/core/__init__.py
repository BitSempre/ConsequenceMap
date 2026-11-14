"""ConsequenceMap core security primitives.

The modules here are the trust-bearing core of the platform:

- ``canonical``  - byte-exact canonicalisation and domain-separated hashing.
- ``authorization`` - the hash-bound approval protocol.

These modules are pure: no I/O, no Hermes import, no network. They are the
only place where a proposal becomes something that can be signed, and the
only place where a signed approval is turned back into a decision.

Invariant C-1 (empty production dependency inventory) holds: this package
uses the standard library only.
"""
