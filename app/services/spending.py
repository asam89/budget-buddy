"""Everyday spending: quick add, receipt scanning, and the token-based inbox.

All three create ordinary expense transactions on one manual account
("Everyday spending"), so they flow into the Expenses grid like any other
transaction:

* Quick add and scanned receipts are saved as confirmed. The person reviewed
  the details in the form before saving.
* Items pushed by outside tools (Muse, an iPhone Shortcut) arrive as
  ``pending`` and wait on the Review page.

Receipt files are stored inside the encrypted database. A file uploaded twice
(same SHA-256) is not stored twice.
"""

import hashlib
import io
import logging
import re
import secrets
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import Account, ApiToken, Category, Entity, ManualActual, Receipt, Transaction

logger = logging.getLogger(__name__)

SPENDING_ACCOUNT_NAME = "Everyday spending"
MAX_RECEIPT_BYTES = 10 * 1024 * 1024
RECEIPT_TYPES = {"image/jpeg", "image/png", "image/webp", "image/heic", "image/heif", "application/pdf"}
ORPHAN_RECEIPT_TTL = timedelta(hours=24)
MAX_IMAGE_SIDE = 1600
TOKEN_PREFIX = "bb_"

RECEIPT_PROMPT = """You are reading a photo or scan of a purchase receipt.
Return ONLY a JSON object with these keys:
  "merchant": the store or business name, or null
  "date": purchase date as YYYY-MM-DD, or null if not visible
  "total": the final amount paid as a number (after tax and tips), or null
  "tax": total tax as a number, or null
  "currency": 3-letter currency code if shown (e.g. "CAD"), or null
  "category": one short spending category, e.g. "Dining", "Groceries", "Entertainment",
              "Gas", "Shopping", "Leisure", or null
  "summary": a few words describing what was bought, or null
Use null rather than guessing. Do not include any other text."""


class SpendingError(ValueError):
    pass


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def spending_account(db: Session) -> Account:
    """The manual account all everyday spending is recorded against (created once)."""
    acct = db.query(Account).filter(Account.name == SPENDING_ACCOUNT_NAME,
                                    Account.plaid_account_id.is_(None)).first()
    if acct is None:
        acct = Account(name=SPENDING_ACCOUNT_NAME, account_type="manual",
                       account_subtype="everyday", current_balance=0.0)
        db.add(acct)
        db.flush()
    return acct


def _default_entity_id(db: Session) -> Optional[int]:
    e = db.query(Entity).filter(Entity.is_default == True).first()  # noqa: E712
    return e.id if e else None


def _clean_amount(amount) -> float:
    try:
        value = round(float(amount), 2)
    except (TypeError, ValueError):
        raise SpendingError("Amount must be a number")
    if value <= 0:
        raise SpendingError("Amount must be more than zero")
    if value > 1_000_000:
        raise SpendingError("Amount looks too large")
    return value


def _expense_category(db: Session, category_id: Optional[int]) -> Optional[Category]:
    if category_id is None:
        return None
    cat = db.get(Category, category_id)
    if cat is None or cat.kind != "expense":
        raise SpendingError("Pick an expense category")
    return cat


def find_category(db: Session, name: Optional[str]) -> Optional[Category]:
    """Best expense-category match for a free-text name (exact, then partial)."""
    n = (name or "").strip().lower()
    if not n:
        return None
    cats = db.query(Category).filter(Category.kind == "expense").all()
    for c in cats:
        if c.name.lower() == n:
            return c
    for c in cats:
        cn = c.name.lower()
        if n in cn or cn in n:
            return c
    return None


def find_entity(db: Session, name: Optional[str]) -> Optional[Entity]:
    n = (name or "").strip().lower()
    if not n:
        return None
    return db.query(Entity).filter(func.lower(Entity.name) == n, Entity.is_active == True).first()  # noqa: E712


def manual_actual_overrides(db: Session, txn: Transaction) -> bool:
    """True when a typed-in actual for this line and month hides transaction totals."""
    if txn.category_id is None:
        return False
    ym = txn.date.strftime("%Y-%m")
    q = db.query(ManualActual).filter(ManualActual.category_id == txn.category_id,
                                      ManualActual.year_month == ym)
    if txn.entity_id is not None:
        q = q.filter(ManualActual.entity_id == txn.entity_id)
    return q.first() is not None


# ---------------------------------------------------------------------------
# Receipts
# ---------------------------------------------------------------------------

def _sniff_type(data: bytes, declared: Optional[str]) -> str:
    if data[:4] == b"%PDF":
        return "application/pdf"
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data[4:12] in (b"ftypheic", b"ftypheix", b"ftypmif1", b"ftypmsf1", b"ftypheif"):
        return "image/heic"
    return (declared or "").lower()


