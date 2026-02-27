# SecureVote — Anonymous Blockchain Voting System

A proof-of-concept anonymous voting system using **RSA blind signatures** and a
custom **Python blockchain** to guarantee:

- **One person, one vote** — cryptographically enforced
- **Complete voter anonymity** — architectural separation via blind signatures
- **Public verifiability** — open-source code + transparent blockchain

---

## Architecture Overview

```
┌────────────────────────────────────────────────────────────────┐
│                        VOTER (Browser)                         │
│  1. generate random token T                                    │
│  2. blind(T, issuer_pub_key) → B, r  (r = blinding factor)    │
│  3. send voter_id + B → Identity Layer                        │
│  4. receive blind_sig(B) from issuer                          │
│  5. unblind(blind_sig, r) → sig on T  (locally, private)      │
│  6. send (T, sig, candidate) → Voting Layer                   │
└────────────────────────────────────────────────────────────────┘
         │ voter_id + blinded_token (issuer cannot see T)
         ▼
┌─────────────────────────┐         ┌──────────────────────────┐
│   IDENTITY LAYER        │         │   ANONYMOUS BALLOT LAYER  │
│   (voter_registry.py)   │         │   (blockchain.py)         │
│                         │         │                           │
│  • verify eligibility   │         │  • verify sig(T, pk)      │
│  • issue blind sig      │         │  • check T not used       │
│  • mark "token_issued"  │         │  • record vote on chain   │
│  • SQLite DB            │         │  • burn token hash        │
│  NO vote data           │         │  NO voter identity        │
└─────────────────────────┘         └──────────────────────────┘
```

The two layers are architecturally separated: **the identity layer never sees
the real token; the voting layer never sees the voter ID.**

---

## Quick Start

### Prerequisites
- Python 3.10+
- pip

### 1. Install dependencies
```bash
cd backend
pip install -r requirements.txt
```

### 2. Start the server
```bash
python api.py
```

The server runs on `http://localhost:5000`.

### 3. Open the UI
Navigate to `http://localhost:5000` in your browser.

---

## Demo Workflow

**Registration**
1. Go to `http://localhost:5000/register`
2. Enter a Voter ID from `VOTER_00001` to `VOTER_00050`
3. Your browser generates a random token, blinds it, and sends only the blinded version to the server
4. The server returns a blind signature; your browser unblinds it locally
5. Your credential (token + signature) is saved in browser localStorage

**Voting**
1. Go to `http://localhost:5000/vote`
2. Your saved credential is loaded automatically (or paste it manually)
3. Select a candidate and submit
4. The server verifies the RSA signature, records the vote on the blockchain, and returns a transaction hash

**Results**
- Go to `http://localhost:5000/results` to see live tallies
- Go to `http://localhost:5000/verify` to inspect the raw blockchain

---

## Running Tests
```bash
cd /path/to/SecureVote
pip install -r backend/requirements.txt
pytest tests/ -v --cov=backend --cov=blockchain --cov-report=term-missing
```

---

## Project Structure

```
SecureVote/
├── backend/
│   ├── blind_signature.py   # RSA blind signature protocol
│   ├── database.py          # SQLite voter registry
│   ├── voter_registry.py    # Token issuance orchestration
│   ├── api.py               # Flask REST API + frontend serving
│   └── requirements.txt
├── blockchain/
│   └── blockchain.py        # Custom PoW blockchain for votes
├── frontend/
│   ├── templates/           # Jinja2 HTML pages
│   │   ├── index.html
│   │   ├── register.html
│   │   ├── vote.html
│   │   ├── results.html
│   │   └── verify.html
│   └── static/
│       ├── css/style.css
│       └── js/
│           ├── crypto.js    # Client-side blind sig (BigInt-based)
│           └── app.js       # API helpers & UI utilities
├── tests/
│   ├── conftest.py
│   ├── test_blind_signature.py
│   ├── test_blockchain.py
│   ├── test_voter_registry.py
│   └── test_api.py
├── docs/
│   ├── ARCHITECTURE.md
│   ├── SETUP.md
│   ├── API.md
│   └── SECURITY.md
├── docker-compose.yml
├── Dockerfile
└── README.md
```

---

## Security Considerations

| Threat | Mitigation |
|---|---|
| Double registration | SQLite unique constraint on `voter_id` |
| Double voting | Token hash stored in blockchain spent-set |
| Voter–vote linkability | RSA blind signatures — issuer never sees the real token |
| Signature forgery | 2048-bit RSA, verified on every vote submission |
| Vote tampering | Blockchain hash chain + PoW mining |
| Input injection | Alphanumeric whitelist on voter IDs, candidate whitelist |

---

## Known Limitations (PoC)

- Single server — not distributed; real deployment needs multiple nodes
- No coercion resistance (vote-selling is theoretically possible)
- Candidates are hardcoded; a real system needs an admin interface
- The demo private key is stored in plaintext in SQLite (use HSM in production)
- No rate limiting on API endpoints

---

## License

MIT — see [LICENSE](LICENSE)
