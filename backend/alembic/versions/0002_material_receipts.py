# — materiali, dobavitelji in prejete serije.
"""Dobavitelji, surovine in prejete serije.

Revision ID: 0002_material_receipts
Revises: 0001_create_app_user
"""
from alembic import op
import sqlalchemy as sa


revision = "0002_material_receipts"
down_revision = "0001_create_app_user"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "supplier",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_table(
        "material",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("type", sa.Enum(
            "ingredient", "packaging", name="material_type",
            native_enum=False, create_constraint=True,
        ), nullable=False),
        sa.Column("unit", sa.String(20), nullable=False),
        sa.Column("min_stock", sa.Numeric(12, 3), server_default="0", nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("min_stock >= 0", name="ck_material_min_stock"),
    )
    op.create_table(
        "material_lot",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("material_id", sa.Integer(), nullable=False),
        sa.Column("supplier_id", sa.Integer(), nullable=False),
        sa.Column("supplier_lot_no", sa.String(80), nullable=False),
        sa.Column("received_qty", sa.Numeric(12, 3), nullable=False),
        sa.Column("remaining_qty", sa.Numeric(12, 3), nullable=False),
        sa.Column("unit_cost", sa.Numeric(12, 3), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("received_by", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["material_id"], ["material.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["supplier_id"], ["supplier.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["received_by"], ["app_user.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("material_id", "supplier_id", "supplier_lot_no", name="uq_material_lot_supplier_series"),
        sa.CheckConstraint("received_qty > 0", name="ck_material_lot_received_qty"),
        sa.CheckConstraint("remaining_qty >= 0 AND remaining_qty <= received_qty", name="ck_material_lot_remaining_qty"),
        sa.CheckConstraint("unit_cost >= 0", name="ck_material_lot_unit_cost"),
        sa.CheckConstraint("length(trim(supplier_lot_no)) > 0", name="ck_material_lot_series_not_blank"),
    )
    op.create_index("ix_material_lot_fifo", "material_lot", ["material_id", "received_at", "id"])


def downgrade() -> None:
    op.drop_index("ix_material_lot_fifo", table_name="material_lot")
    op.drop_table("material_lot")
    op.drop_table("material")
    op.drop_table("supplier")
