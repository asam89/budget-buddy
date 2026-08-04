"""Tests for the net worth feature: asset/liability CRUD, balance-sheet
summary math (totals, per-class, per-entity), and dated snapshots."""

from datetime import date, timedelta

from app.models import Asset, Liability, Entity, NetWorthSnapshot
from app.services.networth import compute_net_worth


# ---- helpers ----

def _seed_entities(db):
    house = Entity(name="House", entity_type="household", is_default=True)
    biz = Entity(name="Consulting", entity_type="business", is_default=False)
    db.add_all([house, biz])
    db.flush()
    return house, biz


# ---- service: summary math ----

def test_summary_empty(db_session):
    nw = compute_net_worth(db_session)
    assert nw.total_assets == 0.0
    assert nw.total_liabilities == 0.0
    assert nw.net_worth == 0.0
    assert nw.assets_by_class == []
    assert nw.by_entity == []


def test_summary_totals_and_net(db_session):
    house, biz = _seed_entities(db_session)
    db_session.add_all([
        Asset(name="Home", asset_class="real_estate", value=800000, entity_id=house.id),
        Asset(name="TFSA", asset_class="investment", value=60000, entity_id=house.id),
        Asset(name="Chequing", asset_class="cash", value=15000),
        Liability(name="Mortgage", liability_class="mortgage", balance=500000, entity_id=house.id),
        Liability(name="Visa", liability_class="credit_card", balance=2500),
    ])
    db_session.commit()

    nw = compute_net_worth(db_session)
    assert nw.total_assets == 875000.0
    assert nw.total_liabilities == 502500.0
    assert nw.net_worth == 372500.0


def test_summary_by_class_grouping_and_order(db_session):
    db_session.add_all([
        Asset(name="Cash A", asset_class="cash", value=1000),
        Asset(name="Cash B", asset_class="cash", value=500),
        Asset(name="Stocks", asset_class="investment", value=20000),
    ])
    db_session.commit()

    nw = compute_net_worth(db_session)
    by_class = {c["key"]: c["total"] for c in nw.assets_by_class}
    assert by_class == {"cash": 1500.0, "investment": 20000.0}
    # canonical ordering: cash before investment
    assert [c["key"] for c in nw.assets_by_class] == ["cash", "investment"]


def test_summary_unknown_class_folded_into_other(db_session):
    db_session.add(Asset(name="Mystery", asset_class="crypto_punk", value=999))
    db_session.commit()

    nw = compute_net_worth(db_session)
    # unknown class must not vanish from the total
    assert nw.total_assets == 999.0
    assert nw.assets_by_class == [{"key": "other", "label": "Other", "total": 999.0}]


def test_summary_by_entity_and_unassigned(db_session):
    house, biz = _seed_entities(db_session)
    db_session.add_all([
        Asset(name="Home", asset_class="real_estate", value=800000, entity_id=house.id),
        Asset(name="Equipment", asset_class="business", value=40000, entity_id=biz.id),
        Asset(name="Cash", asset_class="cash", value=5000),  # unassigned
        Liability(name="Mortgage", liability_class="mortgage", balance=500000, entity_id=house.id),
    ])
    db_session.commit()

    nw = compute_net_worth(db_session)
    by_entity = {b["entity_name"]: b for b in nw.by_entity}

    assert by_entity["House"]["assets"] == 800000.0
    assert by_entity["House"]["liabilities"] == 500000.0
    assert by_entity["House"]["net"] == 300000.0
    assert by_entity["Consulting"]["net"] == 40000.0
    assert by_entity["Unassigned"]["assets"] == 5000.0
    # Unassigned bucket is last
    assert nw.by_entity[-1]["entity_name"] == "Unassigned"
    assert nw.by_entity[-1]["entity_id"] is None


def test_inactive_excluded_from_summary(db_session):
    db_session.add_all([
        Asset(name="Active", asset_class="cash", value=100),
        Asset(name="Sold house", asset_class="real_estate", value=999999, is_active=False),
    ])
    db_session.commit()

    nw = compute_net_worth(db_session)
    assert nw.total_assets == 100.0


# ---- router: CRUD ----

def test_create_and_list_asset(client, db_session):
    resp = client.post("/api/networth/assets", json={
        "name": "Brokerage", "asset_class": "investment", "value": 25000,
    })
    assert resp.status_code == 201
    assert resp.json()["name"] == "Brokerage"

    resp = client.get("/api/networth/assets")
    assert resp.status_code == 200
    assert len(resp.json()) == 1


def test_create_asset_rejects_bad_class(client, db_session):
    resp = client.post("/api/networth/assets", json={
        "name": "X", "asset_class": "not_a_class", "value": 1,
    })
    assert resp.status_code == 422


