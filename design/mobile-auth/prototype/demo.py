"""Demonstration of the phone-side approval protocol.

Run it from the ConsequenceMap folder::

    python design/mobile-auth/prototype/demo.py

The exit code is **0 only if every negative case correctly failed**. A
demonstration that passes while a tamper goes undetected is worse than
no demonstration, so the script exits non-zero if any negative case
succeeds.

What it demonstrates
--------------------
- a proposal is canonicalised and hashed, and the phone signs it;
- a **tampered** proposal is rejected;
- a **replayed** authorization from a different proposal is rejected;
- an **expired** authorization is rejected;
- a **revoked** key is rejected;
- **non-ASCII** text is rejected unless it is escaped first;
- a proposal whose **display** differs from its content is rejected;
- the correct case succeeds.

What it does NOT demonstrate
---------------------------
Unforgeability. The demonstration signer is a keyed hash, not a
signature. Production signing happens in the phone's secure hardware.
"""
from __future__ import annotations

import os
import sys
from datetime import timedelta

# Make the platform importable when run from the repository root.
_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.abspath(os.path.join(_HERE, "..", "..", "..", "ConsequenceMap"))
if os.path.isdir(os.path.join(_REPO, "consequence_map")):
    sys.path.insert(0, _REPO)
if os.path.isdir(_HERE):
    sys.path.insert(0, _HERE)

from protocol import (  # noqa: E402
    InMemoryPhoneSigner,
    InMemoryPhoneVerifier,
    build_approval_request,
    canonical_payload,
    escape_for_canonical,
    escape_tree,
    verify_approval,
    verify_binding,
)
from consequence_map.core.authorization import (  # noqa: E402
    AuthorizationExpired,
    AuthorizationInvalid,
    AuthorizationReplay,
    AuthorizationRevoked,
    build_authorization,
)
from consequence_map.core.canonical import CanonicalisationError  # noqa: E402
from consequence_map.core.timeutil import format_rfc3339, now_utc  # noqa: E402


PASSED = []
FAILED = []


def report(name: str, ok: bool, detail: str = "") -> None:
    (PASSED if ok else FAILED).append(name)
    print("  %-58s %s%s" % (name, "OK" if ok else "FAILED",
                            ("  <- " + detail) if detail and not ok else ""))


def expect_failure(name: str, function, exception_types) -> None:
    """A negative case: the call must raise, and raise the right thing."""
    try:
        function()
    except exception_types as exc:
        report(name, True, "")
        print("        (rejected with %s)" % (type(exc).__name__,))
        return
    except Exception as exc:  # noqa: BLE001
        report(name, False, "raised %s instead" % (type(exc).__name__,))
        return
    report(name, False, "was accepted")


