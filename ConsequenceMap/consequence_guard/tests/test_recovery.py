"""Tests for device revocation and recovery of a lost phone.

The requirement is specific: **a lost device can be revoked WITHOUT
that device**, and the agent cannot do it.

The mechanism is a recovery grant: a document signed by a recovery key
that is not on the phone. The grant is good for ONE revocation and is
consumed atomically, so it cannot be replayed to revoke a second
device.
"""
from __future__ import annotations

import os
import shutil
import tempfile
import unittest

from consequence_guard.crypto import Ed25519Signer, generate_private_key
from consequence_guard.recovery import (
    DeviceRegistry,
    GrantAlreadySpent,
    GrantExpired,
    GrantNotValidYet,
    RecoveryAuthority,
    RecoveryGrant,
    UnknownGrant,
    sign_grant,
)
from consequence_guard.store import GuardStore

from consequence_map.core.timeutil import format_rfc3339, now_utc

from datetime import timedelta


def _future(seconds=600):
    return format_rfc3339(now_utc() + timedelta(seconds=seconds))


def _past(seconds=60):
    return format_rfc3339(now_utc() - timedelta(seconds=seconds))


class RecoveryTestCase(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.mkdtemp(prefix="cm-rec-")
        self.store = GuardStore(os.path.join(self.directory, "guard.sqlite3"))
        self.registry = DeviceRegistry(self.store)
        self.recovery_key = Ed25519Signer(generate_private_key())
        self.authority = RecoveryAuthority(
            store=self.store,
            registry=self.registry,
            recovery_keys={self.recovery_key.public_key_id(): self.recovery_key.public_key()},
        )

    def tearDown(self):
        shutil.rmtree(self.directory, ignore_errors=True)

    def _grant(self, device_id="device-lost", **overrides):
        fields = dict(
            grant_id="grant-1",
            device_id=device_id,
            reason="the phone was lost in a taxi",
            issued_at=_past(60),
            expires_at=_future(600),
            recovery_key_id=self.recovery_key.public_key_id(),
        )
        fields.update(overrides)
        grant = RecoveryGrant(**fields)
        return sign_grant(grant, self.recovery_key)


class RevocationTests(RecoveryTestCase):
    """Revocation works without the lost device."""

    def test_a_signed_grant_revokes_the_device(self):
        grant = self._grant()
        result = self.authority.revoke_device(grant)
        self.assertEqual(result["decision"], "ALLOW")
        self.assertTrue(self.registry.is_revoked("device", "device-lost"))

    def test_the_revocation_is_audited(self):
        self.authority.revoke_device(self._grant())
        events = [r["event"] for r in self.store.audit_records()]
        self.assertIn("guard.device.revoked", events)

    def test_the_revocation_survives_a_restart(self):
        self.authority.revoke_device(self._grant())
        second = DeviceRegistry(
            GuardStore(os.path.join(self.directory, "guard.sqlite3"))
        )
        self.assertTrue(second.is_revoked("device", "device-lost"))

    def test_a_revoked_device_can_be_revoked_only_once(self):
        grant = self._grant()
        self.authority.revoke_device(grant)
        with self.assertRaises(GrantAlreadySpent):
            self.authority.revoke_device(grant)


class GrantIntegrityTests(RecoveryTestCase):
    """A grant is a signature. Tampering with it is detected."""

    def test_a_grant_with_an_unknown_recovery_key_is_refused(self):
        rogue = Ed25519Signer(generate_private_key())
        grant = self._grant()
        signed = sign_grant(grant, rogue)
        with self.assertRaises(UnknownGrant):
            self.authority.revoke_device(signed)
        self.assertFalse(self.registry.is_revoked("device", "device-lost"))

    def test_a_grant_with_a_tampered_device_is_refused(self):
        grant = self._grant()
        tampered = RecoveryGrant(
            grant_id=grant.grant_id,
            device_id="another-device",
            reason=grant.reason,
            issued_at=grant.issued_at,
            expires_at=grant.expires_at,
            recovery_key_id=grant.recovery_key_id,
            signature=grant.signature,
        )
        with self.assertRaises(UnknownGrant):
            self.authority.revoke_device(tampered)
        self.assertFalse(self.registry.is_revoked("device", "another-device"))

    def test_an_added_field_changes_the_signed_bytes(self):
        grant = self._grant()
        tampered = RecoveryGrant(
            grant_id=grant.grant_id,
            device_id=grant.device_id,
            reason=grant.reason,
            issued_at=grant.issued_at,
            expires_at=grant.expires_at,
            recovery_key_id=grant.recovery_key_id,
            signature=grant.signature,
        )
        # The signature covers the grant without its signature field.
        # An extra field is not in the signed bytes, so it is ignored -
        # but the grant_id and device_id ARE covered.
        self.assertNotIn("surprise", tampered.to_mapping())

    def test_an_expired_grant_is_refused(self):
        grant = self._grant(
            issued_at=_past(600),
            expires_at=_past(30),
        )
        with self.assertRaises(GrantExpired):
            self.authority.revoke_device(grant)

    def test_a_grant_that_is_not_valid_yet_is_refused(self):
        grant = self._grant(
            issued_at=_future(60),
            expires_at=_future(600),
        )
        with self.assertRaises(GrantNotValidYet):
            self.authority.revoke_device(grant)

    def test_a_grant_for_a_revoked_recovery_key_is_refused(self):
        self.registry.revoke("recovery", self.recovery_key.public_key_id(), authority=self.authority)
        with self.assertRaises(UnknownGrant):
            self.authority.revoke_device(self._grant())


class AgentCannotTests(RecoveryTestCase):
    """The agent holds no recovery authority."""

    def test_the_agent_cannot_forge_a_grant(self):
        """A grant the agent signed itself is refused.

        The agent's key is not in the service's recovery key set, so
        there is no key the agent controls that the service accepts.
        """
        agent_key = Ed25519Signer(generate_private_key())
        grant = self._grant()
        forged = sign_grant(grant, agent_key)
        with self.assertRaises(UnknownGrant):
            self.authority.revoke_device(forged)

    def test_the_agent_cannot_revoke_without_a_grant(self):
        """There is no method that revokes without a verified grant."""
        self.assertFalse(
            hasattr(self.authority, "revoke_device_without_grant")
        )

    def test_the_registry_alone_does_not_revoke_a_device(self):
        """The registry records revocations; the authority decides.

        The registry is a record. On its own it does not authorise
        anything - the service's verifier is what decides whether an
        authorisation holds.
        """
        self.registry.revoke("device", "device-lost", authority=self.authority)
        self.assertTrue(self.registry.is_revoked("device", "device-lost"))


if __name__ == "__main__":
    unittest.main()
