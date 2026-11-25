# Budget Buddy

A locally-hosted personal finance dashboard. All financial data stays on your machine, encrypted at rest with SQLCipher (256-bit AES).

## Features

- **Account connections** via Plaid (or manual entry)
- **Data import** from CSV, Excel, PDF bank statements (AI-parsed via Claude)
- **Dedup** prevents duplicate transactions on re-import
- **AI review gate** - AI-parsed transactions are flagged "needs review" and never auto-committed
- **Entity ledgers** — track House, Airbnb, Business etc. independently or combined; split shared expenses across entities
- **Auto-tagging rules** — assign transactions to entities automatically based on account, name, or merchant
- **Spending analytics** with category breakdowns, monthly trends, budget-vs-actual, and per-entity breakdowns
- **Net worth balance sheet** — track assets (homes, businesses, investments, vehicles, cash) and liabilities (mortgages, loans, credit) with a total net-worth headline, per-class and per-entity breakdowns, and a snapshot-based net-worth trend chart
- **Local dashboard** accessible from any device on your home network
- **Auth gate** with bcrypt-hashed passwords and signed session cookies
- **Database migrations** via Alembic (reversible, SQLite-compatible)

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

## Security

Budget Buddy runs on your own machine and keeps your data there:

- **Encrypted at rest:** the database is encrypted with SQLCipher (AES-256) using your `DB_PASSPHRASE`.
- **Private network only:** nothing is published to the internet. Reach it from your home network or, recommended, over Tailscale (end-to-end encrypted, only your devices).
- **Accounts:** bcrypt-hashed passwords, one-time invite and reset links, admin-managed access. Signed `HttpOnly` session cookies end when a password changes.
- **Every data endpoint requires sign-in**, and a test fails the build if one doesn't. Cross-site form posts are blocked.
- **Nothing leaves the machine by default.** Data is sent out only to Plaid (if you connect a bank), Claude (if you choose it over local Ollama) and GitHub (updates).
- **Safe updates:** changes reach the Mac only from `main` after CI tests pass. A failed update stops before restarting, so the previous version keeps running.

**Read [docs/SECURITY.md](docs/SECURITY.md)** for the details, a setup checklist and the known gaps (including dependency upgrades still to do).

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.10+ / FastAPI |
| Database | SQLite + SQLCipher (encrypted) |
| ORM | SQLAlchemy 2.x + Alembic |
| Frontend | React 18 + Vite + Tailwind CSS + Recharts |
| Financial data | Plaid API |
| AI parsing | Anthropic Claude API |
| Auth | bcrypt + signed session cookies |

## Tests

```bash
source .venv/bin/activate
python -m pytest tests/ -v
```

Regression tests (300 and counting) covering: dedup logic, CSV/Excel import parsing, analytics aggregation math, entity CRUD, transaction splits, rule matching, per-entity aggregation, net worth balance sheet, schema repair, accounts and sign-in, and security (every endpoint requires sign-in, CSRF).

## Documentation

- **[Security](docs/SECURITY.md)** — How data is protected when self-hosted, how updates are delivered safely, known gaps, setup checklist
- **[Deployment Guide](docs/DEPLOYMENT.md)** — Full setup instructions for Mac and Windows, auto-start on boot, security checklist, updating to new versions
- **[Contributing & Development](docs/CONTRIBUTING.md)** — Branching strategy, dev setup, project structure, versioning, multi-user roadmap
- **[Entities & Rules](docs/ENTITIES.md)** — Entity model, transaction splits, auto-tagging rules, API reference

## API Docs

With the server running, visit http://localhost:8000/docs for interactive API docs (Swagger UI).
