"""Line-level business ownership: Category.entity_id scopes which lines appear.

A category owned by a business (``entity_id`` set) only shows in that business's
grid; a shared category (``entity_id`` is None) shows for every business and in
the unscoped "All" view.
"""

from app.models import Account, Category, Entity
from app.services.aggregation import year_grid


def _entities(db):
    personal = Entity(name="Personal", entity_type="personal", is_default=True)
    ignyte = Entity(name="Ignyte", entity_type="business")
    db.add_all([personal, ignyte, Account(name="Checking", account_type="depository", current_balance=0)])
    db.commit()
    return personal, ignyte


def _ids(lines):
    return {l["category_id"] for l in lines}


def test_year_grid_shows_owned_plus_shared_for_business(db_session):
    personal, ignyte = _entities(db_session)
    shared = Category(name="Groceries", kind="expense", entity_id=None)
    owned = Category(name="Ignyte Software", kind="expense", entity_id=ignyte.id)
    other = Category(name="Realesam Ads", kind="expense", entity_id=personal.id)
    db_session.add_all([shared, owned, other])
    db_session.commit()

    ignyte_ids = _ids(year_grid(db_session, 2026, ignyte.id))
    assert shared.id in ignyte_ids
    assert owned.id in ignyte_ids
    assert other.id not in ignyte_ids  # owned by another business


def test_year_grid_all_view_shows_every_line(db_session):
    personal, ignyte = _entities(db_session)
    shared = Category(name="Groceries", kind="expense", entity_id=None)
    owned = Category(name="Ignyte Software", kind="expense", entity_id=ignyte.id)
    db_session.add_all([shared, owned])
    db_session.commit()

    all_ids = _ids(year_grid(db_session, 2026, None))
    assert {shared.id, owned.id} <= all_ids


def test_year_grid_line_reports_owner(db_session):
    _, ignyte = _entities(db_session)
    owned = Category(name="Ignyte Software", kind="expense", entity_id=ignyte.id)
    db_session.add(owned)
    db_session.commit()

    line = next(l for l in year_grid(db_session, 2026, ignyte.id) if l["category_id"] == owned.id)
    assert line["entity_id"] == ignyte.id


def test_create_category_with_owner(client, db_session):
    _, ignyte = _entities(db_session)
    resp = client.post(
        "/api/categories/",
        json={"name": "Ignyte Software", "kind": "expense", "entity_id": ignyte.id},
    )
    assert resp.status_code == 201
    assert resp.json()["entity_id"] == ignyte.id


def test_create_category_unknown_owner_rejected(client, db_session):
    _entities(db_session)
    resp = client.post(
        "/api/categories/",
        json={"name": "Bogus", "kind": "expense", "entity_id": 99999},
    )
    assert resp.status_code == 404


def test_reassign_and_clear_category_owner(client, db_session):
    _, ignyte = _entities(db_session)
    cat = Category(name="Groceries", kind="expense", entity_id=None)
    db_session.add(cat)
    db_session.commit()
    cat_id = cat.id

    assigned = client.patch(f"/api/categories/{cat_id}", json={"entity_id": ignyte.id})
    assert assigned.status_code == 200
    assert assigned.json()["entity_id"] == ignyte.id

    cleared = client.patch(f"/api/categories/{cat_id}", json={"entity_id": None})
    assert cleared.status_code == 200
    assert cleared.json()["entity_id"] is None


def test_patch_without_entity_id_preserves_owner(client, db_session):
    _, ignyte = _entities(db_session)
    cat = Category(name="Ignyte Software", kind="expense", entity_id=ignyte.id)
    db_session.add(cat)
    db_session.commit()
    cat_id = cat.id

    resp = client.patch(f"/api/categories/{cat_id}", json={"name": "Ignyte SaaS"})
    assert resp.status_code == 200
    assert resp.json()["entity_id"] == ignyte.id
