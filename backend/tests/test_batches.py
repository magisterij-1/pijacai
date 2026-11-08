from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from decimal import Decimal
import re
from threading import Barrier
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.schema import CreateSchema, DropSchema

from app.core.security import create_access_token
from app.database import Base, get_db
from app.main import app
from app.models import Batch, BatchConsumption, Material, MaterialLot, MaterialType, OrderStatus, Product, ProductionLine, ProductionOrder, Recipe, RecipeItem, Role, Supplier, User


def setup_data(db):
    suffix = uuid4().hex
    operator = User(name="Test operater", email=f"batch-op-{suffix}@pijacai.local", password_hash="unused", role=Role.operator)
    planner = User(name="Test planer", email=f"batch-plan-{suffix}@pijacai.local", password_hash="unused", role=Role.planner)
    material = Material(name="Test koncentrat", type=MaterialType.ingredient, unit="kg")
    packaging = Material(name="Test plastenke", type=MaterialType.packaging, unit="kos")
    supplier = Supplier(name=f"Test šarže {suffix}")
    product = Product(name="Test sok", sku=f"BATCH-{suffix}", unit="kos")
    line = ProductionLine(name=f"Test linija {suffix}")
    db.add_all([operator, planner, material, packaging, supplier, product, line])
    db.flush()
    recipe = Recipe(product_id=product.id, version=1, output_qty=Decimal("1000"), active=True)
    db.add(recipe)
    db.flush()
    db.add_all([
        RecipeItem(recipe_id=recipe.id, material_id=material.id, qty=Decimal("80")),
        RecipeItem(recipe_id=recipe.id, material_id=packaging.id, qty=Decimal("1000")),
    ])
    order = ProductionOrder(product_id=product.id, recipe_id=recipe.id, planned_qty=1000,
                            planned_date=datetime.now(timezone.utc).date(), created_by=planner.id)
    db.add(order)

    def lot(target, code, quantity, remaining, day):
        return MaterialLot(material_id=target.id, supplier_id=supplier.id, supplier_lot_no=code,
                           received_qty=Decimal(quantity), remaining_qty=Decimal(remaining), unit_cost=Decimal("1"),
                           received_at=datetime(2026, 11, day, tzinfo=timezone.utc), received_by=planner.id)

    zero = lot(material, "PORABLJENA", "5", "0", 1)
    old = lot(material, "STARA", "30", "30", 2)
    new = lot(material, "NOVA", "60", "60", 3)
    bottles = lot(packaging, "PLASTENKE", "1500", "1500", 2)
    db.add_all([zero, old, new, bottles])
    db.commit()
    return SimpleNamespace(operator=operator, planner=planner, material=material, packaging=packaging,
                           recipe=recipe, product=product, order=order, line=line, lots=[zero, old, new, bottles])


@pytest.fixture
def batch_client(inventory_db):
    data = setup_data(inventory_db)

    def override_db():
        yield inventory_db

    app.dependency_overrides[get_db] = override_db
    try:
        with TestClient(app) as client:
            yield client, inventory_db, data
    finally:
        app.dependency_overrides.clear()


def auth(user):
    return {"Authorization": f"Bearer {create_access_token(user)}"}


def payload(data, **changes):
    return {"line_id": data.line.id, "qty": "500", **changes}


def start_path(data):
    return f"/api/orders/{data.order.id}/batches"


def counts(db, data):
    batches = select(Batch.id).where(Batch.order_id == data.order.id)
    return (db.scalar(select(func.count()).select_from(Batch).where(Batch.order_id == data.order.id)),
            db.scalar(select(func.count()).select_from(BatchConsumption).where(BatchConsumption.batch_id.in_(batches))))


def test_preview_checks_all_ingredients_without_writes(batch_client):
    client, db, data = batch_client
    response = client.post(start_path(data) + "/preview", headers=auth(data.operator), json=payload(data))
    assert response.status_code == 200
    result = response.json()
    assert result["can_start"] is True
    requirements = {item["material_id"]: item for item in result["requirements"]}
    assert Decimal(requirements[data.material.id]["required_qty"]) == 40
    assert Decimal(requirements[data.material.id]["available_qty"]) == 90
    assert Decimal(requirements[data.packaging.id]["required_qty"]) == 500
    assert all(item["status"] == "OK" for item in result["requirements"])
    assert counts(db, data) == (0, 0)
    assert data.order.status == OrderStatus.planned


