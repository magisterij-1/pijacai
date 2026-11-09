# — zagon, FIFO, sočasnost in zaključek šarže.
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
from app.models import Batch, BatchConsumption, BatchStatus, Material, MaterialLot, MaterialType, OrderStatus, Product, ProductionLine, ProductionOrder, Recipe, RecipeItem, Role, Supplier, User


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


@pytest.fixture
def running_batch(batch_client):
    client, db, data = batch_client
    response = client.post(start_path(data), headers=auth(data.operator), json=payload(data))
    assert response.status_code == 201
    return client, db, data, response.json()


def assert_unfinished(db, batch_id):
    batch = db.get(Batch, batch_id, populate_existing=True)
    assert batch.status == BatchStatus.in_production
    assert batch.produced_qty == batch.rejected_qty == 0
    assert batch.finished_at is None


@pytest.mark.parametrize("produced,rejected", [(480, 5), (0, 0), (500, 500), (2147483647, 0)])
def test_finish_records_quantities_and_places_batch_in_quality_queue(running_batch, produced, rejected):
    client, db, data, started = running_batch
    before = {lot.id: lot.remaining_qty for lot in data.lots}
    response = client.post(f"/api/batches/{started['id']}/finish", headers=auth(data.operator),
                           json={"produced_qty": produced, "rejected_qty": rejected})
    assert response.status_code == 200
    result = response.json()
    assert result["status"] == "awaiting_qc"
    assert result["produced_qty"] == produced
    assert result["rejected_qty"] == rejected
    assert datetime.fromisoformat(result["finished_at"]) >= datetime.fromisoformat(started["started_at"])
    assert result["consumptions"] == started["consumptions"]
    saved = db.get(Batch, started["id"], populate_existing=True)
    assert saved.status == BatchStatus.awaiting_qc
    assert (saved.produced_qty, saved.rejected_qty) == (produced, rejected)
    assert saved.finished_at is not None
    db.refresh(data.order)
    assert data.order.status == OrderStatus.in_progress
    for lot in data.lots:
        db.refresh(lot)
        assert lot.remaining_qty == before[lot.id]
    assert counts(db, data) == (1, 3)
    data.planner.role = Role.quality
    db.commit()
    queue = client.get("/api/batches", params={"status_filter": "awaiting_qc", "order_id": data.order.id}, headers=auth(data.planner))
    assert queue.status_code == 200
    assert [batch["id"] for batch in queue.json()] == [started["id"]]
    active = client.get("/api/batches", params={"status_filter": "in_production", "order_id": data.order.id}, headers=auth(data.operator))
    assert active.status_code == 200
    assert active.json() == []


@pytest.mark.parametrize("field,value", [
    ("produced_qty", -1), ("rejected_qty", -1),
    ("produced_qty", 1.5), ("rejected_qty", 1.5),
    ("produced_qty", True), ("rejected_qty", False),
    ("produced_qty", "500"), ("rejected_qty", "0"),
    ("produced_qty", None), ("rejected_qty", None),
    ("produced_qty", 2147483648), ("rejected_qty", 2147483648),
])
def test_finish_rejects_invalid_quantities_without_changes(running_batch, field, value):
    client, db, data, started = running_batch
    body = {"produced_qty": 500, "rejected_qty": 0, field: value}
    response = client.post(f"/api/batches/{started['id']}/finish", headers=auth(data.operator), json=body)
    assert response.status_code == 422
    assert any(item["loc"] == ["body", field] for item in response.json()["detail"])
    assert_unfinished(db, started["id"])


@pytest.mark.parametrize("field", ["produced_qty", "rejected_qty"])
def test_finish_requires_both_quantities(running_batch, field):
    client, db, data, started = running_batch
    body = {"produced_qty": 500, "rejected_qty": 0}
    del body[field]
    response = client.post(f"/api/batches/{started['id']}/finish", headers=auth(data.operator), json=body)
    assert response.status_code == 422
    assert any(item["loc"] == ["body", field] for item in response.json()["detail"])
    assert_unfinished(db, started["id"])


def test_finish_excess_waste_has_error_at_rejected_quantity(running_batch):
    client, db, data, started = running_batch
    response = client.post(f"/api/batches/{started['id']}/finish", headers=auth(data.operator),
                           json={"produced_qty": 10, "rejected_qty": 11})
    assert response.status_code == 422
    error = next(item for item in response.json()["detail"] if item["loc"] == ["body", "rejected_qty"])
    assert "Izmet ne sme presegati proizvedene količine." in error["msg"]
    assert_unfinished(db, started["id"])


@pytest.mark.parametrize("role", [Role.admin, Role.planner, Role.quality, Role.warehouse])
def test_finish_denies_other_roles(running_batch, role):
    client, db, data, started = running_batch
    data.planner.role = role
    db.commit()
    response = client.post(f"/api/batches/{started['id']}/finish", headers=auth(data.planner),
                           json={"produced_qty": 500, "rejected_qty": 0})
    assert response.status_code == 403
    assert_unfinished(db, started["id"])


