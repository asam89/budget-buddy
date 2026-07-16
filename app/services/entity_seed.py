"""Seed the one entity every install needs: a default "Personal".

Deliberately does NOT seed any businesses — entities are user-customizable
from Settings, so a fresh install starts with just Personal (marked default)
and the user adds their own. Idempotent: safe to run on every startup.
"""

from typing import Optional

from sqlalchemy.orm import Session

from app.models import Entity

DEFAULT_ENTITY_NAME = "Personal"
DEFAULT_ENTITY_COLOR = "#10b981"


def default_entity_id(db: Session) -> Optional[int]:
    """Id of the default entity, or None if none exists yet."""
    ent = db.query(Entity).filter(Entity.is_default == True).first()  # noqa: E712
    return ent.id if ent else None


def resolve_entity_id(db: Session, entity_id: Optional[int]) -> Optional[int]:
    """For writes: fall back to the default entity when none is supplied."""
    if entity_id is not None:
        return entity_id
    return default_entity_id(db)


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
