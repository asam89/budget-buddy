"""Per-row notes on income/expense lines, edited straight from the grid."""
from app.models import Category


def test_set_and_clear_note(client, db_session):
    cat = Category(name="Insurance", kind="expense")
    db_session.add(cat)
    db_session.commit()

    resp = client.patch(f"/api/categories/{cat.id}", json={"notes": " renews in March "})
    assert resp.status_code == 200
    assert resp.json()["notes"] == "renews in March"

    cleared = client.patch(f"/api/categories/{cat.id}", json={"notes": ""})
    assert cleared.status_code == 200
    assert cleared.json()["notes"] is None


def test_note_untouched_when_omitted(client, db_session):
    cat = Category(name="Hydro", kind="expense", notes="paid from joint account")
    db_session.add(cat)
    db_session.commit()

    resp = client.patch(f"/api/categories/{cat.id}", json={"name": "Utilities"})
    assert resp.status_code == 200
    assert resp.json()["notes"] == "paid from joint account"


def test_create_category_with_note(client):
    resp = client.post(
        "/api/categories/",
        json={"name": "Daycare", "kind": "expense", "notes": "invoiced monthly"},
    )
    assert resp.status_code in (200, 201)
    assert resp.json()["notes"] == "invoiced monthly"


def test_year_grid_exposes_notes(client, db_session):
    cat = Category(name="Internet", kind="expense", notes="Bell fibre")
    db_session.add(cat)
    db_session.commit()

    resp = client.get("/api/actuals/?year=2026")
    assert resp.status_code == 200
    line = next(l for l in resp.json()["lines"] if l["category_id"] == cat.id)
    assert line["notes"] == "Bell fibre"
