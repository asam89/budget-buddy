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
    changed_files: list[str] = []
    # The version this server process started with; differs from `version`
    # (the code on disk) after an update that hasn't restarted yet.
    running_version: str = ""
    running_commit: Optional[str] = None
    started_at: Optional[str] = None
    restart_needed: bool = False


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
    running, started_at = version_service.running_version()
    return VersionResponse(
        available=info.available,
        version=info.version,
        commit=info.commit,
        commit_date=info.commit_date,
        dirty=info.dirty,
        changed_files=info.changed_files,
        running_version=running.version if running else info.version,
        running_commit=running.commit if running else info.commit,
        started_at=started_at,
        restart_needed=bool(running and running.commit and info.commit and running.commit != info.commit),
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


RESTART_LOG = version_service.REPO_DIR / "restart.log"


@router.post("/restart")
def restart_app(_user: User = Depends(get_current_user)):
    """Restart the Budget Buddy app process (not the machine). Picks up pulled
    code and re-runs startup repairs."""
    script = version_service.RESTART_SCRIPT
    if not script.exists():
        raise HTTPException(status_code=422, detail="scripts/restart.sh not found")
    try:
        with open(RESTART_LOG, "w") as log:
            subprocess.Popen(
                ["bash", str(script)],
                cwd=str(version_service.REPO_DIR),
                stdout=log,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
    except OSError as e:
        raise HTTPException(status_code=500, detail=f"Could not restart: {e}")
    return {"restarting": True}


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
