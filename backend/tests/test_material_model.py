from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError

from app.models import Material, MaterialLot, MaterialType, Role, Supplier, User


@pytest.fixture
def receipt_data(inventory_db):
    suffix = uuid4().hex
    user = User(name="Test skladiščnik", email=f"inventory-{suffix}@pijacai.local",
                password_hash="unused-in-model-tests", role=Role.warehouse)
    supplier = Supplier(name=f"Test dobavitelj {suffix}")
    material = Material(name=f"Test surovina {suffix}", type=MaterialType.ingredient, unit="kg")
    inventory_db.add_all([user, supplier, material])
    inventory_db.flush()
    return {
        "material_id": material.id, "supplier_id": supplier.id,
        "supplier_lot_no": "TEST-SERIJA-1", "received_qty": Decimal("10.125"),
        "remaining_qty": Decimal("10.125"), "unit_cost": Decimal("1.250"),
        "received_by": user.id,
    }


def test_real_postgres_persists_decimals_defaults_and_relationships(inventory_db, receipt_data):
    lot = MaterialLot(**receipt_data)
    inventory_db.add(lot)
    inventory_db.flush()
    inventory_db.refresh(lot)
    assert lot.received_qty == Decimal("10.125")
    assert lot.remaining_qty == lot.received_qty
    assert lot.unit_cost == Decimal("1.250")
    assert lot.received_at.tzinfo is not None
    assert lot.material.min_stock == Decimal("0.000")
    assert lot.material.type == MaterialType.ingredient
    assert lot.supplier.id == receipt_data["supplier_id"]
    assert lot.received_user.role == Role.warehouse


def test_duplicate_supplier_series_is_rejected_in_postgres(inventory_db, receipt_data):
    inventory_db.add(MaterialLot(**receipt_data))
    inventory_db.flush()
    with pytest.raises(IntegrityError):
        with inventory_db.begin_nested():
            inventory_db.add(MaterialLot(**receipt_data))
            inventory_db.flush()
    assert inventory_db.scalar(select(func.count()).select_from(MaterialLot).where(
        MaterialLot.material_id == receipt_data["material_id"],
    )) == 1


def test_same_series_number_is_allowed_for_another_supplier_or_material(inventory_db, receipt_data):
    supplier = Supplier(name=f"Drug test dobavitelj {uuid4().hex}")
    material = Material(name="Test embalaža", type=MaterialType.packaging, unit="kos")
    inventory_db.add_all([supplier, material])
    inventory_db.flush()
    lots = [
        MaterialLot(**receipt_data),
        MaterialLot(**{**receipt_data, "supplier_id": supplier.id}),
        MaterialLot(**{**receipt_data, "material_id": material.id}),
    ]
    inventory_db.add_all(lots)
    inventory_db.flush()
    assert len({lot.id for lot in lots}) == 3


@pytest.mark.parametrize("changes", [
    {"received_qty": Decimal("0")}, {"received_qty": Decimal("-1")},
    {"remaining_qty": Decimal("-0.001")}, {"remaining_qty": Decimal("10.126")},
    {"unit_cost": Decimal("-0.001")}, {"supplier_lot_no": "   "},
])
def test_invalid_receipt_values_are_rejected_by_postgres(inventory_db, receipt_data, changes):
    with pytest.raises(IntegrityError):
        with inventory_db.begin_nested():
            inventory_db.add(MaterialLot(**{**receipt_data, **changes}))
            inventory_db.flush()


@pytest.mark.parametrize("field", ["material_id", "supplier_id", "received_by"])
def test_missing_references_are_rejected_by_postgres(inventory_db, receipt_data, field):
    with pytest.raises(IntegrityError):
        with inventory_db.begin_nested():
            inventory_db.add(MaterialLot(**{**receipt_data, field: -1}))
            inventory_db.flush()


@pytest.mark.parametrize("model,field", [(Material, "material_id"), (Supplier, "supplier_id"), (User, "received_by")])
def test_referenced_records_cannot_be_deleted(inventory_db, receipt_data, model, field):
    inventory_db.add(MaterialLot(**receipt_data))
    inventory_db.flush()
    parent = inventory_db.get(model, receipt_data[field])
    with pytest.raises(IntegrityError):
        with inventory_db.begin_nested():
            inventory_db.delete(parent)
            inventory_db.flush()


def test_postgres_rejects_invalid_material_type_and_negative_min_stock(inventory_db):
    for material_type, minimum in [("invalid", "0"), ("ingredient", "-1")]:
        with pytest.raises(IntegrityError):
            with inventory_db.begin_nested():
                inventory_db.execute(text(
                    "INSERT INTO material (name, type, unit, min_stock) VALUES (:name, :type, :unit, :minimum)"
                ), {"name": "Neveljavna test surovina", "type": material_type, "unit": "kg", "minimum": minimum})
