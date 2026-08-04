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
