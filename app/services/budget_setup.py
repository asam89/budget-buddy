"""AI-assisted budget setup.

Turns a summary budget spreadsheet (expense line items with totals) into
monthly budget targets. A local LLM proposes a category and a
period-normalized monthly amount for each line; everything goes through a
review gate before any Budget rows are written.
"""

import logging
import re
from typing import Optional

import pandas as pd
from sqlalchemy.orm import Session

from app.models import Budget, Category
from app.services.ai_parser import _get_llm_provider
from app.services.llm import LLMProvider
from app.services.sheet_mapper import clean_dataframe, detect_header_row, _safe_float

logger = logging.getLogger(__name__)


# Multiply a source amount by this factor to get a monthly figure.
PERIOD_TO_MONTHLY = {
    "annual": 1 / 12,
    "yearly": 1 / 12,
    "year": 1 / 12,
    "quarterly": 1 / 3,
    "quarter": 1 / 3,
    "monthly": 1.0,
    "month": 1.0,
    "semimonthly": 2.0,
    "semi-monthly": 2.0,
    "biweekly": 26 / 12,
    "bi-weekly": 26 / 12,
    "fortnightly": 26 / 12,
    "weekly": 52 / 12,
    "week": 52 / 12,
    "daily": 365 / 12,
    "day": 365 / 12,
}

_PERIOD_WORDS = set(PERIOD_TO_MONTHLY.keys())


BUDGET_PROMPT = """You are a personal-finance assistant helping a user set up a MONTHLY budget from a spreadsheet they already keep.

You are given a list of budget line items. Each has a label, an amount, and sometimes a stated period (e.g. "annual", "weekly").

For EACH item, return an object with these fields:
- "label": a cleaned, human-readable version of the label
- "category": the best-fitting budget category. Strongly prefer one of these EXISTING categories if it fits: {categories}. Only invent a new concise category name if none fit.
- "monthly_amount": the amount normalized to a MONTHLY number. Rules: annual -> divide by 12; quarterly -> divide by 3; weekly -> multiply by 4.333; biweekly -> multiply by 2.167; daily -> multiply by 30.4. If the period is unclear, assume the amount is already monthly.
- "period": what you judged the source period to be: one of "monthly","annual","quarterly","weekly","biweekly","daily","unknown".
- "kind": "expense" or "income"
- "confidence": a number from 0.0 to 1.0
- "note": a short reason when the item is ambiguous, otherwise ""

Return ONLY valid JSON in this exact shape, preserving the input order:
{{"items": [{{"label": "...", "category": "...", "monthly_amount": 0, "period": "...", "kind": "expense", "confidence": 0.9, "note": ""}}]}}

Input line items:
{items}
"""


