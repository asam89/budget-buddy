"""WS-D: deterministic expense findings + an optional local-AI narrative.

Design (see INVARIANTS.md):
- Findings are computed deterministically from the aggregation layer. They are
  the source of truth and are always shown, even if the LLM is unavailable.
- The LLM receives ONLY the structured findings payload and period labels — no
  raw transactions, account numbers, or merchant lists.
- The narrative is post-validated: any number it states that is not present in
  the findings is rejected, so the model can never fabricate figures.
- The local provider is default; a hosted provider is used only when explicitly
  configured. There is no silent local -> hosted fallback (if the configured
  provider fails, we return findings only).
"""

import hashlib
import json
import logging
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from sqlalchemy.orm import Session

from app.models import Category
from app.services.aggregation import (
    budget_for,
    effective_actual,
    is_valid_year_month,
    month_totals,
)

logger = logging.getLogger(__name__)

PROMPT_VERSION = "v1"
_PROMPT_DIR = Path(__file__).parent / "prompts"

_MONTH_NAMES = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]


def _prev_month(year_month: str) -> str:
    y, m = int(year_month[:4]), int(year_month[5:7])
    if m == 1:
        return f"{y - 1:04d}-12"
    return f"{y:04d}-{m - 1:02d}"


def period_label(year_month: str) -> str:
    y, m = int(year_month[:4]), int(year_month[5:7])
    return f"{_MONTH_NAMES[m - 1]} {y}"


def build_findings(db: Session, year_month: str) -> dict:
    """Compute the deterministic findings for a month from the aggregation layer.

    The payload is intentionally numbers + category names only.
    """
    if not is_valid_year_month(year_month):
        raise ValueError("year_month must be 'YYYY-MM'")

    prev_ym = _prev_month(year_month)
    categories = db.query(Category).filter(Category.kind == "expense").all()

    rows = []
    for cat in categories:
        actual = effective_actual(db, cat, year_month).amount or 0.0
        prev_actual = effective_actual(db, cat, prev_ym).amount or 0.0
        budget = budget_for(db, cat.id, year_month) or 0.0
        if actual == 0 and budget == 0 and prev_actual == 0:
            continue
        rows.append({
            "name": cat.name,
            "actual": round(actual, 2),
            "budget": round(budget, 2),
            "variance": round(actual - budget, 2),
            "previous": round(prev_actual, 2),
            "delta": round(actual - prev_actual, 2),
        })

    mt = month_totals(db, year_month)
    expense_actual = mt.expense_actual
    total = expense_actual or 1.0

    for r in rows:
        r["share_pct"] = round(r["actual"] / total * 100, 1)

    top_categories = sorted(rows, key=lambda r: r["actual"], reverse=True)[:5]
    over_budget = sorted(
        [
            {"name": r["name"], "actual": r["actual"], "budget": r["budget"], "overage": r["variance"]}
            for r in rows
            if r["budget"] > 0 and r["variance"] > 0
        ],
        key=lambda r: r["overage"],
        reverse=True,
    )[:5]
    biggest_changes = sorted(
        [
            {"name": r["name"], "previous": r["previous"], "current": r["actual"], "delta": r["delta"]}
            for r in rows
            if r["previous"] > 0 or r["actual"] > 0
        ],
        key=lambda r: abs(r["delta"]),
        reverse=True,
    )[:5]

    savings_rate = round(mt.saved_actual / mt.income_actual * 100, 1) if mt.income_actual else 0.0

    return {
        "period": year_month,
        "period_label": period_label(year_month),
        "previous_period_label": period_label(prev_ym),
        "totals": {
            "expense_actual": expense_actual,
            "expense_budget": mt.expense_budget,
            "income_actual": mt.income_actual,
            "saved_actual": mt.saved_actual,
            "savings_rate_pct": savings_rate,
        },
        "top_categories": [
            {k: r[k] for k in ("name", "actual", "budget", "variance", "share_pct")}
            for r in top_categories
        ],
        "over_budget": over_budget,
        "biggest_changes": biggest_changes,
    }


def findings_hash(findings: dict) -> str:
    """Stable hash of the findings payload, for cache keying/invalidation."""
    blob = json.dumps(findings, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode()).hexdigest()


def _collect_numbers(obj, out: set[float]) -> None:
    if isinstance(obj, bool):
        return
    if isinstance(obj, (int, float)):
        out.add(round(float(obj), 2))
    elif isinstance(obj, dict):
        for v in obj.values():
            _collect_numbers(v, out)
    elif isinstance(obj, list):
        for v in obj:
            _collect_numbers(v, out)


