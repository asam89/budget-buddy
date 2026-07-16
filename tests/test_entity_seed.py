from app.models import Entity
from app.services.entity_seed import DEFAULT_ENTITY_NAME, seed_default_entity


def test_seed_creates_default_personal(db_session):
    ent = seed_default_entity(db_session)
    assert ent.name == DEFAULT_ENTITY_NAME
    assert ent.is_default is True
    assert ent.entity_type == "personal"
    assert db_session.query(Entity).count() == 1


def test_seed_is_idempotent(db_session):
    first = seed_default_entity(db_session)
    second = seed_default_entity(db_session)
    third = seed_default_entity(db_session)
    assert first.id == second.id == third.id
    assert db_session.query(Entity).filter(Entity.name == DEFAULT_ENTITY_NAME).count() == 1


def test_seed_reuses_existing_personal_without_default(db_session):
    existing = Entity(name=DEFAULT_ENTITY_NAME, entity_type="personal", is_default=False)
    db_session.add(existing)
    db_session.commit()

    ent = seed_default_entity(db_session)
    assert ent.id == existing.id
    assert ent.is_default is True
    assert db_session.query(Entity).count() == 1


def test_seed_leaves_other_default_alone(db_session):
    biz = Entity(name="Ignyte", entity_type="business", is_default=True)
    db_session.add(biz)
    db_session.commit()

    ent = seed_default_entity(db_session)
    assert ent.id == biz.id
    # No Personal auto-created when a default already exists.
    assert db_session.query(Entity).filter(Entity.name == DEFAULT_ENTITY_NAME).count() == 0
