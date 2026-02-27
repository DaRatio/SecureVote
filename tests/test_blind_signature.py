"""
Unit tests for the RSA blind signature module.
"""

import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

from blind_signature import (
    generate_keypair,
    generate_token,
    blind_token,
    blind_sign,
    unblind_signature,
    verify_signature,
    token_to_hex,
    hex_to_token,
    int_to_b64,
    b64_to_int,
    serialize_credential,
    deserialize_credential,
    token_hash,
)


@pytest.fixture(scope="module")
def keypair():
    return generate_keypair()


@pytest.fixture(scope="module")
def token():
    return generate_token()


# ---------------------------------------------------------------------------
# Key generation
# ---------------------------------------------------------------------------

class TestKeyGeneration:
    def test_keypair_generates_pem_strings(self, keypair):
        private_key, public_key = keypair
        assert "BEGIN RSA PRIVATE KEY" in private_key or "BEGIN PRIVATE KEY" in private_key
        assert "BEGIN PUBLIC KEY" in public_key

    def test_keypair_unique(self):
        pk1, _ = generate_keypair()
        pk2, _ = generate_keypair()
        assert pk1 != pk2


# ---------------------------------------------------------------------------
# Token generation
# ---------------------------------------------------------------------------

class TestTokenGeneration:
    def test_token_is_32_bytes(self, token):
        assert len(token) == 32

    def test_tokens_are_unique(self):
        t1 = generate_token()
        t2 = generate_token()
        assert t1 != t2


# ---------------------------------------------------------------------------
# Full blind signature protocol
# ---------------------------------------------------------------------------

class TestBlindSignatureProtocol:
    def test_full_protocol(self, keypair, token):
        private_key, public_key = keypair

        # Step 1: Voter blinds token
        blinded_bytes, blinding_factor = blind_token(token, public_key)
        assert isinstance(blinded_bytes, bytes)
        assert isinstance(blinding_factor, int)
        assert blinding_factor > 1

        # Step 2: Issuer signs blind token (never sees original token)
        blind_sig_int = blind_sign(blinded_bytes, private_key)
        assert isinstance(blind_sig_int, int)

        # Step 3: Voter unblinds to get the actual signature
        signature = unblind_signature(blind_sig_int, blinding_factor, public_key)
        assert isinstance(signature, int)

        # Step 4: Verify signature against original token
        assert verify_signature(token, signature, public_key)

    def test_wrong_token_fails_verification(self, keypair, token):
        private_key, public_key = keypair

        blinded_bytes, blinding_factor = blind_token(token, public_key)
        blind_sig_int = blind_sign(blinded_bytes, private_key)
        signature = unblind_signature(blind_sig_int, blinding_factor, public_key)

        wrong_token = generate_token()
        assert not verify_signature(wrong_token, signature, public_key)

    def test_tampered_signature_fails_verification(self, keypair, token):
        private_key, public_key = keypair

        blinded_bytes, blinding_factor = blind_token(token, public_key)
        blind_sig_int = blind_sign(blinded_bytes, private_key)
        signature = unblind_signature(blind_sig_int, blinding_factor, public_key)

        tampered = signature ^ (1 << 10)  # flip a bit
        assert not verify_signature(token, tampered, public_key)

    def test_signature_from_wrong_key_fails(self, token):
        _, pub1 = generate_keypair()
        priv2, _ = generate_keypair()

        blinded_bytes, blinding_factor = blind_token(token, pub1)
        # Sign with a DIFFERENT private key
        blind_sig_int = blind_sign(blinded_bytes, priv2)
        signature = unblind_signature(blind_sig_int, blinding_factor, pub1)

        assert not verify_signature(token, signature, pub1)

    def test_blinding_unlinkability(self, keypair, token):
        """
        Signing the same token with the same key but different blinding factors
        should produce different blind signatures — demonstrating unlinkability.
        """
        private_key, public_key = keypair

        blinded1, r1 = blind_token(token, public_key)
        blinded2, r2 = blind_token(token, public_key)

        # Blinded values differ
        assert blinded1 != blinded2

        blind_sig1 = blind_sign(blinded1, private_key)
        blind_sig2 = blind_sign(blinded2, private_key)

        # Blind signatures differ
        assert blind_sig1 != blind_sig2

        # Both unblind to valid signatures
        sig1 = unblind_signature(blind_sig1, r1, public_key)
        sig2 = unblind_signature(blind_sig2, r2, public_key)

        assert verify_signature(token, sig1, public_key)
        assert verify_signature(token, sig2, public_key)


# ---------------------------------------------------------------------------
# Serialization helpers
# ---------------------------------------------------------------------------

class TestSerialization:
    def test_token_hex_roundtrip(self, token):
        assert hex_to_token(token_to_hex(token)) == token

    def test_int_b64_roundtrip(self):
        n = 2 ** 2047 + 12345678
        assert b64_to_int(int_to_b64(n)) == n

    def test_credential_roundtrip(self, keypair, token):
        private_key, public_key = keypair
        blinded_bytes, blinding_factor = blind_token(token, public_key)
        blind_sig_int = blind_sign(blinded_bytes, private_key)
        sig = unblind_signature(blind_sig_int, blinding_factor, public_key)

        cred = serialize_credential(token, sig)
        assert "token" in cred
        assert "signature" in cred

        token2, sig2 = deserialize_credential(cred)
        assert token2 == token
        assert sig2 == sig

    def test_token_hash_deterministic(self, token):
        h1 = token_hash(token)
        h2 = token_hash(token)
        assert h1 == h2
        assert len(h1) == 64  # SHA-256 hex

    def test_token_hash_different_tokens(self):
        t1, t2 = generate_token(), generate_token()
        assert token_hash(t1) != token_hash(t2)
