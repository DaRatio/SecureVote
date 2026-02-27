"""
Integration tests for the Flask API using a test client.
"""

import sys
import os
import json
import base64
import tempfile
import pytest

# Ensure paths are correct
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'blockchain'))

import database
import blockchain as bc_module
from blind_signature import (
    generate_keypair,
    generate_token,
    blind_token,
    blind_sign,
    unblind_signature,
    verify_signature,
    serialize_credential,
    int_to_b64,
    token_to_hex,
)


@pytest.fixture(scope="module")
def app_client(tmp_path_factory):
    """Create a Flask test client with isolated DB and chain."""
    tmp = tmp_path_factory.mktemp("securevote_test")

    # Patch DB path
    database.DB_PATH = tmp / "test_registry.db"
    database._local = type('Local', (), {})()  # reset thread-local

    # Patch blockchain file
    bc_module.CHAIN_FILE = tmp / "test_chain.json"
    bc_module._blockchain_instance = None

    import api as api_module
    api_module.DEMO_VOTERS = [f"VOTER_{i:05d}" for i in range(1, 11)]
    api_module.initialize()

    api_module.app.config["TESTING"] = True
    with api_module.app.test_client() as client:
        yield client


# ---------------------------------------------------------------------------
# Health / setup
# ---------------------------------------------------------------------------

def test_health(app_client):
    r = app_client.get('/api/health')
    assert r.status_code == 200
    data = r.get_json()
    assert data["status"] == "ok"


def test_public_key(app_client):
    r = app_client.get('/api/public-key')
    assert r.status_code == 200
    pk = r.get_json()["public_key"]
    assert "PUBLIC KEY" in pk


def test_candidates(app_client):
    r = app_client.get('/api/candidates')
    assert r.status_code == 200
    candidates = r.get_json()["candidates"]
    assert len(candidates) >= 2


# ---------------------------------------------------------------------------
# Registration flow
# ---------------------------------------------------------------------------

def _get_public_key(client):
    return client.get('/api/public-key').get_json()["public_key"]


def _register(client, voter_id):
    """Full registration flow: blind → register → return (token, sig)."""
    public_key = _get_public_key(client)
    token = generate_token()
    blinded_bytes, blinding_factor = blind_token(token, public_key)
    blinded_b64 = base64.b64encode(blinded_bytes).decode()

    r = client.post('/api/register', json={
        "voter_id": voter_id,
        "blinded_token_b64": blinded_b64,
    })
    data = r.get_json()
    if not data.get("success"):
        return None, None, None, data

    blind_sig_b64 = data["blind_sig_b64"]
    from blind_signature import b64_to_int
    blind_sig_int = b64_to_int(blind_sig_b64)
    signature = unblind_signature(blind_sig_int, blinding_factor, public_key)

    return token, signature, public_key, data


class TestRegistration:
    def test_register_eligible_voter(self, app_client):
        token, sig, pk, data = _register(app_client, "VOTER_00001")
        assert data["success"]
        assert "blind_sig_b64" in data

        # Verify the returned signature is cryptographically valid
        assert verify_signature(token, sig, pk)

    def test_register_duplicate_voter(self, app_client):
        _register(app_client, "VOTER_00002")
        _, _, _, data = _register(app_client, "VOTER_00002")
        assert not data["success"]
        assert "already issued" in data["error"].lower() or "already" in data["error"].lower()

    def test_register_ineligible_voter(self, app_client):
        r = app_client.post('/api/register', json={
            "voter_id": "NOT_A_VOTER",
            "blinded_token_b64": base64.b64encode(b"\x00" * 256).decode(),
        })
        data = r.get_json()
        assert not data["success"]
        assert "eligible" in data["error"].lower() or "not found" in data["error"].lower()

    def test_register_missing_fields(self, app_client):
        r = app_client.post('/api/register', json={"voter_id": "VOTER_00003"})
        assert r.status_code == 400

    def test_register_invalid_voter_id_format(self, app_client):
        r = app_client.post('/api/register', json={
            "voter_id": "VOTER; DROP TABLE voters;--",
            "blinded_token_b64": base64.b64encode(b"\x01" * 256).decode(),
        })
        assert r.status_code == 400


class TestVoterStatus:
    def test_status_unregistered_eligible(self, app_client):
        r = app_client.get('/api/voter/VOTER_00004/status')
        data = r.get_json()
        assert data["eligible"]
        assert not data.get("token_issued", False)

    def test_status_registered(self, app_client):
        _register(app_client, "VOTER_00005")
        r = app_client.get('/api/voter/VOTER_00005/status')
        data = r.get_json()
        assert data["token_issued"]

    def test_status_unknown_voter(self, app_client):
        r = app_client.get('/api/voter/UNKNOWN_VOTER/status')
        data = r.get_json()
        assert not data.get("eligible", True)