def allowed_numbers(findings: dict) -> set[float]:
    """Every number the narrative is permitted to state.

    Includes the raw findings numbers plus their whole-dollar roundings, so
    "$1,000" is accepted for a 1000.0 value.
    """
    nums: set[float] = set()
    _collect_numbers(findings, nums)
    expanded: set[float] = set()
    for n in nums:
        expanded.add(n)
        expanded.add(round(n))
        expanded.add(abs(n))
        expanded.add(round(abs(n)))
    return expanded


_NUM_RE = re.compile(r"-?\$?\d[\d,]*(?:\.\d+)?%?")


def _parse_numbers(text: str) -> list[float]:
    found = []
    for m in _NUM_RE.findall(text):
        cleaned = m.replace("$", "").replace(",", "").replace("%", "")
        try:
            found.append(round(float(cleaned), 2))
        except ValueError:
            continue
    return found


def verify_text(text: str, allowed: set[float], tol: float = 1.0) -> bool:
    """True if every number stated in ``text`` matches an allowed finding."""
    for n in _parse_numbers(text):
        if not any(abs(n - a) <= tol for a in allowed):
            return False
    return True


def _load_prompt(findings: dict) -> str:
    template = (_PROMPT_DIR / f"insights_{PROMPT_VERSION}.txt").read_text()
    return template.format(
        period_label=findings["period_label"],
        findings=json.dumps(findings, indent=2),
    )


def validate_narrative(narrative: dict, findings: dict) -> dict:
    """Drop any summary/bullet that states a number not in the findings."""
    allowed = allowed_numbers(findings)
    summary = str(narrative.get("summary", "")).strip()
    bullets = [str(b).strip() for b in narrative.get("bullets", []) if str(b).strip()]

    clean_summary = summary if summary and verify_text(summary, allowed) else ""
    clean_bullets = [b for b in bullets if verify_text(b, allowed)]
    dropped = (1 if summary and not clean_summary else 0) + (len(bullets) - len(clean_bullets))
    return {"summary": clean_summary, "bullets": clean_bullets, "dropped": dropped}


# ---------------------------------------------------------------------------
# Generation + cache
# ---------------------------------------------------------------------------

# In-process cache keyed by (period, prompt_version, findings_hash). Because the
# key embeds the findings hash, any change in source data yields a new key and
# the stale narrative is naturally bypassed.
_CACHE: dict[tuple[str, str, str], dict] = {}


def _cache_key(findings: dict) -> tuple[str, str, str]:
    return (findings["period"], PROMPT_VERSION, findings_hash(findings))


def get_cached(findings: dict) -> Optional[dict]:
    return _CACHE.get(_cache_key(findings))


def generate_insights(db: Session, provider, year_month: str, force: bool = False) -> dict:
    """Build findings and, via the provider, an optional validated narrative.

    Returns a payload that always contains ``findings``; ``generated`` is False
    (with an ``error``) when no narrative could be produced. Never raises for a
    provider failure — deterministic findings stay visible.
    """
    findings = build_findings(db, year_month)
    key = _cache_key(findings)

    if not force and key in _CACHE:
        return {**_CACHE[key], "findings": findings, "cached": True}

    base = {
        "findings": findings,
        "prompt_version": PROMPT_VERSION,
        "cached": False,
    }

    if provider is None:
        return {
            **base,
            "generated": False,
            "narrative": None,
            "model": None,
            "generated_at": None,
            "error": "No AI provider is configured. Showing computed findings only.",
        }

    prompt = _load_prompt(findings)
    started = time.time()
    try:
        raw = provider.complete_json(prompt, max_tokens=800)
    except Exception as e:  # no silent fallback — surface, keep findings
        logger.warning("Insights generation failed: %s", e)
        return {
            **base,
            "generated": False,
            "narrative": None,
            "model": provider.name(),
            "generated_at": None,
            "error": f"AI insights unavailable: {e}",
        }

    narrative = validate_narrative(raw if isinstance(raw, dict) else {}, findings)
    result = {
        **base,
        "generated": True,
        "narrative": narrative,
        "model": provider.name(),
        "generated_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "error": None,
    }
    logger.info(
        "insights generated period=%s model=%s dropped=%d elapsed_ms=%d",
        year_month, provider.name(), narrative["dropped"], int((time.time() - started) * 1000),
    )
    _CACHE[key] = {k: result[k] for k in
                   ("generated", "narrative", "model", "generated_at", "error", "prompt_version")}
    return result
