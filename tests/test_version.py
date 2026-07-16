"""App version resolution + update-check endpoints.

These run inside the repo's own git checkout, so ``current_version`` resolves a
real version and ``check_for_update(fetch=False)`` compares against the already
-fetched ``origin/main`` (no network). The self-update POST is only exercised
for its guard path — we never actually launch ``deploy.sh`` in tests.
"""

from app.routers import version as version_router
from app.services import version as version_service


def test_current_version_available_in_checkout():
    info = version_service.current_version()
    assert info.available is True
    assert info.version and info.version != "unknown"
    assert info.commit


def test_check_for_update_no_fetch_returns_status():
    status = version_service.check_for_update(fetch=False)
    assert status.available is True
    assert status.status in {"up_to_date", "behind", "ahead", "diverged"}


def test_get_version_endpoint(client):
    resp = client.get("/api/version")
    assert resp.status_code == 200
    body = resp.json()
    assert body["available"] is True
    assert body["version"]


def test_update_rejected_when_not_git_checkout(client, monkeypatch):
    monkeypatch.setattr(version_service, "is_git_checkout", lambda: False)
    resp = client.post("/api/version/update")
    assert resp.status_code == 422


def test_update_log_empty_when_missing(client, monkeypatch, tmp_path):
    monkeypatch.setattr(version_router, "UPDATE_LOG", tmp_path / "nope.log")
    resp = client.get("/api/version/update/log")
    assert resp.status_code == 200
    assert resp.json()["lines"] == []
