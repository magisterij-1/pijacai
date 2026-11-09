# — pregled zalog, filtri in vsote.
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.api.dependencies import require_roles
from app.database import get_db
from app.models import Material, MaterialLot, Role, User
from app.schemas.inventory import MaterialLotOut, StockLotOut, StockOut, StockTotal


router = APIRouter(prefix="/api/stock", tags=["Zaloge"])


@router.get("", response_model=StockOut)
def stock(
    material_id: Annotated[int | None, Query(gt=0, le=2147483647)] = None,
    include_consumed: bool = False,
    user: User = Depends(require_roles(Role.warehouse)),
    db: Session = Depends(get_db),
):
    selected_material = None
    if material_id is not None:
        selected_material = db.get(Material, material_id)
        if selected_material is None:
            raise HTTPException(status_code=404, detail="Surovina ni najdena.")

    query = select(MaterialLot).options(
        joinedload(MaterialLot.material), joinedload(MaterialLot.supplier),
    ).order_by(MaterialLot.received_at, MaterialLot.id)
    if material_id is not None:
        query = query.where(MaterialLot.material_id == material_id)
    if not include_consumed:
        query = query.where(MaterialLot.remaining_qty > 0)
    lots = db.scalars(query).all()

    # Seznam in vsote izhajajo iz istega prebranega nabora serij.
    # Skrite porabljene serije imajo količino 0, zato vsote ne spremenijo.
    totals: dict[int, StockTotal] = {}
    if selected_material is not None:
        totals[selected_material.id] = StockTotal(
            material_id=selected_material.id, material_name=selected_material.name,
            unit=selected_material.unit, remaining_qty=Decimal("0.000"),
        )
    result = []
    for lot in lots:
        material = lot.material
        if material.id not in totals:
            totals[material.id] = StockTotal(
                material_id=material.id, material_name=material.name,
                unit=material.unit, remaining_qty=Decimal("0.000"),
            )
        totals[material.id].remaining_qty += lot.remaining_qty
        result.append(StockLotOut(
            **MaterialLotOut.model_validate(lot).model_dump(),
            material_name=material.name, material_type=material.type,
            unit=material.unit, supplier_name=lot.supplier.name,
        ))
    return StockOut(
        lots=result,
        totals=sorted(totals.values(), key=lambda item: (item.material_name, item.material_id)),
    )
