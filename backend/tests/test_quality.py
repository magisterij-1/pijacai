from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.core.security import create_access_token
from app.database import get_db
from app.main import app
from app.models import Batch, BatchStatus, OrderStatus, Product, ProductionLine, ProductionOrder, QualityCheck, QualityParameter, Recipe, Role, User


@pytest.fixture
def quality_client(inventory_db):
    db = inventory_db
    suffix = uuid4().hex
    quality = User(name="Kontrolor", email=f"qc-{suffix}@pijacai.local", password_hash="unused", role=Role.quality)
    operator = User(name="Operater", email=f"op-qc-{suffix}@pijacai.local", password_hash="unused", role=Role.operator)
    product = Product(name="Testni sok", sku=f"QC-{suffix}", unit="kos")
    other = Product(name="Drug izdelek", sku=f"QC-OTHER-{suffix}", unit="kos")
    line = ProductionLine(name=f"QC linija {suffix}")
    db.add_all([quality, operator, product, other, line])
    db.flush()
    recipe = Recipe(product_id=product.id, version=1, output_qty=Decimal("1000"), active=True)
    db.add(recipe)
    db.flush()
    order = ProductionOrder(product_id=product.id, recipe_id=recipe.id, planned_qty=1000,
                            planned_date=datetime.now(timezone.utc).date(), created_by=operator.id, status=OrderStatus.in_progress)
    db.add(order)
    db.flush()
    batch = Batch(batch_code=f"QC-{suffix}", order_id=order.id, line_id=line.id, operator_id=operator.id,
                  production_date=order.planned_date, sequence_no=1, planned_qty=Decimal("1000"),
                  produced_qty=980, rejected_qty=5, status=BatchStatus.awaiting_qc,
                  finished_at=datetime.now(timezone.utc))
    ph = QualityParameter(product_id=product.id, name="pH", unit="pH", min_value=Decimal("2.8"), max_value=Decimal("4"))
    co2 = QualityParameter(product_id=product.id, name="CO₂", unit="g/L", min_value=Decimal("0"), max_value=Decimal("1"))
    foreign = QualityParameter(product_id=other.id, name="pH", unit="pH", min_value=Decimal("6"), max_value=Decimal("7"))
    db.add_all([batch, ph, co2, foreign])
    db.commit()
    data = SimpleNamespace(quality=quality, operator=operator, product=product, batch=batch, ph=ph, co2=co2, foreign=foreign, order=order)

    def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    try:
        with TestClient(app) as client:
            yield client, db, data
    finally:
        app.dependency_overrides.clear()


def auth(user):
    return {"Authorization": f"Bearer {create_access_token(user)}"}


def path(data):
    return f"/api/batches/{data.batch.id}/checks"


def count(db, data):
    return db.scalar(select(func.count()).select_from(QualityCheck).where(QualityCheck.batch_id == data.batch.id))


def test_overview_lists_only_product_parameters_and_missing_measurements(quality_client):
    client, db, data = quality_client
    response = client.get(path(data), headers=auth(data.quality))
    assert response.status_code == 200
    result = response.json()
    assert result["batch_id"] == data.batch.id
    assert result["checks"] == []
    assert [item["id"] for item in result["parameters"]] == [data.ph.id, data.co2.id]
    ph = result["parameters"][0]
    assert ph["name"] == "pH" and ph["unit"] == "pH"
    assert Decimal(ph["min_value"]) == Decimal("2.8")
    assert Decimal(ph["max_value"]) == Decimal("4")
    assert all(item["latest_check"] is None for item in result["parameters"])
    assert count(db, data) == 0


