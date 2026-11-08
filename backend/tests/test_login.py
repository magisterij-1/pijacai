import os
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

os.environ["DATABASE_URL"] = "postgresql+psycopg://test:test@localhost/test"
os.environ["JWT_SECRET"] = "test-only-signing-key-with-at-least-32-bytes"

import jwt
import pytest
from fastapi.testclient import TestClient

from app.core.security import JWT_SECRET, hash_password, verify_password
from app.database import get_db
from app.main import app
from app.models import Role, User


@pytest.fixture
def user():
    return User(
        id=1, name="Testni uporabnik", email="test@pijacai.local",
        password_hash=hash_password("TestnoGeslo123!"), role=Role.admin, active=True,
    )


@pytest.fixture
def client(user):
    db = Mock()
    db.scalar.return_value = user
    db.get.return_value = user

    def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    with TestClient(app) as test_client:
        yield test_client, db
    app.dependency_overrides.clear()


def test_successful_login_returns_signed_token_without_password(client):
    test_client, _ = client
    response = test_client.post("/api/auth/login", json={
        "email": "test@pijacai.local", "password": "TestnoGeslo123!",
    })
    assert response.status_code == 200
    data = response.json()
    payload = jwt.decode(data["access_token"], JWT_SECRET, algorithms=["HS256"])
    assert payload["sub"] == "1"
    assert payload["role"] == "admin"
    assert payload["exp"] - payload["iat"] == 3600
    assert data["expires_in"] == 3600
    assert data["expires_at"] == payload["exp"]
    assert data["token_type"] == "bearer"
    assert data["user"]["email"] == "test@pijacai.local"
    assert "password" not in data["user"]
    assert "password_hash" not in data["user"]
    assert "TestnoGeslo123!" not in response.text


@pytest.mark.parametrize("case", ["unknown_email", "wrong_password", "inactive"])
def test_invalid_login_returns_same_401(client, user, case):
    test_client, db = client
    password = "TestnoGeslo123!"
    if case == "unknown_email":
        db.scalar.return_value = None
    elif case == "wrong_password":
        password = "NapacnoGeslo"
    else:
        user.active = False
    response = test_client.post("/api/auth/login", json={
        "email": "test@pijacai.local", "password": password,
    })
    assert response.status_code == 401
    assert response.json() == {"detail": "Napačna e-pošta ali geslo."}


def test_password_is_hashed_and_overlong_password_is_not_truncated():
    password_hash = hash_password("a" * 72)
    assert password_hash != "a" * 72
    assert verify_password("a" * 72, password_hash)
    assert not verify_password("a" * 73, password_hash)


def test_login_cors_preflight(client):
    test_client, _ = client
    response = test_client.options("/api/auth/login", headers={
        "Origin": "http://localhost:5174",
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "content-type",
    })
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5174"


def signed_token(**claims):
    now = datetime.now(timezone.utc)
    payload = {"sub": "1", "role": "admin", "iat": now, "exp": now + timedelta(hours=1)}
    payload.update(claims)
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")


def test_me_restores_session_with_current_database_role(client, user):
    test_client, db = client
    token = signed_token()
    user.role = Role.planner
    response = test_client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.json()["user"]["role"] == "planner"
    assert "password_hash" not in response.json()["user"]
    assert response.json()["expires_at"] == jwt.decode(token, JWT_SECRET, algorithms=["HS256"])["exp"]
    db.get.assert_called_once_with(User, 1)


@pytest.mark.parametrize("case", ["missing", "invalid", "expired", "bad_signature", "no_exp", "bad_sub", "inactive", "deleted"])
def test_me_rejects_invalid_sessions(client, user, case):
    test_client, db = client
    token = signed_token()
    if case == "invalid":
        token = "invalid-token"
    elif case == "expired":
        token = signed_token(exp=datetime.now(timezone.utc) - timedelta(seconds=1))
    elif case == "bad_signature":
        token = jwt.encode({"sub": "1"}, "another-signing-key-at-least-32-bytes", algorithm="HS256")
    elif case == "no_exp":
        token = jwt.encode({"sub": "1", "role": "admin", "iat": 1}, JWT_SECRET, algorithm="HS256")
    elif case == "bad_sub":
        token = signed_token(sub="not-an-id")
    elif case == "inactive":
        user.active = False
    elif case == "deleted":
        db.get.return_value = None
    headers = {} if case == "missing" else {"Authorization": f"Bearer {token}"}
    response = test_client.get("/api/auth/me", headers=headers)
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
