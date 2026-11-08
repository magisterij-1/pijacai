from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.models import BatchStatus
from app.schemas.inventory import Quantity, RecordId


class LineOption(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str


class BatchStart(BaseModel):
    model_config = ConfigDict(extra="forbid")
    line_id: RecordId
    qty: Quantity


class StockRequirement(BaseModel):
    material_id: int
    material_name: str
    unit: str
    required_qty: Decimal
    available_qty: Decimal
    missing_qty: Decimal
    status: Literal["OK", "PREMALO"]


class BatchPreview(BaseModel):
    order_id: int
    recipe_id: int
    recipe_version: int
    line_id: int
    qty: Decimal
    can_start: bool
    requirements: list[StockRequirement]


class BatchSummary(BaseModel):
    id: int
    batch_code: str
    order_id: int
    product_id: int
    product_name: str
    product_unit: str
    recipe_id: int
    recipe_version: int
    line_id: int
    line_name: str
    operator_id: int
    status: BatchStatus
    planned_qty: Decimal
    produced_qty: int
    rejected_qty: int
    started_at: datetime
    finished_at: datetime | None


class ConsumptionOut(BaseModel):
    material_lot_id: int
    material_id: int
    material_name: str
    supplier_name: str
    supplier_lot_no: str
    qty: Decimal
    unit: str


class BatchDetail(BatchSummary):
    consumptions: list[ConsumptionOut]
