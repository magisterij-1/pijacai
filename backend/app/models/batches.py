from datetime import date, datetime
from decimal import Decimal
from enum import Enum

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, Enum as SQLAlchemyEnum, ForeignKey, Integer, Numeric, String, UniqueConstraint, func, true
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.inventory import MaterialLot
from app.models.production import ProductionOrder


class ProductionLine(Base):
    __tablename__ = "production_line"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())


class BatchStatus(str, Enum):
    in_production = "in_production"
    awaiting_qc = "awaiting_qc"
    released = "released"
    rejected = "rejected"


class Batch(Base):
    __tablename__ = "batch"
    __table_args__ = (
        UniqueConstraint("line_id", "production_date", "sequence_no", name="uq_batch_line_day_sequence"),
        CheckConstraint("sequence_no > 0", name="ck_batch_sequence_no"),
        CheckConstraint("planned_qty > 0", name="ck_batch_planned_qty"),
        CheckConstraint("produced_qty >= 0 AND rejected_qty >= 0 AND rejected_qty <= produced_qty", name="ck_batch_output_quantities"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    batch_code: Mapped[str] = mapped_column(String(80), unique=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("production_order.id", ondelete="RESTRICT"), index=True)
    line_id: Mapped[int] = mapped_column(ForeignKey("production_line.id", ondelete="RESTRICT"))
    production_date: Mapped[date] = mapped_column(Date)
    sequence_no: Mapped[int] = mapped_column(Integer)
    operator_id: Mapped[int] = mapped_column(ForeignKey("app_user.id", ondelete="RESTRICT"))
    status: Mapped[BatchStatus] = mapped_column(SQLAlchemyEnum(
        BatchStatus, name="batch_status", native_enum=False, create_constraint=True, validate_strings=True,
    ), default=BatchStatus.in_production, server_default="in_production")
    planned_qty: Mapped[Decimal] = mapped_column(Numeric(12, 3))
    produced_qty: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    rejected_qty: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decided_by: Mapped[int | None] = mapped_column(ForeignKey("app_user.id", ondelete="RESTRICT"))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decision_note: Mapped[str | None] = mapped_column(String(500))
    order: Mapped[ProductionOrder] = relationship()
    line: Mapped[ProductionLine] = relationship()


class BatchConsumption(Base):
    __tablename__ = "batch_consumption"
    __table_args__ = (
        UniqueConstraint("batch_id", "material_lot_id", name="uq_batch_consumption_lot"),
        CheckConstraint("qty > 0", name="ck_batch_consumption_qty"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("batch.id", ondelete="RESTRICT"), index=True)
    material_lot_id: Mapped[int] = mapped_column(ForeignKey("material_lot.id", ondelete="RESTRICT"), index=True)
    qty: Mapped[Decimal] = mapped_column(Numeric(12, 3))
    lot: Mapped[MaterialLot] = relationship()