def test_shortage_returns_all_missing_quantities_without_partial_changes(batch_client):
    client, db, data = batch_client
    preview = client.post(start_path(data) + "/preview", headers=auth(data.operator), json=payload(data, qty="10000"))
    assert preview.status_code == 200
    assert preview.json()["can_start"] is False
    response = client.post(start_path(data), headers=auth(data.operator), json=payload(data, qty="10000"))
    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["code"] == "INSUFFICIENT_STOCK"
    missing = {item["material_id"]: Decimal(item["missing_qty"]) for item in detail["missing"]}
    assert missing == {data.material.id: Decimal("710"), data.packaging.id: Decimal("8500")}
    assert counts(db, data) == (0, 0)
    db.refresh(data.order)
    assert data.order.status == OrderStatus.planned
    assert [db.get(MaterialLot, lot.id).remaining_qty for lot in data.lots] == [Decimal("0"), Decimal("30"), Decimal("60"), Decimal("1500")]


def test_start_batch_consumes_fifo_and_records_each_lot(batch_client):
    client, db, data = batch_client
    response = client.post(start_path(data), headers=auth(data.operator), json=payload(data))
    assert response.status_code == 201
    result = response.json()
    assert result["status"] == "in_production"
    assert result["operator_id"] == data.operator.id
    assert Decimal(result["planned_qty"]) == 500
    assert re.fullmatch(rf"\d{{4}}-\d{{2}}-\d{{2}}-L{data.line.id}-01", result["batch_code"])
    used = {item["material_lot_id"]: Decimal(item["qty"]) for item in result["consumptions"]}
    assert used == {data.lots[1].id: Decimal("30"), data.lots[2].id: Decimal("10"), data.lots[3].id: Decimal("500")}
    assert data.lots[0].id not in used
    assert counts(db, data) == (1, 3)
    db.refresh(data.order)
    assert data.order.status == OrderStatus.in_progress
    assert [db.get(MaterialLot, lot.id).remaining_qty for lot in data.lots] == [Decimal("0"), Decimal("0"), Decimal("50"), Decimal("1000")]
    read = client.get(f"/api/batches/{result['id']}", headers=auth(data.operator))
    assert read.status_code == 200
    assert read.json()["consumptions"] == result["consumptions"]
    assert client.post(f"/api/orders/{data.order.id}/cancel", headers=auth(data.planner)).status_code == 409


def test_next_batch_can_start_on_in_progress_order_with_unique_sequence(batch_client):
    client, db, data = batch_client
    first = client.post(start_path(data), headers=auth(data.operator), json=payload(data))
    second = client.post(start_path(data), headers=auth(data.operator), json=payload(data))
    assert first.status_code == second.status_code == 201
    assert first.json()["batch_code"].endswith("-01")
    assert second.json()["batch_code"].endswith("-02")
    assert counts(db, data)[0] == 2


@pytest.mark.parametrize("state", [OrderStatus.cancelled, OrderStatus.done])
def test_invalid_order_state_cannot_start_batch(batch_client, state):
    client, db, data = batch_client
    data.order.status = state
    db.commit()
    response = client.post(start_path(data), headers=auth(data.operator), json=payload(data))
    assert response.status_code == 409
    assert counts(db, data) == (0, 0)


def test_inactive_line_cannot_start_and_is_not_in_lookup(batch_client):
    client, db, data = batch_client
    data.line.active = False
    db.commit()
    response = client.post(start_path(data), headers=auth(data.operator), json=payload(data))
    assert response.status_code == 409
    assert counts(db, data) == (0, 0)
    lines = client.get("/api/lookup/lines", headers=auth(data.operator)).json()
    assert data.line.id not in [line["id"] for line in lines]


@pytest.mark.parametrize("changes", [
    {"qty": "0"}, {"qty": "-1"}, {"qty": "NaN"}, {"qty": "0.0001"},
    {"line_id": True}, {"line_id": 0}, {"operator_id": 999}, {"batch_code": "FORGED"},
])
def test_invalid_batch_request_is_422(batch_client, changes):
    client, db, data = batch_client
    response = client.post(start_path(data), headers=auth(data.operator), json=payload(data, **changes))
    assert response.status_code == 422
    assert counts(db, data) == (0, 0)


