from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

from app.core.security import JWT_SECRET, create_access_token, hash_password, verify_password
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
    def refresh(current):
        if current.id is None:
            current.id = 2

    db.refresh.side_effect = refresh

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
@pytest.mark.parametrize("method,path", [
    ("POST", "/api/users"), ("GET", "/api/users"), ("POST", "/api/users/2/deactivate"),
])
def test_non_admin_cannot_manage_users(client, user, role, method, path):
    test_client, db = client
    user.role = role
    response = test_client.request(method, path, headers=authorization(user), json=request_body() if method == "POST" and path == "/api/users" else None)
    assert response.status_code == 403
    assert response.json() == {"detail": "Nimate dostopa."}
    db.scalar.assert_not_called()
    db.scalars.assert_not_called()
    db.add.assert_not_called()
    db.commit.assert_not_called()


@pytest.mark.parametrize("case", ["missing", "invalid", "expired", "inactive", "deleted"])
@pytest.mark.parametrize("method,path", [
    ("POST", "/api/users"), ("GET", "/api/users"), ("POST", "/api/users/2/deactivate"),
])
def test_user_management_requires_valid_active_login(client, user, case, method, path):
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
    response = test_client.request(method, path, headers=headers, json=request_body() if method == "POST" and path == "/api/users" else None)
    assert response.status_code == 401
    db.add.assert_not_called()
    db.commit.assert_not_called()


def test_admin_lists_active_and_inactive_users_without_hashes(client, user):
    test_client, db = client
    target = User(
        id=2, name="Deaktiviran uporabnik", email="inactive@pijacai.local",
        password_hash="secret-hash-not-for-response", role=Role.operator, active=False,
    )
    db.scalars.return_value.all.return_value = [user, target]
    response = test_client.get("/api/users", headers=authorization(user))
    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == [1, 2]
    assert response.json()[1]["active"] is False
    assert "secret-hash-not-for-response" not in response.text
    assert user.password_hash not in response.text
    assert all("password_hash" not in item and "password" not in item for item in response.json())
    db.commit.assert_not_called()


def test_admin_can_view_empty_list(client, user):
    test_client, db = client
    db.scalars.return_value.all.return_value = []
    response = test_client.get("/api/users", headers=authorization(user))
    assert response.status_code == 200
    assert response.json() == []


@pytest.fixture
def target_user(client, user):
    _, db = client
    target = User(
        id=2, name="Operater", email="operator@pijacai.local",
        password_hash=hash_password("Deaktivacija2026!"), role=Role.operator, active=True,
    )
    db.get.side_effect = lambda model, user_id: user if user_id == user.id else target if user_id == target.id else None
    return target


def test_deactivation_preserves_account_and_blocks_login_and_existing_jwt(client, user, target_user):
    test_client, db = client
    old_token = create_access_token(target_user)
    original = (target_user.id, target_user.name, target_user.email, target_user.password_hash, target_user.role)
    response = test_client.post("/api/users/2/deactivate", headers=authorization(user))
    assert response.status_code == 200
    assert response.json()["active"] is False
    assert (target_user.id, target_user.name, target_user.email, target_user.password_hash, target_user.role) == original
    assert "password_hash" not in response.json()
    db.commit.assert_called_once()
    db.delete.assert_not_called()

    db.scalar.return_value = target_user
    login = test_client.post("/api/auth/login", json={
        "email": target_user.email, "password": "Deaktivacija2026!",
    })
    assert login.status_code == 401
    assert login.json() == {"detail": "Napačna e-pošta ali geslo."}
    me = test_client.get("/api/auth/me", headers={"Authorization": f"Bearer {old_token}"})
    assert me.status_code == 401


def test_repeated_deactivation_is_idempotent(client, user, target_user):
    test_client, db = client
    target_user.active = False
    response = test_client.post("/api/users/2/deactivate", headers=authorization(user))
    assert response.status_code == 200
    assert response.json()["active"] is False
    db.commit.assert_not_called()
    db.delete.assert_not_called()


def test_deactivation_of_missing_user_is_404(client, user):
    test_client, db = client
    db.get.side_effect = lambda model, user_id: user if user_id == user.id else None
    response = test_client.post("/api/users/999/deactivate", headers=authorization(user))
    assert response.status_code == 404
    assert response.json() == {"detail": "Uporabnik ni najden."}
    db.commit.assert_not_called()


@pytest.mark.parametrize("user_id", ["0", "-1", "not-an-id", "2147483648"])
def test_invalid_deactivation_id_is_422(client, user, user_id):
    test_client, db = client
    response = test_client.post(f"/api/users/{user_id}/deactivate", headers=authorization(user))
    assert response.status_code == 422
    db.commit.assert_not_called()


def test_self_deactivation_invalidates_administrators_existing_token(client, user):
    test_client, db = client
    token = create_access_token(user)
    response = test_client.post("/api/users/1/deactivate", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert user.active is False
    again = test_client.get("/api/users", headers={"Authorization": f"Bearer {token}"})
    assert again.status_code == 401
    db.delete.assert_not_called()


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
