"""Seed the one entity every install needs: a default "Personal".

Deliberately does NOT seed any businesses — entities are user-customizable
from Settings, so a fresh install starts with just Personal (marked default)
and the user adds their own. Idempotent: safe to run on every startup.
"""

from sqlalchemy.orm import Session

from app.models import Entity

DEFAULT_ENTITY_NAME = "Personal"
DEFAULT_ENTITY_COLOR = "#10b981"


def seed_default_entity(db: Session) -> Entity:
    """Ensure a default entity exists, returning it.

    If any entity is already flagged default, leave everything alone. Otherwise
    reuse an existing "Personal" (flagging it default) or create one.
    """
    existing_default = db.query(Entity).filter(Entity.is_default == True).first()  # noqa: E712
    if existing_default is not None:
        return existing_default

    personal = db.query(Entity).filter(Entity.name == DEFAULT_ENTITY_NAME).first()
    if personal is None:
        personal = Entity(
            name=DEFAULT_ENTITY_NAME,
            entity_type="personal",
            color=DEFAULT_ENTITY_COLOR,
            is_default=True,
            is_active=True,
        )
        db.add(personal)
    else:
        personal.is_default = True
        personal.is_active = True
    db.commit()
    db.refresh(personal)
    return personal
