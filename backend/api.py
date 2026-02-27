"""
SecureVote REST API

Two logically separated services running on the same Flask app:

  Identity Layer (voter registry):
    POST /api/register          — Register voter and get blind signature
    GET  /api/voter/<id>/status — Check registration status
    GET  /api/public-key        — Retrieve issuer public key
    POST /api/verify-token      — Verify an unblinded credential (test helper)

  Anonymous Ballot Layer (blockchain):
    POST /api/vote              — Cast an anonymous vote
    GET  /api/results           — Get current vote tallies
    GET  /api/blockchain        — Get full blockchain (for auditing)
    GET  /api/blockchain/<idx>  — Get a specific block
    GET  /api/blockchain/verify — Verify chain integrity
    GET  /api/stats             — System statistics
"""

import sys
import os
from pathlib import Path

# Allow importing siblings
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "blockchain"))

from flask import Flask, request, jsonify, send_from_directory, render_template
from flask_cors import CORS

from voter_registry import bootstrap, get_public_key, issue_blind_token, voter_status
from blind_signature import (
    verify_signature,
    hex_to_token,
    b64_to_int,
    token_hash,
)
from blockchain import get_blockchain, CANDIDATES

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

TEMPLATE_DIR = Path(__file__).parent.parent / "frontend" / "templates"
STATIC_DIR = Path(__file__).parent.parent / "frontend" / "static"

app = Flask(
    __name__,
    template_folder=str(TEMPLATE_DIR),
    static_folder=str(STATIC_DIR),
)
CORS(app)

# Demo voters seeded on startup
DEMO_VOTERS = [f"VOTER_{i:05d}" for i in range(1, 51)]


# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------

def initialize():
    bootstrap(demo_voter_ids=DEMO_VOTERS)
    # Warm up blockchain singleton
    get_blockchain()
    print("[api] SecureVote initialized and ready.")


# ---------------------------------------------------------------------------
# Frontend routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/register")
def register_page():
    return render_template("register.html")


@app.route("/vote")
def vote_page():
    return render_template("vote.html")


@app.route("/results")
def results_page():
    return render_template("results.html")


@app.route("/verify")
def verify_page():
    return render_template("verify.html")


# ---------------------------------------------------------------------------
# Identity Layer API
# ---------------------------------------------------------------------------

@app.route("/api/register", methods=["POST"])
def api_register():
    """
    Register a voter and issue a blind signature.

    Request JSON:
      { "voter_id": str, "blinded_token_b64": str }

    Response JSON (success):
      { "success": true, "blind_sig_b64": str }

    Response JSON (failure):
      { "success": false, "error": str }
    """
    data = request.get_json(silent=True) or {}
    voter_id = str(data.get("voter_id", "")).strip()
    blinded_token_b64 = str(data.get("blinded_token_b64", "")).strip()

    if not voter_id or not blinded_token_b64:
        return jsonify({"success": False, "error": "voter_id and blinded_token_b64 are required"}), 400

    # Sanitize voter_id — only alphanumeric and underscores
    if not all(c.isalnum() or c == "_" for c in voter_id):
        return jsonify({"success": False, "error": "Invalid voter_id format"}), 400

    result = issue_blind_token(voter_id, blinded_token_b64)
    status_code = 200 if result["success"] else 400
    return jsonify(result), status_code


@app.route("/api/voter/<voter_id>/status", methods=["GET"])
def api_voter_status(voter_id: str):
    """Return registration status for a voter."""
    if not all(c.isalnum() or c == "_" for c in voter_id):
        return jsonify({"error": "Invalid voter_id format"}), 400
    return jsonify(voter_status(voter_id))


@app.route("/api/public-key", methods=["GET"])
def api_public_key():
    """Return the issuer's public key (PEM format)."""
    try:
        pk = get_public_key()
        return jsonify({"public_key": pk})
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 503


