from datetime import datetime, timedelta, timezone
from contextlib import contextmanager
from decimal import Decimal
from unittest.mock import patch
from uuid import uuid4

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.core.security import JWT_SECRET, create_access_token
from app.database import get_db
from app.main import app
from app.models import Material, MaterialLot, MaterialType, Role, Supplier, User


@pytest.fixture
def receipt_client(inventory_db):
    suffix = uuid4().hex
    user = User(name="Test skladiščnik", email=f"receipt-{suffix}@pijacai.local",
                password_hash="unused-in-receipt-tests", role=Role.warehouse)
    material = Material(name=f"Test surovina {suffix}", type=MaterialType.ingredient, unit="kg")
    supplier = Supplier(name=f"Test dobavitelj {suffix}")
    inventory_db.add_all([user, material, supplier])
    inventory_db.flush()

    def override_db():
        yield inventory_db

    app.dependency_overrides[get_db] = override_db
    try:
        with TestClient(app) as client:
            yield client, inventory_db, user, material, supplier
    finally:
        app.dependency_overrides.clear()


def body(material, supplier, **changes):
    return {
        "material_id": material.id, "supplier_id": supplier.id,
        "supplier_lot_no": "TEST-PREJEM-1", "received_qty": "10.125", "unit_cost": "1.250",
        **changes,
    }


def headers(user):
    return {"Authorization": f"Bearer {create_access_token(user)}"}


@pytest.mark.parametrize("material_type", list(MaterialType))
def test_warehouse_receives_material_or_packaging_in_postgres(receipt_client, material_type):
    client, db, user, material, supplier = receipt_client
    material.type = material_type
    db.flush()
    response = client.post("/api/material-lots", headers=headers(user), json=body(material, supplier))
    assert response.status_code == 201
    result = response.json()
    assert Decimal(result["received_qty"]) == Decimal("10.125")
    assert result["remaining_qty"] == result["received_qty"]
    assert result["received_by"] == user.id
    assert datetime.fromisoformat(result["received_at"]).tzinfo is not None
    stored = db.get(MaterialLot, result["id"])
    assert stored.supplier_id == supplier.id
    assert stored.material_id == material.id
    assert stored.remaining_qty == Decimal("10.125")
    assert stored.unit_cost == Decimal("1.250")


@pytest.mark.parametrize("role", list(Role))
@pytest.mark.parametrize("method,path", [
    ("POST", "/api/material-lots"), ("GET", "/api/material-lots"),
    ("GET", "/api/lookup/materials"), ("GET", "/api/lookup/suppliers"),
])
def test_receipt_routes_allow_only_warehouse(receipt_client, role, method, path):
    client, db, user, material, supplier = receipt_client
    user.role = role
    db.flush()
    response = client.request(method, path, headers=headers(user), json=body(material, supplier) if method == "POST" else None)
    expected = (201 if method == "POST" else 200) if role == Role.warehouse else 403
    assert response.status_code == expected


@pytest.mark.parametrize("case", ["missing", "invalid", "expired", "inactive", "deleted"])
@pytest.mark.parametrize("method,path", [
    ("POST", "/api/material-lots"), ("GET", "/api/material-lots"),
    ("GET", "/api/lookup/materials"), ("GET", "/api/lookup/suppliers"),
])
def test_receipt_routes_require_valid_active_login(receipt_client, case, method, path):
    client, db, user, material, supplier = receipt_client
    auth = headers(user)
    if case == "missing":
        auth = {}
    elif case == "invalid":
        auth = {"Authorization": "Bearer invalid-token"}
    elif case == "expired":
        now = datetime.now(timezone.utc)
        token = jwt.encode({"sub": str(user.id), "role": "warehouse", "iat": now - timedelta(hours=2), "exp": now - timedelta(hours=1)}, JWT_SECRET, algorithm="HS256")
        auth = {"Authorization": f"Bearer {token}"}
    elif case == "inactive":
        user.active = False
        db.flush()
    elif case == "deleted":
        db.delete(user)
        db.flush()
    response = client.request(method, path, headers=auth, json=body(material, supplier) if method == "POST" else None)
    assert response.status_code == 401
    assert db.scalar(select(func.count()).select_from(MaterialLot).where(MaterialLot.material_id == material.id)) == 0


