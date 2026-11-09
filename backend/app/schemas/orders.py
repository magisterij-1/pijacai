# — predogled recepture in podatki proizvodnega naloga.
from datetime import date
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from app.models import MaterialType, OrderStatus
from app.schemas.inventory import RecordId


class ProductOption(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    sku: str
    unit: str


class OrderPreviewIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    product_id: RecordId
    planned_qty: Annotated[int, Field(strict=True, gt=0, le=2147483647)]


class OrderCreate(OrderPreviewIn):
    planned_date: date
    # Če je podan, mora še vedno predstavljati aktivno recepturo predogleda.
    recipe_id: RecordId | None = None


class MaterialRequirement(BaseModel):
    material_id: int
    material_name: str
    material_type: MaterialType
    unit: str
    required_qty: Decimal


class OrderPreviewOut(BaseModel):
    product_id: int
    product_name: str
    product_unit: str
    recipe_id: int
    recipe_version: int
    output_qty: Decimal
    planned_qty: int
    requirements: list[MaterialRequirement]


class OrderOut(OrderPreviewOut):
    id: int
    planned_date: date
    status: OrderStatus
    created_by: int
