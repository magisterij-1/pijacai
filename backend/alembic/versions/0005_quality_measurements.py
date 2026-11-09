"""Parametri kakovosti in zgodovina meritev.

Revision ID: 0005_quality_measurements
Revises: 0004_batches_and_consumption
"""
from alembic import op
import sqlalchemy as sa

revision = "0005_quality_measurements"
down_revision = "0004_batches_and_consumption"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "quality_parameter",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("unit", sa.String(20), nullable=False),
        sa.Column("min_value", sa.Numeric(12, 3), nullable=False),
        sa.Column("max_value", sa.Numeric(12, 3), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["product_id"], ["product.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("product_id", "name", name="uq_quality_parameter_product_name"),
        sa.CheckConstraint("min_value >= -999999999.999 AND max_value <= 999999999.999 AND min_value <= max_value", name="ck_quality_parameter_bounds"),
    )
    op.create_index("ix_quality_parameter_product_id", "quality_parameter", ["product_id"])
    op.create_table(
        "quality_check",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("batch_id", sa.Integer(), nullable=False),
        sa.Column("parameter_id", sa.Integer(), nullable=False),
        sa.Column("value", sa.Numeric(12, 3), nullable=False),
        sa.Column("passed", sa.Boolean(), nullable=False),
        sa.Column("checked_by", sa.Integer(), nullable=False),
        sa.Column("checked_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["batch_id"], ["batch.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["parameter_id"], ["quality_parameter.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["checked_by"], ["app_user.id"], ondelete="RESTRICT"),
        sa.CheckConstraint("value >= -999999999.999 AND value <= 999999999.999", name="ck_quality_check_finite_value"),
    )
    op.create_index("ix_quality_check_batch_parameter_latest", "quality_check", ["batch_id", "parameter_id", "checked_at", "id"])


def downgrade() -> None:
    op.drop_index("ix_quality_check_batch_parameter_latest", table_name="quality_check")
    op.drop_table("quality_check")
    op.drop_index("ix_quality_parameter_product_id", table_name="quality_parameter")
    op.drop_table("quality_parameter")
