"""Tests for the guard deployment contract.

The property under test: when the guard cannot be reached, the answer is
a refusal. There is no fallback that approves. That is the single point
at which a deployment is most likely to silently undo the boundary it
exists to provide.
"""
from __future__ import annotations

import unittest

from consequence_map.core.deployment import (
    ContractViolation,
    GuardDeployment,
    GuardUnavailable,
    InProcessDeployment,
)


class _Answering:
    def __init__(self, answer):
        self.answer = answer
        self.calls = []

    def ask(self, payload):
        self.calls.append(payload)
        if isinstance(self.answer, Exception):
            raise self.answer
        return self.answer


class DeploymentTests(unittest.TestCase):
    def test_a_valid_decision_is_passed_through(self):
        transport = _Answering({"decision": "ALLOW", "reason": "every condition held"})
        deployment = GuardDeployment(transport)
        result = deployment.decide({"anything": 1})
        self.assertEqual(result["decision"], "ALLOW")
        self.assertEqual(len(transport.calls), 1)

    def test_a_denial_is_passed_through(self):
        transport = _Answering({"decision": "DENY", "reason": "not on the allowlist"})
        self.assertEqual(
            GuardDeployment(transport).decide({})["decision"], "DENY"
        )

    # T11 - the security service is unavailable
    def test_t11_an_unreachable_guard_raises_rather_than_approving(self):
        transport = _Answering(RuntimeError("the pipe is gone"))
        with self.assertRaises(GuardUnavailable):
            GuardDeployment(transport).decide({})

    def test_t11_a_guard_with_no_transport_raises(self):
        with self.assertRaises(GuardUnavailable):
            GuardDeployment().decide({})

    def test_t11_the_refusal_is_a_denial_with_a_reason(self):
        deployment = GuardDeployment()
        refusal = deployment.refuse("the guard is unreachable")
        self.assertEqual(refusal["decision"], "DENY")
        self.assertFalse(refusal["allowed"])
        self.assertIn("unreachable", refusal["reason"])

    def test_a_transport_returning_none_is_a_contract_violation(self):
        with self.assertRaises(ContractViolation):
            GuardDeployment(_Answering(None)).decide({})

    def test_a_transport_returning_an_unknown_decision_is_a_violation(self):
        with self.assertRaises(ContractViolation):
            GuardDeployment(_Answering({"decision": "MAYBE"})).decide({})

    def test_a_transport_returning_no_reason_is_a_violation(self):
        with self.assertRaises(ContractViolation):
            GuardDeployment(_Answering({"decision": "ALLOW"})).decide({})

    def test_a_transport_returning_a_non_mapping_is_a_violation(self):
        with self.assertRaises(ContractViolation):
            GuardDeployment(_Answering(["ALLOW"])).decide({})


class InProcessHonestyTests(unittest.TestCase):
    def test_the_in_process_deployment_admits_it_has_no_boundary(self):
        deployment = InProcessDeployment()
        self.assertFalse(deployment.provides_boundary)
        described = deployment.describe()
        self.assertFalse(described["provides_boundary"])
        self.assertIn("NO trust boundary", described["warning"])

    def test_the_base_class_does_not_claim_a_boundary_either(self):
        self.assertFalse(GuardDeployment().provides_boundary)


if __name__ == "__main__":
    unittest.main()
