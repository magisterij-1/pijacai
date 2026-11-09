# — meritve, zadnji rezultati, sprostitev in zavrnitev.
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


def release_path(data):
    return f"/api/batches/{data.batch.id}/release"


def measure(client, data, parameter, value):
    response = client.post(path(data), headers=auth(data.quality), json={"parameter_id": parameter.id, "value": value})
    assert response.status_code == 201
    return response.json()


def passing_checks(client, data):
    measure(client, data, data.ph, "3")
    measure(client, data, data.co2, "0.5")


def assert_undecided(db, data):
    db.refresh(data.batch)
    assert data.batch.status == BatchStatus.awaiting_qc
    assert data.batch.decided_by is None
    assert data.batch.decided_at is None
    assert data.batch.decision_note is None


def test_release_records_decision_and_removes_batch_from_quality_queue(quality_client):
    client, db, data = quality_client
    passing_checks(client, data)
    before = datetime.now(timezone.utc)
    response = client.post(release_path(data), headers=auth(data.quality))
    assert response.status_code == 200
    result = response.json()
    assert result["id"] == data.batch.id
    assert result["status"] == "released"
    assert result["decided_by"] == data.quality.id
    assert before <= datetime.fromisoformat(result["decided_at"]) <= datetime.now(timezone.utc)
    assert result["decision_note"] is None
    assert result["produced_qty"] == 980 and result["rejected_qty"] == 5
    db.refresh(data.batch)
    assert data.batch.status == BatchStatus.released
    assert data.batch.decided_by == data.quality.id
    assert data.batch.decided_at is not None
    assert client.get(f"/api/batches/{data.batch.id}", headers=auth(data.quality)).json() == result
    queue = client.get("/api/batches", headers=auth(data.quality), params={"order_id": data.order.id, "status_filter": "awaiting_qc"})
    assert queue.status_code == 200 and queue.json() == []
    released = client.get("/api/batches", headers=auth(data.quality), params={"order_id": data.order.id, "status_filter": "released"})
    assert released.status_code == 200
    assert released.json()[0]["decided_by"] == data.quality.id
    assert count(db, data) == 2
    db.refresh(data.order)
    assert data.order.status == OrderStatus.in_progress


@pytest.mark.parametrize("mode", ["all_missing", "some_missing", "mixed", "invalid"])
def test_release_reports_missing_and_invalid_parameters_without_decision(quality_client, mode):
    client, db, data = quality_client
    if mode == "some_missing":
        measure(client, data, data.ph, "3")
    elif mode in ("mixed", "invalid"):
        measure(client, data, data.ph, "5")
        if mode == "invalid":
            measure(client, data, data.co2, "2")
    response = client.post(release_path(data), headers=auth(data.quality))
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["code"] == "QUALITY_NOT_PASSED"
    expected_missing = {"all_missing": [data.ph, data.co2], "some_missing": [data.co2], "mixed": [data.co2], "invalid": []}[mode]
    expected_invalid = {"all_missing": [], "some_missing": [], "mixed": [data.ph], "invalid": [data.ph, data.co2]}[mode]
    assert detail["missing"] == [{"parameter_id": parameter.id, "name": parameter.name} for parameter in expected_missing]
    assert detail["invalid"] == [{"parameter_id": parameter.id, "name": parameter.name} for parameter in expected_invalid]
    assert_undecided(db, data)


@pytest.mark.parametrize("values,expected_status", [(('5', '3'), 200), (('3', '5'), 422)])
def test_release_uses_latest_check_in_both_directions(quality_client, values, expected_status):
    client, db, data = quality_client
    for value in values:
        measure(client, data, data.ph, value)
    measure(client, data, data.co2, "0")
    response = client.post(release_path(data), headers=auth(data.quality))
    assert response.status_code == expected_status
    assert count(db, data) == 3
    if expected_status == 422:
        assert response.json()["detail"]["invalid"] == [{"parameter_id": data.ph.id, "name": "pH"}]
        assert_undecided(db, data)


@pytest.mark.parametrize("values,expected_status", [(('5', '3'), 200), (('3', '5'), 422)])
def test_release_breaks_equal_check_times_by_highest_id(quality_client, values, expected_status):
    client, db, data = quality_client
    ids = [measure(client, data, data.ph, value)["id"] for value in values]
    for check_id in ids:
        db.get(QualityCheck, check_id).checked_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    db.commit()
    measure(client, data, data.co2, "0.5")
    assert client.post(release_path(data), headers=auth(data.quality)).status_code == expected_status


