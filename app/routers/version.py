"""App version + self-update (git-based) endpoints.

Backed by ``app.services.version``. The update endpoint launches ``deploy.sh``
in a detached session so it survives the server restart the script triggers
(``launchctl kickstart`` / uvicorn relaunch); progress is written to
``update.log`` in the repo root, which the frontend tails while it waits for the
server to come back.
"""
from __future__ import annotations

import subprocess
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.models import User
from app.services import version as version_service
from app.utils.auth import get_current_user

router = APIRouter(prefix="/api/version", tags=["version"])

UPDATE_LOG = version_service.REPO_DIR / "update.log"


class VersionResponse(BaseModel):
    available: bool
    version: str
    commit: Optional[str] = None
    commit_date: Optional[str] = None
    dirty: bool = False


class UpdateCheckResponse(BaseModel):
    available: bool
    status: str
    behind: int = 0
    ahead: int = 0
    local_version: str = ""
    latest_version: str = ""
    error: Optional[str] = None


@router.get("", response_model=VersionResponse)
def get_version(_user: User = Depends(get_current_user)):
    info = version_service.current_version()
    return VersionResponse(
        available=info.available,
        version=info.version,
        commit=info.commit,
        commit_date=info.commit_date,
        dirty=info.dirty,
    )


@router.get("/check", response_model=UpdateCheckResponse)
def check_update(_user: User = Depends(get_current_user)):
    status = version_service.check_for_update()
    return UpdateCheckResponse(**status.__dict__)


@router.post("/update")
def start_update(_user: User = Depends(get_current_user)):
    if not version_service.is_git_checkout():
        raise HTTPException(status_code=422, detail="Not a git checkout — cannot self-update")
    if not version_service.DEPLOY_SCRIPT.exists():
        raise HTTPException(status_code=422, detail="deploy.sh not found")

    try:
        with open(UPDATE_LOG, "w") as log:
            subprocess.Popen(
                ["bash", str(version_service.DEPLOY_SCRIPT)],
                cwd=str(version_service.REPO_DIR),
                stdout=log,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"Could not start update: {e}")

    return {"started": True}


@router.get("/update/log")
def update_log(_user: User = Depends(get_current_user)):
    if not UPDATE_LOG.exists():
        return {"lines": []}
    try:
        text = UPDATE_LOG.read_text(errors="replace")
    except OSError:
        return {"lines": []}
    lines = text.splitlines()
    return {"lines": lines[-50:]}
