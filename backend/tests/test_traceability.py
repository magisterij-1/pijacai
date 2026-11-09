from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app.models import Batch, BatchConsumption, BatchStatus, MaterialLot, Role, Supplier
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


@pytest.mark.parametrize("role", [Role.planner, Role.quality])
def test_lot_trace_lists_all_affected_batches_with_exact_quantities(trace_data, role):
    client, db, data, first = trace_data
    second = client.post(start_path(data), headers=auth(data.operator), json=payload(data))
    assert second.status_code == 201
    data.planner.role = role
    db.commit()
    lot = data.lots[2]
    response = client.get(f"/api/traceability/lot/{lot.id}", headers=auth(data.planner))
    assert response.status_code == 200
    result = response.json()
    assert result["id"] == lot.id
    assert result["material_name"] == data.material.name
    assert result["supplier_lot_no"] == "NOVA"
    assert result["supplier_name"] == lot.supplier.name
    assert result["unit"] == "kg"
    assert [row["batch_id"] for row in result["batches"]] == [first["id"], second.json()["id"]]
    assert [Decimal(row["consumed_qty"]) for row in result["batches"]] == [Decimal("10"), Decimal("40")]
    assert Decimal(result["total_consumed_qty"]) == Decimal("50")
    assert Decimal(result["remaining_qty"]) == Decimal("10")
    assert all(row["product_name"] == data.product.name and row["started_at"] and row["status"] == "in_production" for row in result["batches"])


def test_forward_and_backward_trace_contain_exactly_same_lot_batch_pairs(trace_data):
    client, db, data, first = trace_data
    second = client.post(start_path(data), headers=auth(data.operator), json=payload(data))
    assert second.status_code == 201
    expected = {}
    for batch_id in (first["id"], second.json()["id"]):
        backward = client.get(f"/api/traceability/batch/{batch_id}", headers=auth(data.planner))
        assert backward.status_code == 200
        for row in backward.json()["consumptions"]:
            expected.setdefault(row["material_lot_id"], {})[batch_id] = Decimal(row["qty"])
    for lot_id, batches in expected.items():
        forward = client.get(f"/api/traceability/lot/{lot_id}", headers=auth(data.planner))
        assert forward.status_code == 200
        actual = {row["batch_id"]: Decimal(row["consumed_qty"]) for row in forward.json()["batches"]}
        assert actual == batches
        assert Decimal(forward.json()["total_consumed_qty"]) == sum(batches.values(), Decimal("0"))


@pytest.mark.parametrize("same_time", [True, False])
def test_lot_trace_orders_by_start_time_then_id(trace_data, same_time):
    client, db, data, first = trace_data
    second = client.post(start_path(data), headers=auth(data.operator), json=payload(data))
    assert second.status_code == 201
    db.get(Batch, first["id"]).started_at = datetime(2026, 1, 2, tzinfo=timezone.utc)
    db.get(Batch, second.json()["id"]).started_at = datetime(2026, 1, 2 if same_time else 1, tzinfo=timezone.utc)
    db.commit()
    response = client.get(f"/api/traceability/lot/{data.lots[2].id}", headers=auth(data.planner))
    assert response.status_code == 200
    expected = [first["id"], second.json()["id"]] if same_time else [second.json()["id"], first["id"]]
    assert [row["batch_id"] for row in response.json()["batches"]] == expected


@pytest.mark.parametrize("state", list(BatchStatus))
def test_lot_trace_includes_all_batch_states(trace_data, state):
    client, db, data, first = trace_data
    db.get(Batch, first["id"]).status = state
    db.commit()
    response = client.get(f"/api/traceability/lot/{data.lots[1].id}", headers=auth(data.planner))
    assert response.status_code == 200
    assert response.json()["batches"][0]["status"] == state.value


def test_unconsumed_lot_has_empty_batches_and_zero_total(batch_client):
    client, db, data = batch_client
    response = client.get(f"/api/traceability/lot/{data.lots[1].id}", headers=auth(data.planner))
    assert response.status_code == 200
    assert response.json()["batches"] == []
    assert Decimal(response.json()["total_consumed_qty"]) == 0


def test_fully_consumed_lot_remains_searchable_and_traceable(trace_data):
    client, db, data, first = trace_data
    response = client.get("/api/traceability/lots", params={"material_id": data.material.id, "supplier_lot_no": "  STARA  "}, headers=auth(data.planner))
    assert response.status_code == 200
    assert [row["id"] for row in response.json()] == [data.lots[1].id]
    assert Decimal(response.json()[0]["remaining_qty"]) == 0
    trace = client.get(f"/api/traceability/lot/{data.lots[1].id}", headers=auth(data.planner))
    assert trace.status_code == 200
    assert [row["batch_id"] for row in trace.json()["batches"]] == [first["id"]]


