"""
Unit tests for the custom blockchain module.
"""

import sys
import os
import time
import json
import tempfile
import pytest

# Point at the blockchain directory
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'blockchain'))

# We need to override CHAIN_FILE so tests don't touch the real chain
import blockchain as bc_module


@pytest.fixture(autouse=True)
def isolated_chain(tmp_path):
    """Each test gets its own chain file and a fresh Blockchain instance."""
    chain_file = tmp_path / "chain.json"
    # Patch module-level CHAIN_FILE
    original = bc_module.CHAIN_FILE
    bc_module.CHAIN_FILE = chain_file
    # Reset singleton
    bc_module._blockchain_instance = None
    yield
    bc_module.CHAIN_FILE = original
    bc_module._blockchain_instance = None


from blockchain import Blockchain, Block, get_blockchain, CANDIDATES


class TestBlock:
    def test_hash_is_deterministic(self):
        b = Block(0, 1234567890.0, [], "0" * 64)
        h1 = b._compute_hash()
        h2 = b._compute_hash()
        assert h1 == h2

    def test_roundtrip(self):
        b = Block(1, time.time(), [{"token_hash": "abc", "candidate": "X"}], "dead" * 16)
        d = b.to_dict()
        b2 = Block.from_dict(d)
        assert b2.index == b.index
        assert b2.hash == b.hash
        assert b2.votes == b.votes


class TestBlockchain:
    def test_genesis_block_created(self):
        chain = Blockchain()
        assert len(chain.chain) == 1
        assert chain.chain[0].index == 0
        assert chain.chain[0].previous_hash == "0" * 64

    def test_cast_vote_success(self):
        chain = Blockchain()
        result = chain.cast_vote("token_hash_1", CANDIDATES[0], "sig_hex")
        assert result["success"]
        assert "tx_hash" in result
        assert result["block_index"] == 1

    def test_cast_vote_invalid_candidate(self):
        chain = Blockchain()
        result = chain.cast_vote("token_hash_x", "NotACandidate", "sig")
        assert not result["success"]
        assert "Invalid candidate" in result["error"]

    def test_double_voting_prevented(self):
        chain = Blockchain()
        chain.cast_vote("token_hash_dup", CANDIDATES[0], "sig1")
        result2 = chain.cast_vote("token_hash_dup", CANDIDATES[1], "sig2")
        assert not result2["success"]
        assert "already used" in result2["error"]

    def test_tallies_accurate(self):
        chain = Blockchain()
        chain.cast_vote("t1", CANDIDATES[0], "s")
        chain.cast_vote("t2", CANDIDATES[0], "s")
        chain.cast_vote("t3", CANDIDATES[1], "s")

        tallies = chain.get_tallies()
        assert tallies[CANDIDATES[0]] == 2
        assert tallies[CANDIDATES[1]] == 1
        assert tallies[CANDIDATES[2]] == 0

    def test_chain_grows_with_each_vote(self):
        chain = Blockchain()
        assert len(chain.chain) == 1  # genesis
        chain.cast_vote("t1", CANDIDATES[0], "s")
        assert len(chain.chain) == 2
        chain.cast_vote("t2", CANDIDATES[1], "s")
        assert len(chain.chain) == 3

    def test_chain_validation(self):
        chain = Blockchain()
        chain.cast_vote("t1", CANDIDATES[0], "s")
        chain.cast_vote("t2", CANDIDATES[1], "s")
        result = chain.verify_chain()
        assert result["valid"]

    def test_tampered_chain_fails_validation(self):
        chain = Blockchain()
        chain.cast_vote("t1", CANDIDATES[0], "s")
        # Tamper with a vote directly
        chain.chain[1].votes[0]["candidate"] = CANDIDATES[2]
        result = chain.verify_chain()
        assert not result["valid"]

    def test_is_token_spent(self):
        chain = Blockchain()
        assert not chain.is_token_spent("new_token")
        chain.cast_vote("new_token", CANDIDATES[0], "s")
        assert chain.is_token_spent("new_token")

    def test_get_stats(self):
        chain = Blockchain()
        chain.cast_vote("t1", CANDIDATES[0], "s")
        chain.cast_vote("t2", CANDIDATES[0], "s")
        stats = chain.get_stats()
        assert stats["total_votes"] == 2
        assert stats["block_count"] == 3
        assert stats["spent_tokens"] == 2

    def test_get_block(self):
        chain = Blockchain()
        genesis = chain.get_block(0)
        assert genesis is not None
        assert genesis["index"] == 0

    def test_get_block_out_of_range(self):
        chain = Blockchain()
        assert chain.get_block(99) is None

    def test_chain_persistence(self, tmp_path):
        chain_file = tmp_path / "persist_chain.json"
        bc_module.CHAIN_FILE = chain_file

        chain1 = Blockchain()
        chain1.cast_vote("persistent_token", CANDIDATES[0], "s")

        # Re-create blockchain from the same file
        chain2 = Blockchain()
        assert len(chain2.chain) == 2
        assert chain2.is_token_spent("persistent_token")
        assert chain2.get_tallies()[CANDIDATES[0]] == 1

    def test_proof_of_work(self):
        chain = Blockchain()
        chain.cast_vote("t_pow", CANDIDATES[0], "s")
        block = chain.chain[1]
        prefix = "0" * chain.DIFFICULTY
        assert block.hash.startswith(prefix)
