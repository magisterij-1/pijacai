from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.dependencies import require_roles
from app.database import get_db
from app.models import Material, MaterialLot, Role, Supplier, User
from app.schemas.inventory import MaterialLotCreate, MaterialLotOut, MaterialOption, SupplierOption


router = APIRouter(prefix="/api", tags=["Prejem surovin"])


@router.get("/lookup/materials", response_model=list[MaterialOption])
def materials(user: User = Depends(require_roles(Role.warehouse)), db: Session = Depends(get_db)):
    return db.scalars(select(Material).order_by(Material.name, Material.id)).all()


@router.get("/lookup/suppliers", response_model=list[SupplierOption])
def suppliers(user: User = Depends(require_roles(Role.warehouse)), db: Session = Depends(get_db)):
    return db.scalars(select(Supplier).order_by(Supplier.name, Supplier.id)).all()


def duplicate_lot() -> HTTPException:
    return HTTPException(status_code=409, detail="Ta serija je že vnesena.")


@router.post("/material-lots", response_model=MaterialLotOut, status_code=status.HTTP_201_CREATED)
def receive_material(
    data: MaterialLotCreate,
    user: User = Depends(require_roles(Role.warehouse)),
    db: Session = Depends(get_db),
):
    if db.get(Material, data.material_id) is None:
        raise HTTPException(status_code=404, detail="Surovina ni najdena.")
    if db.get(Supplier, data.supplier_id) is None:
        raise HTTPException(status_code=404, detail="Dobavitelj ni najden.")
    duplicate = db.scalar(select(MaterialLot.id).where(
        MaterialLot.material_id == data.material_id,
        MaterialLot.supplier_id == data.supplier_id,
        MaterialLot.supplier_lot_no == data.supplier_lot_no,
    ))
    if duplicate is not None:
        raise duplicate_lot()
    lot = MaterialLot(
        material_id=data.material_id,
        supplier_id=data.supplier_id,
        supplier_lot_no=data.supplier_lot_no,
        received_qty=data.received_qty,
        remaining_qty=data.received_qty,
        unit_cost=data.unit_cost,
        received_by=user.id,
    )
    db.add(lot)
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        constraint = getattr(getattr(error.orig, "diag", None), "constraint_name", None)
        if getattr(error.orig, "sqlstate", None) == "23505" and constraint == "uq_material_lot_supplier_series":
            raise duplicate_lot() from None
        raise
    db.refresh(lot)
    return lot