def store_receipt(db: Session, data: bytes, filename: Optional[str], content_type: Optional[str]) -> Receipt:
    """Validate and store a receipt file (deduplicated by content)."""
    if not data:
        raise SpendingError("The file is empty")
    if len(data) > MAX_RECEIPT_BYTES:
        raise SpendingError("Receipts must be 10 MB or smaller")
    ctype = _sniff_type(data, content_type)
    if ctype not in RECEIPT_TYPES:
        raise SpendingError("Upload a photo (JPEG, PNG, WebP, HEIC) or a PDF")
    digest = hashlib.sha256(data).hexdigest()
    existing = db.query(Receipt).filter(Receipt.sha256 == digest).first()
    if existing is not None:
        return existing
    # Tidy up receipts that were scanned but never saved with a transaction.
    cutoff = datetime.utcnow() - ORPHAN_RECEIPT_TTL
    linked = db.query(Transaction.receipt_id).filter(Transaction.receipt_id.isnot(None))
    db.query(Receipt).filter(Receipt.created_at < cutoff, ~Receipt.id.in_(linked)).delete(synchronize_session=False)
    r = Receipt(sha256=digest, filename=(filename or "")[:200] or None, content_type=ctype,
                size=len(data), data=data)
    db.add(r)
    db.flush()
    return r


def receipt_transaction(db: Session, receipt_id: int) -> Optional[Transaction]:
    return db.query(Transaction).filter(Transaction.receipt_id == receipt_id).first()


def _image_for_model(data: bytes, ctype: str) -> tuple[bytes, str]:
    """Downscale big photos (faster, cheaper) and convert to JPEG for the model."""
    from PIL import Image, ImageOps

    try:
        img = Image.open(io.BytesIO(data))
    except Exception:
        if ctype in ("image/heic", "image/heif"):
            raise SpendingError("HEIC photos can't be read here. On iPhone, set Camera > Formats > "
                                "Most Compatible, or upload a screenshot.")
        raise SpendingError("Couldn't open that image")
    img = ImageOps.exif_transpose(img).convert("RGB")
    img.thumbnail((MAX_IMAGE_SIDE, MAX_IMAGE_SIDE))
    out = io.BytesIO()
    img.save(out, format="JPEG", quality=85)
    return out.getvalue(), "image/jpeg"


def _parse_date(value) -> Optional[date]:
    if not value:
        return None
    try:
        d = date.fromisoformat(str(value)[:10])
    except ValueError:
        return None
    today = date.today()
    if d > today + timedelta(days=2) or d < today - timedelta(days=3 * 365):
        return None  # implausible: let the person fill it in
    return d


def _parse_money(value) -> Optional[float]:
    if value is None:
        return None
    try:
        v = round(float(re.sub(r"[^0-9.\-]", "", str(value))), 2)
    except ValueError:
        return None
    return v if 0 < v < 1_000_000 else None


@dataclass
class ReceiptDraft:
    receipt_id: int
    merchant: Optional[str] = None
    date: Optional[str] = None
    total: Optional[float] = None
    tax: Optional[float] = None
    currency: Optional[str] = None
    category_id: Optional[int] = None
    category_guess: Optional[str] = None
    summary: Optional[str] = None
    warnings: list[str] = field(default_factory=list)
    already_saved_transaction_id: Optional[int] = None


def scan_receipt(db: Session, receipt: Receipt, provider) -> ReceiptDraft:
    """Read merchant/date/total from a stored receipt. Never raises for AI trouble."""
    draft = ReceiptDraft(receipt_id=receipt.id)
    done = receipt_transaction(db, receipt.id)
    if done is not None:
        draft.already_saved_transaction_id = done.id
        draft.warnings.append("This receipt was already saved.")
    if provider is None:
        draft.warnings.append("No AI provider is set up, so fill in the details yourself.")
        return draft
    try:
        if receipt.content_type == "application/pdf":
            from app.services.ai_parser import extract_text_from_pdf
            text = extract_text_from_pdf(receipt.data)[:8000]
            if not text.strip():
                draft.warnings.append("That PDF has no readable text. Fill in the details yourself.")
                return draft
            result = provider.complete_json(f"{RECEIPT_PROMPT}\n\nReceipt text:\n{text}", max_tokens=600)
        else:
            image, media_type = _image_for_model(receipt.data, receipt.content_type)
            result = provider.complete_json_image(RECEIPT_PROMPT, image, media_type, max_tokens=600)
    except SpendingError as e:
        draft.warnings.append(str(e))
        return draft
    except Exception as e:  # model down, timeout, bad JSON
        logger.warning("Receipt scan failed: %s", e)
        draft.warnings.append("Couldn't read the receipt automatically. Fill in the details yourself.")
        return draft
    if not isinstance(result, dict):
        draft.warnings.append("Couldn't read the receipt automatically. Fill in the details yourself.")
        return draft

    draft.merchant = (str(result.get("merchant") or "").strip() or None)
    d = _parse_date(result.get("date"))
    draft.date = d.isoformat() if d else None
    draft.total = _parse_money(result.get("total"))
    draft.tax = _parse_money(result.get("tax"))
    cur = str(result.get("currency") or "").strip().upper()
    draft.currency = cur if re.fullmatch(r"[A-Z]{3}", cur) else None
    draft.category_guess = (str(result.get("category") or "").strip() or None)
    cat = find_category(db, draft.category_guess)
    draft.category_id = cat.id if cat else None
    draft.summary = (str(result.get("summary") or "").strip()[:200] or None)
    if draft.total is None:
        draft.warnings.append("Couldn't find the total. Please check the amount.")
    if draft.currency and draft.currency != "CAD":
        draft.warnings.append(f"Receipt looks like it's in {draft.currency}; amounts are recorded as entered.")
    return draft


