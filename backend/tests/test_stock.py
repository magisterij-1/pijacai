from datetime import datetime, timedelta, timezone
from decimal import Decimal
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
def stock_client(inventory_db):
    db = inventory_db
    suffix = uuid4().hex
    user = User(name="Test zaloge", email=f"stock-{suffix}@pijacai.local", password_hash="unused", role=Role.warehouse)
    a = Material(name=f"Koncentrat {suffix}", type=MaterialType.ingredient, unit="kg")
    b = Material(name=f"Plastenke {suffix}", type=MaterialType.packaging, unit="kos")
    empty = Material(name=f"Brez zaloge {suffix}", type=MaterialType.ingredient, unit="L")
    supplier = Supplier(name=f"Test zaloge {suffix}")
    db.add_all([user, a, b, empty, supplier])
    db.flush()

    def lot(material, code, received, remaining, day):
        return MaterialLot(
            material_id=material.id, supplier_id=supplier.id, supplier_lot_no=code,
            received_qty=Decimal(received), remaining_qty=Decimal(remaining), unit_cost=Decimal("1.000"),
            received_at=datetime(2026, 11, day, tzinfo=timezone.utc), received_by=user.id,
        )

    # Vrstni red vstavljanja se namerno razlikuje od časa prejema.
    late = lot(a, "POZNA", "0.200", "0.200", 5)
    early = lot(a, "ZGODNJA", "0.100", "0.100", 1)
    consumed = lot(a, "PORABLJENA", "5.000", "0.000", 1)
    packaging = lot(b, "EMBALAZA", "7.000", "7.000", 2)
    tie = lot(a, "ISTI-CAS", "0.300", "0.300", 5)
    db.add_all([late, early, consumed, packaging, tie])
    db.flush()

    def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    try:
        with TestClient(app) as client:
            yield client, db, user, a, b, empty, (late, early, consumed, packaging, tie)
    finally:
        app.dependency_overrides.clear()


def headers(user):
    return {"Authorization": f"Bearer {create_access_token(user)}"}


def test_stock_filters_material_and_orders_fifo_with_id_tiebreaker(stock_client):
    client, _, user, a, _, _, (late, early, _, _, tie) = stock_client
    response = client.get("/api/stock", params={"material_id": a.id}, headers=headers(user))
    assert response.status_code == 200
    result = response.json()
    assert [lot["id"] for lot in result["lots"]] == [early.id, late.id, tie.id]
    assert len(result["totals"]) == 1
    assert Decimal(result["totals"][0]["remaining_qty"]) == Decimal("0.600")


def test_stock_contains_names_units_and_separate_totals(stock_client):
    client, _, user, a, b, _, (_, early, _, _, _) = stock_client
    response = client.get("/api/stock", headers=headers(user))
    assert response.status_code == 200
    result = response.json()
    totals = {item["material_id"]: item for item in result["totals"]}
    assert Decimal(totals[a.id]["remaining_qty"]) == Decimal("0.600")
    assert totals[a.id]["unit"] == "kg"
    assert Decimal(totals[b.id]["remaining_qty"]) == Decimal("7.000")
    assert totals[b.id]["unit"] == "kos"
    row = next(item for item in result["lots"] if item["id"] == early.id)
    assert row["material_name"] == a.name
    assert row["material_type"] == "ingredient"
    assert row["supplier_name"] == early.supplier.name
    assert row["supplier_lot_no"] == "ZGODNJA"
    assert Decimal(row["received_qty"]) == Decimal("0.100")
    assert datetime.fromisoformat(row["received_at"]).tzinfo is not None


def test_include_consumed_changes_rows_but_not_total(stock_client):
    client, _, user, a, _, _, (_, _, consumed, _, _) = stock_client
    default = client.get("/api/stock", params={"material_id": a.id}, headers=headers(user)).json()
    expanded = client.get("/api/stock", params={"material_id": a.id, "include_consumed": "true"}, headers=headers(user)).json()
    assert consumed.id not in [item["id"] for item in default["lots"]]
    assert consumed.id in [item["id"] for item in expanded["lots"]]
    assert len(expanded["lots"]) == len(default["lots"]) + 1
    assert expanded["totals"] == default["totals"]


def test_material_without_lots_has_zero_total(stock_client):
    client, _, user, _, _, empty, _ = stock_client
    response = client.get("/api/stock", params={"material_id": empty.id}, headers=headers(user))
    assert response.status_code == 200
    assert response.json()["lots"] == []
    assert response.json()["totals"] == [{
        "material_id": empty.id, "material_name": empty.name, "unit": "L", "remaining_qty": "0.000",
    }]


def test_fully_consumed_material_still_has_zero_total_when_selected(stock_client):
    client, db, user, a, _, _, _ = stock_client
    for lot in db.scalars(select(MaterialLot).where(MaterialLot.material_id == a.id)):
        lot.remaining_qty = Decimal("0")
    db.flush()
    result = client.get("/api/stock", params={"material_id": a.id}, headers=headers(user)).json()
    assert result["lots"] == []
    assert Decimal(result["totals"][0]["remaining_qty"]) == 0


def test_nonexistent_material_returns_404(stock_client):
    client, db, user, *_ = stock_client
    missing_id = db.scalar(select(func.max(Material.id))) + 1
    response = client.get("/api/stock", params={"material_id": missing_id}, headers=headers(user))
    assert response.status_code == 404
    assert response.json() == {"detail": "Surovina ni najdena."}


@pytest.mark.parametrize("params", [
    {"material_id": "0"}, {"material_id": "-1"}, {"material_id": "invalid"},
    {"material_id": "2147483648"}, {"include_consumed": "invalid"},
])
def test_invalid_stock_query_returns_422(stock_client, params):
    client, _, user, *_ = stock_client
    assert client.get("/api/stock", params=params, headers=headers(user)).status_code == 422


@pytest.mark.parametrize("role", list(Role))
def test_stock_allows_only_warehouse(stock_client, role):
    client, db, user, *_ = stock_client
    user.role = role
    db.flush()
    response = client.get("/api/stock", headers=headers(user))
    assert response.status_code == (200 if role == Role.warehouse else 403)


@pytest.mark.parametrize("case", ["missing", "invalid", "expired", "inactive", "missing_user"])
def test_stock_rejects_invalid_authentication(stock_client, case):
    client, db, user, *_ = stock_client
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
    else:
        absent = User(id=db.scalar(select(func.max(User.id))) + 1, role=Role.warehouse)
        auth = headers(absent)
    assert client.get("/api/stock", headers=auth).status_code == 401
