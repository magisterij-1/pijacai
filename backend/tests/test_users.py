from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

from app.core.security import JWT_SECRET, create_access_token, verify_password
from app.database import get_db
from app.main import app
from app.models import Role, User


@pytest.fixture
def user():
    return User(
        id=1, name="Administrator", email="admin@pijacai.local",
        password_hash="unused-in-creation-tests", role=Role.admin, active=True,
    )


@pytest.fixture
def client(user):
    db = Mock()
    db.get.return_value = user
    db.scalar.return_value = None
    db.refresh.side_effect = lambda created: setattr(created, "id", 2)

    def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    try:
        with TestClient(app) as test_client:
            yield test_client, db
    finally:
        app.dependency_overrides.clear()


def request_body(**changes):
    return {
        "name": "Nov uporabnik", "email": "nov@pijacai.local",
        "password": "VarnoGeslo2026!", "role": "operator", **changes,
    }


def authorization(user):
    return {"Authorization": f"Bearer {create_access_token(user)}"}


@pytest.mark.parametrize("new_role", list(Role))
def test_admin_creates_active_user_with_hashed_password(client, user, new_role):
    test_client, db = client
    response = test_client.post("/api/users", headers=authorization(user), json=request_body(role=new_role.value))
    assert response.status_code == 201
    assert response.json() == {
        "id": 2, "name": "Nov uporabnik", "email": "nov@pijacai.local",
        "role": new_role.value, "active": True,
    }
    created = db.add.call_args.args[0]
    assert created.password_hash != "VarnoGeslo2026!"
    assert verify_password("VarnoGeslo2026!", created.password_hash)
    assert "VarnoGeslo2026!" not in response.text
    assert created.password_hash not in response.text
    db.commit.assert_called_once()
    db.refresh.assert_called_once_with(created)


@pytest.mark.parametrize("role", [Role.planner, Role.operator, Role.quality, Role.warehouse])
def test_non_admin_cannot_create_users(client, user, role):
    test_client, db = client
    user.role = role
    response = test_client.post("/api/users", headers=authorization(user), json=request_body())
    assert response.status_code == 403
    assert response.json() == {"detail": "Nimate dostopa."}
    db.scalar.assert_not_called()
    db.add.assert_not_called()
    db.commit.assert_not_called()


@pytest.mark.parametrize("case", ["missing", "invalid", "expired", "inactive", "deleted"])
def test_creation_requires_valid_active_login(client, user, case):
    test_client, db = client
    headers = authorization(user)
    if case == "missing":
        headers = {}
    elif case == "invalid":
        headers = {"Authorization": "Bearer invalid-token"}
    elif case == "expired":
        now = datetime.now(timezone.utc)
        token = jwt.encode(
            {"sub": "1", "role": "admin", "iat": now - timedelta(hours=2), "exp": now - timedelta(hours=1)},
            JWT_SECRET, algorithm="HS256",
        )
        headers = {"Authorization": f"Bearer {token}"}
    elif case == "inactive":
        user.active = False
    elif case == "deleted":
        db.get.return_value = None
    response = test_client.post("/api/users", headers=headers, json=request_body())
    assert response.status_code == 401
    db.add.assert_not_called()
    db.commit.assert_not_called()


def test_existing_email_is_rejected_without_writing(client, user):
    test_client, db = client
    db.scalar.return_value = User(id=2, email="nov@pijacai.local")
    response = test_client.post("/api/users", headers=authorization(user), json=request_body())
    assert response.status_code == 409
    assert response.json() == {"detail": "Uporabnik s to e-pošto že obstaja."}
    db.add.assert_not_called()
    db.commit.assert_not_called()


def test_concurrent_duplicate_email_rolls_back_and_returns_409(client, user):
    test_client, db = client
    original = Exception("duplicate key")
    original.sqlstate = "23505"
    original.diag = SimpleNamespace(constraint_name="app_user_email_key")
    db.commit.side_effect = IntegrityError("INSERT", {}, original)
    response = test_client.post("/api/users", headers=authorization(user), json=request_body())
    assert response.status_code == 409
    db.rollback.assert_called_once()
    db.refresh.assert_not_called()


@pytest.mark.parametrize("changes", [
    {"name": ""}, {"name": "   "}, {"name": "a" * 121},
    {"email": "invalid"}, {"email": "a b@example.com"}, {"email": "a" * 256 + "@example.com"},
    {"password": "1234567"}, {"password": "a" * 73}, {"password": "č" * 37},
    {"role": "master"}, {"active": False},
])
def test_invalid_creation_is_422_without_echoing_password(client, user, changes):
    test_client, db = client
    body = request_body(**changes)
    response = test_client.post("/api/users", headers=authorization(user), json=body)
    assert response.status_code == 422
    assert body["password"] not in response.text
    db.add.assert_not_called()
    db.commit.assert_not_called()


@pytest.mark.parametrize("field", ["name", "email", "password", "role"])
def test_all_creation_fields_are_required(client, user, field):
    test_client, db = client
    body = request_body()
    del body[field]
    response = test_client.post("/api/users", headers=authorization(user), json=body)
    assert response.status_code == 422
    assert "VarnoGeslo2026!" not in response.text
    db.add.assert_not_called()


def test_name_and_email_are_trimmed_but_password_is_preserved(client, user):
    test_client, db = client
    password = " geslo s presledki "
    response = test_client.post("/api/users", headers=authorization(user), json=request_body(
        name="  Nov uporabnik  ", email="  nov@pijacai.local  ", password=password,
    ))
    assert response.status_code == 201
    assert response.json()["name"] == "Nov uporabnik"
    assert response.json()["email"] == "nov@pijacai.local"
    created = db.add.call_args.args[0]
    assert verify_password(password, created.password_hash)
    assert not verify_password(password.strip(), created.password_hash)