def test_search_keeps_same_supplier_code_from_different_suppliers_separate(trace_data):
    client, db, data, first = trace_data
    original = data.lots[2]
    supplier = Supplier(name=f"Drug dobavitelj {uuid4().hex}")
    db.add(supplier)
    db.flush()
    other = MaterialLot(material_id=data.material.id, supplier_id=supplier.id, supplier_lot_no=original.supplier_lot_no,
                        received_qty=Decimal("10"), remaining_qty=Decimal("10"), unit_cost=Decimal("1"),
                        received_at=original.received_at, received_by=data.operator.id)
    db.add(other)
    db.commit()
    response = client.get("/api/traceability/lots", params={"material_id": data.material.id, "supplier_lot_no": original.supplier_lot_no}, headers=auth(data.planner))
    assert response.status_code == 200
    assert [row["id"] for row in response.json()] == [original.id, other.id]
    assert response.json()[0]["supplier_id"] != response.json()[1]["supplier_id"]
    assert response.json()[1]["supplier_name"] == supplier.name
    unused = client.get(f"/api/traceability/lot/{other.id}", headers=auth(data.planner))
    assert unused.status_code == 200 and unused.json()["batches"] == []


@pytest.mark.parametrize("role", [Role.planner, Role.quality])
def test_trace_material_selection_allows_both_roles_and_includes_packaging(batch_client, role):
    client, db, data = batch_client
    data.planner.role = role
    db.commit()
    response = client.get("/api/traceability/materials", headers=auth(data.planner))
    assert response.status_code == 200
    items = {row["id"]: row for row in response.json()}
    assert items[data.material.id]["unit"] == "kg"
    assert items[data.packaging.id]["type"] == "packaging"
    assert client.get("/api/traceability/lots", headers=auth(data.planner), params={"material_id": data.material.id, "supplier_lot_no": "NOVA"}).status_code == 200


def lot_request(data, endpoint):
    if endpoint == "materials":
        return "/api/traceability/materials", {}
    if endpoint == "search":
        return "/api/traceability/lots", {"material_id": data.material.id, "supplier_lot_no": "NOVA"}
    return f"/api/traceability/lot/{data.lots[2].id}", {}


@pytest.mark.parametrize("role", [Role.operator, Role.warehouse, Role.admin])
@pytest.mark.parametrize("endpoint", ["materials", "search", "lot"])
def test_lot_endpoints_deny_unapproved_roles(batch_client, role, endpoint):
    client, db, data = batch_client
    data.planner.role = role
    db.commit()
    path, params = lot_request(data, endpoint)
    assert client.get(path, params=params, headers=auth(data.planner)).status_code == 403


@pytest.mark.parametrize("case", ["missing", "invalid", "inactive"])
@pytest.mark.parametrize("endpoint", ["materials", "search", "lot"])
def test_lot_endpoints_require_active_login(batch_client, case, endpoint):
    client, db, data = batch_client
    headers = {} if case == "missing" else {"Authorization": "Bearer invalid"}
    if case == "inactive":
        headers = auth(data.planner)
        data.planner.active = False
        db.commit()
    path, params = lot_request(data, endpoint)
    assert client.get(path, params=params, headers=headers).status_code == 401


@pytest.mark.parametrize("lookup", ["id", "code", "wrong_material"])
def test_missing_lot_returns_expected_message(batch_client, lookup):
    client, db, data = batch_client
    if lookup == "id":
        missing = (db.scalar(select(func.max(MaterialLot.id))) or 0) + 1
        path, params = f"/api/traceability/lot/{missing}", {}
    else:
        path = "/api/traceability/lots"
        params = {"material_id": data.packaging.id if lookup == "wrong_material" else data.material.id,
                  "supplier_lot_no": "NOVA" if lookup == "wrong_material" else f"MISSING-{uuid4().hex}"}
    response = client.get(path, params=params, headers=auth(data.planner))
    assert response.status_code == 404
    assert response.json() == {"detail": "Serija ni najdena."}


@pytest.mark.parametrize("changes", [{"material_id": 0}, {"material_id": "abc"}, {"material_id": 2147483648},
                                     {"supplier_lot_no": ""}, {"supplier_lot_no": "   "}, {"supplier_lot_no": "a" * 81}])
def test_lot_search_validates_parameters(batch_client, changes):
    client, db, data = batch_client
    params = {"material_id": data.material.id, "supplier_lot_no": "NOVA", **changes}
    assert client.get("/api/traceability/lots", params=params, headers=auth(data.planner)).status_code == 422


@pytest.mark.parametrize("field", ["material_id", "supplier_lot_no"])
def test_lot_search_requires_both_fields(batch_client, field):
    client, db, data = batch_client
    params = {"material_id": data.material.id, "supplier_lot_no": "NOVA"}
    del params[field]
    assert client.get("/api/traceability/lots", params=params, headers=auth(data.planner)).status_code == 422


@pytest.mark.parametrize("identifier", ["0", "-1", "2147483648", "abc"])
def test_lot_trace_validates_id(batch_client, identifier):
    client, db, data = batch_client
    assert client.get(f"/api/traceability/lot/{identifier}", headers=auth(data.planner)).status_code == 422


def test_forward_trace_does_not_modify_stock_or_consumption(trace_data):
    client, db, data, first = trace_data
    before = {lot.id: (lot.received_qty, lot.remaining_qty) for lot in data.lots}
    response = client.get(f"/api/traceability/lot/{data.lots[2].id}", headers=auth(data.planner))
    assert response.status_code == 200
    for lot in data.lots:
        db.refresh(lot)
        assert (lot.received_qty, lot.remaining_qty) == before[lot.id]
    assert db.scalar(select(func.count()).select_from(BatchConsumption).where(BatchConsumption.batch_id == first["id"])) == 3
    assert db.get(Batch, first["id"], populate_existing=True).status == BatchStatus.in_production
