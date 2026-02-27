# SecureVote — Security Analysis

## Threat Model

SecureVote aims to protect against a **semi-honest adversary**:
- The system operators may be curious but follow the protocol
- External observers can see everything on the public blockchain
- Voters may attempt to vote more than once

It does **not** protect against:
- A fully malicious server that logs all requests with metadata (timing, IP)
- Coercion (an attacker that demands you prove your vote)
- Nation-state level attacks on the RSA assumption

---

## Security Properties

### 1. One Person, One Vote

**Mechanism A — Registration uniqueness**
```sql
voter_id TEXT PRIMARY KEY   -- enforced by SQLite
```
Each `voter_id` can receive exactly one blind signature. Attempting to
register twice returns an error before any signing occurs.

**Mechanism B — Token spend tracking**
The blockchain maintains a `spent_tokens` set (SHA-256 hashes of used tokens).
Before every vote, the system checks:
```python
if token_hash in self.spent_tokens:
    return {"success": False, "error": "Token already used"}
```
This check is atomic (protected by a threading lock) within the blockchain module.

### 2. Voter Anonymity

**RSA Blind Signature Unlinkability**

The blinding factor `r` is chosen uniformly at random by the voter's browser
and is never transmitted. The issuer observes only:

```
B = H(T) * r^e  mod n    (blinded token)
S = B^d         mod n    (blind signature)
```

For the issuer to link `S` back to a specific vote transaction, they would
need to find `r` such that `B = H(T) * r^e mod n` — equivalent to solving the
RSA problem. Under the standard RSA assumption this is computationally infeasible
with 2048-bit keys.

**Separation of logs**
- The identity layer (`/api/register`) logs: `voter_id`, `timestamp`
- The ballot layer (`/api/vote`) logs: `token_hash`, `candidate`, `timestamp`
- **No log entry combines both** — even if all logs are merged, the `token_hash`
  cannot be traced to a `voter_id` without breaking RSA

### 3. Vote Integrity

Every block in the blockchain is cryptographically linked to its predecessor:
```
hash(block_k) = SHA-256(index_k | timestamp_k | votes_k | hash(block_{k-1}) | nonce_k)
```
Modifying any vote in block `k` produces a different hash for block `k`,
which breaks the `previous_hash` reference in block `k+1`, cascading to
invalidate all subsequent blocks. The verifier detects this immediately.

---

## Attack Scenarios and Mitigations

### Double Registration
- **Attack**: Voter submits `VOTER_00001` twice
- **Mitigation**: `has_token_issued()` check before signing; SQLite primary key uniqueness
- **Result**: Second request returns error; no blind signature issued

### Double Voting (Token Reuse)
- **Attack**: Voter submits the same `(token, signature)` twice
- **Mitigation**: `SHA-256(token)` stored in `spent_tokens` on first use
- **Result**: Second vote rejected with "Token already used"

### Forged Token (No Valid Signature)
- **Attack**: Voter invents a `(token, garbage_signature)` pair
- **Mitigation**: Server verifies `sig^e mod n == H(token) mod n` before any blockchain write
- **Result**: Request rejected with HTTP 403

### Vote Tampering
- **Attack**: Attacker modifies a recorded vote on the blockchain
- **Mitigation**: SHA-256 hash chain — modification invalidates all subsequent block hashes
- **Result**: `verify_chain()` returns `valid: false`; tampering is publicly detectable

### SQL Injection
- **Attack**: Malicious `voter_id` like `"'; DROP TABLE voters; --"`
- **Mitigation**: Input whitelist (alphanumeric + underscore only); SQLite parameterized queries
- **Result**: Request rejected before reaching the database

### Candidate Injection
- **Attack**: Voter submits an arbitrary candidate name
- **Mitigation**: Candidate validated against a hardcoded whitelist in both API and blockchain layers
- **Result**: Request rejected with HTTP 400

---

## Cryptographic Parameters

| Parameter | Value | Notes |
|---|---|---|
| RSA key size | 2048 bits | Minimum for demonstration; 3072+ recommended for production |
| Hash function | SHA-256 | Used for token hashing and block hashing |
| Token size | 32 bytes | 256 bits of entropy |
| Blinding factor | Key-sized random | Re-generated per registration |

---

## Known Limitations (PoC)

1. **IP / timing correlation**: The system does not introduce timing delays
   between registration and voting. An attacker monitoring network traffic could
   correlate timing to link identities to votes.

2. **Private key storage**: The RSA private key is stored in SQLite in plaintext.
   Production systems should use an HSM or a secrets manager.

3. **No receipt-freeness**: A voter could screenshot their credential and prove
   their vote to a coercer. Preventing this requires more complex protocols
   (e.g., Juels-Catalano-Jakobsson).

4. **Single point of failure**: The entire system runs on one server. A
   distributed quorum is needed for production trust assumptions.

5. **Token is pre-computed in browser**: If the browser is compromised, the
   token can be stolen before voting. This is unavoidable in a web-based PoC.
