"""Tests for the /healthz probe and the CSRF cross-origin guard middleware."""


def test_healthz_no_auth(client):
    resp = client.get("/healthz")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert "version" in body


def test_csrf_blocks_cross_origin_post(client):
    resp = client.post(
        "/api/networth/assets",
        json={"name": "X", "asset_class": "cash", "value": 1},
        headers={"origin": "http://evil.example.com"},
    )
    assert resp.status_code == 403


def test_csrf_allows_same_origin_post(client):
    # TestClient's host header is "testserver"; a matching Origin is allowed.
    resp = client.post(
        "/api/networth/assets",
        json={"name": "Cash", "asset_class": "cash", "value": 1},
        headers={"origin": "http://testserver"},
    )
    assert resp.status_code == 201


def test_csrf_allows_missing_origin(client):
    # Non-browser clients omit Origin; SameSite=Lax covers browser navigations.
    resp = client.post(
        "/api/networth/assets",
        json={"name": "Cash", "asset_class": "cash", "value": 1},
    )
    assert resp.status_code == 201


def test_csrf_ignores_safe_methods(client):
    resp = client.get(
        "/api/networth/summary",
        headers={"origin": "http://evil.example.com"},
    )
    assert resp.status_code == 200


# Endpoints that must work without signing in. Everything else requires a session.
PUBLIC_ROUTES = {
    ("GET", "/api/auth/status"),
    ("POST", "/api/auth/setup"),      # only works while no account exists
    ("POST", "/api/auth/login"),
    ("POST", "/api/auth/logout"),
    ("GET", "/api/auth/link/{token}"),   # one-time invite/reset links
    ("POST", "/api/auth/link/{token}"),
    ("GET", "/healthz"),
    ("GET", "/{full_path:path}"),     # the web app's static files
}


def _route_deps(dependant):
    out = []
    for d in dependant.dependencies:
        out.append(d.call)
        out += _route_deps(d)
    return out


def test_every_other_endpoint_requires_sign_in():
    """Signed-in user, admin, or (for /api/ingest) an API token."""
    from fastapi.routing import APIRoute
    from app.main import app
    from app.routers.ingest import require_api_token
    from app.utils.auth import get_current_user, require_admin

    guards = {get_current_user, require_admin, require_api_token}
    unprotected = set()
    for r in app.routes:
        if not isinstance(r, APIRoute):
            continue
        deps = _route_deps(r.dependant)
        if guards & set(deps):
            continue
        for m in r.methods:
            if (m, r.path) not in PUBLIC_ROUTES:
                unprotected.add((m, r.path))
    assert unprotected == set(), f"Endpoints reachable without signing in: {sorted(unprotected)}"


def test_plaid_endpoints_reject_anonymous_callers(db_session):
    from fastapi.testclient import TestClient
    from app.database import get_db
    from app.main import app

    app.dependency_overrides[get_db] = lambda: db_session
    try:
        with TestClient(app) as c:
            for path in ("/api/plaid/link-token", "/api/plaid/exchange-token", "/api/plaid/sync-transactions"):
                assert c.post(path, json={}).status_code == 401, path
    finally:
        app.dependency_overrides.clear()
