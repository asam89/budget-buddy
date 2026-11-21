"""Account management for admins: list, invite, reset links, activate, admin."""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User, UserToken
from app.services.users import active_admin_count, create_token
from app.utils.auth import require_admin

router = APIRouter(prefix="/api/users", tags=["users"])


def _iso(dt: Optional[datetime]) -> Optional[str]:
    return dt.isoformat() + "Z" if dt else None


@router.get("")
def list_users(db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    now = datetime.utcnow()
    users = db.query(User).order_by(User.id).all()
    invites = (
        db.query(UserToken)
        .filter(UserToken.purpose == "invite", UserToken.used_at.is_(None), UserToken.expires_at > now)
        .order_by(UserToken.created_at.desc())
        .all()
    )
    return {
        "users": [
            {"id": u.id, "username": u.username, "is_admin": bool(u.is_admin),
             "is_active": bool(u.is_active), "created_at": _iso(u.created_at), "is_you": u.id == admin.id}
            for u in users
        ],
        "invites": [
            {"id": t.id, "note": t.note, "make_admin": bool(t.make_admin),
             "created_at": _iso(t.created_at), "expires_at": _iso(t.expires_at)}
            for t in invites
        ],
    }


class InviteCreate(BaseModel):
    note: Optional[str] = None
    make_admin: bool = False


@router.post("/invites")
def create_invite(data: InviteCreate, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    raw, row = create_token(db, purpose="invite", created_by=admin.id,
                            make_admin=data.make_admin, note=data.note)
    return {"id": row.id, "path": f"/invite/{raw}", "expires_at": _iso(row.expires_at)}


@router.delete("/invites/{invite_id}", status_code=204)
def revoke_invite(invite_id: int, db: Session = Depends(get_db), _admin: User = Depends(require_admin)):
    row = db.query(UserToken).filter(UserToken.id == invite_id, UserToken.purpose == "invite").first()
    if row is None:
        raise HTTPException(status_code=404, detail="Invite not found")
    db.delete(row)
    db.commit()


@router.post("/{user_id}/reset-link")
def create_reset_link(user_id: int, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=404, detail="Active user not found")
    raw, row = create_token(db, purpose="reset", created_by=admin.id, user_id=user.id)
    return {"path": f"/reset/{raw}", "expires_at": _iso(row.expires_at), "username": user.username}


class UserUpdate(BaseModel):
    is_active: Optional[bool] = None
    is_admin: Optional[bool] = None


@router.patch("/{user_id}")
def update_user(user_id: int, data: UserUpdate, db: Session = Depends(get_db),
                admin: User = Depends(require_admin)):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    if user.id == admin.id and (data.is_active is False or data.is_admin is False):
        raise HTTPException(status_code=422, detail="You can't deactivate or demote yourself")
    losing_admin = user.is_admin and user.is_active and (data.is_active is False or data.is_admin is False)
    if losing_admin and active_admin_count(db) <= 1:
        raise HTTPException(status_code=422, detail="Budget Buddy needs at least one active admin")
    if data.is_active is not None:
        user.is_active = data.is_active
    if data.is_admin is not None:
        user.is_admin = data.is_admin
    db.commit()
    return {"id": user.id, "username": user.username, "is_admin": bool(user.is_admin),
            "is_active": bool(user.is_active)}
