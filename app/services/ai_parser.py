import hashlib
import io
import json
import logging
from datetime import date, datetime

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Transaction, ImportSource
from app.services.rule_engine import apply_rules_to_transaction, infer_txn_type

logger = logging.getLogger(__name__)

EXTRACTION_PROMPT = """You are a financial document parser. Extract all transactions from the following bank/credit card statement text.

Return a JSON array where each object has these fields:
- "date": transaction date in YYYY-MM-DD format
- "amount": numeric amount (positive for debits/expenses, negative for credits/income)
- "name": transaction description
- "merchant_name": merchant or payee name if identifiable (null otherwise)
- "category": spending category if obvious (e.g. "Groceries", "Dining", "Gas", "Salary") or null

Only return valid JSON. No markdown fencing. If you cannot extract any transactions, return an empty array [].

Statement text:
{text}"""


def parse_statement_text(
    db: Session,
    text: str,
    filename: str,
    account_id: int,
) -> ImportSource:
    settings = get_settings()
    if not settings.anthropic_api_key:
        source = ImportSource(
            source_type="pdf",
            filename=filename,
            status="failed",
            error_message="ANTHROPIC_API_KEY not configured",
        )
        db.add(source)
        db.commit()
        return source

    import anthropic

    content_hash = hashlib.sha256(text.encode()).hexdigest()

    source = ImportSource(
        source_type="pdf",
        filename=filename,
        file_hash=content_hash,
        status="processing",
    )
    db.add(source)
    db.flush()

    try:
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=4096,
            messages=[
                {"role": "user", "content": EXTRACTION_PROMPT.format(text=text[:8000])}
            ],
        )

        response_text = message.content[0].text.strip()
        if response_text.startswith("```"):
            response_text = response_text.split("\n", 1)[1].rsplit("```", 1)[0]

        transactions_data = json.loads(response_text)

        added = 0
        for item in transactions_data:
            try:
                txn_date = datetime.strptime(item["date"], "%Y-%m-%d").date()
                amount = float(item["amount"])
                name = str(item["name"]).strip()
            except (KeyError, ValueError, TypeError):
                continue

            dedup = Transaction.compute_dedup_hash(txn_date, amount, name, account_id)
            if db.query(Transaction).filter(Transaction.dedup_hash == dedup).first():
                continue

            # AI parser does NOT auto-assign entities — entity assignment
            # follows the rule engine only, per the review-gate philosophy.
            txn = Transaction(
                account_id=account_id,
                import_source_id=source.id,
                amount=amount,
                txn_type=infer_txn_type(amount),
                date=txn_date,
                name=name,
                merchant_name=item.get("merchant_name"),
                review_status="pending",
                review_source="ai_parsed",
                confidence=0.8,
                source_file=filename,
                dedup_hash=dedup,
            )
            db.add(txn)
            db.flush()
            apply_rules_to_transaction(db, txn)
            added += 1

        source.record_count = added
        source.status = "completed"
        db.commit()

    except json.JSONDecodeError as e:
        source.status = "failed"
        source.error_message = f"Failed to parse AI response as JSON: {e}"
        db.commit()
    except Exception as e:
        logger.exception("AI parsing failed")
        source.status = "failed"
        source.error_message = str(e)
        db.commit()

    return source


def extract_text_from_pdf(content: bytes) -> str:
    import pypdf

    reader = pypdf.PdfReader(io.BytesIO(content))
    text_parts = []
    for page in reader.pages:
        text = page.extract_text()
        if text:
            text_parts.append(text)
    return "\n".join(text_parts)
