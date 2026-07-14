"""AI-powered statement parsing — uses LLMProvider abstraction."""

import hashlib
import io
import json
import logging
from datetime import date, datetime

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Transaction, ImportSource, AppSetting
from app.services.llm import get_provider, LLMProvider
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


def _get_llm_provider(db: Session) -> LLMProvider | None:
    """Build LLM provider from config, with DB overrides."""
    settings = get_settings()

    # DB settings override env vars
    provider_name = settings.llm_provider
    ollama_model = settings.ollama_model
    ollama_base_url = settings.ollama_base_url

    for row in db.query(AppSetting).filter(
        AppSetting.key.in_(["llm_provider", "ollama_model", "ollama_base_url"])
    ).all():
        if row.key == "llm_provider":
            provider_name = row.value
        elif row.key == "ollama_model":
            ollama_model = row.value
        elif row.key == "ollama_base_url":
            ollama_base_url = row.value

    return get_provider(
        provider_name=provider_name,
        ollama_base_url=ollama_base_url,
        ollama_model=ollama_model,
        anthropic_api_key=settings.anthropic_api_key,
        llm_timeout=settings.llm_timeout_seconds,
    )


def parse_statement_text(
    db: Session,
    text: str,
    filename: str,
    account_id: int,
) -> ImportSource:
    provider = _get_llm_provider(db)
    if not provider:
        source = ImportSource(
            source_type="pdf",
            filename=filename,
            status="failed",
            error_message="No LLM provider configured (set LLM_PROVIDER and ensure Ollama is running or ANTHROPIC_API_KEY is set)",
        )
        db.add(source)
        db.commit()
        return source

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
        prompt = EXTRACTION_PROMPT.format(text=text[:8000])
        transactions_data = provider.complete_json(prompt)

        if not isinstance(transactions_data, list):
            raise ValueError(f"Expected JSON array, got {type(transactions_data).__name__}")

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
        source.error_message = f"Failed to parse LLM response as JSON: {e}"
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
