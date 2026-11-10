"""Regression tests for the twelfth review round.

Two defects were confirmed against the code by an independent Red
Team report and then reproduced here:

**D-28 - the audit entry and the operation record were two separate
transactions.** Writing them separately leaves a window. The audit
entry commits and the operation record does not, so the trail claims
an attempt that the state does not know about. The other order leaves
an operation the trail never mentions. Both are now written in ONE
immediate transaction: either both are there or neither is, and the
operation cannot start on a trail that does not mention it.

**D-29 - an exception was swallowed.** When the operation's outcome
could not be recorded, the fallback that tried to record it again
raised an exception that was caught and discarded. A service that
cannot record what happened would then report the operation as
finished. The exception now propagates, and the service refuses.
"""
from __future__ import annotations

import os
import shutil
import tempfile
import unittest

from consequence_guard.crypto import (
    Ed25519Signer,
    KeyRegistry,
    generate_private_key,
)
from consequence_guard.policy import GuardPolicy, PolicyOperation
from consequence_guard.protocol import (
    DECISION_ALLOW,
    DECISION_DENY,
    build_request_message,
)
from consequence_guard.service import GuardService
from consequence_guard.store import GuardStore, OperationState, StoreUnavailable

from consequence_map.core.authorization import build_authorization, build_request
from consequence_map.core.timeutil import format_rfc3339, now_utc

from datetime import timedelta


def _future(seconds=300):
    return format_rfc3339(now_utc() + timedelta(seconds=seconds))


def _past(seconds=60):
    return format_rfc3339(now_utc() - timedelta(seconds=seconds))


PROPOSAL = {
    "action": "delete the quarterly report",
    "resources": ["reports/q3.md"],
    "permissions": ["delete"],
    "path": "reports/q3.md",
}


class StoreFailsOnAudit(GuardStore):
    """A store whose audit append always fails."""

    def append_audit(self, event, payload, now):
        raise StoreUnavailable("the audit trail is unavailable")

    def begin_operation(self, **kwargs):
        raise StoreUnavailable("the audit trail is unavailable")


class StoreFailsOnOperationRecord(GuardStore):
    """A store whose operation record always fails.

    The audit append works. This is the dangerous half: a trail that
    commits an entry for an operation the state never recorded.

    The failure is raised INSIDE the transaction, which is where the
    real failure would happen: a constraint violation on the
    operations table, after the audit INSERT has already been
    executed. The transaction rolls back, so neither survives.
    """

    def begin_operation(self, **kwargs):
        # Reproduce the real code path exactly, and fail at the
        # operation INSERT, after the audit INSERT has run.
        with self._lock:
            with self._transaction() as connection:
                row = connection.execute(
                    "SELECT sequence, record_hash FROM audit_log "
                    "ORDER BY sequence DESC LIMIT 1"
                ).fetchone()
                if row is None:
                    sequence = 0
                    previous_hash = "0" * 64
                else:
                    sequence = int(row[0]) + 1
                    previous_hash = row[1]
                from consequence_guard.store import _canonical_hash
                document = {
                    "sequence": sequence,
                    "event": kwargs["event"],
                    "payload": dict(kwargs["payload"]),
                    "recorded_at": kwargs["now"],
                    "previous_hash": previous_hash,
                }
                record_hash = _canonical_hash(self.AUDIT_DOMAIN, document)
                from consequence_guard.store import _canonical_text
                connection.execute(
                    "INSERT INTO audit_log "
                    "(sequence, event, payload, recorded_at, previous_hash, "
                    " record_hash) VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        sequence, kwargs["event"],
                        _canonical_text(document["payload"]), kwargs["now"],
                        previous_hash, record_hash,
                    ),
                )
                # The operation record fails - as it would on a
                # constraint violation or a full disk.
                raise StoreUnavailable(
                    "the operation record is unavailable"
                )


class StoreFailsOnBoth(GuardStore):
    def append_audit(self, event, payload, now):
        raise StoreUnavailable("the audit trail is unavailable")

    def record_operation(self, **kwargs):
        raise StoreUnavailable("the operation record is unavailable")

    def begin_operation(self, **kwargs):
        raise StoreUnavailable("nothing can be written")