def parse_budget_dataframe(df_raw: pd.DataFrame) -> list[dict]:
    """Extract raw budget line items (label, amount, period hint) from a sheet.

    Deterministic pre-pass — no AI. Detects the label column (text), the
    amount column (numeric), and an optional period column.
    """
    header_row = detect_header_row(df_raw)
    if header_row > 0:
        df = df_raw.iloc[header_row + 1:].reset_index(drop=True)
        df.columns = [str(c).strip() for c in df_raw.iloc[header_row]]
    else:
        df = df_raw.copy()
        df.columns = [str(c).strip() for c in df_raw.iloc[0]]
        df = df.iloc[1:].reset_index(drop=True)

    df = clean_dataframe(df)
    if df.empty or len(df.columns) == 0:
        return []

    # Score columns: how many values parse as numbers vs look like period words.
    amount_col = None
    best_numeric = 0.0
    period_col = None
    best_period = 0.0
    for col in df.columns:
        series = df[col].dropna()
        if len(series) == 0:
            continue
        sample = series.head(20)
        num_ok = sum(1 for v in sample if _safe_float(v) is not None)
        num_rate = num_ok / len(sample)
        if num_rate > best_numeric:
            best_numeric = num_rate
            amount_col = col
        period_ok = sum(1 for v in sample if _looks_like_period(v))
        period_rate = period_ok / len(sample)
        if period_rate > best_period and period_rate >= 0.5:
            best_period = period_rate
            period_col = col

    if amount_col is None:
        return []

    # Label column: text column (not amount/period) with the longest strings.
    label_col = None
    best_len = -1.0
    for col in df.columns:
        if col in (amount_col, period_col):
            continue
        series = df[col].dropna().astype(str)
        if len(series) == 0:
            continue
        num_ok = sum(1 for v in series.head(20) if _safe_float(v) is not None)
        if num_ok / min(len(series), 20) > 0.5:
            continue  # mostly numeric, not a label
        avg_len = sum(len(s) for s in series.head(20)) / min(len(series), 20)
        if avg_len > best_len:
            best_len = avg_len
            label_col = col

    items = []
    for _, row in df.iterrows():
        amount = _safe_float(row.get(amount_col))
        if amount is None:
            continue
        label = ""
        if label_col is not None and pd.notna(row.get(label_col)):
            label = str(row.get(label_col)).strip()
        if not label or label.lower() == "nan":
            continue
        period_hint = None
        if period_col is not None and pd.notna(row.get(period_col)):
            period_hint = _normalize_period(row.get(period_col))
        items.append({
            "label": label,
            "amount": round(amount, 2),
            "period_hint": period_hint,
        })
    return items


def _looks_like_period(val) -> bool:
    return _normalize_period(val) is not None


def _normalize_period(val) -> Optional[str]:
    s = str(val).strip().lower()
    if not s:
        return None
    s = s.rstrip("s")  # months -> month
    s = s.replace(" ", "").replace("/", "")
    for word in _PERIOD_WORDS:
        w = word.rstrip("s").replace(" ", "").replace("-", "").replace("/", "")
        if s == w or s == w.replace("-", ""):
            return _canonical_period(word)
    return None


def _canonical_period(word: str) -> str:
    w = word.lower()
    if w in ("annual", "yearly", "year"):
        return "annual"
    if w in ("quarterly", "quarter"):
        return "quarterly"
    if w in ("monthly", "month"):
        return "monthly"
    if w in ("semimonthly", "semi-monthly"):
        return "semimonthly"
    if w in ("biweekly", "bi-weekly", "fortnightly"):
        return "biweekly"
    if w in ("weekly", "week"):
        return "weekly"
    if w in ("daily", "day"):
        return "daily"
    return "monthly"


def normalize_to_monthly(amount: float, period: Optional[str]) -> float:
    """Convert an amount at a given period into a monthly figure."""
    if not period:
        return round(amount, 2)
    factor = PERIOD_TO_MONTHLY.get(period.lower())
    if factor is None:
        factor = PERIOD_TO_MONTHLY.get(_canonical_period(period), 1.0)
    return round(amount * factor, 2)


def propose_budget(
    db: Session,
    items: list[dict],
    provider: Optional[LLMProvider] = None,
) -> dict:
    """Propose category + monthly amount for each raw line item.

    Uses the local LLM when reachable; otherwise falls back to a
    deterministic heuristic so the flow still works offline.
    """
    existing = [c.name for c in db.query(Category).order_by(Category.name).all()]

    if provider is None:
        provider = _get_llm_provider(db)

    ai_used = False
    assisting_model = None
    proposals: Optional[list[dict]] = None

    if provider is not None:
        assisting_model = provider.name()
        health = provider.health()
        if health.reachable and health.model_available:
            try:
                proposals = _propose_with_llm(provider, items, existing)
                ai_used = True
            except Exception:
                logger.exception("LLM budget proposal failed; using heuristic")
                proposals = None

    if proposals is None:
        proposals = _propose_heuristic(items, existing)

    # Align to input length defensively (LLM may drop/add rows).
    aligned = []
    for i, raw in enumerate(items):
        prop = proposals[i] if i < len(proposals) else {}
        monthly = prop.get("monthly_amount")
        period = prop.get("period") or raw.get("period_hint")
        if monthly is None:
            monthly = normalize_to_monthly(raw["amount"], period)
        aligned.append({
            "label": prop.get("label") or raw["label"],
            "source_amount": raw["amount"],
            "period": period or "monthly",
            "monthly_amount": round(float(monthly), 2),
            "category": prop.get("category") or "Other",
            "kind": prop.get("kind") if prop.get("kind") in ("expense", "income") else "expense",
            "confidence": _clamp_conf(prop.get("confidence")),
            "note": prop.get("note") or "",
        })

    return {
        "ai_used": ai_used,
        "assisting_model": assisting_model,
        "existing_categories": existing,
        "items": aligned,
    }