def test_unrepresentable_required_quantity_is_rejected_without_rounding(batch_client):
    client, db, data = batch_client
    data.recipe.output_qty = Decimal("3")
    db.commit()
    response = client.post(start_path(data), headers=auth(data.operator), json=payload(data, qty="1"))
    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "qty"]
    assert counts(db, data) == (0, 0)


@pytest.mark.parametrize("role", list(Role))
@pytest.mark.parametrize("operation", ["start", "preview", "lines"])
def test_only_operator_can_check_stock_or_start(batch_client, role, operation):
    client, db, data = batch_client
    data.operator.role = role
    db.commit()
    if operation == "lines":
        response = client.get("/api/lookup/lines", headers=auth(data.operator))
    else:
        path = start_path(data) + ("/preview" if operation == "preview" else "")
        response = client.post(path, headers=auth(data.operator), json=payload(data))
    expected = (201 if operation == "start" else 200) if role == Role.operator else 403
    assert response.status_code == expected


@pytest.mark.parametrize("role", list(Role))
def test_batch_read_permissions(batch_client, role):
    client, db, data = batch_client
    started = client.post(start_path(data), headers=auth(data.operator), json=payload(data))
    assert started.status_code == 201
    data.operator.role = role
    db.commit()
    expected = 200 if role in (Role.operator, Role.planner, Role.quality) else 403
    assert client.get(f"/api/batches/{started.json()['id']}", headers=auth(data.operator)).status_code == expected
    assert client.get("/api/batches", headers=auth(data.operator)).status_code == expected


@pytest.mark.parametrize("case", ["missing", "invalid", "inactive"])
def test_batch_start_requires_valid_active_login(batch_client, case):
    client, db, data = batch_client
    headers = auth(data.operator)
    if case == "missing":
        headers = {}
    elif case == "invalid":
        headers = {"Authorization": "Bearer invalid-token"}
    else:
        data.operator.active = False
        db.commit()
    assert client.post(start_path(data), headers=headers, json=payload(data)).status_code == 401
    assert counts(db, data) == (0, 0)


def test_failure_after_writing_consumption_rolls_back_everything(batch_client):
    client, db, data = batch_client
    original_flush = db.flush

    def failing_flush(*args, **kwargs):
        writing_consumption = any(isinstance(item, BatchConsumption) for item in db.new)
        original_flush(*args, **kwargs)
        if writing_consumption:
            raise RuntimeError("Simulirana napaka po zapisu porabe")

    with patch.object(db, "flush", side_effect=failing_flush):
        with pytest.raises(RuntimeError, match="Simulirana napaka"):
            client.post(start_path(data), headers=auth(data.operator), json=payload(data))
    assert counts(db, data) == (0, 0)
    assert db.get(ProductionOrder, data.order.id).status == OrderStatus.planned
    assert [db.get(MaterialLot, lot.id).remaining_qty for lot in data.lots] == [Decimal("0"), Decimal("30"), Decimal("60"), Decimal("1500")]
    retry = client.post(start_path(data), headers=auth(data.operator), json=payload(data))
    assert retry.status_code == 201
    assert retry.json()["batch_code"].endswith("-01")


def test_batch_uses_pinned_recipe_even_after_deactivation(batch_client):
    client, db, data = batch_client
    data.recipe.active = False
    db.commit()
    response = client.post(start_path(data), headers=auth(data.operator), json=payload(data))
    assert response.status_code == 201
    assert response.json()["recipe_id"] == data.recipe.id
    assert response.json()["recipe_version"] == 1


@pytest.mark.parametrize("missing", ["order", "line"])
def test_missing_order_or_line_is_404_without_writes(batch_client, missing):
    client, db, data = batch_client
    path, body = start_path(data), payload(data)
    if missing == "order":
        absent = (db.scalar(select(func.max(ProductionOrder.id))) or 0) + 1
        path = f"/api/orders/{absent}/batches"
    else:
        body["line_id"] = (db.scalar(select(func.max(ProductionLine.id))) or 0) + 1
    assert client.post(path, headers=auth(data.operator), json=body).status_code == 404
    assert counts(db, data) == (0, 0)