@pytest.mark.parametrize("value,passed", [("2.800", True), ("4.000", True), ("3.125", True), ("2.799", False), ("4.001", False)])
def test_check_compares_decimal_value_with_inclusive_bounds(quality_client, value, passed):
    client, db, data = quality_client
    before = datetime.now(timezone.utc)
    response = client.post(path(data), headers=auth(data.quality), json={"parameter_id": data.ph.id, "value": value})
    assert response.status_code == 201
    result = response.json()
    assert result["batch_id"] == data.batch.id and result["parameter_id"] == data.ph.id
    assert Decimal(result["value"]) == Decimal(value)
    assert result["passed"] is passed
    assert result["checked_by"] == data.quality.id
    assert before <= datetime.fromisoformat(result["checked_at"]) <= datetime.now(timezone.utc)
    saved = db.get(QualityCheck, result["id"], populate_existing=True)
    assert saved.value == Decimal(value) and saved.passed is passed
    db.refresh(data.batch)
    db.refresh(data.order)
    assert data.batch.status == BatchStatus.awaiting_qc
    assert (data.batch.produced_qty, data.batch.rejected_qty) == (980, 5)
    assert data.order.status == OrderStatus.in_progress


@pytest.mark.parametrize("value", [0, 0.5, "0.001"])
def test_check_accepts_numeric_input_and_zero(quality_client, value):
    client, db, data = quality_client
    response = client.post(path(data), headers=auth(data.quality), json={"parameter_id": data.co2.id, "value": value})
    assert response.status_code == 201
    assert Decimal(response.json()["value"]) == Decimal(str(value))
    assert response.json()["passed"] is True


def test_negative_measurement_is_saved_as_noncompliant(quality_client):
    client, db, data = quality_client
    response = client.post(path(data), headers=auth(data.quality), json={"parameter_id": data.co2.id, "value": "-0.001"})
    assert response.status_code == 201
    assert response.json()["passed"] is False
    assert Decimal(response.json()["value"]) == Decimal("-0.001")


@pytest.mark.parametrize("value", ["", "abc", None, True, [], {}, "NaN", "Infinity", "-Infinity", "3.0001", "1000000000", "-1000000000"])
def test_invalid_value_is_not_saved_and_has_field_error(quality_client, value):
    client, db, data = quality_client
    response = client.post(path(data), headers=auth(data.quality), json={"parameter_id": data.ph.id, "value": value})
    assert response.status_code == 422
    assert any(item["loc"] == ["body", "value"] for item in response.json()["detail"])
    assert count(db, data) == 0


@pytest.mark.parametrize("field", ["value", "parameter_id"])
def test_check_requires_parameter_and_value(quality_client, field):
    client, db, data = quality_client
    body = {"parameter_id": data.ph.id, "value": "3"}
    del body[field]
    response = client.post(path(data), headers=auth(data.quality), json=body)
    assert response.status_code == 422
    assert any(item["loc"] == ["body", field] for item in response.json()["detail"])
    assert count(db, data) == 0


@pytest.mark.parametrize("value", [True, 0, -1, "1", 2147483648])
def test_check_parameter_id_must_be_valid_integer(quality_client, value):
    client, db, data = quality_client
    response = client.post(path(data), headers=auth(data.quality), json={"parameter_id": value, "value": "3"})
    assert response.status_code == 422
    assert any(item["loc"] == ["body", "parameter_id"] for item in response.json()["detail"])
    assert count(db, data) == 0


@pytest.mark.parametrize("field,value", [("passed", True), ("checked_by", 123), ("checked_at", "2020-01-01T00:00:00Z"), ("batch_id", 123)])
def test_client_cannot_forge_check_result_or_author(quality_client, field, value):
    client, db, data = quality_client
    response = client.post(path(data), headers=auth(data.quality), json={"parameter_id": data.ph.id, "value": "3", field: value})
    assert response.status_code == 422
    assert count(db, data) == 0


def test_parameter_from_another_product_is_rejected_at_field(quality_client):
    client, db, data = quality_client
    response = client.post(path(data), headers=auth(data.quality), json={"parameter_id": data.foreign.id, "value": "6.5"})
    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "parameter_id"]
    assert count(db, data) == 0


@pytest.mark.parametrize("state", [BatchStatus.in_production, BatchStatus.released, BatchStatus.rejected])
def test_check_rejects_batch_outside_quality_state(quality_client, state):
    client, db, data = quality_client
    data.batch.status = state
    db.commit()
    response = client.post(path(data), headers=auth(data.quality), json={"parameter_id": data.ph.id, "value": "3"})
    assert response.status_code == 409
    assert count(db, data) == 0


