from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Date, cast, func, select
from sqlalchemy.exc import IntegrityError

from app.core.security import JWT_SECRET, create_access_token
from app.database import get_db
from app.main import app
from app.models import Material, MaterialLot, MaterialType, OrderStatus, Product, ProductionOrder, Recipe, RecipeItem, Role, User


@pytest.fixture
def order_client(inventory_db):
    db = inventory_db
    suffix = uuid4().hex
    user = User(name="Test planer", email=f"orders-{suffix}@pijacai.local", password_hash="unused", role=Role.planner)
    product = Product(name=f"Test sok {suffix}", sku=f"TEST-{suffix}", unit="kos")
    no_recipe = Product(name=f"Brez recepture {suffix}", sku=f"EMPTY-{suffix}", unit="kos")
    materials = [
        Material(name="Test koncentrat", type=MaterialType.ingredient, unit="kg"),
        Material(name="Test sladkor", type=MaterialType.ingredient, unit="kg"),
        Material(name="Test plastenka", type=MaterialType.packaging, unit="kos"),
    ]
    db.add_all([user, product, no_recipe, *materials])
    db.flush()
    recipe = Recipe(product_id=product.id, version=1, output_qty=Decimal("1000"), active=True)
    db.add(recipe)
    db.flush()
    db.add_all([RecipeItem(recipe_id=recipe.id, material_id=material.id, qty=Decimal(qty))
                for material, qty in zip(materials, ("80", "25", "1000"))])
    db.flush()
    today = db.scalar(select(cast(func.timezone("Europe/Ljubljana", func.now()), Date)))

    def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    try:
        with TestClient(app) as client:
            yield client, db, SimpleNamespace(user=user, product=product, no_recipe=no_recipe, recipe=recipe, materials=materials, today=today)
    finally:
        app.dependency_overrides.clear()


def headers(data):
    return {"Authorization": f"Bearer {create_access_token(data.user)}"}


def payload(data, **changes):
    return {"product_id": data.product.id, "planned_qty": 500, "planned_date": data.today.isoformat(), **changes}


def request_data(data, path):
    return {"product_id": data.product.id, "planned_qty": 500} if path.endswith("preview") else payload(data)


def test_preview_calculates_requirements_without_orders_or_stock_changes(order_client):
    client, db, data = order_client
    response = client.post("/api/orders/preview", headers=headers(data), json=request_data(data, "/preview"))
    assert response.status_code == 200
    result = response.json()
    assert result["recipe_id"] == data.recipe.id
    assert result["recipe_version"] == 1
    quantities = {item["material_id"]: Decimal(item["required_qty"]) for item in result["requirements"]}
    assert quantities == dict(zip([material.id for material in data.materials], (Decimal("40"), Decimal("12.5"), Decimal("500"))))
    assert db.scalar(select(func.count()).select_from(ProductionOrder).where(ProductionOrder.product_id == data.product.id)) == 0
    assert db.scalar(select(func.count()).select_from(MaterialLot).where(MaterialLot.material_id.in_([m.id for m in data.materials]))) == 0


def test_create_order_pins_active_recipe_and_planner(order_client):
    client, db, data = order_client
    response = client.post("/api/orders", headers=headers(data), json=payload(data, recipe_id=data.recipe.id))
    assert response.status_code == 201
    result = response.json()
    assert result["status"] == "planned"
    assert result["recipe_id"] == data.recipe.id
    assert result["created_by"] == data.user.id
    assert result["planned_date"] == data.today.isoformat()
    assert result["planned_qty"] == 500
    assert db.get(ProductionOrder, result["id"]).recipe_id == data.recipe.id
    assert db.scalar(select(func.count()).select_from(MaterialLot).where(MaterialLot.material_id.in_([m.id for m in data.materials]))) == 0


