# Budget Buddy — Phase 0 Proposal

## 1. Proposed Stack

| Layer | Choice | Rationale |
|-------|--------|-----------|
| **Backend** | Python 3.11+ / FastAPI | Cross-platform (Mac & Windows). FastAPI gives async, auto-docs, Pydantic validation. You already use Python/FastAPI in other projects (career-dev-bot). |
| **Database** | SQLite via SQLCipher | Zero-config, single-file DB. SQLCipher fork adds transparent **256-bit AES encryption at rest** — no Docker/Postgres overhead. Perfect for a single-user local app. |
| **ORM** | SQLAlchemy 2.x | Works with SQLCipher driver (`sqlcipher3` package). Mature migration support via Alembic. |
| **Frontend** | React 18 + Vite + Tailwind CSS + Recharts | Fast dev builds, modern UI. Recharts for spending/trend charts. Builds to static files served by FastAPI — no separate server needed. |
| **LLM (statement parsing)** | Anthropic Claude API (you already have `ANTHROPIC_API_KEY`) | For PDF/image statement parsing. Only external call; all extracted data stored locally. Could also support local Ollama as a fallback for fully offline use. |
| **Financial data aggregator** | Plaid API | Industry standard. See detailed feasibility below. |

### Hosting Approach (LAN-only)

- FastAPI binds to `0.0.0.0:<port>` — accessible from any device on the LAN via `http://<mac-mini-ip>:8000` or `http://<hostname>.local:8000` (mDNS works out of the box on macOS; on Windows, install Bonjour or use IP directly).
- **No reverse proxy needed** for a single-user LAN app. If you want HTTPS on LAN later, we can add a self-signed cert via uvicorn's `--ssl-keyfile`/`--ssl-certfile`.
- Basic **username/password auth gate** using session cookies (FastAPI + `itsdangerous` for signed sessions). Password hashed with `bcrypt`.
- **Not exposed to public internet** — no port forwarding, no tunnel.

### Cross-Platform Notes

Both Mac Mini (macOS) and Windows can run this stack identically:
- Python 3.11+ installs natively on both.
- SQLite/SQLCipher works on both (pre-built wheels available).
- `npm` builds the frontend on both.
- A simple `start.sh` / `start.bat` or a Python entry script wraps `uvicorn` launch.
- **Open question**: Do you want to target both, or primarily Mac Mini? This affects packaging (e.g., macOS LaunchAgent auto-start vs. Windows Task Scheduler).

---

## 2. Plaid Integration Feasibility

### Coverage
- **Canada**: All Big 5 (RBC, TD, Scotiabank, BMO, CIBC) + Tangerine, Desjardins, 100+ others. Over 99% of Canadian deposit accounts covered.
- **Products available in Canada**: Auth, Balance, Transactions, Investments, Identity, Enrich, Statements.

### Pricing (as of mid-2025)
| Plan | Cost | Limits |
|------|------|--------|
| **Trial (free)** | $0 | 10 Items (connected accounts) in Production. Unlimited API calls per Item. Includes Transactions, Auth, Balance, Identity, Assets, Investments, Statements. **Cannot remove Items to free slots.** |
| **Pay-as-you-go** | Per-item/per-call fees (not publicly listed — shown during Production signup) | No minimum spend. Good for small scale. |
| **Growth** | Lower per-use costs | Annual commitment, minimum spend. |

**Recommendation**: Start with the **Trial plan** — 10 Items is plenty for personal use (e.g., 1 chequing + 1 savings + 2 credit cards = 4 Items). Free, no business registration needed.

### Token Model
- Plaid uses **Link** (a drop-in UI widget) for bank auth. User authenticates directly with their bank via Plaid's hosted flow.
- On success, Plaid returns a `public_token` → your backend exchanges it for an `access_token` via API.
- The `access_token` is stored locally (encrypted in SQLCipher DB). **No raw bank credentials ever touch our system.**
- Tokens are long-lived; Plaid manages session refresh.

### Rate Limits (per-Item, Sandbox/Production)
| Endpoint | Sandbox | Production |
|----------|---------|------------|
| `/transactions/sync` | 50/min | 2,500/min |
| `/transactions/get` | 30/min | 20,000/min |
| `/transactions/refresh` | 2/min, 120/hr | 100/min |
| `/accounts/get` | 15/min | — |

For a single-user personal app, these limits are effectively unlimited.