@pytest.mark.parametrize("changes", [
    {"received_qty": "0"}, {"received_qty": "-1"}, {"unit_cost": "-0.001"},
    {"received_qty": "0.0001"}, {"unit_cost": "1.0001"}, {"received_qty": "1000000000"},
    {"received_qty": "NaN"}, {"received_qty": "Infinity"}, {"unit_cost": "NaN"},
    {"supplier_lot_no": "   "}, {"supplier_lot_no": "a" * 81},
    {"material_id": 0}, {"supplier_id": True},
    {"received_by": 999}, {"remaining_qty": "1"}, {"received_at": "2020-01-01T00:00:00Z"},
])
def test_invalid_receipt_cannot_write_rows(receipt_client, changes):
    client, db, user, material, supplier = receipt_client
    response = client.post("/api/material-lots", headers=headers(user), json=body(material, supplier, **changes))
    assert response.status_code == 422
    assert db.scalar(select(func.count()).select_from(MaterialLot).where(MaterialLot.material_id == material.id)) == 0


@pytest.mark.parametrize("field", ["material_id", "supplier_id", "supplier_lot_no", "received_qty", "unit_cost"])
def test_all_receipt_fields_are_required(receipt_client, field):
    client, _, user, material, supplier = receipt_client
    data = body(material, supplier)
    del data[field]
    assert client.post("/api/material-lots", headers=headers(user), json=data).status_code == 422


@pytest.mark.parametrize("missing", ["material", "supplier"])
def test_missing_reference_returns_404(receipt_client, missing):
    client, db, user, material, supplier = receipt_client
    data = body(material, supplier)
    db.delete(material if missing == "material" else supplier)
    db.flush()
    response = client.post("/api/material-lots", headers=headers(user), json=data)
    assert response.status_code == 404


def test_duplicate_series_is_409_and_does_not_increase_stock(receipt_client):
    client, db, user, material, supplier = receipt_client
    data = body(material, supplier, supplier_lot_no="  SERIJA-1  ")
    first = client.post("/api/material-lots", headers=headers(user), json=data)
    assert first.status_code == 201
    assert first.json()["supplier_lot_no"] == "SERIJA-1"
    again = client.post("/api/material-lots", headers=headers(user), json=body(material, supplier, supplier_lot_no="SERIJA-1"))
    assert again.status_code == 409
    assert again.json() == {"detail": "Ta serija je že vnesena."}
    assert db.scalar(select(func.sum(MaterialLot.remaining_qty)).where(MaterialLot.material_id == material.id)) == Decimal("10.125")


def test_database_duplicate_conflict_is_rolled_back_and_session_remains_usable(receipt_client):
    client, db, user, material, supplier = receipt_client
    data = body(material, supplier)
    assert client.post("/api/material-lots", headers=headers(user), json=data).status_code == 201
    # Simuliramo konflikt, ki ga predhodna poizvedba ni zaznala; napaka pride iz prave baze.
    with patch.object(db, "scalar", return_value=None):
        response = client.post("/api/material-lots", headers=headers(user), json=data)
    assert response.status_code == 409
    assert db.scalar(select(func.count()).select_from(MaterialLot).where(MaterialLot.material_id == material.id)) == 1


def test_zero_unit_cost_is_allowed(receipt_client):
    client, _, user, material, supplier = receipt_client
    response = client.post("/api/material-lots", headers=headers(user), json=body(material, supplier, unit_cost="0"))
    assert response.status_code == 201
    assert Decimal(response.json()["unit_cost"]) == 0


