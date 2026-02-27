# SecureVote — API Reference

Base URL: `http://localhost:5000`

All request and response bodies are JSON. All responses include an HTTP status code.

---

## Identity Layer

### `POST /api/register`

Register a voter and receive a blind signature.

**Request**
```json
{
  "voter_id":         "VOTER_00001",
  "blinded_token_b64": "<base64-encoded blinded token>"
}
```

| Field | Type | Description |
|---|---|---|
| `voter_id` | string | Alphanumeric + underscores only |
| `blinded_token_b64` | string | RSA-blinded token, base64-encoded |

**Response — success (200)**
```json
{
  "success": true,
  "blind_sig_b64": "<base64-encoded blind signature>"
}
```

**Response — failure (400)**
```json
{
  "success": false,
  "error": "Token already issued to this voter"
}
```

Error messages:
- `"Voter ID not found in eligible voters list"` — voter not eligible
- `"Token already issued to this voter"` — duplicate registration attempt
- `"voter_id and blinded_token_b64 are required"` — missing fields
- `"Invalid voter_id format"` — non-alphanumeric characters detected

---

### `GET /api/voter/:voter_id/status`

Check registration status for a voter.

**Response (200)**
```json
{
  "voter_id":        "VOTER_00001",
  "eligible":        true,
  "registered":      true,
  "token_issued":    true,
  "registered_at":   "2024-01-01 12:00:00",
  "token_issued_at": "2024-01-01 12:00:00"
}
```

If voter has not registered yet:
```json
{
  "voter_id":     "VOTER_00001",
  "eligible":     true,
  "registered":   false,
  "token_issued": false
}
```

---

### `GET /api/public-key`

Retrieve the issuer's RSA public key.

**Response (200)**
```json
{
  "public_key": "-----BEGIN PUBLIC KEY-----\n...\n-----END PUBLIC KEY-----\n"
}
```

---

### `POST /api/verify-token`

Test helper: verify that a (token, signature) credential is cryptographically valid.

**Request**
```json
{
  "token_hex":     "<64-char hex string>",
  "signature_b64": "<base64-encoded signature>"
}
```

**Response (200)**
```json
{ "valid": true }
```
or
```json
{ "valid": false, "error": "..." }
```

---

## Anonymous Ballot Layer

### `POST /api/vote`

Cast an anonymous vote. No voter identity is recorded.

**Request**
```json
{
  "token_hex":     "<64-char hex>",
  "signature_b64": "<base64 RSA signature>",
  "candidate":     "Candidate A"
}
```

| Field | Type | Description |
|---|---|---|
| `token_hex` | string | Original random token (hex) |
| `signature_b64` | string | Unblinded RSA signature (base64) |
| `candidate` | string | Must match one of the valid candidates |

**Response — success (200)**
```json
{
  "success":     true,
  "tx_hash":     "0000abc123...",
  "block_index": 42
}
```

**Response — failure**

| Status | Reason |
|---|---|
| 400 | Missing fields |
| 400 | Invalid candidate |
| 400 | Token already used |
| 403 | Invalid token signature |

```json
{ "success": false, "error": "Token already used — double-voting prevented" }
```

---

### `GET /api/results`

Get current vote tallies.

**Response (200)**
```json
{
  "tallies": {
    "Candidate A": 12,
    "Candidate B": 7,
    "Candidate C": 3
  },
  "stats": {
    "block_count":   23,
    "total_votes":   22,
    "spent_tokens":  22,
    "candidates":    ["Candidate A", "Candidate B", "Candidate C"]
  },
  "candidates": ["Candidate A", "Candidate B", "Candidate C"]
}
```

---

### `GET /api/candidates`

List valid candidates.

**Response (200)**
```json
{ "candidates": ["Candidate A", "Candidate B", "Candidate C"] }
```

---

### `GET /api/blockchain`

Return the entire blockchain (for auditing).

**Response (200)**
```json
{
  "chain": [
    {
      "index":         0,
      "timestamp":     1714000000.0,
      "votes":         [],
      "previous_hash": "0000000000000000000000000000000000000000000000000000000000000000",
      "nonce":         0,
      "hash":          "000043ab..."
    },
    {
      "index":         1,
      "timestamp":     1714000001.0,
      "votes": [
        {
          "token_hash": "sha256hex...",
          "candidate":  "Candidate A",
          "timestamp":  1714000001.0,
          "signature":  "firstN chars of sig"
        }
      ],
      "previous_hash": "000043ab...",
      "nonce":         234,
      "hash":          "0000ef12..."
    }
  ]
}
```

---

### `GET /api/blockchain/verify`

Verify blockchain integrity.

**Response (200)**
```json
{
  "valid":       true,
  "block_count": 23,
  "message":     "Chain integrity verified"
}
```

---

### `GET /api/blockchain/:index`

Get a single block by index.

**Response (200)**
```json
{ "index": 5, "timestamp": ..., "votes": [...], ... }
```

**Response (404)**
```json
{ "error": "Block not found" }
```

---

### `GET /api/stats`

System statistics.

**Response (200)**
```json
{
  "block_count":  23,
  "total_votes":  22,
  "spent_tokens": 22,
  "candidates":   ["Candidate A", "Candidate B", "Candidate C"]
}
```

---

### `GET /api/health`

Health check.

**Response (200)**
```json
{ "status": "ok", "service": "SecureVote" }
```