def test_release_requires_measurements_for_newly_added_parameter(quality_client):
    client, db, data = quality_client
    passing_checks(client, data)
    added = QualityParameter(product_id=data.product.id, name="Nivo polnjenja", unit="ml", min_value=Decimal("990"), max_value=Decimal("1010"))
    db.add(added)
    db.commit()
    response = client.post(release_path(data), headers=auth(data.quality))
    assert response.status_code == 422
    assert response.json()["detail"]["missing"] == [{"parameter_id": added.id, "name": added.name}]
    assert_undecided(db, data)


def test_release_without_configured_parameters_is_rejected(quality_client):
    client, db, data = quality_client
    db.delete(data.ph)
    db.delete(data.co2)
    db.commit()
    response = client.post(release_path(data), headers=auth(data.quality))
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "NO_QUALITY_PARAMETERS"
    assert_undecided(db, data)


def test_release_does_not_use_measurements_of_another_batch(quality_client):
    client, db, data = quality_client
    passing_checks(client, data)
    other = Batch(batch_code=f"OTHER-QC-{uuid4().hex}", order_id=data.order.id, line_id=data.batch.line_id,
                  operator_id=data.operator.id, production_date=data.batch.production_date, sequence_no=2,
                  planned_qty=Decimal("100"), status=BatchStatus.awaiting_qc)
    db.add(other)
    db.commit()
    response = client.post(f"/api/batches/{other.id}/release", headers=auth(data.quality))
    assert response.status_code == 422
    assert {item["parameter_id"] for item in response.json()["detail"]["missing"]} == {data.ph.id, data.co2.id}
    db.refresh(other)
    assert other.status == BatchStatus.awaiting_qc and other.decided_at is None


def test_release_prioritizes_measurement_time_over_id(quality_client):
    client, db, data = quality_client
    newer = measure(client, data, data.ph, "3")
    older = measure(client, data, data.ph, "5")
    assert newer["id"] < older["id"]
    db.get(QualityCheck, newer["id"]).checked_at = datetime(2026, 1, 2, tzinfo=timezone.utc)
    db.get(QualityCheck, older["id"]).checked_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    db.commit()
    measure(client, data, data.co2, "0.5")
    assert client.post(release_path(data), headers=auth(data.quality)).status_code == 200


def test_release_can_be_decided_by_another_quality_user(quality_client):
    client, db, data = quality_client
    passing_checks(client, data)
    data.operator.role = Role.quality
    db.commit()
    response = client.post(release_path(data), headers=auth(data.operator))
    assert response.status_code == 200
    assert response.json()["decided_by"] == data.operator.id


@pytest.mark.parametrize("role", [Role.admin, Role.operator, Role.planner, Role.warehouse])
def test_release_denies_other_roles(quality_client, role):
    client, db, data = quality_client
    passing_checks(client, data)
    data.operator.role = role
    db.commit()
    response = client.post(release_path(data), headers=auth(data.operator))
    assert response.status_code == 403
    assert_undecided(db, data)


@pytest.mark.parametrize("case", ["missing", "invalid", "inactive"])
def test_release_requires_active_login(quality_client, case):
    client, db, data = quality_client
    headers = {} if case == "missing" else {"Authorization": "Bearer invalid"}
    if case == "inactive":
        headers = auth(data.quality)
        data.quality.active = False
        db.commit()
    assert client.post(release_path(data), headers=headers).status_code == 401
    assert_undecided(db, data)


@pytest.mark.parametrize("state", [BatchStatus.in_production, BatchStatus.released, BatchStatus.rejected])
def test_release_denies_incorrect_state_without_overwriting_decision(quality_client, state):
    client, db, data = quality_client
    passing_checks(client, data)
    stamp = datetime(2026, 1, 1, tzinfo=timezone.utc)
    data.batch.status = state
    data.batch.decided_by = data.quality.id
    data.batch.decided_at = stamp
    data.batch.decision_note = "Predhodna odločitev."
    db.commit()
    assert client.post(release_path(data), headers=auth(data.quality)).status_code == 409
    db.refresh(data.batch)
    assert data.batch.status == state
    assert data.batch.decided_by == data.quality.id
    assert data.batch.decided_at == stamp
    assert data.batch.decision_note == "Predhodna odločitev."