def test_finish_denies_another_operator(running_batch):
    client, db, data, started = running_batch
    data.planner.role = Role.operator
    db.commit()
    response = client.post(f"/api/batches/{started['id']}/finish", headers=auth(data.planner),
                           json={"produced_qty": 500, "rejected_qty": 0})
    assert response.status_code == 403
    assert_unfinished(db, started["id"])


@pytest.mark.parametrize("case", ["missing", "invalid", "inactive"])
def test_finish_requires_active_login(running_batch, case):
    client, db, data, started = running_batch
    headers = {} if case == "missing" else {"Authorization": "Bearer invalid"}
    if case == "inactive":
        headers = auth(data.operator)
        data.operator.active = False
        db.commit()
    response = client.post(f"/api/batches/{started['id']}/finish", headers=headers,
                           json={"produced_qty": 500, "rejected_qty": 0})
    assert response.status_code == 401
    assert_unfinished(db, started["id"])


def test_finish_cannot_overwrite_previously_finished_batch(running_batch):
    client, db, data, started = running_batch
    path = f"/api/batches/{started['id']}/finish"
    first = client.post(path, headers=auth(data.operator), json={"produced_qty": 480, "rejected_qty": 5})
    assert first.status_code == 200
    second = client.post(path, headers=auth(data.operator), json={"produced_qty": 999, "rejected_qty": 1})
    assert second.status_code == 409
    saved = client.get(f"/api/batches/{started['id']}", headers=auth(data.operator))
    assert saved.status_code == 200
    assert saved.json() == first.json()


@pytest.mark.parametrize("state", [BatchStatus.released, BatchStatus.rejected])
def test_finish_cannot_change_decided_batch(running_batch, state):
    client, db, data, started = running_batch
    batch = db.get(Batch, started["id"])
    batch.status = state
    db.commit()
    response = client.post(f"/api/batches/{batch.id}/finish", headers=auth(data.operator),
                           json={"produced_qty": 500, "rejected_qty": 0})
    assert response.status_code == 409
    db.refresh(batch)
    assert batch.status == state
    assert batch.produced_qty == batch.rejected_qty == 0
    assert batch.finished_at is None


def test_finish_missing_batch_is_404(batch_client):
    client, db, data = batch_client
    absent = (db.scalar(select(func.max(Batch.id))) or 0) + 1
    response = client.post(f"/api/batches/{absent}/finish", headers=auth(data.operator),
                           json={"produced_qty": 500, "rejected_qty": 0})
    assert response.status_code == 404
    assert counts(db, data) == (0, 0)


def test_finish_rejects_extra_state_fields(running_batch):
    client, db, data, started = running_batch
    response = client.post(f"/api/batches/{started['id']}/finish", headers=auth(data.operator),
                           json={"produced_qty": 500, "rejected_qty": 0, "status": "released"})
    assert response.status_code == 422
    assert_unfinished(db, started["id"])


def test_finish_commit_failure_rolls_back_and_allows_retry(running_batch):
    client, db, data, started = running_batch
    path = f"/api/batches/{started['id']}/finish"
    before = {lot.id: lot.remaining_qty for lot in data.lots}
    with patch.object(db, "commit", side_effect=RuntimeError("Simulirana napaka zaključka")):
        with pytest.raises(RuntimeError, match="Simulirana napaka zaključka"):
            client.post(path, headers=auth(data.operator), json={"produced_qty": 480, "rejected_qty": 5})
    assert_unfinished(db, started["id"])
    for lot in data.lots:
        db.refresh(lot)
        assert lot.remaining_qty == before[lot.id]
    assert counts(db, data) == (1, 3)
    retry = client.post(path, headers=auth(data.operator), json={"produced_qty": 480, "rejected_qty": 5})
    assert retry.status_code == 200


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


@pytest.mark.parametrize("quantity,used,remaining", [
    ("10", "0.800", "29.200"),
    ("375", "30.000", "0.000"),
])
def test_fifo_uses_only_oldest_lot_when_it_is_sufficient(batch_client, quantity, used, remaining):
    client, db, data = batch_client
    response = client.post(start_path(data), headers=auth(data.operator), json=payload(data, qty=quantity))
    assert response.status_code == 201
    consumption = {item["material_lot_id"]: Decimal(item["qty"]) for item in response.json()["consumptions"]}
    assert consumption == {data.lots[1].id: Decimal(used), data.lots[3].id: Decimal(quantity)}
    db.refresh(data.lots[1])
    db.refresh(data.lots[2])
    assert data.lots[1].remaining_qty == Decimal(remaining)
    assert data.lots[2].remaining_qty == Decimal("60")
    assert counts(db, data) == (1, 2)


def test_fifo_prioritizes_receipt_time_over_lot_id(batch_client):
    client, db, data = batch_client
    old, new = data.lots[1:3]
    assert old.id < new.id
    new.received_at = datetime(2026, 11, 1, tzinfo=timezone.utc)
    db.commit()
    response = client.post(start_path(data), headers=auth(data.operator), json=payload(data))
    assert response.status_code == 201
    used = {item["material_lot_id"]: Decimal(item["qty"]) for item in response.json()["consumptions"]}
    assert used == {new.id: Decimal("40"), data.lots[3].id: Decimal("500")}
    db.refresh(old)
    db.refresh(new)
    assert old.remaining_qty == Decimal("30")
    assert new.remaining_qty == Decimal("20")


