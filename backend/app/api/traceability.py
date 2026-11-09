from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.api.batches import PathId, detail
from app.api.dependencies import require_roles
from app.database import get_db
from app.models import Batch, BatchConsumption, Material, MaterialLot, ProductionOrder, Role, User
from app.schemas.inventory import MaterialOption
from app.schemas.traceability import BatchTraceability, LotBatchConsumption, LotTraceability, MaterialConsumptionTotal, TraceLot


router = APIRouter(prefix="/api/traceability", tags=["Sledljivost"])


def batch_query():
    return select(Batch).options(
        joinedload(Batch.order).joinedload(ProductionOrder.product),
        joinedload(Batch.order).joinedload(ProductionOrder.recipe),
        joinedload(Batch.line),
    )


def batch_result(db: Session, batch: Batch | None) -> BatchTraceability:
    if batch is None:
        raise HTTPException(status_code=404, detail="Šarža ni najdena.")
    result = detail(db, batch)
    totals = {}
    for consumption in result.consumptions:
        if consumption.material_id not in totals:
            totals[consumption.material_id] = MaterialConsumptionTotal(
                material_id=consumption.material_id, material_name=consumption.material_name,
                unit=consumption.unit, consumed_qty=Decimal("0.000"),
            )
        totals[consumption.material_id].consumed_qty += consumption.qty
    return BatchTraceability(**result.model_dump(), totals=[totals[key] for key in sorted(totals)])


@router.get("/batch", response_model=BatchTraceability)
def trace_batch_by_code(
    batch_code: Annotated[str, Query(min_length=1, max_length=80, pattern=r"\S")],
    user: User = Depends(require_roles(Role.planner, Role.quality)),
    db: Session = Depends(get_db),
):
    return batch_result(db, db.scalar(batch_query().where(Batch.batch_code == batch_code.strip())))


@router.get("/batch/{batch_id}", response_model=BatchTraceability)
def trace_batch(batch_id: PathId, user: User = Depends(require_roles(Role.planner, Role.quality)), db: Session = Depends(get_db)):
    return batch_result(db, db.scalar(batch_query().where(Batch.id == batch_id)))


def lot_query():
    return select(MaterialLot).options(joinedload(MaterialLot.material), joinedload(MaterialLot.supplier))


def lot_summary(lot: MaterialLot) -> TraceLot:
    return TraceLot(id=lot.id, material_id=lot.material_id, material_name=lot.material.name, unit=lot.material.unit,
                    supplier_id=lot.supplier_id, supplier_name=lot.supplier.name, supplier_lot_no=lot.supplier_lot_no,
                    received_qty=lot.received_qty, remaining_qty=lot.remaining_qty, received_at=lot.received_at)


@router.get("/materials", response_model=list[MaterialOption])
def trace_materials(user: User = Depends(require_roles(Role.planner, Role.quality)), db: Session = Depends(get_db)):
    return db.scalars(select(Material).order_by(Material.name, Material.id)).all()


@router.get("/lots", response_model=list[TraceLot])
def find_lots(
    material_id: Annotated[int, Query(gt=0, le=2147483647)],
    supplier_lot_no: Annotated[str, Query(min_length=1, max_length=80, pattern=r"\S")],
    user: User = Depends(require_roles(Role.planner, Role.quality)),
    db: Session = Depends(get_db),
):
    lots = db.scalars(lot_query().where(MaterialLot.material_id == material_id, MaterialLot.supplier_lot_no == supplier_lot_no.strip())
                      .order_by(MaterialLot.received_at, MaterialLot.id)).all()
    if not lots:
        raise HTTPException(status_code=404, detail="Serija ni najdena.")
    return [lot_summary(lot) for lot in lots]


@router.get("/lot/{lot_id}", response_model=LotTraceability)
def trace_lot(lot_id: PathId, user: User = Depends(require_roles(Role.planner, Role.quality)), db: Session = Depends(get_db)):
    lot = db.scalar(lot_query().where(MaterialLot.id == lot_id))
    if lot is None:
        raise HTTPException(status_code=404, detail="Serija ni najdena.")
    rows = db.execute(select(BatchConsumption, Batch).select_from(BatchConsumption).join(Batch, Batch.id == BatchConsumption.batch_id)
                      .where(BatchConsumption.material_lot_id == lot.id)
                      .options(joinedload(Batch.order).joinedload(ProductionOrder.product))
                      .order_by(Batch.started_at, Batch.id, BatchConsumption.id)).all()
    return LotTraceability(**lot_summary(lot).model_dump(), total_consumed_qty=sum((row.qty for row, _ in rows), Decimal("0.000")),
                           batches=[LotBatchConsumption(batch_id=batch.id, batch_code=batch.batch_code,
                               product_id=batch.order.product_id, product_name=batch.order.product.name,
                               started_at=batch.started_at, status=batch.status, consumed_qty=consumption.qty,
                           ) for consumption, batch in rows])