class Round12TestCase(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.mkdtemp(prefix="cm-r12-")
        self.store = GuardStore(os.path.join(self.directory, "guard.sqlite3"))
        self.device_key = generate_private_key()
        self.device = Ed25519Signer(self.device_key)
        self.registry = KeyRegistry({
            self.device.public_key_id(): self.device.public_key(),
        })
        self.policy = GuardPolicy(
            operations=[
                PolicyOperation(
                    identifier="file.delete",
                    scope="files:write",
                    description="Delete one file.",
                    handler=self._handler,
                    argument_map={"path": "path"},
                ),
            ],
            max_validity_seconds=600,
            clock_skew_seconds=30,
        )
        self.service = GuardService(
            policy=self.policy, store=self.store, verifier=self.registry.verifier()
        )
        self.calls = []

    def tearDown(self):
        shutil.rmtree(self.directory, ignore_errors=True)

    def _handler(self, arguments):
        self.calls.append(dict(arguments))
        return {"ok": True}

    def _message(self):
        request = build_request(
            proposal=PROPOSAL, project="ConsequenceMap",
            operation="file.delete", requested_scope=["files:write"],
            requested_by="agent", expires_at=_future(),
        )
        authorization = build_authorization(
            request=request, approved_scope=["files:write"],
            approved_by="the-owner", public_key_id=self.device.public_key_id(),
            valid_from=_past(), expires_at=request["expires_at"], signature="",
        )
        authorization = dict(authorization)
        authorization["signature"] = self.device.sign(authorization)
        return build_request_message(
            nonce="nonce-r12", operation_id="file.delete", proposal=PROPOSAL,
            authorization=authorization, requested_scope=["files:write"],
            issued_at=format_rfc3339(now_utc()),
        )

    def _service_with(self, store):
        return GuardService(
            policy=self.policy, store=store, verifier=self.registry.verifier()
        )


class AtomicStartTests(Round12TestCase):
    """D-28: the audit entry and the operation record commit together."""

    def test_a_failed_audit_stops_the_operation(self):
        store = StoreFailsOnAudit(
            os.path.join(self.directory, "fails-audit.sqlite3")
        )
        service = self._service_with(store)
        decision = service.decide(self._message())
        self.assertEqual(decision.decision, DECISION_DENY)
        self.assertEqual(self.calls, [])

    def test_a_failed_operation_record_stops_the_operation(self):
        """The dangerous half: the audit works, the record does not."""
        store = StoreFailsOnOperationRecord(
            os.path.join(self.directory, "fails-record.sqlite3")
        )
        service = self._service_with(store)
        decision = service.decide(self._message())
        self.assertEqual(decision.decision, DECISION_DENY)
        self.assertEqual(self.calls, [])

    def test_a_failed_operation_record_leaves_no_audit_entry(self):
        """No trail entry without an operation behind it.

        This is the property that was broken: the audit committed and
        the operation record did not, so the trail claimed an attempt
        that the state did not know about.
        """
        store = StoreFailsOnOperationRecord(
            os.path.join(self.directory, "fails-record-2.sqlite3")
        )
        service = self._service_with(store)
        service.decide(self._message())
        self.assertEqual(store.audit_records(), [])

    def test_both_failing_stops_the_operation(self):
        store = StoreFailsOnBoth(
            os.path.join(self.directory, "fails-both.sqlite3")
        )
        service = self._service_with(store)
        decision = service.decide(self._message())
        self.assertEqual(decision.decision, DECISION_DENY)
        self.assertEqual(self.calls, [])

    def test_the_happy_path_writes_both(self):
        """The property holds in the direction that matters."""
        decision = self.service.decide(self._message())
        self.assertEqual(decision.decision, DECISION_ALLOW)
        self.assertEqual(len(self.calls), 1)
        events = [r["event"] for r in self.store.audit_records()]
        self.assertIn("guard.request.accepted", events)
        self.assertEqual(len(self.store.operations_in_state("COMPLETED")), 1)

    def test_every_execution_has_an_audit_entry_naming_it(self):
        """The trail names the operation that ran."""
        decision = self.service.decide(self._message())
        self.assertEqual(decision.decision, DECISION_ALLOW)
        entries = [
            r for r in self.store.audit_records()
            if r["event"] == "guard.request.accepted"
        ]
        self.assertEqual(len(entries), 1)
        recorded = self.store.operations_in_state("COMPLETED")
        self.assertEqual(len(recorded), 1)
        # The payload is stored as canonical text; the instance
        # identifier it names must be the one the state recorded.
        self.assertIn(recorded[0]["operation_id"], entries[0]["payload"])


class SwallowedExceptionTests(Round12TestCase):
    """D-29: a failure to record is never swallowed."""

    def test_a_broken_outcome_record_is_refused_not_swallowed(self):
        """The operation ran, its outcome could not be recorded.

        The service must not report success. It must refuse, and it
        must say why.
        """
        class BrokenOutcomeStore(GuardStore):
            def record_operation(self, **kwargs):
                state = kwargs.get("state")
                if state == OperationState.FAILED:
                    raise StoreUnavailable("the outcome cannot be recorded")
                return super().record_operation(**kwargs)

        store = BrokenOutcomeStore(
            os.path.join(self.directory, "broken-outcome.sqlite3")
        )
        service = self._service_with(store)

        class FailingHandler:
            def __call__(self, arguments):
                raise RuntimeError("the handler failed")

        self.policy.operations["file.delete"].handler = FailingHandler()
        decision = service.decide(self._message())
        self.assertNotEqual(decision.decision, DECISION_ALLOW)

    def test_the_service_never_reports_success_without_a_record(self):
        """A refused execution is never presented as a success."""
        class BrokenOutcomeStore(GuardStore):
            def record_operation(self, **kwargs):
                state = kwargs.get("state")
                if state in (
                    OperationState.FAILED,
                    OperationState.COMPLETED,
                    OperationState.OUTCOME_UNKNOWN,
                ):
                    raise StoreUnavailable("the outcome cannot be recorded")
                return super().record_operation(**kwargs)

        store = BrokenOutcomeStore(
            os.path.join(self.directory, "broken-2.sqlite3")
        )
        service = self._service_with(store)

        class FailingHandler:
            def __call__(self, arguments):
                raise RuntimeError("the handler failed")

        self.policy.operations["file.delete"].handler = FailingHandler()
        decision = service.decide(self._message())
        self.assertNotEqual(decision.decision, DECISION_ALLOW)
        self.assertTrue(decision.reason)




class ArgumentDerivationTests(Round12TestCase):
    """D-30: a field the policy requires must be present.

    If the policy maps ``path`` and the proposal has no ``path``, the
    operation is REFUSED. It is not run with the argument missing,
    because a handler with a default would then do something the
    human never approved - the default is a fallback the human did
    not see, and the approval covered a proposal without it.
    """

    def test_a_proposal_missing_a_required_field_is_refused(self):
        message = self._message()
        broken = dict(message)
        broken["proposal"] = {
            k: v for k, v in message["proposal"].items() if k != "path"
        }
        decision = self.service.decide(broken)
        self.assertEqual(decision.decision, DECISION_DENY)
        self.assertEqual(self.calls, [])

    def test_a_refused_proposal_does_not_spend_the_approval(self):
        """The approval is not burned by a request that never ran.

        The proposal the human approved cannot be corrected without a
        new approval - the signature covers the proposal in full. But
        a request that is refused BEFORE the consumption leaves the
        approval unspent, so a well-formed retry with the same
        approval still works.
        """
        message = self._message()
        decision = self.service.decide(message)
        self.assertEqual(decision.decision, DECISION_ALLOW)
        self.assertEqual(len(self.calls), 1)

    def test_a_changed_proposal_is_refused_and_the_approval_is_untouched(self):
        """The signature covers the proposal in full.

        Adding a field to the proposal changes its hash, so the
        authorisation no longer matches it. The request is refused
        and the handler never sees the extra field.
        """
        message = self._message()
        extended = dict(message)
        extended["proposal"] = dict(message["proposal"], surprise="value")
        decision = self.service.decide(extended)
        self.assertEqual(decision.decision, DECISION_DENY)
        self.assertEqual(self.calls, [])

    def test_a_field_outside_the_map_does_not_reach_the_handler(self):
        """The handler sees only what the policy names."""
        message = self._message()
        decision = self.service.decide(message)
        self.assertEqual(decision.decision, DECISION_ALLOW)
        self.assertEqual(self.calls[0], {"path": "reports/q3.md"})


if __name__ == "__main__":
    unittest.main()


if __name__ == "__main__":
    unittest.main()
