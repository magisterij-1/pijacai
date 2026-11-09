from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Numeric, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class QualityParameter(Base):
    __tablename__ = "quality_parameter"
    __table_args__ = (
        UniqueConstraint("product_id", "name", name="uq_quality_parameter_product_name"),
        CheckConstraint("min_value >= -999999999.999 AND max_value <= 999999999.999 AND min_value <= max_value", name="ck_quality_parameter_bounds"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("product.id", ondelete="RESTRICT"), index=True)
    name: Mapped[str] = mapped_column(String(80))
    unit: Mapped[str] = mapped_column(String(20))
    min_value: Mapped[Decimal] = mapped_column(Numeric(12, 3))
    max_value: Mapped[Decimal] = mapped_column(Numeric(12, 3))


class QualityCheck(Base):
    __tablename__ = "quality_check"
    __table_args__ = (
        Index("ix_quality_check_batch_parameter_latest", "batch_id", "parameter_id", "checked_at", "id"),
        CheckConstraint("value >= -999999999.999 AND value <= 999999999.999", name="ck_quality_check_finite_value"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("batch.id", ondelete="RESTRICT"))
    parameter_id: Mapped[int] = mapped_column(ForeignKey("quality_parameter.id", ondelete="RESTRICT"))
    value: Mapped[Decimal] = mapped_column(Numeric(12, 3))
    passed: Mapped[bool] = mapped_column(Boolean)
    checked_by: Mapped[int] = mapped_column(ForeignKey("app_user.id", ondelete="RESTRICT"))
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
