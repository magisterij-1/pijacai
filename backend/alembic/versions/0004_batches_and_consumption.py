# — linije, šarže in zapisi porabe.
"""Proizvodne linije, šarže in FIFO poraba.

Revision ID: 0004_batches_and_consumption
Revises: 0003_production_orders
"""
from alembic import op
import sqlalchemy as sa


revision = "0004_batches_and_consumption"
down_revision = "0003_production_orders"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "production_line",
        sa.Column("id", sa.Integer(), nullable=False), sa.Column("name", sa.String(80), nullable=False),
        sa.Column("active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.PrimaryKeyConstraint("id"), sa.UniqueConstraint("name"),
    )
    op.create_table(
        "batch",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("batch_code", sa.String(80), nullable=False),
        sa.Column("order_id", sa.Integer(), nullable=False),
        sa.Column("line_id", sa.Integer(), nullable=False),
        sa.Column("production_date", sa.Date(), nullable=False),
        sa.Column("sequence_no", sa.Integer(), nullable=False),
        sa.Column("operator_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.Enum("in_production", "awaiting_qc", "released", "rejected", name="batch_status", native_enum=False, create_constraint=True), server_default="in_production", nullable=False),
        sa.Column("planned_qty", sa.Numeric(12, 3), nullable=False),
        sa.Column("produced_qty", sa.Integer(), server_default="0", nullable=False),
        sa.Column("rejected_qty", sa.Integer(), server_default="0", nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decided_by", sa.Integer(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decision_note", sa.String(500), nullable=True),
        sa.PrimaryKeyConstraint("id"), sa.UniqueConstraint("batch_code"),
        sa.UniqueConstraint("line_id", "production_date", "sequence_no", name="uq_batch_line_day_sequence"),
        sa.ForeignKeyConstraint(["order_id"], ["production_order.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["line_id"], ["production_line.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["operator_id"], ["app_user.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["decided_by"], ["app_user.id"], ondelete="RESTRICT"),
        sa.CheckConstraint("sequence_no > 0", name="ck_batch_sequence_no"),
        sa.CheckConstraint("planned_qty > 0", name="ck_batch_planned_qty"),
        sa.CheckConstraint("produced_qty >= 0 AND rejected_qty >= 0 AND rejected_qty <= produced_qty", name="ck_batch_output_quantities"),
    )
    op.create_index("ix_batch_order_id", "batch", ["order_id"])
    op.create_table(
        "batch_consumption",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("batch_id", sa.Integer(), nullable=False),
        sa.Column("material_lot_id", sa.Integer(), nullable=False),
        sa.Column("qty", sa.Numeric(12, 3), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["batch_id"], ["batch.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["material_lot_id"], ["material_lot.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("batch_id", "material_lot_id", name="uq_batch_consumption_lot"),
        sa.CheckConstraint("qty > 0", name="ck_batch_consumption_qty"),
    )
    op.create_index("ix_batch_consumption_batch_id", "batch_consumption", ["batch_id"])
    op.create_index("ix_batch_consumption_material_lot_id", "batch_consumption", ["material_lot_id"])


def downgrade() -> None:
    op.drop_index("ix_batch_consumption_material_lot_id", table_name="batch_consumption")
    op.drop_index("ix_batch_consumption_batch_id", table_name="batch_consumption")
    op.drop_table("batch_consumption")
    op.drop_index("ix_batch_order_id", table_name="batch")
    op.drop_table("batch")
    op.drop_table("production_line")