@pytest.mark.parametrize("role", [Role.admin, Role.operator, Role.planner, Role.warehouse])
@pytest.mark.parametrize("method", ["get", "post"])
def test_only_quality_role_can_access_measurements(quality_client, role, method):
    client, db, data = quality_client
    data.operator.role = role
    db.commit()
    options = {"headers": auth(data.operator)}
    if method == "post":
        options["json"] = {"parameter_id": data.ph.id, "value": "3"}
    assert getattr(client, method)(path(data), **options).status_code == 403
    assert count(db, data) == 0


@pytest.mark.parametrize("case", ["missing", "invalid", "inactive"])
@pytest.mark.parametrize("method", ["get", "post"])
def test_measurements_require_active_login(quality_client, case, method):
    client, db, data = quality_client
    headers = {} if case == "missing" else {"Authorization": "Bearer invalid"}
    if case == "inactive":
        headers = auth(data.quality)
        data.quality.active = False
        db.commit()
    options = {"headers": headers}
    if method == "post":
        options["json"] = {"parameter_id": data.ph.id, "value": "3"}
    assert getattr(client, method)(path(data), **options).status_code == 401
    assert count(db, data) == 0


@pytest.mark.parametrize("method", ["get", "post"])
def test_missing_batch_is_404(quality_client, method):
    client, db, data = quality_client
    missing = (db.scalar(select(func.max(Batch.id))) or 0) + 1
    options = {"headers": auth(data.quality)}
    if method == "post":
        options["json"] = {"parameter_id": data.ph.id, "value": "3"}
    assert getattr(client, method)(f"/api/batches/{missing}/checks", **options).status_code == 404
    assert count(db, data) == 0


def test_missing_parameter_is_404_without_saved_check(quality_client):
    client, db, data = quality_client
    missing = (db.scalar(select(func.max(QualityParameter.id))) or 0) + 1
    response = client.post(path(data), headers=auth(data.quality), json={"parameter_id": missing, "value": "3"})
    assert response.status_code == 404
    assert count(db, data) == 0


@pytest.mark.parametrize("values", [("5", "3"), ("3", "5")])
def test_repeat_measurement_appends_history_and_latest_takes_precedence(quality_client, values):
    client, db, data = quality_client
    saved = []
    for value in values:
        response = client.post(path(data), headers=auth(data.quality), json={"parameter_id": data.ph.id, "value": value})
        assert response.status_code == 201
        saved.append(response.json())
    assert saved[0]["id"] != saved[1]["id"]
    overview = client.get(path(data), headers=auth(data.quality)).json()
    ph = next(item for item in overview["parameters"] if item["id"] == data.ph.id)
    assert ph["latest_check"] == saved[1]
    assert overview["checks"] == [saved[1], saved[0]]
    assert next(item for item in overview["parameters"] if item["id"] == data.co2.id)["latest_check"] is None
    assert count(db, data) == 2


def test_equal_measurement_times_use_highest_id_as_latest(quality_client):
    client, db, data = quality_client
    ids = []
    for value in ["3", "5"]:
        response = client.post(path(data), headers=auth(data.quality), json={"parameter_id": data.ph.id, "value": value})
        assert response.status_code == 201
        ids.append(response.json()["id"])
    stamp = datetime(2026, 1, 1, tzinfo=timezone.utc)
    for check_id in ids:
        db.get(QualityCheck, check_id).checked_at = stamp
    db.commit()
    response = client.get(path(data), headers=auth(data.quality))
    assert response.status_code == 200
    latest = response.json()["parameters"][0]["latest_check"]
    assert latest["id"] == max(ids)
    assert latest["passed"] is False


def test_check_commit_failure_rolls_back_and_allows_retry(quality_client):
    client, db, data = quality_client
    body = {"parameter_id": data.ph.id, "value": "3"}
    with patch.object(db, "commit", side_effect=RuntimeError("Simulirana napaka meritve")):
        with pytest.raises(RuntimeError, match="Simulirana napaka meritve"):
            client.post(path(data), headers=auth(data.quality), json=body)
    assert count(db, data) == 0
    db.refresh(data.batch)
    assert data.batch.status == BatchStatus.awaiting_qc
    assert client.post(path(data), headers=auth(data.quality), json=body).status_code == 201
    assert count(db, data) == 1
