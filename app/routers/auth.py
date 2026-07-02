from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.schemas import LoginRequest, SetupRequest, UserOut
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
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    set_session_cookie(response, user.id)
    return user


@router.post("/login", response_model=UserOut)
def login(data: LoginRequest, response: Response, db: Session = Depends(get_db)):
    user = db.query(User).filter(
        User.username == data.username, User.is_active == True
    ).first()
    if not user or not verify_password(data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    set_session_cookie(response, user.id)
    return user


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(SESSION_COOKIE)
    return {"status": "ok"}


@router.get("/me", response_model=UserOut)
def get_me(user: User = Depends(get_current_user)):
    return user
