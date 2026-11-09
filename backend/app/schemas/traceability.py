from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel

from app.schemas.batches import BatchDetail
from app.models import BatchStatus


class MaterialConsumptionTotal(BaseModel):
    material_id: int
    material_name: str
    unit: str
    consumed_qty: Decimal


class BatchTraceability(BatchDetail):
    totals: list[MaterialConsumptionTotal]


class TraceLot(BaseModel):
    id: int
    material_id: int
    material_name: str
    unit: str
    supplier_id: int
    supplier_name: str
    supplier_lot_no: str
    received_qty: Decimal
    remaining_qty: Decimal
    received_at: datetime


class LotBatchConsumption(BaseModel):
    batch_id: int
    batch_code: str
    product_id: int
    product_name: str
    started_at: datetime
    status: BatchStatus
    consumed_qty: Decimal


class LotTraceability(TraceLot):
    batches: list[LotBatchConsumption]
    total_consumed_qty: Decimal
