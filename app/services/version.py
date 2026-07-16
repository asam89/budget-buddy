"""Resolve the running app version and check GitHub for updates.

Budget Buddy is deployed from a git checkout (see ``deploy.sh``), so the
"version" is derived from git at runtime: the nearest tag when releases are
tagged (e.g. ``v0.4.0``), otherwise a short commit SHA. The update check
compares the local ``HEAD`` against ``origin/<branch>`` after a fetch.

Everything degrades gracefully: when git is unavailable (e.g. a packaged
desktop build with no checkout) the functions report ``available=False`` rather
than raising, so the endpoint and UI can hide the feature.
"""
from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

REPO_DIR = Path(__file__).resolve().parent.parent.parent
DEPLOY_SCRIPT = REPO_DIR / "deploy.sh"
DEFAULT_BRANCH = "main"


@dataclass
class VersionInfo:
    available: bool
    version: str
    commit: Optional[str] = None
    commit_date: Optional[str] = None
    dirty: bool = False


@dataclass
class UpdateStatus:
    available: bool
    status: str  # "up_to_date" | "behind" | "ahead" | "diverged" | "unknown"
    behind: int = 0
    ahead: int = 0
    local_version: str = ""
    latest_version: str = ""
    error: Optional[str] = None


def _git(*args: str, timeout: int = 30) -> Optional[str]:
    """Run a git command in the repo, returning stripped stdout or None."""
    try:
        out = subprocess.run(
            ["git", *args],
            cwd=str(REPO_DIR),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode != 0:
        return None
    return out.stdout.strip()


def is_git_checkout() -> bool:
    return _git("rev-parse", "--is-inside-work-tree") == "true"


def current_version() -> VersionInfo:
    if not is_git_checkout():
        return VersionInfo(available=False, version="unknown")

    described = _git("describe", "--tags", "--always", "--dirty")
    commit = _git("rev-parse", "--short", "HEAD")
    commit_date = _git("show", "-s", "--format=%cI", "HEAD")
    dirty = bool(_git("status", "--porcelain"))

    return VersionInfo(
        available=True,
        version=described or commit or "unknown",
        commit=commit,
        commit_date=commit_date,
        dirty=dirty,
    )


def _latest_remote_version(branch: str) -> str:
    """Nearest tag reachable from the remote tip, else the remote short SHA."""
    tag = _git("describe", "--tags", "--abbrev=0", f"origin/{branch}")
    if tag:
        return tag
    sha = _git("rev-parse", "--short", f"origin/{branch}")
    return sha or "unknown"


def check_for_update(branch: str = DEFAULT_BRANCH, fetch: bool = True) -> UpdateStatus:
    if not is_git_checkout():
        return UpdateStatus(
            available=False, status="unknown", error="Not a git checkout"
        )

    if fetch and _git("fetch", "--quiet", "origin", branch, timeout=60) is None:
        return UpdateStatus(
            available=False,
            status="unknown",
            local_version=current_version().version,
            error="Could not reach GitHub to check for updates",
        )

    counts = _git("rev-list", "--left-right", "--count", f"HEAD...origin/{branch}")
    if not counts:
        return UpdateStatus(
            available=False, status="unknown", error="Could not compare with origin"
        )
    try:
        ahead_str, behind_str = counts.split()
        ahead, behind = int(ahead_str), int(behind_str)
    except ValueError:
        return UpdateStatus(available=False, status="unknown", error="Bad git output")

    if behind and ahead:
        status = "diverged"
    elif behind:
        status = "behind"
    elif ahead:
        status = "ahead"
    else:
        status = "up_to_date"

    return UpdateStatus(
        available=True,
        status=status,
        behind=behind,
        ahead=ahead,
        local_version=current_version().version,
        latest_version=_latest_remote_version(branch),
    )
