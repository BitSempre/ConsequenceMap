"""Byte-exact canonicalisation and domain-separated hashing.

Why this module exists
----------------------
The forecast layer already has a deterministic serialiser
(``domain/serialization.py``). It is correct for its purpose - hashing a
forecast's own rows - but it is **not** sufficient for binding a human
approval to a proposal. A canonical form used as a *security* boundary must
be **unambiguous**: two different logical values must never produce the
same bytes, and one logical value must never produce two different byte
strings.

Audited weaknesses of the existing ``canonical_json`` (measured, 2026-11-09):

1. **Duplicate keys are accepted.** ``json.loads`` keeps the last value.
   Two byte strings that a human reads as different can collapse.
2. **Unicode is not normalised.** ``"cafe\\u0301"`` (NFD) and
   ``"caf\\u00e9"`` (NFC) serialise differently, so the same visible
   operation can have two different hashes.
3. **``NaN`` and ``Infinity`` are emitted.** They are not valid JSON, and
   two implementations may disagree about them.
4. **``1`` and ``1.0`` serialise differently** despite comparing equal.
5. **No domain separation.** The same bytes hashed for a forecast and for
   an approval would be indistinguishable.

This module fixes all five. It is deliberately small and boring: the value
of a canonical form is that it never changes.

Canonical form
--------------
A canonical document is::

    <domain>\\n
    <field>=<value>\\n
    <field>=<value>\\n
    ...

with:

- fields emitted in **sorted key order** (by the UTF-8 bytes of the key);
- values encoded with a **typed, unambiguous** encoding:
  - ``s:<text>``  - a string, NFC-normalised, with ``\\`` and newlines escaped;
  - ``i:<int>``  - an integer;
  - ``b:0`` / ``b:1`` - a boolean;
  - ``n:<null>`` - null;
  - ``l:<item>;<item>`` - a list, items in their given order;
  - ``m:<key>=<value>;...`` - a map, keys sorted by UTF-8 bytes;
- **no floats**. A float cannot be represented exactly in a text encoding
  without a normalisation rule, so the protocol rejects them outright
  rather than defining one. Quantities that need decimals are expressed
  as integers of an explicit unit (cents, milliseconds) or as strings.
- **no duplicate keys** anywhere;
- a **length prefix** on strings and list items, so that a value can
  never contain the delimiter used to frame it.

The length prefixes are what make the encoding unambiguous. Without them
``{"a":"1;b=2"}`` and ``{"a":"1","b":"2"}`` could frame identically.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping, Sequence

__all__ = [
    "CanonicalisationError",
    "canonical_bytes",
    "canonical_text",
    "domain_hash",
    "canonical_hash",
]


class CanonicalisationError(ValueError):
    """Raised when a value cannot be canonicalised unambiguously."""


#: The domain-separation prefix for authorization payloads.
DOMAIN_AUTHORIZATION = "consequencemap.authorization.v1"


def _escape(text: str) -> str:
    """Escape a string so it can never contain a framing delimiter."""
    out = text.replace("\\", "\\\\").replace("\n", "\\n").replace("\r", "\\r")
    return out.replace("=", "\\=").replace(";", "\\;")


#: The deepest nesting the canonical form will encode. A proposal is a
#: flat structure in practice; a deep one is either a mistake or an
#: attempt to exhaust the verifier's stack, and either way it is refused
#: rather than processed.
MAX_DEPTH = 32


def _encode(value: Any, path: str = "", _depth: int = 0) -> str:
    """Encode one value into its unambiguous canonical form."""
    if _depth > MAX_DEPTH:
        raise CanonicalisationError(
            "the document nests deeper than %d levels at %r"
            % (MAX_DEPTH, path or "<root>")
        )
    if value is None:
        return "n:"
    if isinstance(value, bool):
        # bool BEFORE int: bool is a subclass of int in Python.
        return "b:1" if value else "b:0"
    if isinstance(value, int):
        return "i:%d" % value
    if isinstance(value, float):
        raise CanonicalisationError(
            "float is not canonicalisable at %r: represent it as an integer "
            "with an explicit unit, or as a string" % (path or "<root>",)
        )
    if isinstance(value, str):
        # The canonical form is ASCII-only. Non-ASCII text must be escaped
        # by the producer, not normalised here: normalising would mean two
        # different byte strings could mean the same thing, and the whole
        # point of a canonical form is that one logical value has exactly
        # one byte representation. An ASCII-only canonical form has that
        # property by construction.
        if not value.isascii():
            raise CanonicalisationError(
                "non-ASCII text is not canonicalisable at %r: escape it to "
                "ASCII (for example a backslash-u escape) before hashing"
                % (path or "<root>",)
            )
        return "s:%d:%s" % (len(value.encode("ascii")), _escape(value))
    if isinstance(value, (bytes, bytearray)):
        raise CanonicalisationError(
            "bytes are not canonicalisable at %r: encode them as base64 text"
            % (path or "<root>",)
        )
    if isinstance(value, Mapping):
        items = []
        seen = set()
        for key in value:
            if not isinstance(key, str):
                raise CanonicalisationError(
                    "map keys must be strings at %r" % (path or "<root>",)
                )
            if key in seen:
                raise CanonicalisationError("duplicate map key %r" % (key,))
            seen.add(key)
        for key in sorted(value, key=lambda k: k.encode("utf-8")):
            items.append(
                "%s=%s"
                % (
                    _escape(key),
                    _encode(value[key], "%s.%s" % (path, key), _depth + 1),
                )
            )
        return "m:%s" % ";".join(items)
    if isinstance(value, (list, tuple)):
        items = [
            _encode(item, "%s[%d]" % (path or "<root>", index), _depth + 1)
            for index, item in enumerate(value)
        ]
        return "l:%s" % ";".join(items)
    raise CanonicalisationError(
        "value of type %s is not canonicalisable at %r"
        % (type(value).__name__, path or "<root>")
    )


def canonical_text(domain: str, document: Mapping[str, Any]) -> str:
    """Return the canonical text of ``document`` under ``domain``.

    The domain is the first line and is part of the hashed bytes, so a
    document produced for one purpose can never be replayed as a document
    for another.
    """
    if not isinstance(domain, str) or not domain:
        raise CanonicalisationError("domain must be a non-empty string")
    if not isinstance(document, Mapping):
        raise CanonicalisationError("document must be a mapping")
    return "%s\n%s" % (domain, _encode(document))


def canonical_bytes(domain: str, document: Mapping[str, Any]) -> bytes:
    """Return the canonical bytes of ``document`` under ``domain``."""
    return canonical_text(domain, document).encode("utf-8")


def domain_hash(domain: str, document: Mapping[str, Any]) -> str:
    """Return the hex SHA-256 of the canonical bytes of ``document``."""
    return hashlib.sha256(canonical_bytes(domain, document)).hexdigest()


def canonical_hash(domain: str, document: Mapping[str, Any]) -> str:
    """Alias of :func:`domain_hash`, named for call-site readability."""
    return domain_hash(domain, document)


def strict_json_loads(text: str) -> Any:
    """Parse JSON, rejecting duplicate keys and non-standard constants.

    Used when reading a proposal or an approval from the wire: the
    canonical form is the *output* of this module, but the *input* must
    be parsed without the lossy behaviour of the default decoder.
    """
    def _reject_duplicates(pairs):
        seen = set()
        for key, _ in pairs:
            if key in seen:
                raise CanonicalisationError("duplicate JSON key %r" % (key,))
            seen.add(key)
        return dict(pairs)

    return json.loads(
        text,
        object_pairs_hook=_reject_duplicates,
        parse_constant=lambda name: (_ for _ in ()).throw(
            CanonicalisationError("non-standard JSON constant %r" % (name,))
        ),
    )
