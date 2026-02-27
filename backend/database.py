"""
Voter Registry Database

Uses SQLite to track voter eligibility and token-issuance status.
This is the permissioned identity layer — it knows WHO voted (got a token),
but never records WHAT they voted for.
"""

import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path

DB_PATH = Path(__file__).parent / "voter_registry.db"

# Thread-local connection cache
_local = threading.local()


def get_connection() -> sqlite3.Connection:
    if not hasattr(_local, "conn") or _local.conn is None:
        _local.conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        _local.conn.row_factory = sqlite3.Row
        _local.conn.execute("PRAGMA journal_mode=WAL")
        _local.conn.execute("PRAGMA foreign_keys=ON")
    return _local.conn


@contextmanager
def get_db():
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def init_db():
    """Create tables if they do not exist."""
    with get_db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS voters (
                voter_id        TEXT PRIMARY KEY,
                registered_at   TEXT NOT NULL DEFAULT (datetime('now')),
                token_issued    INTEGER NOT NULL DEFAULT 0,
                token_issued_at TEXT
            );

            CREATE TABLE IF NOT EXISTS issuer_keys (
                id          INTEGER PRIMARY KEY CHECK (id = 1),
                private_key TEXT NOT NULL,
                public_key  TEXT NOT NULL,
                created_at  TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS eligible_voters (
                voter_id    TEXT PRIMARY KEY,
                name        TEXT
            );
        """)


# ---------------------------------------------------------------------------
# Voter operations
# ---------------------------------------------------------------------------

def seed_eligible_voters(voter_ids: list):
    """Pre-populate the eligible voters list (admin operation)."""
    with get_db() as conn:
        conn.executemany(
            "INSERT OR IGNORE INTO eligible_voters (voter_id) VALUES (?)",
            [(vid,) for vid in voter_ids],
        )


def is_eligible(voter_id: str) -> bool:
    with get_db() as conn:
        row = conn.execute(
            "SELECT voter_id FROM eligible_voters WHERE voter_id = ?", (voter_id,)
        ).fetchone()
        return row is not None


def has_token_issued(voter_id: str) -> bool:
    with get_db() as conn:
        row = conn.execute(
            "SELECT token_issued FROM voters WHERE voter_id = ?", (voter_id,)
        ).fetchone()
        if row is None:
            return False
        return bool(row["token_issued"])


def register_voter(voter_id: str):
    """Record that a voter has been issued a token (mark them as registered)."""
    with get_db() as conn:
        conn.execute(
            """INSERT INTO voters (voter_id, token_issued, token_issued_at)
               VALUES (?, 1, datetime('now'))
               ON CONFLICT(voter_id) DO UPDATE
               SET token_issued=1, token_issued_at=datetime('now')
               WHERE token_issued=0""",
            (voter_id,),
        )


def get_voter_status(voter_id: str) -> dict:
    """Return the registration status for a voter."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT voter_id, registered_at, token_issued, token_issued_at "
            "FROM voters WHERE voter_id = ?",
            (voter_id,),
        ).fetchone()
        if row is None:
            eligible = is_eligible(voter_id)
            return {
                "voter_id": voter_id,
                "eligible": eligible,
                "registered": False,
                "token_issued": False,
            }
        return {
            "voter_id": row["voter_id"],
            "eligible": True,
            "registered": True,
            "token_issued": bool(row["token_issued"]),
            "registered_at": row["registered_at"],
            "token_issued_at": row["token_issued_at"],
        }


# ---------------------------------------------------------------------------
# Issuer key operations
# ---------------------------------------------------------------------------

def store_issuer_keys(private_key: str, public_key: str):
    with get_db() as conn:
        conn.execute(
            """INSERT INTO issuer_keys (id, private_key, public_key)
               VALUES (1, ?, ?)
               ON CONFLICT(id) DO UPDATE
               SET private_key=excluded.private_key,
                   public_key=excluded.public_key,
                   created_at=datetime('now')""",
            (private_key, public_key),
        )


def get_issuer_keys() -> tuple:
    """Return (private_key_pem, public_key_pem) or (None, None)."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT private_key, public_key FROM issuer_keys WHERE id=1"
        ).fetchone()
        if row is None:
            return None, None
        return row["private_key"], row["public_key"]
