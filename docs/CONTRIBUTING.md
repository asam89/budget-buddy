# Contributing & Development Workflow

## Branching Strategy

Budget Buddy uses a **version-based branching model**:

```
main (stable, deployable)
 ├── v1.1-feature-name    ← feature branch for next version
 ├── v1.1-another-feature ← another feature for same version
 └── v1.2-big-change      ← future version
```

### Rules

1. **`main` is always deployable** — only merge tested, reviewed code.
2. **One branch per feature or version** — name it `v<version>-<description>` (e.g., `v1.1-multi-user`, `v1.2-google-sheets`).
3. **Open a Pull Request** for every change — no direct pushes to `main`.
4. **Tag releases** after merging: `git tag v1.1.0 && git push --tags`.

---

## Development Setup

```bash
git clone https://github.com/asam89/budget-buddy.git
cd budget-buddy

# Backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Frontend (dev mode with hot reload)
cd frontend
npm install
npm run dev    # starts Vite dev server on :5173
```

Run the backend in a separate terminal:

```bash
source .venv/bin/activate
uvicorn app.main:app --reload --port 8000
```

The Vite dev server proxies `/api` requests to the FastAPI backend automatically.

---

## Making Changes

### 1. Create a branch

```bash
git checkout main
git pull origin main
git checkout -b v1.1-my-feature
```

### 2. Develop

- **Backend code**: `app/` directory (FastAPI routers, services, models)
- **Frontend code**: `frontend/src/` (React components, pages)
- **Tests**: `tests/` directory

### 3. Run tests before committing

```bash
source .venv/bin/activate
python -m pytest tests/ -v
```

All 19 regression tests must pass:
- Dedup logic (hash determinism, reimport produces 0 duplicates)
- Import parsing (CSV, Excel, column detection, date formats)
- Analytics math (income/expense totals, budget-vs-actual, pending exclusion)

### 4. Commit and push

```bash
git add -A
git commit -m "v1.1: Add multi-user support"
git push -u origin v1.1-my-feature
```

### 5. Open a Pull Request

Go to https://github.com/asam89/budget-buddy/pulls and create a PR from your branch into `main`.

### 6. After merge, tag the release

```bash
git checkout main
git pull origin main
git tag v1.1.0
git push --tags
```

### 7. Deploy

On your Mac Mini / production machine:

```bash
cd /path/to/budget-buddy
git pull origin main
source .venv/bin/activate
pip install -r requirements.txt
cd frontend && npm install && npm run build && cd ..
# Restart the server
```

---

## Project Structure

```
budget-buddy/
├── app/
│   ├── main.py              # FastAPI entry point
│   ├── config.py             # Pydantic settings (.env loading)
│   ├── database.py           # SQLCipher engine setup
│   ├── models.py             # SQLAlchemy ORM models (8 tables)
│   ├── schemas.py            # Pydantic request/response schemas
│   ├── routers/
│   │   ├── auth.py           # Login, setup, session management
│   │   ├── accounts.py       # Account CRUD
│   │   ├── transactions.py   # Transaction CRUD + review
│   │   ├── categories.py     # Category management + defaults
│   │   ├── budgets.py        # Budget targets per category
│   │   ├── bills.py          # Recurring bill entries
│   │   ├── plaid.py          # Plaid Link integration
│   │   ├── imports.py        # File upload (CSV/Excel/PDF)
│   │   └── dashboard.py      # Analytics endpoints
│   ├── services/
│   │   ├── importer.py       # CSV/Excel parsing + dedup
│   │   └── ai_parser.py      # Claude API statement extraction
│   └── utils/
│       └── auth.py           # Password hashing, session cookies
├── frontend/
│   └── src/
│       ├── App.tsx            # Router + auth check
│       ├── api/client.ts      # Typed API client
│       ├── components/        # Sidebar, shared components
│       └── pages/             # Dashboard, Accounts, Transactions, etc.
├── tests/                     # Regression tests
├── data/                      # SQLCipher database file (git-ignored)
├── docs/                      # This documentation
├── .env.example               # Environment variable template
└── requirements.txt           # Python dependencies
```

---

## Adding New Features

### Adding a new API endpoint

1. Create or edit a router in `app/routers/`
2. Add Pydantic schemas in `app/schemas.py`
3. Add the router to `app/main.py` if it's a new file
4. Add corresponding frontend page/component
5. Write tests in `tests/`

### Adding a new database table

1. Add the SQLAlchemy model in `app/models.py`
2. The table is created automatically on startup (`Base.metadata.create_all`)
3. For production migrations (column changes, not new tables), use Alembic

### Adding a new frontend page

1. Create the component in `frontend/src/pages/`
2. Add the route in `frontend/src/App.tsx`
3. Add the nav link in `frontend/src/components/Sidebar.tsx`
4. Add API functions in `frontend/src/api/client.ts`

---

## Versioning

We follow [Semantic Versioning](https://semver.org/):

- **v1.0.0** — Current: single-user, local deployment
- **v1.1.0** — Planned: multi-user support, user registration
- **v1.2.0** — Planned: Google Sheets import, enhanced analytics
- **v2.0.0** — Planned: cloud-hosted option for public users

---

## Multi-User Roadmap

To support multiple users and offer the app for free:

### Self-Hosted (free for users)
Users clone and deploy their own instance. Zero cost to you. The repo is public and includes full deployment docs.

### Centrally Hosted (you host for users)
Requires:
1. Multi-user data isolation (`user_id` FK on all data tables)
2. User registration flow
3. VPS/cloud server with HTTPS (Let's Encrypt + nginx)
4. Plaid upgrade from Trial (10 Items) to Pay-as-you-go plan
5. Rate limiting and security hardening
