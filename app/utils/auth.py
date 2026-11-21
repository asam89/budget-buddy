from datetime import datetime, timedelta

import bcrypt
from fastapi import Depends, HTTPException, Request, Response
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db
from app.models import User

SESSION_COOKIE = "bb_session"
SESSION_MAX_AGE = 60 * 60 * 24 * 7  # 7 days


def get_serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(get_settings().secret_key)


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())


def password_version(password_hash: str) -> str:
    """Short fingerprint of the password hash. Sessions carry it, so changing or
    resetting a password signs out every other session for that account."""
    import hashlib
    return hashlib.sha256(password_hash.encode()).hexdigest()[:16]


def create_session_token(user: User) -> str:
    s = get_serializer()
    return s.dumps({"uid": user.id, "pv": password_version(user.password_hash)})


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    s = get_serializer()
    try:
        data = s.loads(token, max_age=SESSION_MAX_AGE)
    except (BadSignature, SignatureExpired):
        raise HTTPException(status_code=401, detail="Session expired")

    user = db.query(User).filter(User.id == data["uid"], User.is_active == True).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    if data.get("pv") != password_version(user.password_hash):
        raise HTTPException(status_code=401, detail="Password changed, please sign in again")
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Only an admin can do that")
    return user


def set_session_cookie(response: Response, user: User) -> None:
    token = create_session_token(user)
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=SESSION_MAX_AGE,
        httponly=True,
        samesite="lax",
        secure=get_settings().cookie_secure,
    )
