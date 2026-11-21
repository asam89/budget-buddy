from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.schemas import LoginRequest, SetupRequest, UserOut
from app.services.users import AccountError, check_password, find_token, redeem_token
from app.utils.auth import (
    hash_password, verify_password, set_session_cookie,
    get_current_user, SESSION_COOKIE,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.get("/status")
def auth_status(db: Session = Depends(get_db)):
    user_count = db.query(User).count()
    return {"setup_required": user_count == 0}


@router.post("/setup", response_model=UserOut)
def initial_setup(data: SetupRequest, response: Response, db: Session = Depends(get_db)):
    if db.query(User).count() > 0:
        raise HTTPException(status_code=400, detail="Setup already completed")

    user = User(
        username=data.username,
        password_hash=hash_password(data.password),
        is_admin=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    set_session_cookie(response, user)
    return user


@router.post("/login", response_model=UserOut)
def login(data: LoginRequest, response: Response, db: Session = Depends(get_db)):
    user = db.query(User).filter(
        User.username == data.username, User.is_active == True
    ).first()
    if not user or not verify_password(data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    set_session_cookie(response, user)
    return user


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(SESSION_COOKIE)
    return {"status": "ok"}


@router.get("/me", response_model=UserOut)
def get_me(user: User = Depends(get_current_user)):
    return user


class PasswordChange(BaseModel):
    current_password: str
    new_password: str


@router.post("/password", response_model=UserOut)
def change_password(
    data: PasswordChange,
    response: Response,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Change your own password. Other sessions for this account are signed out."""
    if not verify_password(data.current_password, user.password_hash):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    try:
        check_password(data.new_password)
    except AccountError as e:
        raise HTTPException(status_code=422, detail=str(e))
    user.password_hash = hash_password(data.new_password)
    db.commit()
    db.refresh(user)
    set_session_cookie(response, user)  # keep this session signed in
    return user


# ---- One-time links (no login needed: the token is the proof) ----

@router.get("/link/{token}")
def link_info(token: str, db: Session = Depends(get_db)):
    row = find_token(db, token)
    if row is None:
        return {"valid": False}
    username = db.get(User, row.user_id).username if row.purpose == "reset" else None
    return {"valid": True, "purpose": row.purpose, "username": username,
            "expires_at": row.expires_at.isoformat() + "Z"}


class LinkRedeem(BaseModel):
    password: str
    username: Optional[str] = None


@router.post("/link/{token}", response_model=UserOut)
def link_redeem(token: str, data: LinkRedeem, response: Response, db: Session = Depends(get_db)):
    try:
        user = redeem_token(db, token, password=data.password, username=data.username)
    except AccountError as e:
        raise HTTPException(status_code=422, detail=str(e))
    set_session_cookie(response, user)
    return user
