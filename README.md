# Budget Buddy

A locally-hosted personal finance dashboard. All financial data stays on your machine, encrypted at rest with SQLCipher (256-bit AES).

## Features

- **Account connections** via Plaid (or manual entry)
- **Data import** from CSV, Excel, PDF bank statements (AI-parsed via Claude)
- **Dedup** prevents duplicate transactions on re-import
- **AI review gate** - AI-parsed transactions are flagged "needs review" and never auto-committed
- **Spending analytics** with category breakdowns, monthly trends, and budget-vs-actual tracking
- **Local dashboard** accessible from any device on your home network
- **Auth gate** with bcrypt-hashed passwords and signed session cookies

## Quick Start

```bash
# Clone and set up
git clone https://github.com/asam89/budget-buddy.git
cd budget-buddy

# Backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Frontend
cd frontend && npm install && npm run build && cd ..

# Configure
cp .env.example .env
# Edit .env with your DB passphrase, Plaid keys, Anthropic key

# Run
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Open http://localhost:8000 — on first visit, create your admin account.

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.10+ / FastAPI |
| Database | SQLite + SQLCipher (encrypted) |
| ORM | SQLAlchemy 2.x |
| Frontend | React 18 + Vite + Tailwind CSS + Recharts |
| Financial data | Plaid API |
| AI parsing | Anthropic Claude API |
| Auth | bcrypt + signed session cookies |

## Tests

```bash
source .venv/bin/activate
python -m pytest tests/ -v
```

19 regression tests covering: dedup logic, CSV/Excel import parsing, and analytics aggregation math.

## API Docs

With the server running, visit http://localhost:8000/docs for interactive API docs (Swagger UI).
