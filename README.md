# Budget Buddy

A local-first personal finance dashboard that runs on your Mac Mini or Windows desktop. Connect your bank accounts, credit cards, and investment accounts to track funds in and out — all data stays on your machine.

## Features

- **Local Dashboard** — Beautiful web UI served locally, accessible at `http://localhost:8000`
- **Bank & Credit Card Connections** — Connect financial institutions via Plaid
- **Transaction Tracking** — Automatic categorization of income and expenses
- **Funds In & Out** — Real-time view of money flowing through your accounts
- **Charts & Analytics** — Spending trends, category breakdowns, net worth tracking
- **Privacy First** — All data stored locally in SQLite; nothing leaves your machine

## Tech Stack

- **Backend**: Python 3.11+ / FastAPI / SQLite
- **Frontend**: React / Vite / Tailwind CSS / Recharts
- **Financial Data**: Plaid API (bank/CC/investment connections)

## Quick Start

### Prerequisites

- Python 3.11+
- Node.js 18+
- A [Plaid](https://plaid.com/) account (free Sandbox for testing)

### Setup

```bash
# Clone the repo
git clone https://github.com/asam89/budget-buddy.git
cd budget-buddy

# Backend setup
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env        # Add your Plaid credentials

# Frontend setup
cd frontend
npm install
npm run build
cd ..

# Run the app
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Open `http://localhost:8000` in your browser.

## Environment Variables

| Variable | Description |
|----------|-------------|
| `PLAID_CLIENT_ID` | Your Plaid client ID |
| `PLAID_SECRET` | Your Plaid secret key |
| `PLAID_ENV` | Plaid environment (`sandbox`, `development`, `production`) |
| `SECRET_KEY` | App secret key for session encryption |

## Project Structure

```
budget-buddy/
├── app/
│   ├── main.py              # FastAPI app entry point
│   ├── config.py            # Configuration & env vars
│   ├── database.py          # SQLite setup & session
│   ├── models.py            # SQLAlchemy models
│   ├── schemas.py           # Pydantic schemas
│   └── routers/
│       ├── accounts.py      # Account management endpoints
│       ├── transactions.py  # Transaction endpoints
│       ├── plaid.py         # Plaid integration endpoints
│       └── dashboard.py     # Dashboard data endpoints
├── frontend/
│   ├── src/
│   │   ├── App.tsx
│   │   ├── components/      # React components
│   │   ├── pages/           # Dashboard pages
│   │   └── api/             # API client
│   └── package.json
├── requirements.txt
├── .env.example
└── README.md
```

## License

MIT
