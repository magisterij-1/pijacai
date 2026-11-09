from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app.models import Batch, BatchConsumption, BatchStatus, MaterialLot, Role
# Skupna integracijska priprava z dejanskim FIFO zagonom; fixture uporablja inventory_db.
from test_batches import auth, batch_client, payload, start_path


@pytest.fixture
def trace_data(batch_client):
    client, db, data = batch_client
    response = client.post(start_path(data), headers=auth(data.operator), json=payload(data))
    assert response.status_code == 201
    return client, db, data, response.json()


@pytest.mark.parametrize("role", [Role.planner, Role.quality])
def test_trace_returns_each_consumed_lot_and_exact_material_totals(trace_data, role):
    client, db, data, started = trace_data
    data.planner.role = role
    db.commit()
    response = client.get(f"/api/traceability/batch/{started['id']}", headers=auth(data.planner))
    assert response.status_code == 200
    result = response.json()
    assert result["product_id"] == data.product.id
    assert result["product_name"] == data.product.name
    assert result["batch_code"] == started["batch_code"]
    assert result["status"] == "in_production"
    assert result["consumptions"] == started["consumptions"]
    assert len(result["consumptions"]) == 3
    rows = {row["material_lot_id"]: row for row in result["consumptions"]}
    assert set(rows) == {data.lots[1].id, data.lots[2].id, data.lots[3].id}
    assert rows[data.lots[1].id]["supplier_lot_no"] == "STARA"
    assert rows[data.lots[2].id]["supplier_lot_no"] == "NOVA"
    assert rows[data.lots[1].id]["supplier_name"] == data.lots[1].supplier.name
    assert rows[data.lots[1].id]["material_name"] == data.material.name
    assert Decimal(rows[data.lots[1].id]["qty"]) == Decimal("30")
    assert Decimal(rows[data.lots[2].id]["qty"]) == Decimal("10")
    totals = {row["material_id"]: row for row in result["totals"]}
    assert Decimal(totals[data.material.id]["consumed_qty"]) == Decimal("40")
    assert totals[data.material.id]["unit"] == "kg"
    assert Decimal(totals[data.packaging.id]["consumed_qty"]) == Decimal("500")
    assert totals[data.packaging.id]["unit"] == "kos"
    recorded = db.execute(select(MaterialLot.material_id, func.sum(BatchConsumption.qty))
                          .join(BatchConsumption, BatchConsumption.material_lot_id == MaterialLot.id)
                          .where(BatchConsumption.batch_id == started["id"]).group_by(MaterialLot.material_id)).all()
    assert {material: quantity for material, quantity in recorded} == {material: Decimal(row["consumed_qty"]) for material, row in totals.items()}


@pytest.mark.parametrize("role", [Role.planner, Role.quality])
def test_lookup_by_exact_code_matches_lookup_by_id(trace_data, role):
    client, db, data, started = trace_data
    data.planner.role = role
    db.commit()
    headers = auth(data.planner)
    by_id = client.get(f"/api/traceability/batch/{started['id']}", headers=headers)
    by_code = client.get("/api/traceability/batch", params={"batch_code": "  " + started["batch_code"] + "  "}, headers=headers)
    assert by_id.status_code == by_code.status_code == 200
    assert by_code.json() == by_id.json()


@pytest.mark.parametrize("state", list(BatchStatus))
def test_traceability_is_available_in_all_batch_states(trace_data, state):
    client, db, data, started = trace_data
    batch = db.get(Batch, started["id"])
    batch.status = state
    if state == BatchStatus.rejected:
        batch.decision_note = "Neustrezna vrednost pH."
        batch.decided_by = data.planner.id
    db.commit()
    response = client.get(f"/api/traceability/batch/{batch.id}", headers=auth(data.planner))
    assert response.status_code == 200
    assert response.json()["status"] == state.value
    assert response.json()["consumptions"] == started["consumptions"]
    assert response.json()["decision_note"] == batch.decision_note