# ---------------------------------------------------------------------------
# Saving spending
# ---------------------------------------------------------------------------

def record_spending(
    db: Session,
    *,
    amount,
    description: str,
    on_date: Optional[date] = None,
    merchant: Optional[str] = None,
    category_id: Optional[int] = None,
    new_category: Optional[str] = None,
    entity_id: Optional[int] = None,
    notes: Optional[str] = None,
    receipt_id: Optional[int] = None,
    source: str = "manual",
    pending: bool = False,
    external_id: Optional[str] = None,
    confidence: Optional[float] = None,
) -> tuple[Transaction, bool]:
    """Create one expense. Returns (transaction, created). created=False means a
    duplicate external_id or an already-saved receipt returned the existing one."""
    value = _clean_amount(amount)
    name = (description or merchant or "").strip()
    if not name:
        raise SpendingError("Say what it was for")
    on_date = on_date or date.today()
    if on_date > date.today() + timedelta(days=2):
        raise SpendingError("Date is in the future")

    dedup = None
    if external_id:
        ext = str(external_id).strip()[:200]
        dedup = "ext:" + hashlib.sha256(f"{source}:{ext}".encode()).hexdigest()
        existing = db.query(Transaction).filter(Transaction.dedup_hash == dedup).first()
        if existing is not None:
            return existing, False

    if receipt_id is not None:
        if db.get(Receipt, receipt_id) is None:
            raise SpendingError("That receipt wasn't found. Upload it again.")
        done = receipt_transaction(db, receipt_id)
        if done is not None:
            return done, False

    cat = _expense_category(db, category_id)
    if cat is None and (new_category or "").strip():
        cat = find_category(db, new_category)
        if cat is None or cat.name.lower() != new_category.strip().lower():
            cat = Category(name=new_category.strip()[:80], kind="expense", entity_id=None)
            db.add(cat)
            db.flush()

    if entity_id is not None:
        ent = db.get(Entity, entity_id)
        if ent is None or not ent.is_active:
            raise SpendingError("Unknown business")
    ent_id = entity_id or _default_entity_id(db)

    txn = Transaction(
        account_id=spending_account(db).id,
        amount=value,
        date=on_date,
        name=name[:200],
        merchant_name=(merchant or "").strip()[:200] or None,
        category_id=cat.id if cat else None,
        entity_id=ent_id,
        entity_source="manual" if entity_id else "default",
        txn_type="expense",
        notes=(notes or "").strip() or None,
        review_status="pending" if pending else "confirmed",
        review_source=source,
        confidence=confidence,
        dedup_hash=dedup,
        receipt_id=receipt_id,
    )
    db.add(txn)
    db.commit()
    db.refresh(txn)
    return txn, True


# ---------------------------------------------------------------------------
# API tokens
# ---------------------------------------------------------------------------

def _token_hash(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def create_api_token(db: Session, name: str, created_by: int) -> tuple[str, ApiToken]:
    label = (name or "").strip()[:80]
    if not label:
        raise SpendingError("Give the token a name, e.g. 'Muse' or 'iPhone Shortcut'")
    raw = TOKEN_PREFIX + secrets.token_urlsafe(32)
    row = ApiToken(name=label, token_hash=_token_hash(raw), prefix=raw[:10], created_by=created_by)
    db.add(row)
    db.commit()
    db.refresh(row)
    return raw, row


def check_api_token(db: Session, raw: str) -> Optional[ApiToken]:
    if not raw or not raw.startswith(TOKEN_PREFIX):
        return None
    row = db.query(ApiToken).filter(ApiToken.token_hash == _token_hash(raw),
                                    ApiToken.revoked_at.is_(None)).first()
    if row is not None:
        row.last_used_at = datetime.utcnow()
        db.commit()
    return row
