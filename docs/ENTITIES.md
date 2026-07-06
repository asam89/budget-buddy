# Entities, Splits & Rules

## Overview

An **Entity** represents a financial ledger — a distinct area of your finances you want to track independently. Examples:
- "House" (household expenses)
- "Airbnb — 123 Main St" (rental property income & expenses)
- "Consulting LLC" (business ledger)

Every transaction belongs to exactly one entity, or is **split** across multiple entities (e.g., a shared utility bill).

## Data Model

### Entity

| Field | Type | Description |
|-------|------|-------------|
| `name` | String (unique) | Display name |
| `entity_type` | String | `household`, `rental`, `business`, or `other` |
| `is_default` | Boolean | Fallback for untagged transactions (only one entity can be default) |
| `color` / `icon` | String | UI customization |
| `is_active` | Boolean | Soft-delete; inactive entities are hidden from dropdowns |

### Transaction Changes

Two new columns on `transactions`:

| Field | Type | Description |
|-------|------|-------------|
| `entity_id` | FK → entities.id | Which entity owns this transaction (NULL if split) |
| `txn_type` | String | `expense`, `income`, or `transfer` — inferred from amount sign on import |
| `entity_source` | String | How the entity was assigned: `rule`, `default`, or `manual` |

### Transaction Splits

For shared expenses (e.g., a $200 hydro bill split 70/30 between House and Airbnb):

| Field | Type | Description |
|-------|------|-------------|
| `transaction_id` | FK → transactions.id | Parent transaction |
| `entity_id` | FK → entities.id | Which entity owns this portion |
| `amount` | Float | Signed amount (same convention as Transaction.amount) |
| `percent` | Float (optional) | If set, amount is derived from percent × parent amount |

**Rules:**
- A transaction has EITHER `entity_id` (whole transaction → one entity) OR ≥2 split rows. Never both.
- Split amounts must sum to the parent transaction amount (validated to the cent).
- All analytics attribute split portions to their respective entities.

### Example: Splitting a Utility Bill

```
Transaction: Hydro Bill, $200.00

Split 1: House    → $140.00 (70%)
Split 2: Airbnb   → $60.00  (30%)
                    --------
Total:              $200.00  ✓
```

In the House dashboard, this shows as a $140 expense. In Airbnb's dashboard, $60.

## Entity Rules (Auto-Tagging)

Rules automatically assign entities to transactions during import or Plaid sync.

| Field | Type | Description |
|-------|------|-------------|
| `entity_id` | FK | Target entity |
| `field` | String | Which transaction field to match: `name`, `merchant_name`, `account_id`, `category_id` |
| `operator` | String | `contains`, `equals`, or `starts_with` |
| `value` | String | Value to match against |
| `priority` | Integer | Lower runs first; first match wins |

### Example Rules

| Priority | Field | Operator | Value | Entity |
|----------|-------|----------|-------|--------|
| 10 | `account_id` | `equals` | `5` | Airbnb |
| 50 | `name` | `contains` | `airbnb` | Airbnb |
| 100 | `name` | `contains` | `rental insurance` | Airbnb |

With these rules:
- Everything on account #5 (the Airbnb credit card) automatically goes to the Airbnb entity.
- Any transaction mentioning "airbnb" in the name goes to Airbnb.
- Everything else falls through to the default entity (House).

### Retroactive Application

Rules can be applied retroactively to existing transactions:
1. **Dry-run** (`POST /api/entities/{id}/rules/apply`) — preview how many transactions would be reassigned, with a sample of 10.
2. **Commit** (`POST /api/entities/{id}/rules/apply/commit`) — actually reassign the matched transactions.

## API Endpoints

### Entity CRUD
- `GET /api/entities/` — list all entities
- `POST /api/entities/` — create entity
- `GET /api/entities/{id}` — get entity
- `PUT /api/entities/{id}` — update entity
- `DELETE /api/entities/{id}` — deactivate entity (soft-delete)

### Entity Rules
- `GET /api/entities/{id}/rules` — list rules for entity
- `POST /api/entities/{id}/rules` — create rule
- `DELETE /api/entities/{id}/rules/{rule_id}` — delete rule
- `POST /api/entities/{id}/rules/apply` — dry-run rule application
- `POST /api/entities/{id}/rules/apply/commit` — commit rule application

### Transaction Entity Operations
- `PATCH /api/transactions/{id}/entity?entity_id=X` — assign entity to transaction
- `PUT /api/transactions/{id}/splits` — set splits (replaces entity_id)
- `DELETE /api/transactions/{id}/splits` — remove splits (reverts to default entity)
- `POST /api/transactions/bulk-entity` — bulk-assign entity to multiple transactions

### Dashboard
- `GET /api/dashboard/summary?entity_id=X` — filtered dashboard for one entity
- `GET /api/dashboard/entity-breakdown?months=N` — per-entity income/expense/net breakdown

### Saved Views
- `GET /api/entities/views/all` — list saved views
- `POST /api/entities/views` — create saved view
- `PUT /api/entities/views/{id}` — update saved view
- `DELETE /api/entities/views/{id}` — delete saved view

## Migration

The initial migration (`alembic/versions/001_...`) creates all new tables and:
1. Seeds two entities: **House** (default, type=household) and **Airbnb** (type=rental)
2. Seeds two saved views: "House — this month" and "Airbnb — this month"
3. Backfills all existing transactions to the House entity with `entity_source='default'`

Run migrations on your existing database:
```bash
source .venv/bin/activate
alembic upgrade head
```
