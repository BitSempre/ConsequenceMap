"""The copy lint (specification section 12.2).

A prediction is never presented as a guarantee. This module rejects the
prohibited vocabulary in user-facing copy. It is a lint, not an enforcement
point on a write path: Phase 2A implements it, Phase 2B wires it into the
production path (AC-DATA-18).
"""
from __future__ import annotations

#: The prohibited vocabulary. Matched case-insensitively.
GUARANTEE_WORDS = (
    "guarantee", "guaranteed", "guarantees", "ensures", "ensured",
    "will never fail", "cannot fail", "always succeeds", "impossible",
    "definitely", "certainly", "no risk", "risk-free", "risk free",
    "100%", "perfect", "always works",
)


class CopyLintError(ValueError):
    """Raised when a piece of copy contains prohibited guarantee language."""

    def __init__(self, found, text):
        self.found = found
        self.text = text
        super().__init__(
            f"the text contains prohibited guarantee language: {found!r}"
        )


def assert_no_guarantee_language(text: str) -> None:
    """Raise `CopyLintError` when `text` contains prohibited vocabulary.

    Returns None when the text is clean.
    """
    if not isinstance(text, str):
        return None
    lowered = text.lower()
    for word in GUARANTEE_WORDS:
        needle = word.lower()
        if needle in lowered:
            raise CopyLintError(word, text)
    return None
