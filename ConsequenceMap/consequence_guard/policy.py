"""The guard's protected policy.

This module holds the policy classes. The policy is DATA plus the
HANDLERS it names. The handlers live in code; the policy names them.
A policy that could name a handler would be a policy that could name
anything.
"""
from __future__ import annotations

from .service import GuardPolicy, PolicyError, PolicyOperation

__all__ = ["GuardPolicy", "PolicyError", "PolicyOperation"]
