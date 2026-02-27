"""
Unit tests for the voter registry module.
"""

import sys
import os
import base64
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

import database
from blind_signature import generate_token, blind_token


@pytest.fixture(autouse=True)
def isolated_db(tmp_path):
    """Each test gets its own SQLite database."""
    database.DB_PATH = tmp_path / "test_registry.db"
    # Reset thread-local connection
    import threading
    database._local = threading.local()
    database.init_db()
    yield
    # Teardown: close connection if open
    if hasattr(database._local, 'conn') and database._local.conn:
        database._local.conn.close()
        database._local.conn = None


@pytest.fixture
def registry(isolated_db):
    from voter_registry import bootstrap, issue_blind_token, voter_status
    bootstrap(demo_voter_ids=["VOTER_001", "VOTER_002", "VOTER_003"])
    return issue_blind_token, voter_status


@pytest.fixture
def public_key(isolated_db, registry):
    from voter_registry import get_public_key
    return get_public_key()


class TestBootstrap:
    def test_keys_generated_on_first_boot(self):
        from voter_registry import bootstrap, get_public_key
        bootstrap()
        pk = get_public_key()
        assert "PUBLIC KEY" in pk

    def test_keys_not_regenerated(self):
        from voter_registry import bootstrap, get_public_key
        bootstrap()
        pk1 = get_public_key()
        bootstrap()
        pk2 = get_public_key()
        assert pk1 == pk2

    def test_eligible_voters_seeded(self):
        from voter_registry import bootstrap
        bootstrap(demo_voter_ids=["V1", "V2", "V3"])
        assert database.is_eligible("V1")
        assert database.is_eligible("V2")
        assert not database.is_eligible("V4")


class TestTokenIssuance:
    def test_issue_token_to_eligible_voter(self, registry, public_key):
        issue_blind_token, voter_status = registry
        token = generate_token()
        blinded_bytes, _ = blind_token(token, public_key)
        blinded_b64 = base64.b64encode(blinded_bytes).decode()

        result = issue_blind_token("VOTER_001", blinded_b64)
        assert result["success"]
        assert "blind_sig_b64" in result

    def test_reject_ineligible_voter(self, registry, public_key):
        issue_blind_token, _ = registry
        token = generate_token()
        blinded_bytes, _ = blind_token(token, public_key)
        blinded_b64 = base64.b64encode(blinded_bytes).decode()

        result = issue_blind_token("NOT_ELIGIBLE", blinded_b64)
        assert not result["success"]
        assert "eligible" in result["error"].lower() or "not found" in result["error"].lower()

    def test_reject_duplicate_registration(self, registry, public_key):
        issue_blind_token, _ = registry

        def make_blinded():
            token = generate_token()
            blinded_bytes, _ = blind_token(token, public_key)
            return base64.b64encode(blinded_bytes).decode()

        # First registration
        r1 = issue_blind_token("VOTER_002", make_blinded())
        assert r1["success"]

        # Second registration with same voter ID
        r2 = issue_blind_token("VOTER_002", make_blinded())
        assert not r2["success"]
        assert "already issued" in r2["error"].lower()

    def test_invalid_base64_rejected(self, registry):
        issue_blind_token, _ = registry
        result = issue_blind_token("VOTER_003", "!!!not-valid-base64!!!")
        assert not result["success"]


class TestVoterStatus:
    def test_status_before_registration(self, registry):
        _, voter_status = registry
        status = voter_status("VOTER_001")
        assert status["eligible"]
        assert not status["token_issued"]
        assert not status["registered"]

    def test_status_after_registration(self, registry, public_key):
        issue_blind_token, voter_status = registry
        token = generate_token()
        blinded_bytes, _ = blind_token(token, public_key)
        blinded_b64 = base64.b64encode(blinded_bytes).decode()
        issue_blind_token("VOTER_001", blinded_b64)

        status = voter_status("VOTER_001")
        assert status["token_issued"]
        assert status["registered"]

    def test_status_unknown_voter(self, registry):
        _, voter_status = registry
        status = voter_status("UNKNOWN")
        assert not status["eligible"]
        assert not status["registered"]
