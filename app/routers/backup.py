"""Download a full backup (see services.backup)."""

import logging
import os
import shutil

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

from app.config import get_settings
from app.database import engine
from app.models import User
from app.services.backup import build_backup
from app.utils.auth import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/backup", tags=["backup"])


@router.get("/download")
def download_backup(_user: User = Depends(get_current_user)):
    try:
        path = build_backup(engine, get_settings().db_passphrase)
    except Exception:
        logger.exception("Backup failed")
        raise HTTPException(status_code=500, detail="Backup failed. Check the server log for details.")
    return FileResponse(
        path,
        media_type="application/zip",
        filename=os.path.basename(path),
        background=BackgroundTask(shutil.rmtree, os.path.dirname(path), ignore_errors=True),
    )