def test_fifo_breaks_equal_receipt_times_by_lot_id(batch_client):
    client, db, data = batch_client
    old, new = data.lots[1:3]
    new.received_at = old.received_at
    db.commit()
    assert old.id < new.id
    response = client.post(start_path(data), headers=auth(data.operator), json=payload(data))
    assert response.status_code == 201
    used = {item["material_lot_id"]: Decimal(item["qty"]) for item in response.json()["consumptions"]}
    assert used == {old.id: Decimal("30"), new.id: Decimal("10"), data.lots[3].id: Decimal("500")}


def test_fifo_consumes_remaining_quantity_instead_of_received_quantity(batch_client):
    client, db, data = batch_client
    old, new = data.lots[1:3]
    old.remaining_qty = Decimal("7.125")
    db.commit()
    response = client.post(start_path(data), headers=auth(data.operator), json=payload(data, qty="100"))
    assert response.status_code == 201
    used = {item["material_lot_id"]: Decimal(item["qty"]) for item in response.json()["consumptions"]}
    assert used == {old.id: Decimal("7.125"), new.id: Decimal("0.875"), data.lots[3].id: Decimal("100")}
    db.refresh(old)
    db.refresh(new)
    assert old.remaining_qty == 0
    assert old.received_qty == Decimal("30")
    assert new.remaining_qty == Decimal("59.125")


def test_start_accepts_exactly_available_ingredient_quantity(batch_client):
    client, db, data = batch_client
    response = client.post(start_path(data), headers=auth(data.operator), json=payload(data, qty="1125"))
    assert response.status_code == 201
    used = {item["material_lot_id"]: Decimal(item["qty"]) for item in response.json()["consumptions"]}
    assert used == {data.lots[1].id: Decimal("30"), data.lots[2].id: Decimal("60"), data.lots[3].id: Decimal("1125")}
    for lot in data.lots:
        db.refresh(lot)
    assert [lot.remaining_qty for lot in data.lots] == [Decimal("0"), Decimal("0"), Decimal("0"), Decimal("375")]


@pytest.mark.parametrize("preview_first", [False, True])
def test_packaging_shortage_keeps_sufficient_ingredients_unchanged(batch_client, preview_first):
    client, db, data = batch_client
    if preview_first:
        preview = client.post(start_path(data) + "/preview", headers=auth(data.operator), json=payload(data))
        assert preview.status_code == 200
        assert preview.json()["can_start"] is True
    data.lots[3].remaining_qty = Decimal("499.999")
    db.commit()
    response = client.post(start_path(data), headers=auth(data.operator), json=payload(data))
    assert response.status_code == 409
    missing = response.json()["detail"]["missing"]
    assert len(missing) == 1
    assert missing[0]["material_id"] == data.packaging.id
    assert Decimal(missing[0]["missing_qty"]) == Decimal("0.001")
    assert counts(db, data) == (0, 0)
    db.refresh(data.order)
    assert data.order.status == OrderStatus.planned
    for lot in data.lots:
        db.refresh(lot)
    assert [lot.remaining_qty for lot in data.lots] == [Decimal("0"), Decimal("30"), Decimal("60"), Decimal("499.999")]


def test_repeated_starts_conserve_stock_and_record_recipe_totals_per_batch(batch_client):
    client, db, data = batch_client
    before = {lot.id: (lot.remaining_qty, lot.received_qty) for lot in data.lots}
    consumed = {lot.id: Decimal("0") for lot in data.lots}
    for quantity, expected in [("250", {data.material.id: Decimal("20"), data.packaging.id: Decimal("250")}),
                               ("500", {data.material.id: Decimal("40"), data.packaging.id: Decimal("500")})]:
        response = client.post(start_path(data), headers=auth(data.operator), json=payload(data, qty=quantity))
        assert response.status_code == 201
        batch_id = response.json()["id"]
        rows = db.execute(select(MaterialLot.material_id, BatchConsumption.material_lot_id, BatchConsumption.qty)
                          .join(MaterialLot, MaterialLot.id == BatchConsumption.material_lot_id)
                          .where(BatchConsumption.batch_id == batch_id)).all()
        totals = {}
        for material_id, lot_id, quantity_used in rows:
            assert quantity_used > 0
            totals[material_id] = totals.get(material_id, Decimal("0")) + quantity_used
            consumed[lot_id] += quantity_used
        assert totals == expected
        assert len(rows) == len({lot_id for _, lot_id, _ in rows})
    assert counts(db, data) == (2, 5)
    for lot in data.lots:
        db.refresh(lot)
        remaining_before, received_before = before[lot.id]
        assert lot.remaining_qty >= 0
        assert lot.remaining_qty + consumed[lot.id] == remaining_before
        assert lot.received_qty == received_before


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