@app.route("/api/verify-token", methods=["POST"])
def api_verify_token():
    """
    Test helper: verify that an unblinded credential is valid.

    Request JSON:
      { "token_hex": str, "signature_b64": str }
    """
    data = request.get_json(silent=True) or {}
    token_hex = str(data.get("token_hex", "")).strip()
    sig_b64 = str(data.get("signature_b64", "")).strip()

    if not token_hex or not sig_b64:
        return jsonify({"valid": False, "error": "token_hex and signature_b64 are required"}), 400

    try:
        token_bytes = hex_to_token(token_hex)
        sig_int = b64_to_int(sig_b64)
        pk = get_public_key()
        valid = verify_signature(token_bytes, sig_int, pk)
        return jsonify({"valid": valid})
    except Exception as e:
        return jsonify({"valid": False, "error": str(e)}), 400


# ---------------------------------------------------------------------------
# Anonymous Ballot Layer API
# ---------------------------------------------------------------------------

@app.route("/api/vote", methods=["POST"])
def api_vote():
    """
    Cast an anonymous vote.

    Request JSON:
      {
        "token_hex":     str,   # the voter's original random token (hex)
        "signature_b64": str,   # the unblinded RSA signature (base64)
        "candidate":     str    # name of the candidate
      }

    Response JSON (success):
      { "success": true, "tx_hash": str, "block_index": int }

    Response JSON (failure):
      { "success": false, "error": str }
    """
    data = request.get_json(silent=True) or {}
    token_hex = str(data.get("token_hex", "")).strip()
    sig_b64 = str(data.get("signature_b64", "")).strip()
    candidate = str(data.get("candidate", "")).strip()

    if not token_hex or not sig_b64 or not candidate:
        return jsonify({"success": False, "error": "token_hex, signature_b64, and candidate are required"}), 400

    # Validate candidate against whitelist
    if candidate not in CANDIDATES:
        return jsonify({"success": False, "error": f"Invalid candidate. Choose from: {CANDIDATES}"}), 400

    # Verify the blind signature against the token
    try:
        token_bytes = hex_to_token(token_hex)
        sig_int = b64_to_int(sig_b64)
        pk = get_public_key()
    except Exception as e:
        return jsonify({"success": False, "error": f"Malformed credential: {e}"}), 400

    if not verify_signature(token_bytes, sig_int, pk):
        return jsonify({"success": False, "error": "Invalid token signature — credential rejected"}), 403

    # Compute token hash (public identifier, no link to voter ID)
    th = token_hash(token_bytes)

    # Cast vote on the blockchain
    bc = get_blockchain()
    result = bc.cast_vote(
        token_hash=th,
        candidate=candidate,
        signature_hex=sig_b64[:64],  # store first 64 chars for audit
    )

    status_code = 200 if result["success"] else 400
    return jsonify(result), status_code


@app.route("/api/results", methods=["GET"])
def api_results():
    """Return current vote tallies."""
    bc = get_blockchain()
    tallies = bc.get_tallies()
    stats = bc.get_stats()
    return jsonify({"tallies": tallies, "stats": stats, "candidates": CANDIDATES})


@app.route("/api/blockchain", methods=["GET"])
def api_blockchain():
    """Return the full blockchain for auditing."""
    bc = get_blockchain()
    return jsonify({"chain": bc.get_chain()})


@app.route("/api/blockchain/verify", methods=["GET"])
def api_blockchain_verify():
    """Verify chain integrity."""
    bc = get_blockchain()
    return jsonify(bc.verify_chain())


@app.route("/api/blockchain/<int:block_index>", methods=["GET"])
def api_block(block_index: int):
    """Return a specific block by index."""
    bc = get_blockchain()
    block = bc.get_block(block_index)
    if block is None:
        return jsonify({"error": "Block not found"}), 404
    return jsonify(block)


@app.route("/api/stats", methods=["GET"])
def api_stats():
    """Return system statistics."""
    bc = get_blockchain()
    return jsonify(bc.get_stats())


@app.route("/api/candidates", methods=["GET"])
def api_candidates():
    """Return the list of valid candidates."""
    return jsonify({"candidates": CANDIDATES})


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@app.route("/api/health", methods=["GET"])
def api_health():
    return jsonify({"status": "ok", "service": "SecureVote"})


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    initialize()
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("DEBUG", "false").lower() == "true"
    app.run(host="0.0.0.0", port=port, debug=debug)
