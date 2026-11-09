# — izdelki, recepture in proizvodni nalogi.
"""Izdelki, verzije receptur in proizvodni nalogi.

Revision ID: 0003_production_orders
Revises: 0002_material_receipts
"""
from alembic import op
import sqlalchemy as sa


revision = "0003_production_orders"
down_revision = "0002_material_receipts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "product",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("sku", sa.String(60), nullable=False),
        sa.Column("unit", sa.String(20), nullable=False),
        sa.PrimaryKeyConstraint("id"), sa.UniqueConstraint("sku"),
    )
    op.create_table(
        "recipe",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("output_qty", sa.Numeric(12, 3), nullable=False),
        sa.Column("active", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["product_id"], ["product.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("product_id", "version", name="uq_recipe_product_version"),
        sa.CheckConstraint("version > 0", name="ck_recipe_version"),
        sa.CheckConstraint("output_qty > 0", name="ck_recipe_output_qty"),
    )
    op.create_index("uq_recipe_active_product", "recipe", ["product_id"], unique=True, postgresql_where=sa.text("active"))
    op.create_table(
        "recipe_item",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("recipe_id", sa.Integer(), nullable=False),
        sa.Column("material_id", sa.Integer(), nullable=False),
        sa.Column("qty", sa.Numeric(12, 3), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["recipe_id"], ["recipe.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["material_id"], ["material.id"], ondelete="RESTRICT"),
        sa.UniqueConstraint("recipe_id", "material_id", name="uq_recipe_item_material"),
        sa.CheckConstraint("qty > 0", name="ck_recipe_item_qty"),
    )
    op.create_table(
        "production_order",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("recipe_id", sa.Integer(), nullable=False),
        sa.Column("planned_qty", sa.Integer(), nullable=False),
        sa.Column("planned_date", sa.Date(), nullable=False),
        sa.Column("status", sa.Enum("planned", "in_progress", "done", "cancelled", name="order_status", native_enum=False, create_constraint=True), server_default="planned", nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["product_id"], ["product.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["recipe_id"], ["recipe.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by"], ["app_user.id"], ondelete="RESTRICT"),
        sa.CheckConstraint("planned_qty > 0", name="ck_order_planned_qty"),
    )


def downgrade() -> None:
    op.drop_table("production_order")
    op.drop_table("recipe_item")
    op.drop_index("uq_recipe_active_product", table_name="recipe")
    op.drop_table("recipe")
    op.drop_table("product")
