# Sending spending into Budget Buddy

Three ways to record everyday spending (leisure, cash, odds and ends):

| Way | Best for | Lands as |
|-----|----------|----------|
| **Add spending** button (sidebar) or the `/add` page | Typing it in, on a computer or phone | Saved straight away |
| **Snap or upload receipt** (in the same form) | Paper receipts, PDF receipts | Saved after you check the details |
| **Connected tools** (API token) | Muse, an iPhone Shortcut, scripts | Waiting on the **Review** page |

Everything is recorded as an expense on the **Everyday spending** account, so it
flows into the Expenses grid, the dashboard and reports like any other
transaction.

> **One thing to know:** on the Expenses page, a line's actual for a month is
> *either* a number you typed into the cell *or* the sum of its transactions,
> never both. If you typed an actual for a line, spending entries for that
> line and month won't change the total until you clear that cell. The form
> warns you when that happens.

## 1. Quick add

- **Computer:** click **Add spending** at the top of the sidebar.
- **Phone:** open `https://<your-budget-buddy>/add`, then in Safari tap
  **Share → Add to Home Screen**. It opens straight to the form.

Enter the amount, what it was, a category and a business. The form remembers
your last category and business. Choose **+ New category…** to create one,
e.g. **Leisure & Misc**, then set a monthly budget for it on the Expenses page
to track spending against an allowance.

## 2. Receipts

In the same form, tap **Snap or upload receipt** (on a phone you can take a
photo or pick one), or drop a photo or PDF onto it.

- Your AI provider (Settings → AI provider) reads the store, date, total and a
  suggested category, and fills in the form. **With Ollama nothing leaves the
  Mac mini.** With Claude, the receipt image is sent to Anthropic.
- Check the details and tap **Save spending**. Nothing is recorded before that.
- The receipt is stored inside the encrypted database. A paperclip next to the
  transaction (Transactions and Review pages) opens it.
- Uploading the same file twice is recognised, so a receipt is never recorded
  twice.
- Photos up to 10 MB: JPEG, PNG, WebP, or PDF. iPhone HEIC photos are accepted
  for storage. If one can't be read, set **Settings → Camera → Formats → Most
  Compatible** or upload a screenshot.
- The AI needs a vision-capable model. `gemma3` (the default) is one.

## 3. Connected tools (API tokens)

An admin creates a token in **Settings → Connected tools**. Give it a name
(e.g. "Muse"). The token is shown once; copy it into the tool. Revoke it any
time and the tool stops working immediately.

Tokens can **only** add spending for review. They can't read your data or
change anything else. Only a hash of each token is stored.

### The request

```
POST https://<your-budget-buddy>/api/ingest/spending
Authorization: Bearer bb_xxxxxxxx
Content-Type: application/json
```

```json
{
  "amount": 24.50,
  "merchant": "Cineplex",
  "description": "Movie night",
  "date": "2026-11-25",
  "category": "Leisure & Misc",
  "business": "Personal",
  "notes": "with Sam",
  "external_id": "email-8f3a2c",
  "receipt_base64": "<optional base64 of a JPEG/PNG/PDF>",
  "receipt_filename": "cineplex.jpg"
}
```

| Field | Required | Notes |
|-------|----------|-------|
| `amount` | yes | Positive number, the amount spent |
| `merchant` or `description` | one of them | What it was |
| `date` | no | `YYYY-MM-DD`; defaults to today |
| `category` | no | Matched to an expense line by name (exact, then partial). Unmatched names are kept in the notes for you |
| `business` | no | Matched to a business by name; defaults to your default business |
| `external_id` | recommended | Your own ID for this item (e.g. the email's message ID). Sending the same one again returns the existing item instead of a duplicate, even after it's approved |
| `receipt_base64` | no | Receipt file, base64-encoded, up to 10 MB |

Response:

```json
{"id": 412, "status": "pending", "duplicate": false,
 "category_matched": "Leisure & Misc", "business_matched": "Personal"}
```

`401` means a missing, wrong or revoked token. `422` means the data was
rejected (the message says why).

### Test it with curl

```bash
curl -X POST "https://<your-budget-buddy>/api/ingest/spending" \
  -H "Authorization: Bearer bb_xxxxxxxx" \
  -H "Content-Type: application/json" \
  -d '{"amount": 12.75, "merchant": "Test Cafe", "external_id": "test-1"}'
```

Then open **Review**: the item is waiting there.

### iPhone: log every Apple Pay tap automatically

The Shortcuts app can run when you pay with Apple Pay and send the merchant
and amount to Budget Buddy. Your phone must be able to reach Budget Buddy (e.g.
Tailscale on the phone).

1. Create a token named "iPhone" in Settings → Connected tools.
2. Open **Shortcuts → Automation → New Automation → Transaction** (also called
   Wallet). Pick your cards, choose **Run Immediately**, then **New Blank
   Automation**.
3. Add **Get Contents of URL**:
   - URL: `https://<your-budget-buddy>/api/ingest/spending`
   - Method: **POST**
   - Headers: `Authorization` = `Bearer bb_…`
   - Request Body: **JSON** with `amount` = the **Amount** variable and
     `merchant` = the **Merchant** variable (both come from the Transaction
     trigger). Optionally add `category` = `Leisure & Misc`.
4. Tap a card to pay. The purchase appears on the Review page; approve it there.

Apple's menu names change between iOS versions; if a step looks different,
look for the automation trigger that runs "when I tap a card in Wallet".

### Muse or an email job

Any tool that can make an HTTP request works the same way: parse the email or
receipt, then POST the fields above. Use the email's message ID as
`external_id`, so re-running the job never creates duplicates.