def _propose_with_llm(
    provider: LLMProvider, items: list[dict], categories: list[str]
) -> list[dict]:
    lines = []
    for it in items:
        period = f", period={it['period_hint']}" if it.get("period_hint") else ""
        lines.append(f"- label={it['label']!r}, amount={it['amount']}{period}")
    prompt = BUDGET_PROMPT.format(
        categories=", ".join(categories) if categories else "(none yet)",
        items="\n".join(lines),
    )
    result = provider.complete_json(prompt)
    if isinstance(result, dict):
        result = result.get("items", [])
    if not isinstance(result, list):
        raise ValueError("LLM did not return a list of items")
    return result


def _propose_heuristic(items: list[dict], categories: list[str]) -> list[dict]:
    lower_cats = {c.lower(): c for c in categories}
    out = []
    for it in items:
        label = it["label"]
        period = it.get("period_hint") or "monthly"
        category = "Other"
        ll = label.lower()
        for kw, cat in lower_cats.items():
            if kw in ll or ll in kw:
                category = cat
                break
        out.append({
            "label": label,
            "category": category,
            "monthly_amount": normalize_to_monthly(it["amount"], period),
            "period": period,
            "kind": "expense",
            "confidence": 0.3,
            "note": "Heuristic (local AI unavailable)",
        })
    return out


def _clamp_conf(val) -> float:
    try:
        c = float(val)
    except (TypeError, ValueError):
        return 0.5
    return max(0.0, min(1.0, round(c, 2)))


def commit_budget(db: Session, items: list[dict]) -> dict:
    """Create categories + monthly Budget targets from reviewed items.

    Expense items are aggregated by category into a single monthly limit and
    upserted onto the active (no year_month) budget for that category. Income
    items are counted but do not create budget limits.
    """
    totals: dict[str, float] = {}
    income_count = 0
    for it in items:
        if it.get("kind") == "income":
            income_count += 1
            continue
        name = str(it.get("category") or "Other").strip() or "Other"
        amount = float(it.get("monthly_amount") or 0)
        totals[name] = round(totals.get(name, 0.0) + amount, 2)

    created_categories = 0
    created_budgets = 0
    updated_budgets = 0

    for cat_name, monthly_limit in totals.items():
        category = db.query(Category).filter(Category.name == cat_name).first()
        if not category:
            category = Category(name=cat_name)
            db.add(category)
            db.flush()
            created_categories += 1

        budget = (
            db.query(Budget)
            .filter(
                Budget.category_id == category.id,
                Budget.year_month.is_(None),
                Budget.is_active == True,  # noqa: E712
            )
            .first()
        )
        if budget:
            budget.monthly_limit = monthly_limit
            updated_budgets += 1
        else:
            db.add(Budget(category_id=category.id, monthly_limit=monthly_limit))
            created_budgets += 1

    db.commit()
    return {
        "categories_created": created_categories,
        "budgets_created": created_budgets,
        "budgets_updated": updated_budgets,
        "income_items_skipped": income_count,
        "categories_budgeted": len(totals),
    }
