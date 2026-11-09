from datetime import datetime
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.inventory import RecordId


class QualityCheckCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    parameter_id: RecordId
    value: Annotated[Decimal, Field(max_digits=12, decimal_places=3, allow_inf_nan=False)]


class QualityCheckOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    batch_id: int
    parameter_id: int
    value: Decimal
    passed: bool
    checked_by: int
    checked_at: datetime


class ParameterWithLatest(BaseModel):
    id: int
    product_id: int
    name: str
    unit: str
    min_value: Decimal
    max_value: Decimal
    latest_check: QualityCheckOut | None


class QualityOverview(BaseModel):
    batch_id: int
    parameters: list[ParameterWithLatest]
    checks: list[QualityCheckOut]