@pytest.mark.parametrize("role", list(Role))
@pytest.mark.parametrize("method,path,allowed", [
    ("POST", "/api/orders", (Role.planner,)),
    ("POST", "/api/orders/preview", (Role.planner,)),
    ("GET", "/api/lookup/products", (Role.planner,)),
    ("GET", "/api/orders", (Role.planner, Role.operator)),
])
def test_order_route_permissions(order_client, role, method, path, allowed):
    client, db, data = order_client
    data.user.role = role
    db.flush()
    response = client.request(method, path, headers=headers(data), json=request_data(data, path) if method == "POST" else None)
    expected = (201 if path == "/api/orders" and method == "POST" else 200) if role in allowed else 403
    assert response.status_code == expected


@pytest.mark.parametrize("case", ["missing", "invalid", "inactive"])
@pytest.mark.parametrize("method,path", [
    ("POST", "/api/orders"), ("POST", "/api/orders/preview"),
    ("GET", "/api/lookup/products"), ("GET", "/api/orders"),
])
def test_orders_require_valid_login(order_client, case, method, path):
    client, db, data = order_client
    auth = headers(data)
    if case == "missing":
        auth = {}
    elif case == "invalid":
        auth = {"Authorization": "Bearer invalid-token"}
    else:
        data.user.active = False
        db.flush()
    response = client.request(method, path, headers=auth, json=request_data(data, path) if method == "POST" else None)
    assert response.status_code == 401


@pytest.mark.parametrize("changes", [
    {"planned_qty": 0}, {"planned_qty": -1}, {"planned_qty": 1.5}, {"planned_qty": True},
    {"planned_qty": "500"}, {"planned_qty": 2147483648}, {"product_id": 0},
    {"planned_date": "invalid-date"}, {"created_by": 999}, {"status": "done"}, {"recipe_id": True},
])
def test_invalid_order_is_rejected_without_insert(order_client, changes):
    client, db, data = order_client
    response = client.post("/api/orders", headers=headers(data), json=payload(data, **changes))
    assert response.status_code == 422
    assert db.scalar(select(func.count()).select_from(ProductionOrder).where(ProductionOrder.product_id == data.product.id)) == 0


@pytest.mark.parametrize("field", ["product_id", "planned_qty", "planned_date"])
def test_order_fields_are_required(order_client, field):
    client, _, data = order_client
    body = payload(data)
    del body[field]
    assert client.post("/api/orders", headers=headers(data), json=body).status_code == 422


def test_past_business_date_is_rejected(order_client):
    client, _, data = order_client
    response = client.post("/api/orders", headers=headers(data), json=payload(data, planned_date=(data.today - timedelta(days=1)).isoformat()))
    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "planned_date"]


@pytest.mark.parametrize("path", ["/api/orders", "/api/orders/preview"])
def test_product_without_active_recipe_is_rejected(order_client, path):
    client, _, data = order_client
    body = request_data(data, path)
    body["product_id"] = data.no_recipe.id
    response = client.post(path, headers=headers(data), json=body)
    assert response.status_code == 409
    assert response.json() == {"detail": "Za ta izdelek ni aktivne recepture."}


def test_products_lookup_excludes_missing_and_empty_recipes(order_client):
    client, db, data = order_client
    db.add(Recipe(product_id=data.no_recipe.id, version=1, output_qty=Decimal("1000"), active=True))
    db.flush()
    response = client.get("/api/lookup/products", headers=headers(data))
    assert response.status_code == 200
    ids = [item["id"] for item in response.json()]
    assert data.product.id in ids
    assert data.no_recipe.id not in ids
    body = payload(data, product_id=data.no_recipe.id)
    assert client.post("/api/orders", headers=headers(data), json=body).status_code == 409


def test_unknown_product_is_404(order_client):
    client, db, data = order_client
    missing = db.scalar(select(func.max(Product.id))) + 1
    response = client.post("/api/orders", headers=headers(data), json=payload(data, product_id=missing))
    assert response.status_code == 404


def test_stale_preview_recipe_is_rejected(order_client):
    client, _, data = order_client
    response = client.post("/api/orders", headers=headers(data), json=payload(data, recipe_id=data.recipe.id + 1000))
    assert response.status_code == 409
    assert "Ponovno preveri" in response.json()["detail"]


