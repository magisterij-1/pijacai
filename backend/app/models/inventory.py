# — material, dobavitelj in serija na zalogi.
from datetime import datetime
from decimal import Decimal
from enum import Enum

from sqlalchemy import CheckConstraint, DateTime, Enum as SQLAlchemyEnum, ForeignKey, Index, Numeric, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.user import User


class MaterialType(str, Enum):
    ingredient = "ingredient"
    packaging = "packaging"


class Supplier(Base):
    __tablename__ = "supplier"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)


class Material(Base):
    __tablename__ = "material"
    __table_args__ = (CheckConstraint("min_stock >= 0", name="ck_material_min_stock"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    type: Mapped[MaterialType] = mapped_column(SQLAlchemyEnum(
        MaterialType, name="material_type", native_enum=False,
        create_constraint=True, validate_strings=True,
    ))
    unit: Mapped[str] = mapped_column(String(20))
    min_stock: Mapped[Decimal] = mapped_column(Numeric(12, 3), default=Decimal("0"), server_default="0")


class MaterialLot(Base):
    __tablename__ = "material_lot"
    __table_args__ = (
        UniqueConstraint("material_id", "supplier_id", "supplier_lot_no", name="uq_material_lot_supplier_series"),
        CheckConstraint("received_qty > 0", name="ck_material_lot_received_qty"),
        CheckConstraint("remaining_qty >= 0 AND remaining_qty <= received_qty", name="ck_material_lot_remaining_qty"),
        CheckConstraint("unit_cost >= 0", name="ck_material_lot_unit_cost"),
        CheckConstraint("length(trim(supplier_lot_no)) > 0", name="ck_material_lot_series_not_blank"),
        Index("ix_material_lot_fifo", "material_id", "received_at", "id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    material_id: Mapped[int] = mapped_column(ForeignKey("material.id", ondelete="RESTRICT"))
    supplier_id: Mapped[int] = mapped_column(ForeignKey("supplier.id", ondelete="RESTRICT"))
    supplier_lot_no: Mapped[str] = mapped_column(String(80))
    received_qty: Mapped[Decimal] = mapped_column(Numeric(12, 3))
    remaining_qty: Mapped[Decimal] = mapped_column(Numeric(12, 3))
    unit_cost: Mapped[Decimal] = mapped_column(Numeric(12, 3))
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    received_by: Mapped[int] = mapped_column(ForeignKey("app_user.id", ondelete="RESTRICT"))

    material: Mapped[Material] = relationship()
    supplier: Mapped[Supplier] = relationship()
    received_user: Mapped[User] = relationship()
