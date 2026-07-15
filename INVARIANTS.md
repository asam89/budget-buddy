# Budget Buddy — Invariants

Rules that must hold across the app. Every PR states which of these it touches
and how they are protected.

## Data & security
1. The local database is encrypted at rest with SQLCipher; the passphrase is never committed.
2. No raw banking credentials are stored. `.env` is never committed.
3. AI-created transactions are written with `review_status="pending"`.
4. Transaction deduplication uses `SHA-256(date|amount|normalized_name|account_id)`.

## Manual actuals & saved (PRs #18–#21)
5. Manual actuals are explicit user data. Imports, rules, and background jobs never create them.
6. A manual actual, if present, is the effective actual for that category/month; the transaction sum stays available as reference. Manual and transaction actuals are never added together.
7. Manual amounts are stored non-negative; sign is derived from `Category.kind` (income adds, expense subtracts).
8. `saved = income − expenses`, derived from the same effective-actual aggregation everywhere it appears.

## No catch-all category (Expenses spec, WS-A)
9. No catch-all category exists. Anything uncategorizable waits in the review queue for explicit assignment. The name "Other" is reserved and rejected server-side (creation via the categories API or budget-setup commit fails with a validation error).
10. Budget-setup imports never auto-file into a catch-all; lines without a confident category surface for review, and a commit is rejected until every line has a real category.

## Trend views & AI insights (Expenses spec, WS-C/WS-D)
11. Trend views and insights are projections of the effective-actual aggregation layer; they store no figures.
12. The AI summary is prose over deterministically computed findings; the model receives the findings payload only. No financial data reaches a hosted provider unless the hosted provider is explicitly selected in settings. Local-model failure degrades to deterministic findings, never a silent hosted fallback.
13. Insights are advisory and side-effect free; generation never mutates financial data.

## Navigation
14. Navigation consolidation removes entry points, never capabilities; every pre-consolidation route redirects to its successor.