@pytest.mark.parametrize("field", ["line_id", "qty"])
def test_batch_start_fields_are_required(batch_client, field):
    client, db, data = batch_client
    body = payload(data)
    del body[field]
    assert client.post(start_path(data), headers=auth(data.operator), json=body).status_code == 422
    assert counts(db, data) == (0, 0)


def test_order_with_a_batch_cannot_be_cancelled_even_if_status_is_inconsistent(batch_client):
    client, db, data = batch_client
    assert client.post(start_path(data), headers=auth(data.operator), json=payload(data)).status_code == 201
    data.order.status = OrderStatus.planned
    db.commit()
    response = client.post(f"/api/orders/{data.order.id}/cancel", headers=auth(data.planner))
    assert response.status_code == 409
    assert "šarža že zagnana" in response.json()["detail"]


@pytest.fixture
def concurrent_sessions(postgres_database_url):
    # Ločena shema omogoča prave commite na več povezavah brez poseganja v razvojne vrstice.
    schema = "test_batches_" + uuid4().hex
    engine = create_engine(postgres_database_url, execution_options={"schema_translate_map": {None: schema}})
    created = False
    try:
        with engine.begin() as connection:
            connection.execute(CreateSchema(schema))
            Base.metadata.create_all(connection)
        created = True
        yield sessionmaker(bind=engine, expire_on_commit=False)
    finally:
        if created:
            assert re.fullmatch(r"test_batches_[0-9a-f]{32}", schema)
            with engine.begin() as connection:
                connection.execute(DropSchema(schema, cascade=True))
        engine.dispose()


def test_concurrent_requests_cannot_double_spend_stock(concurrent_sessions, monkeypatch):
    from app.services import batch_start
    factory = concurrent_sessions
    with factory() as db:
        data = setup_data(db)
        other_operator = User(name="Drugi operater", email=f"second-{uuid4().hex}@pijacai.local", password_hash="unused", role=Role.operator)
        other_line = ProductionLine(name="Druga sočasna linija")
        other_order = ProductionOrder(product_id=data.product.id, recipe_id=data.recipe.id, planned_qty=1000,
                                      planned_date=data.order.planned_date, created_by=data.planner.id)
        db.add_all([other_operator, other_line, other_order])
        db.commit()
        jobs = [(data.order.id, data.line.id, auth(data.operator)), (other_order.id, other_line.id, auth(other_operator))]
        material_id, packaging_id = data.material.id, data.packaging.id

    barrier = Barrier(2)
    original_prepare = batch_start.prepare

    def synchronized_prepare(*args, **kwargs):
        if kwargs.get("lock"):
            barrier.wait(timeout=15)
        return original_prepare(*args, **kwargs)

    monkeypatch.setattr(batch_start, "prepare", synchronized_prepare)

    def override_db():
        with factory() as db:
            yield db

    app.dependency_overrides[get_db] = override_db
    try:
        with TestClient(app) as client:
            def request(job):
                order_id, line_id, headers = job
                return client.post(f"/api/orders/{order_id}/batches", headers=headers, json={"line_id": line_id, "qty": "1000"})
            with ThreadPoolExecutor(max_workers=2) as pool:
                responses = list(pool.map(request, jobs))
        assert sorted(response.status_code for response in responses) == [201, 409]
        loser = next(response for response in responses if response.status_code == 409)
        assert loser.json()["detail"]["code"] == "INSUFFICIENT_STOCK"
        with factory() as db:
            assert db.scalar(select(func.count()).select_from(Batch)) == 1
            assert db.scalar(select(func.sum(MaterialLot.remaining_qty)).where(MaterialLot.material_id == material_id)) == Decimal("10")
            assert db.scalar(select(func.sum(MaterialLot.remaining_qty)).where(MaterialLot.material_id == packaging_id)) == Decimal("500")
            assert db.scalar(select(func.count()).select_from(MaterialLot).where(MaterialLot.remaining_qty < 0)) == 0
            assert sorted(order.status.value for order in db.scalars(select(ProductionOrder))) == ["in_progress", "planned"]
    finally:
        app.dependency_overrides.clear()