def test_later_stock_consumption_does_not_change_previous_trace(trace_data):
    client, db, data, started = trace_data
    path = f"/api/traceability/batch/{started['id']}"
    before = client.get(path, headers=auth(data.planner))
    assert before.status_code == 200
    second = client.post(start_path(data), headers=auth(data.operator), json=payload(data))
    assert second.status_code == 201
    assert second.json()["id"] != started["id"]
    stock_before = {lot.id: lot.remaining_qty for lot in data.lots}
    after = client.get(path, headers=auth(data.planner))
    assert after.status_code == 200 and after.json() == before.json()
    assert db.scalar(select(func.count()).select_from(BatchConsumption).where(BatchConsumption.batch_id == started["id"])) == 3
    for lot in data.lots:
        db.refresh(lot)
        assert lot.remaining_qty == stock_before[lot.id]


@pytest.mark.parametrize("lookup", ["id", "code"])
def test_missing_batch_returns_expected_message(batch_client, lookup):
    client, db, data = batch_client
    missing = (db.scalar(select(func.max(Batch.id))) or 0) + 1
    path = f"/api/traceability/batch/{missing}" if lookup == "id" else "/api/traceability/batch"
    options = {"headers": auth(data.planner)}
    if lookup == "code":
        options["params"] = {"batch_code": f"NEOBSTOJECA-{uuid4().hex}"}
    response = client.get(path, **options)
    assert response.status_code == 404
    assert response.json() == {"detail": "Šarža ni najdena."}


@pytest.mark.parametrize("role", [Role.operator, Role.warehouse, Role.admin])
@pytest.mark.parametrize("lookup", ["id", "code"])
def test_trace_denies_unapproved_roles(trace_data, role, lookup):
    client, db, data, started = trace_data
    data.planner.role = role
    db.commit()
    path = f"/api/traceability/batch/{started['id']}" if lookup == "id" else "/api/traceability/batch"
    options = {"headers": auth(data.planner)}
    if lookup == "code":
        options["params"] = {"batch_code": started["batch_code"]}
    assert client.get(path, **options).status_code == 403


@pytest.mark.parametrize("case", ["missing", "invalid", "inactive"])
@pytest.mark.parametrize("lookup", ["id", "code"])
def test_trace_requires_active_login(trace_data, case, lookup):
    client, db, data, started = trace_data
    headers = {} if case == "missing" else {"Authorization": "Bearer invalid"}
    if case == "inactive":
        headers = auth(data.planner)
        data.planner.active = False
        db.commit()
    path = f"/api/traceability/batch/{started['id']}" if lookup == "id" else "/api/traceability/batch"
    options = {"headers": headers}
    if lookup == "code":
        options["params"] = {"batch_code": started["batch_code"]}
    assert client.get(path, **options).status_code == 401


@pytest.mark.parametrize("code", ["", "   ", "a" * 81])
def test_trace_rejects_invalid_code(batch_client, code):
    client, db, data = batch_client
    response = client.get("/api/traceability/batch", params={"batch_code": code}, headers=auth(data.planner))
    assert response.status_code == 422
    assert any(item["loc"] == ["query", "batch_code"] for item in response.json()["detail"])


def test_trace_code_is_required(batch_client):
    client, db, data = batch_client
    assert client.get("/api/traceability/batch", headers=auth(data.planner)).status_code == 422


@pytest.mark.parametrize("identifier", ["0", "-1", "2147483648", "abc"])
def test_trace_rejects_invalid_id(batch_client, identifier):
    client, db, data = batch_client
    assert client.get(f"/api/traceability/batch/{identifier}", headers=auth(data.planner)).status_code == 422


def test_trace_empty_consumption_returns_empty_lists(trace_data):
    client, db, data, started = trace_data
    # Uvožena zgodovinska šarža brez porabe se lahko bere, vendar ne izmisli serij.
    batch = Batch(batch_code=f"EMPTY-{uuid4().hex}", order_id=data.order.id, line_id=data.line.id,
                  operator_id=data.operator.id, production_date=data.order.planned_date,
                  sequence_no=999, planned_qty=Decimal("1"), status=BatchStatus.in_production)
    db.add(batch)
    db.commit()
    response = client.get(f"/api/traceability/batch/{batch.id}", headers=auth(data.planner))
    assert response.status_code == 200
    assert response.json()["consumptions"] == []
    assert response.json()["totals"] == []