def test_saved_receipt_appears_in_list_with_remaining_stock(receipt_client):
    client, _, user, material, supplier = receipt_client
    created = client.post("/api/material-lots", headers=headers(user), json=body(material, supplier))
    assert created.status_code == 201
    result = client.get("/api/material-lots", headers=headers(user))
    assert result.status_code == 200
    matching = [item for item in result.json() if item["id"] == created.json()["id"]]
    assert len(matching) == 1
    assert Decimal(matching[0]["remaining_qty"]) == Decimal("10.125")


def test_lookup_options_include_real_material_and_supplier(receipt_client):
    client, _, user, material, supplier = receipt_client
    materials = client.get("/api/lookup/materials", headers=headers(user))
    suppliers = client.get("/api/lookup/suppliers", headers=headers(user))
    assert materials.status_code == suppliers.status_code == 200
    assert {"id": material.id, "name": material.name, "type": "ingredient", "unit": "kg"} in materials.json()
    assert {"id": supplier.id, "name": supplier.name} in suppliers.json()


@pytest.mark.parametrize("change", ["material", "supplier"])
def test_same_series_number_is_allowed_for_different_reference(receipt_client, change):
    client, db, user, material, supplier = receipt_client
    first = client.post("/api/material-lots", headers=headers(user), json=body(material, supplier))
    assert first.status_code == 201
    if change == "material":
        material = Material(name="Druga test embalaža", type=MaterialType.packaging, unit="kos")
        db.add(material)
    else:
        supplier = Supplier(name=f"Drug test dobavitelj {uuid4().hex}")
        db.add(supplier)
    db.flush()
    second = client.post("/api/material-lots", headers=headers(user), json=body(material, supplier))
    assert second.status_code == 201
    assert second.json()["id"] != first.json()["id"]


@pytest.mark.parametrize("quantity,cost", [
    ("0.001", "0.001"), ("999999999.999", "999999999.999"),
])
def test_receipt_accepts_valid_numeric_boundaries(receipt_client, quantity, cost):
    client, db, user, material, supplier = receipt_client
    response = client.post("/api/material-lots", headers=headers(user), json=body(material, supplier, received_qty=quantity, unit_cost=cost))
    assert response.status_code == 201
    result = response.json()
    assert Decimal(result["received_qty"]) == Decimal(quantity)
    assert Decimal(result["unit_cost"]) == Decimal(cost)
    assert set(result) == {"id", "material_id", "supplier_id", "supplier_lot_no", "received_qty", "remaining_qty", "unit_cost", "received_at", "received_by"}
    assert db.get(MaterialLot, result["id"]).received_by == user.id


@pytest.mark.parametrize("method,path", [
    ("POST", "/api/material-lots"), ("GET", "/api/material-lots"),
    ("GET", "/api/lookup/materials"), ("GET", "/api/lookup/suppliers"),
])
def test_old_warehouse_claim_is_rejected_after_database_role_change(receipt_client, method, path):
    client, db, user, material, supplier = receipt_client
    auth = headers(user)
    user.role = Role.admin
    db.flush()
    response = client.request(method, path, headers=auth, json=body(material, supplier) if method == "POST" else None)
    assert response.status_code == 403
    assert db.scalar(select(func.count()).select_from(MaterialLot).where(MaterialLot.material_id == material.id)) == 0


def test_demo_inventory_seed_is_repeatable_without_receipts(inventory_db, monkeypatch):
    from app import seed_inventory

    @contextmanager
    def test_session():
        yield inventory_db

    monkeypatch.setattr(seed_inventory, "SessionLocal", test_session)

    def counts():
        return tuple(inventory_db.scalar(select(func.count()).select_from(model)) for model in (Supplier, Material, MaterialLot, User))

    before = counts()
    seed_inventory.main()
    first = counts()
    seed_inventory.main()
    assert counts() == first
    assert first[2:] == before[2:]
