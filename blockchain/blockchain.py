"""
Anonymous Ballot Blockchain

A simple proof-of-authority blockchain that records anonymous votes.
Each block contains a batch of votes. The chain is publicly auditable.

Key properties:
- Votes are stored with a token-hash (not the voter ID)
- Used token hashes are tracked in a spent-set to prevent double-voting
- No voter identity information is stored on the chain
"""

import hashlib
import json
import time
import threading
from pathlib import Path
from typing import Optional

CHAIN_FILE = Path(__file__).parent / "chain.json"
CANDIDATES = ["Candidate A", "Candidate B", "Candidate C"]


class Block:
    def __init__(
        self,
        index: int,
        timestamp: float,
        votes: list,
        previous_hash: str,
        nonce: int = 0,
    ):
        self.index = index
        self.timestamp = timestamp
        self.votes = votes  # list of {"token_hash": str, "candidate": str}
        self.previous_hash = previous_hash
        self.nonce = nonce
        self.hash = self._compute_hash()

    def _compute_hash(self) -> str:
        content = json.dumps(
            {
                "index": self.index,
                "timestamp": self.timestamp,
                "votes": self.votes,
                "previous_hash": self.previous_hash,
                "nonce": self.nonce,
            },
            sort_keys=True,
        )
        return hashlib.sha256(content.encode()).hexdigest()

    def to_dict(self) -> dict:
        return {
            "index": self.index,
            "timestamp": self.timestamp,
            "votes": self.votes,
            "previous_hash": self.previous_hash,
            "nonce": self.nonce,
            "hash": self.hash,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Block":
        b = cls(
            index=data["index"],
            timestamp=data["timestamp"],
            votes=data["votes"],
            previous_hash=data["previous_hash"],
            nonce=data["nonce"],
        )
        b.hash = data["hash"]
        return b


class Blockchain:
    DIFFICULTY = 2  # PoW difficulty (leading zeros in hex)

    def __init__(self):
        self._lock = threading.Lock()
        self.chain: list[Block] = []
        self.pending_votes: list[dict] = []
        self.spent_tokens: set[str] = set()
        self._load_or_init()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _load_or_init(self):
        if CHAIN_FILE.exists():
            try:
                with open(CHAIN_FILE) as f:
                    data = json.load(f)
                self.chain = [Block.from_dict(b) for b in data["chain"]]
                self.spent_tokens = set(data.get("spent_tokens", []))
                if not self._is_valid():
                    raise ValueError("Loaded chain is invalid — reinitializing")
                return
            except Exception as e:
                print(f"[blockchain] Warning: could not load chain ({e}), reinitializing")

        # Create genesis block
        genesis = Block(
            index=0,
            timestamp=time.time(),
            votes=[],
            previous_hash="0" * 64,
        )
        self.chain = [genesis]
        self._save()

    def _save(self):
        CHAIN_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(CHAIN_FILE, "w") as f:
            json.dump(
                {
                    "chain": [b.to_dict() for b in self.chain],
                    "spent_tokens": list(self.spent_tokens),
                },
                f,
                indent=2,
            )

    # ------------------------------------------------------------------
    # Core operations
    # ------------------------------------------------------------------

    def _proof_of_work(self, block: Block) -> Block:
        """Mine the block until its hash starts with DIFFICULTY leading zeros."""
        prefix = "0" * self.DIFFICULTY
        while not block.hash.startswith(prefix):
            block.nonce += 1
            block.hash = block._compute_hash()
        return block

    def cast_vote(self, token_hash: str, candidate: str, signature_hex: str) -> dict:
        """
        Record an anonymous vote on the blockchain.

        Returns a dict with { success, tx_hash, block_index, error }.
        """
        with self._lock:
            # Validate candidate
            if candidate not in CANDIDATES:
                return {"success": False, "error": f"Invalid candidate. Choose from: {CANDIDATES}"}

            # Prevent double-voting
            if token_hash in self.spent_tokens:
                return {"success": False, "error": "Token already used — double-voting prevented"}

            # Mark token as spent
            self.spent_tokens.add(token_hash)

            # Add vote to pending
            vote_record = {
                "token_hash": token_hash,
                "candidate": candidate,
                "timestamp": time.time(),
                "signature": signature_hex,
            }
            self.pending_votes.append(vote_record)

            # Mine a new block for every vote (simple PoA-style — one vote per block)
            block = Block(
                index=len(self.chain),
                timestamp=time.time(),
                votes=[vote_record],
                previous_hash=self.chain[-1].hash,
            )
            block = self._proof_of_work(block)
            self.chain.append(block)
            self.pending_votes.clear()
            self._save()

            return {
                "success": True,
                "tx_hash": block.hash,
                "block_index": block.index,
            }

    def is_token_spent(self, token_hash: str) -> bool:
        with self._lock:
            return token_hash in self.spent_tokens

    # ------------------------------------------------------------------
    # Query / audit
    # ------------------------------------------------------------------

    def get_tallies(self) -> dict:
        """Count votes for each candidate across the entire chain."""
        tallies = {c: 0 for c in CANDIDATES}
        with self._lock:
            for block in self.chain[1:]:  # skip genesis
                for vote in block.votes:
                    candidate = vote.get("candidate")
                    if candidate in tallies:
                        tallies[candidate] += 1
        return tallies

    def get_chain(self) -> list:
        with self._lock:
            return [b.to_dict() for b in self.chain]

    def get_block(self, index: int) -> Optional[dict]:
        with self._lock:
            if 0 <= index < len(self.chain):
                return self.chain[index].to_dict()
            return None

    def get_stats(self) -> dict:
        with self._lock:
            total_votes = sum(len(b.votes) for b in self.chain[1:])
            return {
                "block_count": len(self.chain),
                "total_votes": total_votes,
                "spent_tokens": len(self.spent_tokens),
                "candidates": CANDIDATES,
            }

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def _is_valid(self) -> bool:
        """Verify chain integrity."""
        for i in range(1, len(self.chain)):
            current = self.chain[i]
            previous = self.chain[i - 1]

            if current.hash != current._compute_hash():
                return False
            if current.previous_hash != previous.hash:
                return False
        return True

    def verify_chain(self) -> dict:
        """Public method for chain verification (audit tool)."""
        with self._lock:
            valid = self._is_valid()
            return {
                "valid": valid,
                "block_count": len(self.chain),
                "message": "Chain integrity verified" if valid else "Chain integrity FAILED",
            }


# Singleton instance shared across the application
_blockchain_instance: Optional[Blockchain] = None
_blockchain_lock = threading.Lock()


def get_blockchain() -> Blockchain:
    global _blockchain_instance
    if _blockchain_instance is None:
        with _blockchain_lock:
            if _blockchain_instance is None:
                _blockchain_instance = Blockchain()
    return _blockchain_instance
