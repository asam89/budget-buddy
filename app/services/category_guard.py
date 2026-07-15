"""Rules protecting the "no catch-all category" invariant.

The name "Other" (in any case, with surrounding whitespace) is reserved and may
never be created: anything that cannot be confidently categorized waits in the
review queue for explicit assignment instead of being silently filed away.
"""

RESERVED_OTHER_MESSAGE = (
    'The category name "Other" is not allowed. Budget Buddy has no catch-all '
    "category — items that can't be categorized wait in the review queue for "
    "you to assign a real category."
)


def is_reserved_other(name: str | None) -> bool:
    """True if ``name`` is the reserved catch-all name ("other", any case)."""
    return (name or "").strip().lower() == "other"
