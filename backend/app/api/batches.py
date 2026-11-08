from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.api.dependencies import require_roles
from app.database import get_db
from app.models import Batch, BatchConsumption, BatchStatus, MaterialLot, ProductionLine, ProductionOrder, Role, User
from app.schemas.batches import BatchDetail, BatchPreview, BatchStart, BatchSummary, ConsumptionOut, LineOption
from app.services.batch_start import prepare, start


router = APIRouter(prefix="/api", tags=["Šarže"])
PathId = Annotated[int, Path(gt=0, le=2147483647)]


def summary(batch: Batch) -> BatchSummary:
    return BatchSummary(
        id=batch.id, batch_code=batch.batch_code, order_id=batch.order_id,
        product_id=batch.order.product_id, product_name=batch.order.product.name, product_unit=batch.order.product.unit,
        recipe_id=batch.order.recipe_id, recipe_version=batch.order.recipe.version,
        line_id=batch.line_id, line_name=batch.line.name, operator_id=batch.operator_id,
        status=batch.status, planned_qty=batch.planned_qty, produced_qty=batch.produced_qty, rejected_qty=batch.rejected_qty,
        started_at=batch.started_at, finished_at=batch.finished_at,
    )


def detail(db: Session, batch: Batch) -> BatchDetail:
    rows = db.scalars(select(BatchConsumption).where(BatchConsumption.batch_id == batch.id).options(
        joinedload(BatchConsumption.lot).joinedload(MaterialLot.material),
        joinedload(BatchConsumption.lot).joinedload(MaterialLot.supplier),
    ).order_by(BatchConsumption.id)).all()
    return BatchDetail(**summary(batch).model_dump(), consumptions=[ConsumptionOut(
        material_lot_id=row.material_lot_id, material_id=row.lot.material_id,
        material_name=row.lot.material.name, supplier_name=row.lot.supplier.name,
        supplier_lot_no=row.lot.supplier_lot_no, qty=row.qty, unit=row.lot.material.unit,
    ) for row in rows])


@router.get("/lookup/lines", response_model=list[LineOption])
def lines(user: User = Depends(require_roles(Role.operator)), db: Session = Depends(get_db)):
    return db.scalars(select(ProductionLine).where(ProductionLine.active.is_(True)).order_by(ProductionLine.name, ProductionLine.id)).all()


@router.post("/orders/{order_id}/batches/preview", response_model=BatchPreview)
def preview_batch(order_id: PathId, data: BatchStart, user: User = Depends(require_roles(Role.operator)), db: Session = Depends(get_db)):
    return prepare(db, order_id, data)[2]


@router.post("/orders/{order_id}/batches", response_model=BatchDetail, status_code=status.HTTP_201_CREATED)
def start_batch(order_id: PathId, data: BatchStart, user: User = Depends(require_roles(Role.operator)), db: Session = Depends(get_db)):
    try:
        batch = start(db, order_id, data, user)
        result = detail(db, batch)
        db.commit()
        return result
    except Exception:
        db.rollback()
        raise


@router.get("/batches", response_model=list[BatchSummary])
def batches(
    order_id: Annotated[int | None, Query(gt=0, le=2147483647)] = None,
    status_filter: BatchStatus | None = None,
    user: User = Depends(require_roles(Role.operator, Role.planner, Role.quality)),
    db: Session = Depends(get_db),
):
    query = select(Batch).options(
        joinedload(Batch.order).joinedload(ProductionOrder.product),
        joinedload(Batch.order).joinedload(ProductionOrder.recipe),
        joinedload(Batch.line),
    ).order_by(Batch.started_at.desc(), Batch.id.desc())
    if order_id is not None:
        query = query.where(Batch.order_id == order_id)
    if status_filter is not None:
        query = query.where(Batch.status == status_filter)
    return [summary(batch) for batch in db.scalars(query).all()]


@router.get("/batches/{batch_id}", response_model=BatchDetail)
def batch_detail(batch_id: PathId, user: User = Depends(require_roles(Role.operator, Role.planner, Role.quality)), db: Session = Depends(get_db)):
    batch = db.get(Batch, batch_id)
    if batch is None:
        raise HTTPException(status_code=404, detail="Šarža ni najdena.")
    return detail(db, batch)
