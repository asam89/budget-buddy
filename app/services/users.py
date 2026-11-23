"""Accounts: admins, one-time invite/reset links, password rules.

Budget Buddy is self-hosted with no email, so invites and resets are links an
admin copies and sends however they like. Every account sees the same books;
admins can also manage accounts.
"""

import hashlib
import re
import secrets
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import User, UserToken
from app.utils.auth import hash_password

INVITE_TTL = timedelta(days=7)
RESET_TTL = timedelta(hours=24)
MIN_PASSWORD = 8
USERNAME_RE = re.compile(r"^[A-Za-z0-9._@-]{3,40}$")


class AccountError(ValueError):
    pass


def check_password(password: str) -> None:
    if len(password or "") < MIN_PASSWORD:
        raise AccountError(f"Password must be at least {MIN_PASSWORD} characters")


def check_username(db: Session, username: str) -> str:
    name = (username or "").strip()
    if not USERNAME_RE.match(name):
        raise AccountError("Username must be 3-40 letters, numbers or . _ @ -")
    if db.query(User).filter(func.lower(User.username) == name.lower()).first():
        raise AccountError("That username is taken")
    return name


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def ensure_admin(db: Session) -> None:
    """Databases from before admins existed: the oldest active account becomes admin."""
    if db.query(User).filter(User.is_admin == True, User.is_active == True).first():  # noqa: E712
        return
    first = db.query(User).filter(User.is_active == True).order_by(User.id).first()  # noqa: E712
    if first is not None:
        first.is_admin = True
        db.commit()


def active_admin_count(db: Session) -> int:
    return db.query(User).filter(User.is_admin == True, User.is_active == True).count()  # noqa: E712


def create_token(db: Session, *, purpose: str, created_by: int, user_id: Optional[int] = None,
                 make_admin: bool = False, note: Optional[str] = None,
                 now: Optional[datetime] = None) -> tuple[str, UserToken]:
    """Create a one-time link token. Returns (raw_token, row); store only the row."""
    now = now or datetime.utcnow()
    if purpose == "reset":
        # A new reset link replaces any unused ones for the same account.
        db.query(UserToken).filter(
            UserToken.purpose == "reset", UserToken.user_id == user_id, UserToken.used_at.is_(None)
        ).delete()
    raw = secrets.token_urlsafe(32)
    row = UserToken(
        token_hash=_hash(raw), purpose=purpose, user_id=user_id, make_admin=make_admin,
        note=(note or "").strip() or None, created_by=created_by, created_at=now,
        expires_at=now + (INVITE_TTL if purpose == "invite" else RESET_TTL),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return raw, row


def find_token(db: Session, raw: str, now: Optional[datetime] = None) -> Optional[UserToken]:
    """A usable token: exists, unused, unexpired, and (for resets) the account is active."""
    now = now or datetime.utcnow()
    row = db.query(UserToken).filter(UserToken.token_hash == _hash(raw or "")).first()
    if row is None or row.used_at is not None or row.expires_at <= now:
        return None
    if row.purpose == "reset":
        target = db.get(User, row.user_id)
        if target is None or not target.is_active:
            return None
    return row


def redeem_token(db: Session, raw: str, *, password: str, username: Optional[str] = None,
                 now: Optional[datetime] = None) -> User:
    """Use an invite (creates the account) or a reset link (sets the password)."""
    now = now or datetime.utcnow()
    row = find_token(db, raw, now)
    if row is None:
        raise AccountError("This link is invalid, expired or already used. Ask for a new one.")
    check_password(password)
    if row.purpose == "invite":
        user = User(username=check_username(db, username or ""),
                    password_hash=hash_password(password), is_admin=bool(row.make_admin))
        db.add(user)
    else:
        user = db.get(User, row.user_id)
        user.password_hash = hash_password(password)
    row.used_at = now
    db.commit()
    db.refresh(user)
    return user