def test_repeated_release_is_409_and_new_measurement_is_blocked(quality_client):
    client, db, data = quality_client
    passing_checks(client, data)
    first = client.post(release_path(data), headers=auth(data.quality))
    assert first.status_code == 200
    assert client.post(release_path(data), headers=auth(data.quality)).status_code == 409
    attempt = client.post(path(data), headers=auth(data.quality), json={"parameter_id": data.ph.id, "value": "5"})
    assert attempt.status_code == 409
    saved = client.get(f"/api/batches/{data.batch.id}", headers=auth(data.quality))
    assert saved.json() == first.json()
    assert count(db, data) == 2


def test_release_missing_batch_is_404(quality_client):
    client, db, data = quality_client
    missing = (db.scalar(select(func.max(Batch.id))) or 0) + 1
    assert client.post(f"/api/batches/{missing}/release", headers=auth(data.quality)).status_code == 404
    assert_undecided(db, data)


def test_release_commit_failure_rolls_back_decision_and_preserves_checks(quality_client):
    client, db, data = quality_client
    passing_checks(client, data)
    with patch.object(db, "commit", side_effect=RuntimeError("Simulirana napaka sprostitve")):
        with pytest.raises(RuntimeError, match="Simulirana napaka sprostitve"):
            client.post(release_path(data), headers=auth(data.quality))
    assert_undecided(db, data)
    assert count(db, data) == 2
    assert client.post(release_path(data), headers=auth(data.quality)).status_code == 200


def reject_path(data):
    return f"/api/batches/{data.batch.id}/reject"


REJECTION_NOTE = "Vrednost pH presega dovoljeno mejo."


@pytest.mark.parametrize("measurements", ["none", "partial", "failed", "passed"])
def test_reject_records_decision_regardless_of_measurement_completion(quality_client, measurements):
    client, db, data = quality_client
    if measurements == "partial":
        measure(client, data, data.ph, "3")
    elif measurements == "failed":
        measure(client, data, data.ph, "5")
    elif measurements == "passed":
        passing_checks(client, data)
    check_count = count(db, data)
    before = datetime.now(timezone.utc)
    response = client.post(reject_path(data), headers=auth(data.quality), json={"decision_note": REJECTION_NOTE})
    assert response.status_code == 200
    result = response.json()
    assert result["status"] == "rejected"
    assert result["decision_note"] == REJECTION_NOTE
    assert result["decided_by"] == data.quality.id
    assert before <= datetime.fromisoformat(result["decided_at"]) <= datetime.now(timezone.utc)
    db.refresh(data.batch)
    assert data.batch.status == BatchStatus.rejected
    assert data.batch.decision_note == REJECTION_NOTE
    assert data.batch.decided_by == data.quality.id
    assert data.batch.decided_at is not None
    assert (data.batch.produced_qty, data.batch.rejected_qty) == (980, 5)
    assert count(db, data) == check_count
    db.refresh(data.order)
    assert data.order.status == OrderStatus.in_progress
    queue = client.get("/api/batches", headers=auth(data.quality), params={"order_id": data.order.id, "status_filter": "awaiting_qc"})
    assert queue.status_code == 200 and queue.json() == []
    # Vse tri dovoljene bralne vloge morajo videti isti shranjeni razlog.
    for role in (Role.operator, Role.planner, Role.quality):
        data.operator.role = role
        db.commit()
        read = client.get(f"/api/batches/{data.batch.id}", headers=auth(data.operator))
        assert read.status_code == 200 and read.json() == result


@pytest.mark.parametrize("note", ["", "   \t\n    ", "kratko", "123456789", "a" * 501, None, 123, True, [], {}])
def test_invalid_rejection_reason_has_field_error_without_changes(quality_client, note):
    client, db, data = quality_client
    response = client.post(reject_path(data), headers=auth(data.quality), json={"decision_note": note})
    assert response.status_code == 422
    assert any(item["loc"] == ["body", "decision_note"] for item in response.json()["detail"])
    assert_undecided(db, data)


@pytest.mark.parametrize("note,expected", [
    ("1234567890", "1234567890"),
    ("ž" * 500, "ž" * 500),
    ("  " + REJECTION_NOTE + " \n", REJECTION_NOTE),
    ("  " + "a" * 500 + "  ", "a" * 500),
])
def test_rejection_accepts_boundaries_and_trims_reason(quality_client, note, expected):
    client, db, data = quality_client
    response = client.post(reject_path(data), headers=auth(data.quality), json={"decision_note": note})
    assert response.status_code == 200
    assert response.json()["decision_note"] == expected
    db.refresh(data.batch)
    assert data.batch.decision_note == expected


def test_rejection_requires_reason_field(quality_client):
    client, db, data = quality_client
    response = client.post(reject_path(data), headers=auth(data.quality), json={})
    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "decision_note"]
    assert_undecided(db, data)