### Data Scopes
`/transactions/sync` returns: date, amount, merchant name, category (Plaid auto-categorizes), location, payment channel, pending status, ISO currency code. Up to **730 days** of history on first sync.

### Alternatives Considered
| Service | Notes |
|---------|-------|
| **Flinks** | Canada-native. 15,000+ NA institutions. Enterprise-focused pricing — likely overkill/expensive for personal use. |
| **BankSync** | Consumer wrapper over Plaid/Flinks. Pushes to Google Sheets/Notion. Not a raw API — less control. |
| **Manual CSV/PDF import** | Always available as a fallback. No API cost. We build this regardless. |

**Verdict**: Plaid Trial is the clear winner for personal use — free, excellent Canadian coverage, clean token model.

### ⚠️ Direct Bank Scraping Warning
Direct bank scraping (Selenium/Playwright against bank login pages) is **fragile, risky, and potentially violates bank ToS**. Banks actively fight automation. Plaid (or a similar aggregator) is the realistic, sustainable path for live account connections.

---

## 3. Encryption-at-Rest Approach

### Recommendation: SQLCipher

- **SQLCipher** is a battle-tested fork of SQLite providing transparent 256-bit AES encryption.
- Python driver: `sqlcipher3` (pip-installable, pre-built wheels for macOS/Windows).
- The entire DB file is encrypted — not just specific columns. No data leaks via temp files or WAL.
- Passphrase set via `PRAGMA key = '<passphrase>'` at connection time.
- Passphrase stored in `.env` (git-ignored), entered by user on first setup.
- **Performance overhead**: 5-15% on typical operations — negligible for a personal app.

### What Gets Encrypted
- Plaid access tokens
- Account balances and metadata
- All transaction data
- Budget and category data

### Alternative Considered
Column-level encryption (e.g., `cryptography.fernet` per-field) — rejected because it's more complex, doesn't protect the schema/metadata, and SQLCipher gives whole-DB encryption with zero application-level code.

---

## 4. AI Statement Parsing

### Approach: LLM-Powered Extraction with Review Gate

```
Upload (PDF/CSV/image)
    │
    ├─ CSV/Excel? → Deterministic parser (pandas) → normalize
    │
    └─ PDF/Image? → Extract text (pypdf / pdfplumber)
                        │
                        ├─ Enough text? → LLM (Claude) extracts structured transactions
                        │
                        └─ Scanned/image? → OCR (pytesseract) → LLM extracts
                                            │
                                            └─ All AI-parsed transactions flagged
                                               "needs_review" — NEVER auto-committed
```

### Key Design Rules
1. **AI-parsed data is never trusted blindly**: every AI-extracted transaction gets `review_status = "pending"` and is shown with source (which file, which page) and optional confidence.
2. **User must confirm** before transactions affect analytics.
3. **Editable**: user can correct merchant name, amount, category, date before confirming.
4. **Fallback**: if AI parsing fails, user can manually enter the transaction.

### Libraries
- `pandas` + `openpyxl` for Excel/CSV (deterministic, $0)
- `pypdf` / `pdfplumber` for PDF text extraction
- `pytesseract` for OCR on scanned statements
- Anthropic Claude API for structured extraction from unstructured text
- Google Sheets API (`google-api-python-client`, read-only OAuth scope) for Sheets import

### Existing Open-Source Reference
`bankstatementparser` (GitHub) does exactly this pipeline: deterministic parsers first → LLM fallback → vision model for scans. We can either use it as a dependency or follow its architecture.

---

## 5. Data Model Draft

