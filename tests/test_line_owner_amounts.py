"""Amounts follow the line's business, so none are stranded outside the owner's grid."""

from sqlalchemy import text

from app.models import Budget, Category, Entity, ManualActual
from app.services.aggregation import year_grid
from app.services.line_owner import realign_all_owned_lines


def _setup(db):
    personal = Entity(name="Personal", entity_type="personal", is_default=True)
    realesam = Entity(name="Realesam", entity_type="business")
    ignyte = Entity(name="Ignyte", entity_type="business")
    db.add_all([personal, realesam, ignyte])
    db.commit()
    return personal, realesam, ignyte


def _cell(db, cat_id, entity_id, month=11):
    line = next(l for l in year_grid(db, 2026, entity_id) if l["category_id"] == cat_id)
    return line["months"][month - 1] if "months" in line else line["cells"][month - 1]


def test_startup_realign_moves_stranded_amounts_to_owner(db_session):
    personal, realesam, _ = _setup(db_session)
    airbnb = Category(name="Rental - Airbnb", kind="income", entity_id=realesam.id)
    db_session.add(airbnb)
    db_session.commit()
    db_session.add_all([
        Budget(category_id=airbnb.id, entity_id=personal.id, monthly_limit=1500, year_month="2026-11"),
        ManualActual(category_id=airbnb.id, entity_id=personal.id, year_month="2026-11", amount=1500),
    ])
    db_session.commit()
    assert _cell(db_session, airbnb.id, realesam.id)["effective"] is None   # the bug

    totals = realign_all_owned_lines(db_session)
    db_session.commit()

    assert totals["budgets_moved"] == 1 and totals["actuals_moved"] == 1
    cell = _cell(db_session, airbnb.id, realesam.id)
    assert cell["budget"] == 1500 and cell["effective"] == 1500
    all_cell = _cell(db_session, airbnb.id, None)
    assert all_cell["budget"] == 1500 and all_cell["effective"] == 1500    # not doubled


def test_owner_value_wins_on_conflict_and_nothing_is_deleted(db_session):
    personal, realesam, _ = _setup(db_session)
    cat = Category(name="Rental - Grayson", kind="income", entity_id=realesam.id)
    db_session.add(cat)
    db_session.commit()
    db_session.add_all([
        ManualActual(category_id=cat.id, entity_id=personal.id, year_month="2026-11", amount=2000),
        ManualActual(category_id=cat.id, entity_id=realesam.id, year_month="2026-11", amount=2760),
        ManualActual(category_id=cat.id, entity_id=personal.id, year_month="2026-10", amount=2760),
    ])
    db_session.commit()

    totals = realign_all_owned_lines(db_session)
    db_session.commit()

    assert totals["actuals_moved"] == 1 and totals["actual_conflicts"] == 1
    assert db_session.query(ManualActual).count() == 3
    assert _cell(db_session, cat.id, realesam.id, 11)["effective"] == 2760
    assert _cell(db_session, cat.id, realesam.id, 10)["effective"] == 2760


def test_two_other_businesses_same_month_moves_only_one(db_session):
    personal, realesam, ignyte = _setup(db_session)
    cat = Category(name="Line", kind="expense", entity_id=realesam.id)
    db_session.add(cat)
    db_session.commit()
    db_session.add_all([
        ManualActual(category_id=cat.id, entity_id=personal.id, year_month="2026-11", amount=10),
        ManualActual(category_id=cat.id, entity_id=ignyte.id, year_month="2026-11", amount=20),
    ])
    db_session.commit()
    totals = realign_all_owned_lines(db_session)
    db_session.commit()
    assert totals["actuals_moved"] == 1 and totals["actual_conflicts"] == 1


def test_every_month_budget_moves_and_matches_null_slot(db_session):
    personal, realesam, _ = _setup(db_session)
    cat = Category(name="Line", kind="expense", entity_id=realesam.id)
    db_session.add(cat)
    db_session.commit()
    db_session.add_all([
        Budget(category_id=cat.id, entity_id=personal.id, monthly_limit=100, year_month=None),
        Budget(category_id=cat.id, entity_id=realesam.id, monthly_limit=50, year_month="2026-03"),
    ])
    db_session.commit()
    totals = realign_all_owned_lines(db_session)
    db_session.commit()
    assert totals["budgets_moved"] == 1 and totals["budget_conflicts"] == 0
    assert _cell(db_session, cat.id, realesam.id, 11)["budget"] == 100
    assert _cell(db_session, cat.id, realesam.id, 3)["budget"] == 50


def test_shared_lines_are_untouched(db_session):
    personal, realesam, _ = _setup(db_session)
    cat = Category(name="T4", kind="income", entity_id=None)
    db_session.add(cat)
    db_session.commit()
    db_session.add_all([
        ManualActual(category_id=cat.id, entity_id=personal.id, year_month="2026-11", amount=1),
        ManualActual(category_id=cat.id, entity_id=realesam.id, year_month="2026-11", amount=2),
    ])
    db_session.commit()
    realign_all_owned_lines(db_session)
    db_session.commit()
    owners = sorted(r.entity_id for r in db_session.query(ManualActual).all())
    assert owners == sorted([personal.id, realesam.id])


def test_changing_a_lines_business_moves_its_amounts(client, db_session):
    personal, realesam, _ = _setup(db_session)
    cat = Category(name="Rental - Airbnb", kind="income", entity_id=personal.id)
    db_session.add(cat)
    db_session.commit()
    db_session.add_all([
        Budget(category_id=cat.id, entity_id=personal.id, monthly_limit=1500, year_month="2026-11"),
        ManualActual(category_id=cat.id, entity_id=personal.id, year_month="2026-11", amount=1500),
    ])
    db_session.commit()

    r = client.patch(f"/api/categories/{cat.id}", json={"entity_id": realesam.id})
    assert r.status_code == 200
    db_session.expire_all()
    cell = _cell(db_session, cat.id, realesam.id)
    assert cell["budget"] == 1500 and cell["effective"] == 1500

    # Moving to Shared leaves amounts where they are.
    assert client.patch(f"/api/categories/{cat.id}", json={"entity_id": None}).status_code == 200
    db_session.expire_all()
    assert {r.entity_id for r in db_session.query(ManualActual).all()} == {realesam.id}


def test_startup_migration_runs_the_realign(tmp_path):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.database import Base
    from app.services.entity_scope_migration import migrate_entity_scoping

    engine = create_engine(f"sqlite:///{tmp_path / 'm.db'}")
    Base.metadata.create_all(bind=engine)
    db = sessionmaker(bind=engine)()
    personal, realesam, _ = _setup(db)
    cat = Category(name="Rental - Airbnb", kind="income", entity_id=realesam.id)
    db.add(cat)
    db.commit()
    db.add(ManualActual(category_id=cat.id, entity_id=None, year_month="2026-11", amount=1500))
    db.commit()

    migrate_entity_scoping(engine)
    migrate_entity_scoping(engine)   # idempotent

    db.expire_all()
    assert [r.entity_id for r in db.query(ManualActual).all()] == [realesam.id]
    db.close()
    engine.dispose()
