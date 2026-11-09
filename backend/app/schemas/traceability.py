from decimal import Decimal

from pydantic import BaseModel

from app.schemas.batches import BatchDetail


class MaterialConsumptionTotal(BaseModel):
    material_id: int
    material_name: str
    unit: str
    consumed_qty: Decimal


class BatchTraceability(BatchDetail):
    totals: list[MaterialConsumptionTotal]
