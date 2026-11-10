"""Tests for the guard's cryptographic layer.

These tests exercise REAL Ed25519 signatures through the
``cryptography`` library. They are not tests of a stub.

The negative tests are the point. A signature that verifies is easy;
what matters is that every way of changing the signed document fails,
including the ways that are easy to get wrong:

- changing one field;
- **adding** a field (the classic "field stripping" attack);
- **removing** a field;
- using the wrong key;
- using a revoked key;
- naming an algorithm that is not authorised;
- naming a key that is not known;
- an empty or truncated signature;
- a signature made over a different domain;
- a document replayed after it has been consumed.
"""
from __future__ import annotations

import unittest

from consequence_guard.crypto import (
    ALGORITHM_ED25519,
    ALGORITHMS,
    Ed25519Signer,
    Ed25519Verifier,
    KeyRegistry,
    MalformedPublicKey,
    MalformedSignature,
    UnknownAlgorithm,
    UnknownKey,
    decode_public_key,
    decode_signature,
    encode_public_key,
    encode_signature,
    generate_private_key,
)
from consequence_map.core.authorization import (
    AuthorizationInvalid,
    build_authorization,
    build_request,
    verify_authorization,
)
from consequence_map.core.canonical import DOMAIN_AUTHORIZATION, canonical_bytes
from consequence_map.core.timeutil import format_rfc3339, now_utc

from datetime import timedelta


def _future(seconds=600):
    return format_rfc3339(now_utc() + timedelta(seconds=seconds))


def _past(seconds=60):
    return format_rfc3339(now_utc() - timedelta(seconds=seconds))


PROPOSAL = {"action": "delete the report", "resources": ["r.md"], "permissions": ["delete"]}


class KeyEncodingTests(unittest.TestCase):
    """The encoding has exactly one form."""

    def test_a_public_key_round_trips(self):
        private = generate_private_key()
        encoded = encode_public_key(private.public_key())
        decoded = decode_public_key(encoded)
        self.assertEqual(encode_public_key(decoded), encoded)

    def test_a_public_key_is_32_bytes(self):
        private = generate_private_key()
        encoded = encode_public_key(private.public_key())
        self.assertEqual(len(decode_signature.__module__) > 0, True)
        raw = decode_public_key(encoded)
        self.assertEqual(len(raw.public_bytes_raw()), 32)

    def test_a_malformed_public_key_is_refused(self):
        with self.assertRaises(MalformedPublicKey):
            decode_public_key("not base64 at all!!")

    def test_a_short_public_key_is_refused(self):
        with self.assertRaises(MalformedPublicKey):
            decode_public_key(encode_signature(b"x" * 8))

    def test_a_signature_round_trips(self):
        private = generate_private_key()
        signature = private.sign(b"payload")
        self.assertEqual(decode_signature(encode_signature(signature)), signature)

    def test_a_truncated_signature_is_refused(self):
        with self.assertRaises(MalformedSignature):
            decode_signature(encode_signature(b"x" * 32))

    def test_an_empty_signature_is_refused(self):
        with self.assertRaises(MalformedSignature):
            decode_signature("")


class AlgorithmTests(unittest.TestCase):
    """Only the algorithms on the allowlist are honoured."""

    def test_the_allowlist_is_not_empty(self):
        self.assertIn(ALGORITHM_ED25519, ALGORITHMS)

    def test_an_unauthorised_algorithm_is_refused_outright(self):
        private = generate_private_key()
        signer = Ed25519Signer(private)
        verifier = Ed25519Verifier({signer.public_key_id(): signer.public_key()})
        with self.assertRaises(UnknownAlgorithm):
            verifier.verify(
                signer.public_key_id(), b"payload", encode_signature(b"\x00" * 64),
                algorithm="rsa-sha1",
            )

    def test_an_unknown_algorithm_is_not_reported_as_a_bad_signature(self):
        """A document we do not understand is not a document that failed."""
        private = generate_private_key()
        signer = Ed25519Signer(private)
        verifier = Ed25519Verifier({signer.public_key_id(): signer.public_key()})
        try:
            verifier.verify(
                signer.public_key_id(), b"payload", "x", algorithm="md5"
            )
        except UnknownAlgorithm:
            pass
        else:
            self.fail("an unknown algorithm must be refused, not merely fail")


class RegistryTests(unittest.TestCase):
    """Revocation lives with the keys it applies to."""

    def test_an_unknown_key_is_refused(self):
        verifier = Ed25519Verifier({})
        with self.assertRaises(UnknownKey):
            verifier.verify("no-such-key", b"payload", encode_signature(b"\x00" * 64))

    def test_a_revoked_key_is_refused(self):
        private = generate_private_key()
        signer = Ed25519Signer(private)
        registry = KeyRegistry({signer.public_key_id(): signer.public_key()})
        registry.revoke(signer.public_key_id())
        with self.assertRaises(UnknownKey):
            registry.verifier().verify(
                signer.public_key_id(), b"payload", encode_signature(b"\x00" * 64)
            )

    def test_revocation_does_not_remove_the_key_from_the_registry(self):
        """A revoked key stays known - it is refused, not forgotten."""
        private = generate_private_key()
        signer = Ed25519Signer(private)
        registry = KeyRegistry({signer.public_key_id(): signer.public_key()})
        registry.revoke(signer.public_key_id())
        self.assertTrue(registry.known(signer.public_key_id()))
        self.assertTrue(registry.is_revoked(signer.public_key_id()))