def test_create_asset_rejects_negative_value(client, db_session):
    resp = client.post("/api/networth/assets", json={
        "name": "X", "asset_class": "cash", "value": -5,
    })
    assert resp.status_code == 422


def test_create_asset_rejects_unknown_entity(client, db_session):
    resp = client.post("/api/networth/assets", json={
        "name": "X", "asset_class": "cash", "value": 1, "entity_id": 9999,
    })
    assert resp.status_code == 422


def test_asset_out_includes_entity_name(client, db_session):
    house, _ = _seed_entities(db_session)
    db_session.commit()
    resp = client.post("/api/networth/assets", json={
        "name": "Home", "asset_class": "real_estate", "value": 100, "entity_id": house.id,
    })
    assert resp.json()["entity_name"] == "House"


def test_update_asset(client, db_session):
    a = Asset(name="TFSA", asset_class="investment", value=100)
    db_session.add(a)
    db_session.commit()

    resp = client.patch(f"/api/networth/assets/{a.id}", json={"value": 250})
    assert resp.status_code == 200
    assert resp.json()["value"] == 250.0


def test_delete_asset(client, db_session):
    a = Asset(name="Car", asset_class="vehicle", value=15000)
    db_session.add(a)
    db_session.commit()

    resp = client.delete(f"/api/networth/assets/{a.id}")
    assert resp.status_code == 204
    assert db_session.query(Asset).count() == 0


def test_update_missing_asset_404(client, db_session):
    resp = client.patch("/api/networth/assets/123", json={"value": 1})
    assert resp.status_code == 404


def test_create_and_list_liability(client, db_session):
    resp = client.post("/api/networth/liabilities", json={
        "name": "Mortgage", "liability_class": "mortgage", "balance": 500000,
    })
    assert resp.status_code == 201

    resp = client.get("/api/networth/liabilities")
    assert len(resp.json()) == 1


def test_create_liability_rejects_bad_class(client, db_session):
    resp = client.post("/api/networth/liabilities", json={
        "name": "X", "liability_class": "nope", "balance": 1,
    })
    assert resp.status_code == 422


# ---- router: summary endpoint ----

def test_summary_endpoint(client, db_session):
    db_session.add_all([
        Asset(name="Cash", asset_class="cash", value=10000),
        Liability(name="Card", liability_class="credit_card", balance=1500),
    ])
    db_session.commit()

    resp = client.get("/api/networth/summary")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_assets"] == 10000.0
    assert data["total_liabilities"] == 1500.0
    assert data["net_worth"] == 8500.0


# ---- router: snapshots ----

def test_snapshot_records_current_totals(client, db_session):
    db_session.add_all([
        Asset(name="Cash", asset_class="cash", value=10000),
        Liability(name="Card", liability_class="credit_card", balance=1500),
    ])
    db_session.commit()

    resp = client.post("/api/networth/snapshots", json={})
    assert resp.status_code == 201
    data = resp.json()
    assert data["net_worth"] == 8500.0
    assert data["as_of_date"] == date.today().isoformat()


def test_snapshot_same_date_overwrites(client, db_session):
    a = Asset(name="Cash", asset_class="cash", value=100)
    db_session.add(a)
    db_session.commit()

    today = date.today().isoformat()
    r1 = client.post("/api/networth/snapshots", json={"as_of_date": today})
    assert r1.json()["net_worth"] == 100.0

    a.value = 300
    db_session.commit()
    r2 = client.post("/api/networth/snapshots", json={"as_of_date": today})
    assert r2.json()["net_worth"] == 300.0

    # only one snapshot for the date
    assert db_session.query(NetWorthSnapshot).count() == 1


def test_snapshots_listed_in_date_order(client, db_session):
    db_session.add(Asset(name="Cash", asset_class="cash", value=100))
    db_session.commit()

    today = date.today()
    for d in (today - timedelta(days=2), today, today - timedelta(days=1)):
        client.post("/api/networth/snapshots", json={"as_of_date": d.isoformat()})

    resp = client.get("/api/networth/snapshots")
    dates = [s["as_of_date"] for s in resp.json()]
    assert dates == sorted(dates)


def test_delete_snapshot(client, db_session):
    db_session.add(Asset(name="Cash", asset_class="cash", value=100))
    db_session.commit()
    snap = client.post("/api/networth/snapshots", json={}).json()

    resp = client.delete(f"/api/networth/snapshots/{snap['id']}")
    assert resp.status_code == 204
    assert db_session.query(NetWorthSnapshot).count() == 0
