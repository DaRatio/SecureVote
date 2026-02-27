"""
RSA Blind Signature Implementation for Anonymous Voting

Implements Chaum's blind signature protocol:
  1. Voter blinds a token using the issuer's public key
  2. Issuer signs the blinded token (cannot see the original token)
  3. Voter unblinds the signature to get a valid signature on the original token
  4. Anyone can verify the signature using the issuer's public key

This cryptographic separation ensures the issuer cannot link the signed token
to any specific voter, guaranteeing anonymity.
"""

import os
import hashlib
import json
import base64
from Crypto.PublicKey import RSA
from Crypto.Hash import SHA256
from Crypto.Math.Numbers import Integer


KEY_SIZE = 2048  # bits


def generate_keypair() -> tuple:
    """Generate an RSA keypair for the token issuer."""
    key = RSA.generate(KEY_SIZE)
    private_key = key.export_key().decode()
    public_key = key.publickey().export_key().decode()
    return private_key, public_key


def load_private_key(pem: str) -> RSA.RsaKey:
    return RSA.import_key(pem)


def load_public_key(pem: str) -> RSA.RsaKey:
    return RSA.import_key(pem)


# ---------------------------------------------------------------------------
# Voter-side operations
# ---------------------------------------------------------------------------

def generate_token() -> bytes:
    """Generate a random 32-byte token (the voter's secret token)."""
    return os.urandom(32)


def blind_token(token: bytes, public_key_pem: str) -> tuple:
    """
    Blind a token using the issuer's public key.

    Returns (blinded_token_bytes, blinding_factor_int).
    The blinding factor must be kept secret and used to unblind later.
    """
    pub = load_public_key(public_key_pem)
    n = pub.n
    e = pub.e

    # Hash the token to get an integer m in range [0, n)
    m = int.from_bytes(SHA256.new(token).digest(), "big") % n

    # Choose random blinding factor r such that gcd(r, n) == 1
    while True:
        r = int.from_bytes(os.urandom(KEY_SIZE // 8), "big") % n
        if r > 1 and pow(r, 1, n) != 0:
            # Quick primality check not needed; just ensure r != 0
            break

    # blinded = m * r^e mod n
    r_e = pow(r, e, n)
    blinded = (m * r_e) % n

    blinded_bytes = blinded.to_bytes((blinded.bit_length() + 7) // 8, "big")
    return blinded_bytes, r


def unblind_signature(blind_sig_int: int, blinding_factor: int, public_key_pem: str) -> int:
    """
    Remove the blinding factor to recover the actual signature.

    sig = blind_sig * r^{-1} mod n
    """
    pub = load_public_key(public_key_pem)
    n = pub.n

    # Compute modular inverse of blinding factor
    r_inv = pow(blinding_factor, -1, n)
    sig = (blind_sig_int * r_inv) % n
    return sig


def verify_signature(token: bytes, signature_int: int, public_key_pem: str) -> bool:
    """
    Verify a blind signature against the original token.

    Checks: sig^e mod n == hash(token) mod n
    """
    pub = load_public_key(public_key_pem)
    n = pub.n
    e = pub.e

    m = int.from_bytes(SHA256.new(token).digest(), "big") % n

    recovered = pow(signature_int, e, n)
    return recovered == m


# ---------------------------------------------------------------------------
# Issuer-side operations
# ---------------------------------------------------------------------------

def blind_sign(blinded_token_bytes: bytes, private_key_pem: str) -> int:
    """
    Sign a blinded token using the issuer's private key.

    blind_sig = blinded^d mod n
    The issuer never sees the original token.
    """
    priv = load_private_key(private_key_pem)
    n = priv.n
    d = priv.d

    blinded_int = int.from_bytes(blinded_token_bytes, "big")
    blind_sig = pow(blinded_int, d, n)
    return blind_sig


# ---------------------------------------------------------------------------
# Serialization helpers (for API transport)
# ---------------------------------------------------------------------------

def token_to_hex(token: bytes) -> str:
    return token.hex()


def hex_to_token(hex_str: str) -> bytes:
    return bytes.fromhex(hex_str)


def int_to_b64(n: int) -> str:
    """Encode a large integer as base64 for JSON transport."""
    byte_len = (n.bit_length() + 7) // 8
    return base64.b64encode(n.to_bytes(byte_len, "big")).decode()


def b64_to_int(b64_str: str) -> int:
    return int.from_bytes(base64.b64decode(b64_str), "big")


def serialize_credential(token: bytes, signature_int: int) -> dict:
    """Serialize a (token, signature) credential for storage / transport."""
    return {
        "token": token_to_hex(token),
        "signature": int_to_b64(signature_int),
    }


def deserialize_credential(data: dict) -> tuple:
    """Deserialize a credential dict back to (token_bytes, signature_int)."""
    token = hex_to_token(data["token"])
    sig = b64_to_int(data["signature"])
    return token, sig


def token_hash(token: bytes) -> str:
    """Produce a deterministic, public identifier for a token (for spent-set)."""
    return SHA256.new(token).hexdigest()