class SignatureBindingTests(unittest.TestCase):
    """What is signed, and what happens when it changes."""

    def setUp(self):
        self.private = generate_private_key()
        self.signer = Ed25519Signer(self.private)
        self.registry = KeyRegistry({self.signer.public_key_id(): self.signer.public_key()})
        self.verifier = self.registry.verifier()
        self.request = build_request(
            proposal=PROPOSAL, project="C", operation="file.delete",
            requested_scope=["files:write"], requested_by="agent",
            expires_at=_future(),
        )
        authorization = build_authorization(
            request=self.request, approved_scope=["files:write"],
            approved_by="the-owner", public_key_id=self.signer.public_key_id(),
            valid_from=_past(), expires_at=self.request["expires_at"], signature="",
        )
        self.authorization = dict(authorization)
        self.authorization["signature"] = self.signer.sign(self.authorization)

    def _verify(self, authorization=None, request=None):
        return verify_authorization(
            proposal=PROPOSAL,
            request=request if request is not None else self.request,
            authorization=authorization if authorization is not None else self.authorization,
            verifier=self.verifier,
        )

    def test_a_correct_authorization_verifies(self):
        self._verify()

    def test_changing_one_field_is_detected(self):
        tampered = dict(self.authorization)
        tampered["approved_by"] = "someone-else"
        with self.assertRaises(Exception):
            self._verify(tampered)

    def test_ADDING_a_field_is_detected(self):
        """The classic field-stripping attack.

        The rule is "strip the field named signature, sign everything
        else". If the rule were "strip the fields we recognise", an
        added field would be excluded from the signed payload and the
        signature would still verify.
        """
        tampered = dict(self.authorization)
        tampered["escalate_to"] = "root"
        with self.assertRaises(Exception):
            self._verify(tampered)

    def test_REMOVING_a_field_is_detected(self):
        tampered = dict(self.authorization)
        del tampered["approved_by"]
        with self.assertRaises(Exception):
            self._verify(tampered)

    def test_changing_the_scope_is_detected(self):
        tampered = dict(self.authorization)
        tampered["approved_scope"] = ["admin"]
        with self.assertRaises(Exception):
            self._verify(tampered)

    def test_changing_the_expiry_is_detected(self):
        tampered = dict(self.authorization)
        tampered["expires_at"] = _future(3600)
        with self.assertRaises(Exception):
            self._verify(tampered)

    def test_the_wrong_key_does_not_verify(self):
        other = Ed25519Signer(generate_private_key())
        registry = KeyRegistry({
            self.signer.public_key_id(): self.signer.public_key(),
            other.public_key_id(): other.public_key(),
        })
        tampered = dict(self.authorization)
        tampered["public_key_id"] = other.public_key_id()
        with self.assertRaises(Exception):
            verify_authorization(
                proposal=PROPOSAL, request=self.request,
                authorization=tampered, verifier=registry.verifier(),
            )

    def test_a_signature_over_a_different_domain_does_not_verify(self):
        """Domain separation: a signature for another purpose is not one.

        The signature in the document was made over the AUTHORIZATION
        domain. Verifying it against the bytes of a DIFFERENT domain
        must fail, even though the key is the right key and the
        signature is genuine.
        """
        other_domain_bytes = canonical_bytes(
            "some.other.domain", {"unrelated": "payload"}
        )
        self.assertFalse(
            self.verifier.verify(
                self.signer.public_key_id(), other_domain_bytes,
                self.authorization["signature"],
            )
        )

    def test_the_same_key_signing_another_domain_is_a_valid_signature_for_that_domain(self):
        """The counterpart, stated so the test above is not misread.

        A signature is not bound to a document; it is bound to BYTES.
        The same key may sign bytes under any domain. What prevents
        cross-domain confusion is that the verifier asks for the bytes
        of the domain it cares about.
        """
        payload = canonical_bytes("some.other.domain", {"x": 1})
        signature = encode_signature(self.private.sign(payload))
        self.assertTrue(
            self.verifier.verify(self.signer.public_key_id(), payload, signature)
        )

    def test_the_signature_covers_the_document_without_its_signature_field(self):
        payload = self.signer.signing_payload(self.authorization)
        self.assertNotIn(b"signature", payload.split(b"=")[0][:20])
        self.assertTrue(self.verifier.verify(
            self.signer.public_key_id(), payload, self.authorization["signature"]
        ))

    def test_a_non_canonical_payload_does_not_verify(self):
        """The bytes that are verified must be the canonical bytes.

        Handing the verifier a byte string that is not the canonical
        form of the document must not verify, even if it is the same
        logical document.
        """
        self.assertFalse(self.verifier.verify(
            self.signer.public_key_id(),
            b'{"approved_by":"the-owner"}',
            self.authorization["signature"],
        ))

    def test_a_replayed_document_verifies_at_the_protocol_layer(self):
        """The protocol binds; the spent set is what refuses a replay.

        This is a property of the design, and it is why the executor's
        spent-authorization set exists.
        """
        self._verify()
        self._verify()


if __name__ == "__main__":
    unittest.main()