def test_new_recipe_version_does_not_change_existing_order(order_client):
    client, db, data = order_client
    first = client.post("/api/orders", headers=headers(data), json=payload(data)).json()
    data.recipe.active = False
    db.flush()
    new = Recipe(product_id=data.product.id, version=2, output_qty=Decimal("1000"), active=True)
    db.add(new)
    db.flush()
    db.add(RecipeItem(recipe_id=new.id, material_id=data.materials[0].id, qty=Decimal("160")))
    db.flush()
    second_response = client.post("/api/orders", headers=headers(data), json=payload(data))
    assert second_response.status_code == 201
    second = second_response.json()
    assert second["recipe_id"] == new.id
    assert Decimal(second["requirements"][0]["required_qty"]) == Decimal("80")
    orders = client.get("/api/orders", headers=headers(data)).json()
    old = next(order for order in orders if order["id"] == first["id"])
    assert old["recipe_id"] == data.recipe.id
    assert old["recipe_version"] == 1
    assert len(old["requirements"]) == 3
    assert Decimal(old["requirements"][0]["required_qty"]) == Decimal("40")


def test_operator_sees_new_planned_orders_and_not_cancelled_or_done(order_client):
    client, db, data = order_client
    created = []
    for state in OrderStatus:
        order = ProductionOrder(product_id=data.product.id, recipe_id=data.recipe.id, planned_qty=100,
                                planned_date=data.today, status=state, created_by=data.user.id)
        db.add(order)
        created.append(order)
    db.flush()
    planner = client.get("/api/orders", headers=headers(data)).json()
    assert {order.id for order in created}.issubset({order["id"] for order in planner})
    data.user.role = Role.operator
    db.flush()
    visible = client.get("/api/orders", headers=headers(data)).json()
    own = [order for order in visible if order["product_id"] == data.product.id]
    assert {order["status"] for order in own} == {"planned", "in_progress"}


def test_postgres_allows_only_one_active_recipe_per_product(order_client):
    _, db, data = order_client
    with pytest.raises(IntegrityError):
        with db.begin_nested():
            db.add(Recipe(product_id=data.product.id, version=2, output_qty=Decimal("1000"), active=True))
            db.flush()


def test_demo_production_seed_is_repeatable_without_orders_or_stock(order_client, monkeypatch):
    from app import seed_production
    _, db, _ = order_client

    @contextmanager
    def test_session():
        yield db

    monkeypatch.setattr(seed_production, "SessionLocal", test_session)
    before = tuple(db.scalar(select(func.count()).select_from(model)) for model in (ProductionOrder, MaterialLot))
    seed_production.main()
    first = tuple(db.scalar(select(func.count()).select_from(model)) for model in (Product, Recipe, RecipeItem))
    seed_production.main()
    assert tuple(db.scalar(select(func.count()).select_from(model)) for model in (Product, Recipe, RecipeItem)) == first
    assert tuple(db.scalar(select(func.count()).select_from(model)) for model in (ProductionOrder, MaterialLot)) == before


def planned_order(db, data, state=OrderStatus.planned):
    order = ProductionOrder(product_id=data.product.id, recipe_id=data.recipe.id, planned_qty=500,
                            planned_date=data.today, status=state, created_by=data.user.id)
    db.add(order)
    db.flush()
    return order


def test_planner_cancels_order_preserving_details_and_history(order_client):
    client, db, data = order_client
    order = planned_order(db, data)
    original = (order.id, order.product_id, order.recipe_id, order.planned_qty, order.planned_date, order.created_by)
    response = client.post(f"/api/orders/{order.id}/cancel", headers=headers(data))
    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"
    db.refresh(order)
    assert (order.id, order.product_id, order.recipe_id, order.planned_qty, order.planned_date, order.created_by) == original
    assert order.status == OrderStatus.cancelled
    planner_view = client.get("/api/orders", headers=headers(data)).json()
    assert next(item for item in planner_view if item["id"] == order.id)["status"] == "cancelled"
    data.user.role = Role.operator
    db.flush()
    assert order.id not in [item["id"] for item in client.get("/api/orders", headers=headers(data)).json()]


