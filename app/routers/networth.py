"""Net worth router — assets, liabilities, balance-sheet summary, snapshots."""

from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import (
    Asset, Liability, Entity, NetWorthSnapshot, User,
    ASSET_CLASSES, LIABILITY_CLASSES,
)
from app.schemas import (
    AssetOut, AssetCreate, AssetUpdate,
    LiabilityOut, LiabilityCreate, LiabilityUpdate,
    NetWorthSummary, NetWorthSnapshotOut, NetWorthSnapshotCreate,
)
from app.services.networth import compute_net_worth
from app.utils.auth import get_current_user

router = APIRouter(prefix="/api/networth", tags=["networth"])


def _with_entity_name(row, db: Session):
    """Attach the resolved entity name for the *Out schema."""
    row.entity_name = (
        db.query(Entity.name).filter(Entity.id == row.entity_id).scalar()
        if row.entity_id is not None else None
    )
    return row


def _validate_entity(db: Session, entity_id: Optional[int]) -> None:
    if entity_id is not None and not db.query(Entity).filter(Entity.id == entity_id).first():
        raise HTTPException(status_code=422, detail="Unknown entity_id")


# ---- Summary ----

@router.get("/summary", response_model=NetWorthSummary)
def net_worth_summary(
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    nw = compute_net_worth(db)
    return NetWorthSummary(
        total_assets=nw.total_assets,
        total_liabilities=nw.total_liabilities,
        net_worth=nw.net_worth,
        assets_by_class=nw.assets_by_class,
        liabilities_by_class=nw.liabilities_by_class,
        by_entity=nw.by_entity,
    )


# ---- Assets ----

@router.get("/assets", response_model=list[AssetOut])
def list_assets(
    include_inactive: bool = False,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    query = db.query(Asset)
    if not include_inactive:
        query = query.filter(Asset.is_active == True)
    return [_with_entity_name(a, db) for a in query.order_by(Asset.name).all()]


@router.post("/assets", response_model=AssetOut, status_code=201)
def create_asset(
    data: AssetCreate,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    if data.asset_class not in ASSET_CLASSES:
        raise HTTPException(status_code=422, detail=f"asset_class must be one of {ASSET_CLASSES}")
    _validate_entity(db, data.entity_id)

    asset = Asset(**data.model_dump())
    db.add(asset)
    db.commit()
    db.refresh(asset)
    return _with_entity_name(asset, db)


@router.patch("/assets/{asset_id}", response_model=AssetOut)
def update_asset(
    asset_id: int,
    data: AssetUpdate,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    asset = db.query(Asset).filter(Asset.id == asset_id).first()
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")

    updates = data.model_dump(exclude_unset=True)
    if "asset_class" in updates and updates["asset_class"] not in ASSET_CLASSES:
        raise HTTPException(status_code=422, detail=f"asset_class must be one of {ASSET_CLASSES}")
    if "entity_id" in updates:
        _validate_entity(db, updates["entity_id"])

    for key, value in updates.items():
        setattr(asset, key, value)
    db.commit()
    db.refresh(asset)
    return _with_entity_name(asset, db)


@router.delete("/assets/{asset_id}", status_code=204)
def delete_asset(
    asset_id: int,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    asset = db.query(Asset).filter(Asset.id == asset_id).first()
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    db.delete(asset)
    db.commit()


# ---- Liabilities ----

@router.get("/liabilities", response_model=list[LiabilityOut])
def list_liabilities(
    include_inactive: bool = False,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    query = db.query(Liability)
    if not include_inactive:
        query = query.filter(Liability.is_active == True)
    return [_with_entity_name(l, db) for l in query.order_by(Liability.name).all()]


@router.post("/liabilities", response_model=LiabilityOut, status_code=201)
def create_liability(
    data: LiabilityCreate,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    if data.liability_class not in LIABILITY_CLASSES:
        raise HTTPException(status_code=422, detail=f"liability_class must be one of {LIABILITY_CLASSES}")
    _validate_entity(db, data.entity_id)

    liability = Liability(**data.model_dump())
    db.add(liability)
    db.commit()
    db.refresh(liability)
    return _with_entity_name(liability, db)


@router.patch("/liabilities/{liability_id}", response_model=LiabilityOut)
def update_liability(
    liability_id: int,
    data: LiabilityUpdate,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    liability = db.query(Liability).filter(Liability.id == liability_id).first()
    if not liability:
        raise HTTPException(status_code=404, detail="Liability not found")

    updates = data.model_dump(exclude_unset=True)
    if "liability_class" in updates and updates["liability_class"] not in LIABILITY_CLASSES:
        raise HTTPException(status_code=422, detail=f"liability_class must be one of {LIABILITY_CLASSES}")
    if "entity_id" in updates:
        _validate_entity(db, updates["entity_id"])

    for key, value in updates.items():
        setattr(liability, key, value)
    db.commit()
    db.refresh(liability)
    return _with_entity_name(liability, db)


@router.delete("/liabilities/{liability_id}", status_code=204)
def delete_liability(
    liability_id: int,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    liability = db.query(Liability).filter(Liability.id == liability_id).first()
    if not liability:
        raise HTTPException(status_code=404, detail="Liability not found")
    db.delete(liability)
    db.commit()


# ---- Snapshots (net worth over time) ----

@router.get("/snapshots", response_model=list[NetWorthSnapshotOut])
def list_snapshots(
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    return (
        db.query(NetWorthSnapshot)
        .order_by(NetWorthSnapshot.as_of_date, NetWorthSnapshot.id)
        .all()
    )


@router.post("/snapshots", response_model=NetWorthSnapshotOut, status_code=201)
def create_snapshot(
    data: NetWorthSnapshotCreate,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    """Capture current totals as a dated snapshot. If a snapshot already
    exists for the date it is overwritten, so recording twice in one day
    doesn't create duplicate points on the trend chart."""
    nw = compute_net_worth(db)
    as_of = data.as_of_date or date.today()

    snapshot = (
        db.query(NetWorthSnapshot)
        .filter(NetWorthSnapshot.as_of_date == as_of)
        .first()
    )
    if snapshot is None:
        snapshot = NetWorthSnapshot(as_of_date=as_of)
        db.add(snapshot)

    snapshot.total_assets = nw.total_assets
    snapshot.total_liabilities = nw.total_liabilities
    snapshot.net_worth = nw.net_worth
    snapshot.note = data.note

    db.commit()
    db.refresh(snapshot)
    return snapshot


@router.delete("/snapshots/{snapshot_id}", status_code=204)
def delete_snapshot(
    snapshot_id: int,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    snapshot = db.query(NetWorthSnapshot).filter(NetWorthSnapshot.id == snapshot_id).first()
    if not snapshot:
        raise HTTPException(status_code=404, detail="Snapshot not found")
    db.delete(snapshot)
    db.commit()
