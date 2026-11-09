# — prejemi, šifranti, zaloge in decimalne omejitve.
from datetime import datetime
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.models import MaterialType


RecordId = Annotated[int, Field(strict=True, gt=0, le=2147483647)]
Quantity = Annotated[Decimal, Field(gt=0, max_digits=12, decimal_places=3, allow_inf_nan=False)]
UnitCost = Annotated[Decimal, Field(ge=0, max_digits=12, decimal_places=3, allow_inf_nan=False)]


class MaterialLotCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    material_id: RecordId
    supplier_id: RecordId
    supplier_lot_no: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]
    received_qty: Quantity
    unit_cost: UnitCost


class MaterialLotOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    material_id: int
    supplier_id: int
    supplier_lot_no: str
    received_qty: Decimal
    remaining_qty: Decimal
    unit_cost: Decimal
    received_at: datetime
    received_by: int


class MaterialOption(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    type: MaterialType
    unit: str


class SupplierOption(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str


class StockLotOut(MaterialLotOut):
    material_name: str
    material_type: MaterialType
    unit: str
    supplier_name: str


class StockTotal(BaseModel):
    material_id: int
    material_name: str
    unit: str
    remaining_qty: Decimal


class StockOut(BaseModel):
    lots: list[StockLotOut]
    totals: list[StockTotal]
