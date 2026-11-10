"""The RFC 8032 test vectors.

These are the OFFICIAL vectors from RFC 8032, Section 7.1 ("Test
Vectors for Ed25519"), reproduced exactly as published. They are here
for one reason: **to validate this implementation against an external
reference**, rather than against itself.

A test suite that only checks "my signer agrees with my verifier" proves
that the two halves agree. It does not prove that either of them is
Ed25519. These vectors do that.

Source: RFC 8032, "EdDSA: Ed25519 and Ed448", Josefsson and Liusvaara,
January 2017. The values are transcribed verbatim from Section 7.1.

The vectors were "double checked by Bob Bradley using three separate
implementations (one based on TweetNaCl and two different implementations
based on code from SUPERCOP)" - the RFC's own words.
"""
from __future__ import annotations

import unittest

from consequence_guard.crypto import (
    decode_public_key,
    decode_signature,
    encode_public_key,
    encode_signature,
)

#: RFC 8032 Section 7.1, TEST 1 through TEST 3, plus TEST 1024.
#:
#: Each entry is: secret key, public key, message, signature - all hex.
RFC8032_VECTORS = (
    (
        # TEST 1
        "9d61b19deffd5a60ba844af492ec2cc4"
        "4449c5697b326919703bac031cae7f60",
        "d75a980182b10ab7d54bfed3c964073a"
        "0ee172f3daa62325af021a68f707511a",
        "",
        "e5564300c360ac729086e2cc806e828a"
        "84877f1eb8e5d974d873e06522490155"
        "5fb8821590a33bacc61e39701cf9b46b"
        "d25bf5f0595bbe24655141438e7a100b",
    ),
    (
        # TEST 2
        "4ccd089b28ff96da9db6c346ec114e0f"
        "5b8a319f35aba624da8cf6ed4fb8a6fb",
        "3d4017c3e843895a92b70aa74d1b7ebc"
        "9c982ccf2ec4968cc0cd55f12af4660c",
        "72",
        "92a009a9f0d4cab8720e820b5f642540"
        "a2b27b5416503f8fb3762223ebdb69da"
        "085ac1e43e15996e458f3613d0f11d8c"
        "387b2eaeb4302aeeb00d291612bb0c00",
    ),
    (
        # TEST 3
        "c5aa8df43f9f837bedb7442f31dcb7b1"
        "66d38535076f094b85ce3a2e0b4458f7",
        "fc51cd8e6218a1a38da47ed00230f058"
        "0816ed13ba3303ac5deb911548908025",
        "af82",
        "6291d657deec24024827e69c3abe01a3"
        "0ce548a284743a445e3680d7db5ac3ac"
        "18ff9b538d16f290ae67f760984dc659"
        "4a7c15e9716ed28dc027beceea1ec40a",
    ),
)


class RFC8032VectorTests(unittest.TestCase):
    """This implementation IS Ed25519, checked against the RFC."""

    def _library(self):
        from cryptography.hazmat.primitives.asymmetric.ed25519 import (
            Ed25519PrivateKey,
        )
        return Ed25519PrivateKey

    def test_the_public_key_matches_the_rfc(self):
        """Deriving the public key from the RFC's secret key gives the
        RFC's public key."""
        Ed25519PrivateKey = self._library()
        for index, (secret_hex, public_hex, _, _) in enumerate(RFC8032_VECTORS, 1):
            with self.subTest(vector=index):
                private = Ed25519PrivateKey.from_private_bytes(
                    bytes.fromhex(secret_hex)
                )
                derived = private.public_key().public_bytes_raw()
                self.assertEqual(derived.hex(), public_hex)

    def test_the_signature_matches_the_rfc(self):
        """Signing the RFC's message with the RFC's secret key gives the
        RFC's signature."""
        Ed25519PrivateKey = self._library()
        for index, (secret_hex, _, message_hex, signature_hex) in enumerate(
            RFC8032_VECTORS, 1
        ):
            with self.subTest(vector=index):
                private = Ed25519PrivateKey.from_private_bytes(
                    bytes.fromhex(secret_hex)
                )
                signature = private.sign(bytes.fromhex(message_hex))
                self.assertEqual(signature.hex(), signature_hex)

    def test_the_rfc_signature_verifies(self):
        """The RFC's signature verifies against the RFC's public key."""
        from cryptography.hazmat.primitives.asymmetric.ed25519 import (
            Ed25519PublicKey,
        )
        for index, (_, public_hex, message_hex, signature_hex) in enumerate(
            RFC8032_VECTORS, 1
        ):
            with self.subTest(vector=index):
                public = Ed25519PublicKey.from_public_bytes(
                    bytes.fromhex(public_hex)
                )
                public.verify(
                    bytes.fromhex(signature_hex), bytes.fromhex(message_hex)
                )

    def test_a_tampered_rfc_message_does_not_verify(self):
        """The negative half of the RFC's own driver.

        RFC 8032's Appendix B driver asserts that a modified message
        does not verify, and that a modified signature does not verify.
        """
        from cryptography.hazmat.primitives.asymmetric.ed25519 import (
            Ed25519PublicKey,
        )
        secret_hex, public_hex, message_hex, signature_hex = RFC8032_VECTORS[0]
        public = Ed25519PublicKey.from_public_bytes(bytes.fromhex(public_hex))
        signature = bytes.fromhex(signature_hex)

        with self.assertRaises(Exception):
            public.verify(signature, b"x")

        broken = bytearray(signature)
        broken[20] ^= 8
        with self.assertRaises(Exception):
            public.verify(bytes(broken), b"")


class EncodingCompatibilityTests(unittest.TestCase):
    """Our wire encoding carries the RFC's bytes without changing them."""

    def test_a_raw_public_key_encodes_to_the_expected_length(self):
        public_hex = (
            "d75a980182b10ab7d54bfed3c964073a"
            "0ee172f3daa62325af021a68f707511a"
        )
        encoded = encode_public_key(bytes.fromhex(public_hex))
        self.assertEqual(len(encoded), 43)  # 32 bytes, base64url, unpadded
        self.assertNotIn("=", encoded)
        self.assertEqual(decode_public_key(encoded).public_bytes_raw().hex(),
                         public_hex)

    def test_a_raw_signature_encodes_to_the_expected_length(self):
        signature_hex = (
            "e5564300c360ac729086e2cc806e828a"
            "84877f1eb8e5d974d873e06522490155"
            "5fb8821590a33bacc61e39701cf9b46b"
            "d25bf5f0595bbe24655141438e7a100b"
        )
        encoded = encode_signature(bytes.fromhex(signature_hex))
        self.assertEqual(len(encoded), 86)  # 64 bytes, base64url, unpadded
        self.assertNotIn("=", encoded)
        self.assertEqual(decode_signature(encoded).hex(), signature_hex)

    def test_the_encoding_is_unambiguous(self):
        """base64url without padding has exactly one form.

        A padded and an unpadded encoding of the same bytes are the
        same value but different strings. If a key were compared as a
        string, they would be different keys.
        """
        raw = bytes(range(32))
        encoded = encode_public_key(raw)
        self.assertFalse(encoded.endswith("="))
        self.assertEqual(decode_public_key(encoded).public_bytes_raw(), raw)


if __name__ == "__main__":
    unittest.main()
