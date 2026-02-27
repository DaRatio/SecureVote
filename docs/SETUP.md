# SecureVote — Setup Guide

## Prerequisites

| Tool | Version | Notes |
|---|---|---|
| Python | 3.10+ | Required |
| pip | Latest | Bundled with Python |
| Docker | 24+ | Optional (for Docker setup) |
| Modern browser | Chrome/Firefox/Edge | For the frontend |

---

## Option A: Local Python Setup (Recommended for Development)

### 1. Clone the repository
```bash
git clone <repo-url>
cd SecureVote
```

### 2. (Optional) Create a virtual environment
```bash
python -m venv .venv
source .venv/bin/activate      # Linux/macOS
.venv\Scripts\activate.bat     # Windows
```

### 3. Install Python dependencies
```bash
pip install -r backend/requirements.txt
```

### 4. Start the application
```bash
cd backend
python api.py
```

On first startup the server will:
1. Initialize the SQLite database (`backend/voter_registry.db`)
2. Generate a 2048-bit RSA keypair and store it in the database
3. Seed 50 demo voter IDs (`VOTER_00001` – `VOTER_00050`)
4. Initialize the blockchain (`blockchain/chain.json`)

### 5. Open the UI
Navigate to `http://localhost:5000`

---

## Option B: Docker

### 1. Build and start
```bash
docker-compose up --build
```

### 2. Open the UI
Navigate to `http://localhost:5000`

### Stop
```bash
docker-compose down
```

Data is persisted in Docker volumes so votes survive container restarts.

---

## Configuration

Environment variables (set before starting `api.py`):

| Variable | Default | Description |
|---|---|---|
| `PORT` | `5000` | HTTP port to listen on |
| `DEBUG` | `false` | Enable Flask debug mode |

Example:
```bash
PORT=8080 DEBUG=true python api.py
```

---

## Running Tests

```bash
# From the repository root
pytest tests/ -v --cov=backend --cov=blockchain --cov-report=term-missing
```

Expected output: all tests pass, coverage ≥ 70%.

---

## Resetting the System

To reset all votes and re-run the demo from scratch:

```bash
rm -f backend/voter_registry.db blockchain/chain.json
python backend/api.py   # re-initializes everything
```

---

## Troubleshooting

**`ModuleNotFoundError: No module named 'Crypto'`**
```bash
pip install pycryptodome
```

**Port already in use**
```bash
PORT=5001 python backend/api.py
```

**Registration fails with "not found in eligible voters list"**
The demo seeds voters `VOTER_00001` through `VOTER_00050`. Use one of these IDs.
To add custom voters, modify `DEMO_VOTERS` in `backend/api.py` or call
`database.seed_eligible_voters([...])` directly.

**Credential not found on the Vote page**
The credential is stored in browser `localStorage`. If you registered in a
different browser or cleared storage, use the "Paste credential manually" option.