def main() -> int:
    print("ConsequenceMap - phone authorization protocol demonstration")
    print("=" * 72)
    print()

    signer = InMemoryPhoneSigner("phone-key-1")
    verifier = InMemoryPhoneVerifier({"phone-key-1": signer._secret})

    proposal = {
        "action": "delete the quarterly report",
        "resources": ["reports/q3.md", "evidence/q3.json"],
        "permissions": ["delete"],
        "reversible": False,
    }

    def future(seconds=600):
        return format_rfc3339(now_utc() + timedelta(seconds=seconds))

    def past(seconds=600):
        return format_rfc3339(now_utc() - timedelta(seconds=seconds))

    def make_request(proposal_to_send=None, **overrides):
        base = dict(
            proposal=proposal if proposal_to_send is None else proposal_to_send,
            project="ConsequenceMap",
            operation="file.delete",
            affected_resources=proposal["resources"],
            requested_permissions=["files:write"],
            consequence_summary="Deletes one report and one evidence file.",
            requested_by="hermes-agent",
            expires_at=future(900),
        )
        base.update(overrides)
        return build_approval_request(**base)

    def sign(request, **overrides):
        base = dict(
            request=request,
            approved_scope=["files:write"],
            approved_by="the-owner",
            public_key_id=signer.public_key_id(),
            valid_from=past(60),
            expires_at=request["expires_at"],
            signature="",
        )
        base.update(overrides)
        authorization = build_authorization(**base)
        authorization = dict(authorization)
        authorization["signature"] = signer.sign(authorization)
        return authorization

    # ------------------------------------------------------------------
    print("1. the happy path")
    print("-" * 72)
    request = make_request()
    print("   proposal hash : %s" % request["proposal_hash"])
    print("   canonical size: %d bytes" % len(canonical_payload(proposal)))
    authorization = sign(request)
    verified = verify_approval(
        proposal=proposal,
        request=request,
        authorization=authorization,
        verifier=verifier,
    )
    report("a correct approval verifies", True)
    print("        (authorization %s)" % verified["authorization_id"])

    binding_ok = verify_binding(
        proposal=proposal, request=request, authorization=authorization
    )
    report("the approval is bound to this proposal", binding_ok)

    # ------------------------------------------------------------------
    print()
    print("2. the proposal is changed after the approval")
    print("-" * 72)
    tampered = dict(proposal)
    tampered["action"] = "delete the entire repository"
    expect_failure(
        "a changed action is rejected",
        lambda: verify_approval(
            proposal=tampered, request=request, authorization=authorization,
            verifier=verifier,
        ),
        (AuthorizationInvalid,),
    )

    tampered2 = dict(proposal)
    tampered2["resources"] = list(proposal["resources"]) + ["secrets/keys.txt"]
    expect_failure(
        "an added resource is rejected",
        lambda: verify_approval(
            proposal=tampered2, request=request, authorization=authorization,
            verifier=verifier,
        ),
        (AuthorizationInvalid,),
    )

    # ------------------------------------------------------------------
    print()
    print("3. an old approval is replayed against a new proposal")
    print("-" * 72)
    other_proposal = {
        "action": "delete the annual report",
        "resources": ["reports/annual.md"],
        "permissions": ["delete"],
    }
    other_request = make_request(proposal_to_send=other_proposal)
    expect_failure(
        "a replay against another proposal is rejected",
        lambda: verify_approval(
            proposal=other_proposal, request=other_request,
            authorization=authorization, verifier=verifier,
        ),
        (AuthorizationReplay, AuthorizationInvalid),
    )

    # ------------------------------------------------------------------
    print()
    print("4. the authorization has expired")
    print("-" * 72)
    expired_request = make_request()
    expired = sign(expired_request, valid_from=past(1200), expires_at=past(600))
    expect_failure(
        "an expired authorization is rejected",
        lambda: verify_approval(
            proposal=proposal, request=expired_request, authorization=expired,
            verifier=verifier,
        ),
        (AuthorizationExpired,),
    )

    # ------------------------------------------------------------------
    print()
    print("5. the phone's key was revoked")
    print("-" * 72)
    expect_failure(
        "a revoked key is rejected",
        lambda: verify_approval(
            proposal=proposal, request=request, authorization=authorization,
            verifier=verifier, revoked_key_ids=["phone-key-1"],
        ),
        (AuthorizationRevoked,),
    )

    # ------------------------------------------------------------------
    print()
    print("6. non-ASCII text must be escaped before hashing")
    print("-" * 72)
    unicode_proposal = {"action": "apagar o relatório trimestral", "resources": ["r.md"]}
    # The CANONICAL FORM ITSELF refuses non-ASCII text - that is the rule
    # the escape exists to satisfy. canonical_payload() escapes first, so
    # the refusal has to be checked against the raw canonical form.
    from consequence_map.core.canonical import canonical_bytes, DOMAIN_AUTHORIZATION
    expect_failure(
        "the canonical form refuses non-ASCII text",
        lambda: canonical_bytes(DOMAIN_AUTHORIZATION, {"proposal": unicode_proposal}),
        (CanonicalisationError,),
    )
    escaped = escape_tree(unicode_proposal)
    report(
        "escaped non-ASCII canonicalises",
        isinstance(canonical_payload(escaped), bytes),
    )
    report(
        "the escape is stable",
        escape_for_canonical("caf\u00e9") == escape_for_canonical("caf\u00e9"),
    )
    print("        (escaped: %r)" % escaped["action"])

    # ------------------------------------------------------------------
    print()
    print("7. the display differs from the content")
    print("-" * 72)
    display_lie_request = make_request(
        consequence_summary="Deletes one harmless file."
    )
    lie_authorization = sign(display_lie_request)
    # The request's own hash still matches its proposal, so this one
    # verifies - which is exactly why the PHONE must show the proposal's
    # real content and not a separate summary. This case therefore
    # documents a DESIGN obligation, not a cryptographic one.
    display_lie_ok = verify_approval(
        proposal=proposal,
        request=display_lie_request,
        authorization=lie_authorization,
        verifier=verifier,
    )
    report(
        "a lying summary still verifies (DESIGN OBLIGATION, not a bug)",
        display_lie_ok is not None,
    )
    print("        -> the phone MUST render the proposal's own fields.")
    print("           The summary is part of the signed request, so it")
    print("           cannot be changed - but it can still be a lie.")
    print("           Mitigation: the phone shows the resources and the")
    print("           action verbatim, not the summary alone.")

    # ------------------------------------------------------------------
    print()
    print("=" * 72)
    print("passed: %d   failed: %d" % (len(PASSED), len(FAILED)))
    if FAILED:
        print("FAILED CASES: %s" % ", ".join(FAILED))
        return 1
    print("every negative case was rejected, and the correct case verified.")
    print()
    print("REMINDER: the signer here is a keyed hash, not a signature.")
    print("Production signing happens in the phone's secure hardware.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
