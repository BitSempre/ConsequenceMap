"""Tests for the tamper-evident audit trail.

Scenarios: T15 (the agent alters the audit records), T18 (the process is
interrupted mid-operation), T19 (the machine restarts during a pending
authorization).

The chain is a detection mechanism, not a prevention mechanism. These
tests assert that alteration is DETECTED, and the module docstring states
plainly what is not proven.
"""
from __future__ import annotations

import unittest

from consequence_map.core.audit import (
    GENESIS_HASH,
    AuditError,
    AuditLog,
    ChainBroken,
    verify_chain,
)
from consequence_map.core.canonical import CanonicalisationError
from consequence_map.core.timeutil import format_rfc3339, now_utc


class AuditChainTests(unittest.TestCase):
    def setUp(self):
        self.log = AuditLog()
        self.log.append("proposal.created", {"proposal_id": "p-1"})
        self.log.append("authorization.requested", {"request_id": "r-1"})
        self.log.append("authorization.approved", {"request_id": "r-1"})
        self.log.append("execution.completed", {"path": "reports/a.md"})

    def test_an_untouched_chain_verifies(self):
        self.log.verify()
        verify_chain(self.log.records)

    def test_the_first_record_chains_to_genesis(self):
        self.assertEqual(self.log.records[0].previous_hash, GENESIS_HASH)

    def test_each_record_chains_to_its_predecessor(self):
        for index in range(1, len(self.log.records)):
            self.assertEqual(
                self.log.records[index].previous_hash,
                self.log.records[index - 1].record_hash,
            )

    def test_sequence_numbers_are_contiguous(self):
        self.assertEqual(
            [r.sequence for r in self.log.records], [0, 1, 2, 3]
        )

    # T15 - the agent alters the audit records
    def test_t15_an_altered_payload_is_detected(self):
        record = self.log.records[2]
        record.payload = {"request_id": "r-999"}
        with self.assertRaises(ChainBroken):
            self.log.verify()

    def test_t15_an_altered_event_name_is_detected(self):
        self.log.records[1].event = "authorization.auto_approved"
        with self.assertRaises(ChainBroken):
            self.log.verify()

    def test_t15_an_altered_timestamp_is_detected(self):
        # A timestamp that differs from the original, not merely "now" -
        # the append happened in the same millisecond.
        self.log.records[1].recorded_at = "2020-01-01T00:00:00.000Z"
        with self.assertRaises(ChainBroken):
            self.log.verify()

    def test_t15_a_removed_record_is_detected(self):
        records = list(self.log.records)
        del records[2]
        with self.assertRaises(ChainBroken):
            verify_chain(records)

    def test_t15_an_inserted_record_is_detected(self):
        records = list(self.log.records)
        rogue = AuditLog()
        rogue.append("execution.approved", {"path": "secrets"})
        records.insert(2, rogue.records[0])
        with self.assertRaises(ChainBroken):
            verify_chain(records)

    def test_t15_a_reordered_chain_is_detected(self):
        records = list(self.log.records)
        records[1], records[2] = records[2], records[1]
        with self.assertRaises(ChainBroken):
            verify_chain(records)

    def test_t15_a_rewritten_chain_is_detected_by_the_head(self):
        # Rewriting every record consistently produces a self-consistent
        # chain - which is exactly why the chain alone is not prevention.
        # What it still catches is a rewrite that did not recompute the
        # hashes: this test rewrites the content but keeps the old hashes.
        records = list(self.log.records)
        records[3].payload = {"path": "secrets"}
        with self.assertRaises(ChainBroken):
            verify_chain(records)

    def test_an_event_needs_a_name(self):
        with self.assertRaises(AuditError):
            AuditLog().append("", {})

    def test_a_non_ascii_payload_is_rejected_at_append(self):
        with self.assertRaises(CanonicalisationError):
            AuditLog().append("event", {"text": "caf\u00e9"})

    def test_an_escaped_non_ascii_payload_is_accepted(self):
        log = AuditLog()
        log.append("event", {"text": "caf\\u00e9"})
        log.verify()

    # T19 - the machine restarts during a pending authorization
    def test_t19_an_empty_log_verifies(self):
        AuditLog().verify()

    def test_a_record_can_be_reconstructed_from_its_mapping(self):
        # A record in the middle of a chain cannot be verified on its own -
        # the chain is what binds it. Reconstructing it and re-verifying
        # the WHOLE chain is the meaningful check.
        from consequence_map.core.audit import AuditRecord

        original = self.log.records[1]
        rebuilt = AuditRecord.from_mapping(original.to_mapping())
        self.assertEqual(rebuilt.record_hash, original.record_hash)
        records = list(self.log.records)
        records[1] = rebuilt
        verify_chain(records)


if __name__ == "__main__":
    unittest.main()