# ---------------------------------------------------------------------------
# Voting flow
# ---------------------------------------------------------------------------

class TestVoting:
    def test_cast_valid_vote(self, app_client):
        token, sig, pk, reg_data = _register(app_client, "VOTER_00006")
        assert reg_data["success"]

        cred = serialize_credential(token, sig)
        candidates = app_client.get('/api/candidates').get_json()["candidates"]

        r = app_client.post('/api/vote', json={
            "token_hex": cred["token"],
            "signature_b64": cred["signature"],
            "candidate": candidates[0],
        })
        data = r.get_json()
        assert data["success"]
        assert "tx_hash" in data
        assert data["block_index"] >= 1

    def test_double_vote_prevented(self, app_client):
        token, sig, pk, reg_data = _register(app_client, "VOTER_00007")
        cred = serialize_credential(token, sig)
        candidates = app_client.get('/api/candidates').get_json()["candidates"]

        r1 = app_client.post('/api/vote', json={
            "token_hex": cred["token"],
            "signature_b64": cred["signature"],
            "candidate": candidates[0],
        })
        assert r1.get_json()["success"]

        r2 = app_client.post('/api/vote', json={
            "token_hex": cred["token"],
            "signature_b64": cred["signature"],
            "candidate": candidates[1],
        })
        data2 = r2.get_json()
        assert not data2["success"]
        assert "already used" in data2["error"].lower()

    def test_vote_invalid_signature(self, app_client):
        token = generate_token()
        fake_sig = int_to_b64(12345)  # garbage signature

        r = app_client.post('/api/vote', json={
            "token_hex": token_to_hex(token),
            "signature_b64": fake_sig,
            "candidate": bc_module.CANDIDATES[0],
        })
        assert r.status_code == 403

    def test_vote_invalid_candidate(self, app_client):
        token, sig, pk, reg_data = _register(app_client, "VOTER_00008")
        cred = serialize_credential(token, sig)

        r = app_client.post('/api/vote', json={
            "token_hex": cred["token"],
            "signature_b64": cred["signature"],
            "candidate": "NotACandidate",
        })
        assert r.status_code == 400

    def test_vote_missing_fields(self, app_client):
        r = app_client.post('/api/vote', json={"candidate": bc_module.CANDIDATES[0]})
        assert r.status_code == 400


# ---------------------------------------------------------------------------
# Results & blockchain
# ---------------------------------------------------------------------------

class TestResultsAndBlockchain:
    def test_results_endpoint(self, app_client):
        r = app_client.get('/api/results')
        assert r.status_code == 200
        data = r.get_json()
        assert "tallies" in data
        assert "stats" in data

    def test_tallies_match_votes_cast(self, app_client):
        # Cast a vote and confirm tallies increment
        token, sig, pk, reg_data = _register(app_client, "VOTER_00009")
        cred = serialize_credential(token, sig)
        candidates = app_client.get('/api/candidates').get_json()["candidates"]
        candidate = candidates[0]

        before = app_client.get('/api/results').get_json()["tallies"][candidate]
        app_client.post('/api/vote', json={
            "token_hex": cred["token"],
            "signature_b64": cred["signature"],
            "candidate": candidate,
        })
        after = app_client.get('/api/results').get_json()["tallies"][candidate]
        assert after == before + 1

    def test_blockchain_endpoint(self, app_client):
        r = app_client.get('/api/blockchain')
        assert r.status_code == 200
        data = r.get_json()
        assert isinstance(data["chain"], list)
        # Genesis block always present
        assert data["chain"][0]["index"] == 0

    def test_blockchain_verify(self, app_client):
        r = app_client.get('/api/blockchain/verify')
        assert r.status_code == 200
        data = r.get_json()
        assert data["valid"]

    def test_block_lookup(self, app_client):
        r = app_client.get('/api/blockchain/0')
        assert r.status_code == 200
        data = r.get_json()
        assert data["index"] == 0

    def test_block_not_found(self, app_client):
        r = app_client.get('/api/blockchain/9999')
        assert r.status_code == 404

    def test_stats_endpoint(self, app_client):
        r = app_client.get('/api/stats')
        assert r.status_code == 200
        data = r.get_json()
        assert "total_votes" in data
        assert "block_count" in data
