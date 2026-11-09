from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.api.batches import PathId, detail
from app.api.dependencies import require_roles
from app.database import get_db
from app.models import Batch, ProductionOrder, Role, User
from app.schemas.traceability import BatchTraceability, MaterialConsumptionTotal


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
