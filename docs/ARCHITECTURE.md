# SecureVote — Architecture

## System Overview

SecureVote is composed of two logically separated subsystems connected only
through the cryptographic token abstraction:

```
┌──────────────────────────────────────────────────────────────────────┐
│                           VOTER (Browser)                             │
│                                                                        │
│  T = random_bytes(32)        # secret token, never leaves browser     │
│  B, r = blind(T, PK_issuer) # blinded token + blinding factor r      │
│  ─────────────── POST /api/register ─────────────────────────────►   │
│                                                                        │
│  ◄──────── blind_sig = blind_sign(B, SK_issuer) ───────────────────  │
│                                                                        │
│  sig = unblind(blind_sig, r) # valid RSA sig on T (browser only)     │
│  ─────────────── POST /api/vote ──────────────────────────────────►  │
│     body: { token: T, signature: sig, candidate: "C" }               │
└──────────────────────────────────────────────────────────────────────┘
              │                                    │
    voter_id + B                          T + sig + candidate
              │                                    │
              ▼                                    ▼
   ┌─────────────────────┐           ┌─────────────────────────┐
   │  IDENTITY LAYER      │           │  ANONYMOUS BALLOT LAYER  │
   │  voter_registry.py   │           │  blockchain.py           │
   │                      │           │                          │
   │  Knows: who voted    │           │  Knows: sig is valid,    │
   │  Doesn't know: what  │           │         vote choice      │
   │  voter voted         │           │  Doesn't know: who voted │
   └─────────────────────┘           └─────────────────────────┘
```

## Component Details

### Component 1: Identity Layer (`backend/`)

**voter_registry.py**
- Calls `database.py` to check eligibility and prevent duplicate issuance
- Calls `blind_signature.py::blind_sign()` to produce the blind signature
- The issued blind signature is computed over the **blinded** token — the issuer never sees `T`

**database.py (SQLite)**
Tables:
- `eligible_voters` — pre-seeded list of valid voter IDs
- `voters` — records each voter's registration state (`token_issued` flag)
- `issuer_keys` — stores the RSA keypair (private key used only for signing)

**blind_signature.py**
Implements Chaum's RSA blind signature scheme:
```
Voter:    B = (H(T) * r^e) mod n      (blinding, where r is secret)
Issuer:   S = B^d mod n               (blind signing)
Voter:    sig = (S * r^{-1}) mod n    (unblinding)
Verify:   sig^e mod n == H(T) mod n   (verification)
```

### Component 2: Anonymous Ballot Layer (`blockchain/`)

**blockchain.py**
- Maintains a hash-linked chain of blocks
- Each block contains one vote record: `{token_hash, candidate, timestamp, sig_fragment}`
- Token hashes are stored in a `spent_tokens` set — prevents reuse
- Simple Proof-of-Work (2 leading hex zeros) mines each block

Block structure:
```json
{
  "index": 42,
  "timestamp": 1714000000.0,
  "votes": [
    {
      "token_hash": "sha256(T)",
      "candidate": "Candidate A",
      "timestamp": 1714000000.0,
      "signature": "<first 64 chars of sig_b64>"
    }
  ],
  "previous_hash": "0000abc...",
  "nonce": 1337,
  "hash": "0000def..."
}
```

### Component 3: API Layer (`backend/api.py`)

Flask application exposing two sets of endpoints:

| Group | Path | Description |
|---|---|---|
| Identity | `POST /api/register` | Issue blind signature |
| Identity | `GET /api/voter/:id/status` | Registration status |
| Identity | `GET /api/public-key` | Issuer's public key |
| Identity | `POST /api/verify-token` | Test helper |
| Ballot | `POST /api/vote` | Cast anonymous vote |
| Ballot | `GET /api/results` | Vote tallies |
| Ballot | `GET /api/blockchain` | Full chain (auditing) |
| Ballot | `GET /api/blockchain/verify` | Chain integrity |
| Ballot | `GET /api/blockchain/<n>` | Single block |

### Component 4: Frontend (`frontend/`)

Pure HTML + JavaScript. No framework needed for the PoC.

**crypto.js** — Client-side RSA blind signature using native `BigInt`:
- `generateToken()` — `crypto.getRandomValues()`
- `blindToken(T, PK)` — blind operation
- `unblindSignature(blind_sig, r, PK)` — unblinding
- `verifySignature(T, sig, PK)` — local pre-verification before submission
- All large integer arithmetic uses JavaScript's native `BigInt` (no library needed)

## Data Flow — Registration

```
Browser                       Server (Identity Layer)
───────                       ─────────────────────────
T = random(32 bytes)
B, r = blind(T, PK)
─────── POST /api/register ──► check eligible
         voter_id + B          check not already issued
                               blind_sig = B^d mod n
                              ◄─── blind_sig ────────────
sig = (blind_sig * r⁻¹) mod n
                               mark voter as "registered"
```

## Data Flow — Voting

```
Browser                       Server (Ballot Layer)
───────                       ─────────────────────
─────── POST /api/vote ──────► verify: sig^e mod n == H(T) mod n
         T, sig, candidate     verify: hash(T) not in spent_tokens
                               add hash(T) to spent_tokens
                               mine block with vote record
                              ◄─── tx_hash, block_index ──────────
```

## Anonymity Guarantee

The mathematical foundation of anonymity is the **blinding factor `r`**:

1. The issuer receives `B = H(T) * r^e mod n`
2. The issuer returns `S = B^d = H(T)^d * r mod n`
3. The voter computes `sig = S * r⁻¹ = H(T)^d mod n`
4. The issuer sees only `B` and `S` — the `r` factor makes them computationally
   unlinkable to `T` (under the RSA assumption)

Even if the issuer and the blockchain operator collude and share all their
logs, they cannot match an identity to a vote without breaking RSA.

## Blockchain Integrity

Each block's hash covers: index, timestamp, votes, previous_hash, nonce.

Chain validation re-computes every hash and verifies the `previous_hash` linkage.
Any modification to a vote in block `k` invalidates all subsequent hashes.

## Security Boundaries

```
TRUSTED (identity layer only):
  • voter_id ↔ registration status

UNTRUSTED / PUBLIC:
  • issuer public key
  • all votes on blockchain
  • vote tallies

PRIVATE (never transmitted):
  • token T (generated in browser)
  • blinding factor r (used and discarded)
  • voter's final credential (token + sig)
```