```sql
-- Financial institutions (banks, credit unions)
institutions
    id              INTEGER PRIMARY KEY
    plaid_inst_id   TEXT UNIQUE         -- nullable (manual accounts have none)
    name            TEXT NOT NULL
    logo_url        TEXT
    created_at      DATETIME

-- Plaid connection tokens
plaid_items
    id              INTEGER PRIMARY KEY
    item_id         TEXT UNIQUE NOT NULL
    access_token    TEXT NOT NULL       -- encrypted at rest via SQLCipher
    institution_id  INTEGER REFERENCES institutions
    cursor          TEXT               -- for /transactions/sync pagination
    is_active       BOOLEAN DEFAULT 1
    created_at      DATETIME
    updated_at      DATETIME

-- Bank/CC/investment accounts
accounts
    id              INTEGER PRIMARY KEY
    plaid_account_id TEXT UNIQUE        -- nullable for manual accounts
    plaid_item_id   INTEGER REFERENCES plaid_items
    institution_id  INTEGER REFERENCES institutions
    name            TEXT NOT NULL
    official_name   TEXT
    account_type    TEXT NOT NULL       -- checking, savings, credit, investment
    account_subtype TEXT
    mask            TEXT               -- last 4 digits
    current_balance REAL DEFAULT 0
    available_balance REAL
    currency        TEXT DEFAULT 'CAD'
    is_active       BOOLEAN DEFAULT 1
    created_at      DATETIME
    updated_at      DATETIME

-- Spending/income categories
categories
    id              INTEGER PRIMARY KEY
    name            TEXT UNIQUE NOT NULL -- e.g. "Groceries", "Dining", "Salary"
    parent_id       INTEGER REFERENCES categories  -- hierarchical
    icon            TEXT
    color           TEXT
    is_system       BOOLEAN DEFAULT 0  -- Plaid-provided vs user-created
    created_at      DATETIME

-- Normalized transactions (ALL sources converge here)
transactions
    id              INTEGER PRIMARY KEY
    plaid_txn_id    TEXT UNIQUE        -- nullable for manual/imported
    account_id      INTEGER NOT NULL REFERENCES accounts
    import_source_id INTEGER REFERENCES import_sources  -- which import batch
    amount          REAL NOT NULL      -- positive = expense, negative = income
    currency        TEXT DEFAULT 'CAD'
    date            DATE NOT NULL
    name            TEXT NOT NULL
    merchant_name   TEXT
    category_id     INTEGER REFERENCES categories
    pending         BOOLEAN DEFAULT 0
    review_status   TEXT DEFAULT 'confirmed'  -- 'confirmed', 'pending', 'rejected'
    review_source   TEXT               -- 'plaid', 'manual', 'ai_parsed', 'csv_import'
    confidence      REAL               -- AI confidence score (0-1), null for non-AI
    source_file     TEXT               -- original filename for imports
    source_page     INTEGER            -- page number for PDF imports
    dedup_hash      TEXT UNIQUE        -- SHA-256(date|amount|name|account_id) for dedup
    notes           TEXT
    created_at      DATETIME

-- Import batches (tracks each file upload / sync)
import_sources
    id              INTEGER PRIMARY KEY
    source_type     TEXT NOT NULL       -- 'plaid_sync', 'csv', 'excel', 'pdf', 'google_sheets', 'manual'
    filename        TEXT               -- original filename
    file_hash       TEXT               -- SHA-256 of file content (detect re-uploads)
    record_count    INTEGER DEFAULT 0
    status          TEXT DEFAULT 'processing'  -- 'processing', 'completed', 'failed'
    error_message   TEXT
    imported_by     TEXT               -- user who triggered
    created_at      DATETIME

-- Monthly budget targets
budgets
    id              INTEGER PRIMARY KEY
    category_id     INTEGER NOT NULL REFERENCES categories
    monthly_limit   REAL NOT NULL
    year_month      TEXT               -- '2025-07' — nullable means "every month"
    is_active       BOOLEAN DEFAULT 1
    created_at      DATETIME
    updated_at      DATETIME

-- Recurring bills (manual entries for non-API bills)
bills
    id              INTEGER PRIMARY KEY
    name            TEXT NOT NULL
    amount          REAL NOT NULL
    currency        TEXT DEFAULT 'CAD'
    category_id     INTEGER REFERENCES categories
    frequency       TEXT NOT NULL       -- 'monthly', 'biweekly', 'quarterly', 'annual'
    due_day         INTEGER            -- day of month (1-31)
    next_due_date   DATE
    is_active       BOOLEAN DEFAULT 1
    notes           TEXT
    created_at      DATETIME
    updated_at      DATETIME
```

### Key Design Decisions
- **Single `transactions` table** — all import paths (Plaid, CSV, Excel, PDF, Sheets, manual) write to the same table. `review_source` tracks origin.
- **`review_status`** — Plaid and CSV imports can be auto-confirmed; AI-parsed always starts as `"pending"`.
- **`categories` table** — separate from transactions for consistency. Plaid categories map to this table; user can create custom ones.
- **`bills` table** — for recurring charges that can't be linked via Plaid (gym, rent to a person, etc.).

---

## 6. Dedup Logic

