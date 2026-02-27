"""
Voter Registry — Token Issuance Logic

Orchestrates the registration flow:
  1. Verify voter eligibility
  2. Prevent duplicate registration
  3. Blind-sign the voter's blinded token
  4. Mark voter as registered in the database

The issuer ONLY sees the blinded token — it cannot link the resulting
signed token to any future vote transaction.
"""

import sys
from pathlib import Path

# Ensure backend directory is on path when run standalone
sys.path.insert(0, str(Path(__file__).parent))

from blind_signature import (
    generate_keypair,
    blind_sign,
    int_to_b64,
)
from database import (
    init_db,
    get_issuer_keys,
    store_issuer_keys,
    is_eligible,
    has_token_issued,
    register_voter,
    get_voter_status,
    seed_eligible_voters,
)


def bootstrap(demo_voter_ids: list = None):
    """
    Initialize the database, generate issuer keys, and optionally
    seed a list of eligible voter IDs for demo purposes.
    """
    init_db()

    # Generate keys only if they don't exist yet
    private_key, public_key = get_issuer_keys()
    if private_key is None:
        print("[registry] Generating RSA keypair...")
        private_key, public_key = generate_keypair()
        store_issuer_keys(private_key, public_key)
        print("[registry] RSA keypair stored.")
    else:
        print("[registry] Issuer keys already exist.")

    # Seed demo voters
    if demo_voter_ids:
        seed_eligible_voters(demo_voter_ids)
        print(f"[registry] Seeded {len(demo_voter_ids)} eligible voters.")

    return public_key


def get_public_key() -> str:
    """Return the issuer's public key PEM."""
    _, public_key = get_issuer_keys()
    if public_key is None:
        raise RuntimeError("Issuer keys not initialized. Run bootstrap() first.")
    return public_key


def issue_blind_token(voter_id: str, blinded_token_b64: str) -> dict:
    """
    Issue a blind signature for an eligible, unregistered voter.

    Parameters
    ----------
    voter_id : str
        The voter's identity (e.g. "VOTER_12345")
    blinded_token_b64 : str
        The voter's blinded token as base64 (produced client-side via blind_token())

    Returns
    -------
    dict with keys:
        success       : bool
        blind_sig_b64 : str (only on success) — blind signature as base64
        error         : str (only on failure)
    """
    # --- Eligibility check ---
    if not is_eligible(voter_id):
        return {"success": False, "error": "Voter ID not found in eligible voters list"}

    # --- Duplicate registration check ---
    if has_token_issued(voter_id):
        return {"success": False, "error": "Token already issued to this voter"}

    # --- Retrieve issuer private key ---
    private_key, _ = get_issuer_keys()
    if private_key is None:
        return {"success": False, "error": "Issuer not initialized"}

    # --- Blind-sign the blinded token ---
    import base64 as _b64
    try:
        blinded_bytes = _b64.b64decode(blinded_token_b64)
    except Exception:
        return {"success": False, "error": "Invalid base64 encoding for blinded token"}

    blind_sig_int = blind_sign(blinded_bytes, private_key)
    blind_sig_b64 = int_to_b64(blind_sig_int)

    # --- Mark voter as registered (atomic in SQLite) ---
    register_voter(voter_id)

    return {"success": True, "blind_sig_b64": blind_sig_b64}


def voter_status(voter_id: str) -> dict:
    """Return registration status for a voter."""
    return get_voter_status(voter_id)