@pytest.mark.parametrize("role", list(Role))
def test_cancellation_only_allows_planner(order_client, role):
    client, db, data = order_client
    order = planned_order(db, data)
    data.user.role = role
    db.flush()
    response = client.post(f"/api/orders/{order.id}/cancel", headers=headers(data))
    assert response.status_code == (200 if role == Role.planner else 403)
    db.refresh(order)
    assert order.status == (OrderStatus.cancelled if role == Role.planner else OrderStatus.planned)


@pytest.mark.parametrize("state", [OrderStatus.in_progress, OrderStatus.done, OrderStatus.cancelled])
def test_non_planned_orders_cannot_be_cancelled(order_client, state):
    client, db, data = order_client
    order = planned_order(db, data, state)
    response = client.post(f"/api/orders/{order.id}/cancel", headers=headers(data))
    assert response.status_code == 409
    if state == OrderStatus.in_progress:
        assert response.json() == {"detail": "Naloga ni mogoče odpovedati, ker je šarža že zagnana."}
    db.refresh(order)
    assert order.status == state


def test_repeated_cancellation_is_rejected_without_deleting_order(order_client):
    client, db, data = order_client
    order = planned_order(db, data)
    assert client.post(f"/api/orders/{order.id}/cancel", headers=headers(data)).status_code == 200
    assert client.post(f"/api/orders/{order.id}/cancel", headers=headers(data)).status_code == 409
    assert db.get(ProductionOrder, order.id).status == OrderStatus.cancelled


def test_missing_order_returns_404_on_cancellation(order_client):
    client, db, data = order_client
    missing = (db.scalar(select(func.max(ProductionOrder.id))) or 0) + 1
    response = client.post(f"/api/orders/{missing}/cancel", headers=headers(data))
    assert response.status_code == 404
    assert response.json() == {"detail": "Proizvodni nalog ni najden."}


@pytest.mark.parametrize("order_id", ["0", "-1", "invalid", "2147483648"])
def test_invalid_cancellation_id_returns_422(order_client, order_id):
    client, _, data = order_client
    assert client.post(f"/api/orders/{order_id}/cancel", headers=headers(data)).status_code == 422


@pytest.mark.parametrize("case", ["missing", "invalid", "expired", "inactive"])
def test_cancellation_requires_valid_active_login(order_client, case):
    client, db, data = order_client
    order = planned_order(db, data)
    auth = headers(data)
    if case == "missing":
        auth = {}
    elif case == "invalid":
        auth = {"Authorization": "Bearer invalid-token"}
    elif case == "expired":
        now = datetime.now(timezone.utc)
        token = jwt.encode({"sub": str(data.user.id), "role": "planner", "iat": now - timedelta(hours=2), "exp": now - timedelta(hours=1)}, JWT_SECRET, algorithm="HS256")
        auth = {"Authorization": f"Bearer {token}"}
    else:
        data.user.active = False
        db.flush()
    assert client.post(f"/api/orders/{order.id}/cancel", headers=auth).status_code == 401
    db.refresh(order)
    assert order.status == OrderStatus.planned


def test_old_planner_claim_cannot_cancel_after_role_change(order_client):
    client, db, data = order_client
    order = planned_order(db, data)
    auth = headers(data)
    data.user.role = Role.operator
    db.flush()
    assert client.post(f"/api/orders/{order.id}/cancel", headers=auth).status_code == 403
    db.refresh(order)
    assert order.status == OrderStatus.planned


def test_planned_order_can_be_cancelled_after_its_recipe_is_deactivated(order_client):
    client, db, data = order_client
    order = planned_order(db, data)
    data.recipe.active = False
    db.flush()
    response = client.post(f"/api/orders/{order.id}/cancel", headers=headers(data))
    assert response.status_code == 200
    assert response.json()["recipe_id"] == data.recipe.id
    assert response.json()["status"] == "cancelled"
