# — izdelek, receptura, sestavine in nalog.
from datetime import date
from decimal import Decimal
from enum import Enum

from sqlalchemy import Boolean, CheckConstraint, Date, Enum as SQLAlchemyEnum, ForeignKey, Index, Integer, Numeric, String, UniqueConstraint, false, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.inventory import Material


class Product(Base):
    __tablename__ = "product"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    sku: Mapped[str] = mapped_column(String(60), unique=True)
    unit: Mapped[str] = mapped_column(String(20))


class Recipe(Base):
    __tablename__ = "recipe"
    __table_args__ = (
        UniqueConstraint("product_id", "version", name="uq_recipe_product_version"),
        CheckConstraint("version > 0", name="ck_recipe_version"),
        CheckConstraint("output_qty > 0", name="ck_recipe_output_qty"),
        Index("uq_recipe_active_product", "product_id", unique=True, postgresql_where=text("active")),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("product.id", ondelete="RESTRICT"))
    version: Mapped[int] = mapped_column(Integer)
    output_qty: Mapped[Decimal] = mapped_column(Numeric(12, 3))
    active: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false())
    items: Mapped[list["RecipeItem"]] = relationship(back_populates="recipe", order_by="RecipeItem.id")


class RecipeItem(Base):
    __tablename__ = "recipe_item"
    __table_args__ = (
        UniqueConstraint("recipe_id", "material_id", name="uq_recipe_item_material"),
        CheckConstraint("qty > 0", name="ck_recipe_item_qty"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    recipe_id: Mapped[int] = mapped_column(ForeignKey("recipe.id", ondelete="RESTRICT"))
    material_id: Mapped[int] = mapped_column(ForeignKey("material.id", ondelete="RESTRICT"))
    qty: Mapped[Decimal] = mapped_column(Numeric(12, 3))
    recipe: Mapped[Recipe] = relationship(back_populates="items")
    material: Mapped[Material] = relationship()


class OrderStatus(str, Enum):
    planned = "planned"
    in_progress = "in_progress"
    done = "done"
    cancelled = "cancelled"


class ProductionOrder(Base):
    __tablename__ = "production_order"
    __table_args__ = (CheckConstraint("planned_qty > 0", name="ck_order_planned_qty"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("product.id", ondelete="RESTRICT"))
    recipe_id: Mapped[int] = mapped_column(ForeignKey("recipe.id", ondelete="RESTRICT"))
    planned_qty: Mapped[int] = mapped_column(Integer)
    planned_date: Mapped[date] = mapped_column(Date)
    status: Mapped[OrderStatus] = mapped_column(SQLAlchemyEnum(
        OrderStatus, name="order_status", native_enum=False, create_constraint=True, validate_strings=True,
    ), default=OrderStatus.planned, server_default="planned")
    created_by: Mapped[int] = mapped_column(ForeignKey("app_user.id", ondelete="RESTRICT"))
    product: Mapped[Product] = relationship()
    recipe: Mapped[Recipe] = relationship()