### Approach: Content-Based Hash

```python
import hashlib

def compute_dedup_hash(date: str, amount: float, name: str, account_id: int) -> str:
    """SHA-256 hash of normalized transaction fields."""
    normalized = f"{date}|{amount:.2f}|{name.strip().lower()}|{account_id}"
    return hashlib.sha256(normalized.encode()).hexdigest()
```

### Rules
1. Before inserting any transaction, compute `dedup_hash` and check for existing match.
2. If match found → skip (don't duplicate).
3. For Plaid transactions, `plaid_txn_id` is also unique — serves as a secondary dedup key.
4. For file imports, `import_sources.file_hash` detects re-uploading the exact same file → warn user before re-processing.
5. Edge case: two legitimate transactions with identical date/amount/name (e.g., two $5.00 coffees on the same day) — we add a sequence counter or use the Plaid transaction ID to differentiate. For manual/CSV imports, we show a "possible duplicate" warning rather than silently deduping.

### Regression Tests Required
- Same CSV imported twice → 0 new transactions on second import.
- Same Plaid sync run twice → 0 duplicates.
- Two legitimate same-day, same-amount transactions → both kept.
- PDF re-upload with same content → warning shown.

---

## 7. Data Flow Diagram

```
┌─────────────────────────────────────────────────────────┐
│                    YOUR HOME NETWORK                     │
│                                                          │
│  ┌──────────┐    HTTP (LAN only)    ┌──────────────────┐│
│  │  Phone / │◄────────────────────►│  Mac Mini / PC    ││
│  │  Laptop  │   :8000               │                   ││
│  └──────────┘                       │  ┌─────────────┐  ││
│                                     │  │  FastAPI     │  ││
│                                     │  │  + React SPA │  ││
│                                     │  └──────┬──────┘  ││
│                                     │         │         ││
│                                     │  ┌──────▼──────┐  ││
│                                     │  │  SQLCipher   │  ││
│                                     │  │  (encrypted) │  ││
│                                     │  └─────────────┘  ││
│                                     └──────────────────┘││
└───────────────────────────┬─────────────────────────────┘
                            │ HTTPS (outbound only)
                ┌───────────┼───────────┐
                ▼           ▼           ▼
          ┌──────────┐ ┌─────────┐ ┌──────────┐
          │  Plaid   │ │ Claude  │ │ Google   │
          │  API     │ │ API     │ │ Sheets   │
          │(bank/CC) │ │(parsing)│ │ API      │
          └──────────┘ └─────────┘ └──────────┘

          Plaid: bank auth + transaction sync
          Claude: PDF/image statement parsing
          Google: Sheets import (read-only)
```

---

## 8. Open Questions

1. **Target OS**: Mac Mini only, or do you need Windows support too? (Affects packaging/auto-start approach, not the core code.)

2. **Plaid Trial plan**: Are you OK with the 10-Item limit (free), or do you foresee needing more connected accounts? If 10 is enough, we avoid any Plaid costs entirely.

3. **Google Sheets import**: Do you actively use Google Sheets for financial tracking today? If not, we can defer this to a later phase and focus on CSV/Excel/PDF first.

4. **Currency**: Primarily CAD? Do you have USD accounts too? (Affects display formatting and potential multi-currency logic.)

5. **Auth on LAN**: Simple username/password is the plan. Do you want multi-user support (e.g., family members with separate logins), or single-user is fine?

6. **Auto-start**: Should the app auto-launch on boot (macOS LaunchAgent / Windows Task Scheduler), or are you fine manually starting it?

7. **Budget alerts**: Do you want notifications (email, push, etc.) when approaching budget limits, or is the dashboard view sufficient?

8. **Existing data**: Do you have existing financial data in spreadsheets/CSVs that you'd want to import on day one? If so, could you share a sample (redacted) so I can tailor the parser?

---

## Next Steps (pending your answers)

Once you approve this architecture (or request changes), I'll proceed to:
1. Create the GitHub repo (need PAT with `repo` scope — the one provided has `read` but not `create` permission)
2. Build Phase 1: Core backend (SQLCipher DB, models, auth, Plaid integration)
3. Build Phase 2: Import pipeline (CSV/Excel/PDF with AI parsing + dedup)
4. Build Phase 3: Dashboard UI (charts, analytics, budget tracking)
5. Regression tests for parsing, dedup, and analytics math
