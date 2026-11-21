"""Accounts: invites, reset links, password change, admin rules, session sign-out."""

from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.database import get_db
from app.main import app
from app.models import User, UserToken
from app.services.users import ensure_admin
from app.utils.auth import hash_password


@pytest.fixture
def real(db_session):
    """Client with real cookie auth (no get_current_user override)."""
    def override_get_db():
        yield db_session
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def _new_client():
    return TestClient(app)


def _setup_admin(c, username="alex", password="first-pass-1"):
    r = c.post("/api/auth/setup", json={"username": username, "password": password})
    assert r.status_code == 200 and r.json()["is_admin"] is True
    return r.json()


def test_invite_flow_creates_a_signed_in_account(real, db_session):
    _setup_admin(real)
    inv = real.post("/api/users/invites", json={"note": "Sam"}).json()
    token = inv["path"].split("/")[-1]
    assert db_session.query(UserToken).one().token_hash != token   # only the hash is stored

    guest = _new_client()
    info = guest.get(f"/api/auth/link/{token}").json()
    assert info == {"valid": True, "purpose": "invite", "username": None, "expires_at": info["expires_at"]}
    r = guest.post(f"/api/auth/link/{token}", json={"username": "sam", "password": "sams-pass-1"})
    assert r.status_code == 200 and r.json()["username"] == "sam" and r.json()["is_admin"] is False
    assert guest.get("/api/auth/me").json()["username"] == "sam"      # signed in by the link
    assert guest.get("/api/users").status_code == 403                 # not an admin

    # single use
    assert guest.get(f"/api/auth/link/{token}").json() == {"valid": False}
    again = _new_client().post(f"/api/auth/link/{token}", json={"username": "sam2", "password": "x" * 10})
    assert again.status_code == 422
    # the invited user can sign in normally afterwards
    assert _new_client().post("/api/auth/login", json={"username": "sam", "password": "sams-pass-1"}).status_code == 200


def test_invite_validation_and_admin_invites(real):
    _setup_admin(real)
    token = real.post("/api/users/invites", json={"make_admin": True}).json()["path"].split("/")[-1]
    guest = _new_client()
    assert "at least 8" in guest.post(f"/api/auth/link/{token}", json={"username": "kim", "password": "short"}).json()["detail"]
    assert "taken" in guest.post(f"/api/auth/link/{token}", json={"username": "ALEX", "password": "long-enough"}).json()["detail"]
    assert "Username" in guest.post(f"/api/auth/link/{token}", json={"username": "a b", "password": "long-enough"}).json()["detail"]
    r = guest.post(f"/api/auth/link/{token}", json={"username": "kim", "password": "long-enough"})
    assert r.json()["is_admin"] is True


def test_expired_and_revoked_invites_fail(real, db_session):
    _setup_admin(real)
    t1 = real.post("/api/users/invites", json={}).json()
    row = db_session.get(UserToken, t1["id"])
    row.expires_at = datetime.utcnow() - timedelta(minutes=1)
    db_session.commit()
    assert real.get(f"/api/auth/link/{t1['path'].split('/')[-1]}").json() == {"valid": False}

    t2 = real.post("/api/users/invites", json={}).json()
    assert len(real.get("/api/users").json()["invites"]) == 1          # expired one hidden
    assert real.delete(f"/api/users/invites/{t2['id']}").status_code == 204
    assert real.get(f"/api/auth/link/{t2['path'].split('/')[-1]}").json() == {"valid": False}


def test_reset_link_sets_password_and_signs_out_old_sessions(real):
    _setup_admin(real)
    token = real.post("/api/users/invites", json={}).json()["path"].split("/")[-1]
    sam = _new_client()
    sam.post(f"/api/auth/link/{token}", json={"username": "sam", "password": "old-password"})
    sam_id = sam.get("/api/auth/me").json()["id"]

    reset = real.post(f"/api/users/{sam_id}/reset-link").json()
    rtoken = reset["path"].split("/")[-1]
    assert reset["username"] == "sam"
    info = _new_client().get(f"/api/auth/link/{rtoken}").json()
    assert info["purpose"] == "reset" and info["username"] == "sam"

    other = _new_client()
    assert other.post(f"/api/auth/link/{rtoken}", json={"password": "new-password"}).status_code == 200
    assert other.get("/api/auth/me").json()["username"] == "sam"
    # sam's old session is signed out; old password no longer works
    assert sam.get("/api/auth/me").status_code == 401
    assert _new_client().post("/api/auth/login", json={"username": "sam", "password": "old-password"}).status_code == 401
    assert _new_client().post("/api/auth/login", json={"username": "sam", "password": "new-password"}).status_code == 200


def test_new_reset_link_replaces_the_old_one(real):
    me = _setup_admin(real)
    first = real.post(f"/api/users/{me['id']}/reset-link").json()["path"].split("/")[-1]
    second = real.post(f"/api/users/{me['id']}/reset-link").json()["path"].split("/")[-1]
    assert real.get(f"/api/auth/link/{first}").json() == {"valid": False}
    assert real.get(f"/api/auth/link/{second}").json()["valid"] is True


def test_change_password(real):
    _setup_admin(real)
    other_session = _new_client()
    other_session.post("/api/auth/login", json={"username": "alex", "password": "first-pass-1"})
    assert real.post("/api/auth/password", json={"current_password": "wrong", "new_password": "second-pass-2"}).status_code == 400
    assert real.post("/api/auth/password", json={"current_password": "first-pass-1", "new_password": "short"}).status_code == 422
    assert real.post("/api/auth/password", json={"current_password": "first-pass-1", "new_password": "second-pass-2"}).status_code == 200
    assert real.get("/api/auth/me").status_code == 200                 # this session stays signed in
    assert other_session.get("/api/auth/me").status_code == 401        # others are signed out
    assert _new_client().post("/api/auth/login", json={"username": "alex", "password": "second-pass-2"}).status_code == 200


def test_admin_guardrails(real):
    me = _setup_admin(real)
    assert "yourself" in real.patch(f"/api/users/{me['id']}", json={"is_active": False}).json()["detail"]
    assert "yourself" in real.patch(f"/api/users/{me['id']}", json={"is_admin": False}).json()["detail"]
    token = real.post("/api/users/invites", json={}).json()["path"].split("/")[-1]
    sam = _new_client()
    sam_id = sam.post(f"/api/auth/link/{token}", json={"username": "sam", "password": "sams-pass-1"}).json()["id"]
    assert sam.patch(f"/api/users/{me['id']}", json={"is_active": False}).status_code == 403

    assert real.patch(f"/api/users/{sam_id}", json={"is_active": False}).json()["is_active"] is False
    assert sam.get("/api/auth/me").status_code == 401                  # deactivated = signed out
    assert _new_client().post("/api/auth/login", json={"username": "sam", "password": "sams-pass-1"}).status_code == 401
    assert real.post(f"/api/users/{sam_id}/reset-link").status_code == 404   # no reset for deactivated


def test_ensure_admin_promotes_oldest_on_old_databases(db_session):
    db_session.add_all([User(username="first", password_hash=hash_password("x" * 8)),
                        User(username="second", password_hash=hash_password("x" * 8))])
    db_session.commit()
    ensure_admin(db_session)
    assert [u.username for u in db_session.query(User).filter(User.is_admin == True)] == ["first"]  # noqa: E712
    ensure_admin(db_session)  # idempotent
    assert db_session.query(User).filter(User.is_admin == True).count() == 1  # noqa: E712