@pytest.mark.parametrize("field,value", [("decided_by", 123), ("decided_at", "2020-01-01T00:00:00Z"), ("status", "released")])
def test_rejection_cannot_forge_author_time_or_status(quality_client, field, value):
    client, db, data = quality_client
    response = client.post(reject_path(data), headers=auth(data.quality), json={"decision_note": REJECTION_NOTE, field: value})
    assert response.status_code == 422
    assert_undecided(db, data)


@pytest.mark.parametrize("role", [Role.operator, Role.planner, Role.warehouse, Role.admin])
def test_rejection_denies_other_roles(quality_client, role):
    client, db, data = quality_client
    data.operator.role = role
    db.commit()
    response = client.post(reject_path(data), headers=auth(data.operator), json={"decision_note": REJECTION_NOTE})
    assert response.status_code == 403
    assert_undecided(db, data)


@pytest.mark.parametrize("case", ["missing", "invalid", "inactive"])
def test_rejection_requires_active_login(quality_client, case):
    client, db, data = quality_client
    headers = {} if case == "missing" else {"Authorization": "Bearer invalid"}
    if case == "inactive":
        headers = auth(data.quality)
        data.quality.active = False
        db.commit()
    response = client.post(reject_path(data), headers=headers, json={"decision_note": REJECTION_NOTE})
    assert response.status_code == 401
    assert_undecided(db, data)


@pytest.mark.parametrize("state", [BatchStatus.in_production, BatchStatus.released, BatchStatus.rejected])
def test_rejection_denies_other_states_and_preserves_decision(quality_client, state):
    client, db, data = quality_client
    stamp = datetime(2026, 1, 1, tzinfo=timezone.utc)
    data.batch.status = state
    data.batch.decided_by = data.quality.id
    data.batch.decided_at = stamp
    data.batch.decision_note = "Predhodna odločitev."
    db.commit()
    response = client.post(reject_path(data), headers=auth(data.quality), json={"decision_note": REJECTION_NOTE})
    assert response.status_code == 409
    db.refresh(data.batch)
    assert data.batch.status == state
    assert data.batch.decided_by == data.quality.id
    assert data.batch.decided_at == stamp
    assert data.batch.decision_note == "Predhodna odločitev."


def test_rejected_batch_cannot_be_released_remeasured_or_rejected_again(quality_client):
    client, db, data = quality_client
    passing_checks(client, data)
    first = client.post(reject_path(data), headers=auth(data.quality), json={"decision_note": REJECTION_NOTE})
    assert first.status_code == 200
    assert client.post(release_path(data), headers=auth(data.quality)).status_code == 409
    assert client.post(reject_path(data), headers=auth(data.quality), json={"decision_note": "Drug razlog zavrnitve."}).status_code == 409
    assert client.post(path(data), headers=auth(data.quality), json={"parameter_id": data.ph.id, "value": "3"}).status_code == 409
    read = client.get(f"/api/batches/{data.batch.id}", headers=auth(data.quality))
    assert read.status_code == 200 and read.json() == first.json()
    assert count(db, data) == 2


def test_rejection_missing_batch_is_404(quality_client):
    client, db, data = quality_client
    missing = (db.scalar(select(func.max(Batch.id))) or 0) + 1
    response = client.post(f"/api/batches/{missing}/reject", headers=auth(data.quality), json={"decision_note": REJECTION_NOTE})
    assert response.status_code == 404
    assert_undecided(db, data)


def test_rejection_does_not_require_configured_parameters(quality_client):
    client, db, data = quality_client
    db.delete(data.ph)
    db.delete(data.co2)
    db.commit()
    response = client.post(reject_path(data), headers=auth(data.quality), json={"decision_note": REJECTION_NOTE})
    assert response.status_code == 200
    assert response.json()["status"] == "rejected"


def test_rejection_commit_failure_rolls_back_and_preserves_measurements(quality_client):
    client, db, data = quality_client
    passing_checks(client, data)
    with patch.object(db, "commit", side_effect=RuntimeError("Simulirana napaka zavrnitve")):
        with pytest.raises(RuntimeError, match="Simulirana napaka zavrnitve"):
            client.post(reject_path(data), headers=auth(data.quality), json={"decision_note": REJECTION_NOTE})
    assert_undecided(db, data)
    assert count(db, data) == 2
    retry = client.post(reject_path(data), headers=auth(data.quality), json={"decision_note": REJECTION_NOTE})
    assert retry.status_code == 200
