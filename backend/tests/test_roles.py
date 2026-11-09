from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

import jwt
import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from fastapi.routing import APIRoute

from app.api.dependencies import require_roles
from app.core.security import JWT_SECRET, create_access_token
from app.database import get_db
from app.models import Role, User
from app.main import app


@pytest.fixture
def user():
    return User(
        id=1, name="Testni uporabnik", email="test@pijacai.local",
        password_hash="unused-in-role-tests", role=Role.planner, active=True,
    )


@pytest.fixture
def protected_client(user):
    """Ločena testna aplikacija; produkcijskemu API ne dodaja testnih poti."""
    def make_client(*allowed_roles):
        test_app = FastAPI()
        db = Mock()
        db.get.return_value = user

        def override_db():
            yield db

        test_app.dependency_overrides[get_db] = override_db

        @test_app.get("/protected")
        def protected(current: User = Depends(require_roles(*allowed_roles))):
            return {"user_id": current.id, "role": current.role.value}

        return TestClient(test_app), db

    return make_client


@pytest.mark.parametrize("allowed_role", list(Role))
@pytest.mark.parametrize("current_role", list(Role))
def test_only_explicitly_allowed_role_can_access(protected_client, user, allowed_role, current_role):
    user.role = current_role
    client, db = protected_client(allowed_role)
    token = create_access_token(user)
    with client:
        response = client.get("/protected", headers={"Authorization": f"Bearer {token}"})
    if current_role == allowed_role:
        assert response.status_code == 200
        assert response.json() == {"user_id": 1, "role": current_role.value}
    else:
        assert response.status_code == 403
        assert response.json() == {"detail": "Nimate dostopa."}
    db.get.assert_called_once_with(User, 1)


@pytest.mark.parametrize("current_role", list(Role))
def test_endpoint_can_allow_multiple_roles(protected_client, user, current_role):
    user.role = current_role
    client, _ = protected_client(Role.planner, Role.quality)
    with client:
        response = client.get("/protected", headers={
            "Authorization": f"Bearer {create_access_token(user)}",
        })
    assert response.status_code == (200 if current_role in (Role.planner, Role.quality) else 403)


@pytest.mark.parametrize("case", ["missing", "invalid", "expired", "inactive", "deleted"])
def test_invalid_authentication_returns_401_before_role_check(protected_client, user, case):
    # Uporabnik nima zahtevane vloge; neveljavna prijava ima prednost pred 403.
    client, db = protected_client(Role.quality)
    token = create_access_token(user)
    if case == "invalid":
        token = "invalid-token"
    elif case == "expired":
        now = datetime.now(timezone.utc)
        token = jwt.encode(
            {"sub": "1", "role": "planner", "iat": now - timedelta(hours=2), "exp": now - timedelta(hours=1)},
            JWT_SECRET, algorithm="HS256",
        )
    elif case == "inactive":
        user.active = False
    elif case == "deleted":
        db.get.return_value = None
    headers = {} if case == "missing" else {"Authorization": f"Bearer {token}"}
    with client:
        response = client.get("/protected", headers=headers)
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    if case in ("missing", "invalid", "expired"):
        db.get.assert_not_called()


@pytest.mark.parametrize("token_role,current_role,expected", [
    (Role.planner, Role.warehouse, 403),
    (Role.warehouse, Role.planner, 200),
])
def test_database_role_takes_precedence_over_old_token_role(
    protected_client, user, token_role, current_role, expected,
):
    user.role = token_role
    token = create_access_token(user)
    user.role = current_role
    client, _ = protected_client(Role.planner)
    with client:
        response = client.get("/protected", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == expected


def test_missing_allowed_roles_is_a_configuration_error():
    with pytest.raises(ValueError, match="vsaj eno"):
        require_roles()


def test_existing_api_routes_have_an_explicit_access_policy():
    # Ob novi poslovni poti dopolni ta seznam in dodaj vedenjske teste njenih vlog.
    public_routes = {("GET", "/api/health"), ("POST", "/api/auth/login")}
    authenticated_routes = {("GET", "/api/auth/me")}
    restricted_routes = {
        ("POST", "/api/users"),
        ("GET", "/api/users"),
        ("POST", "/api/users/{user_id}/deactivate"),
        ("POST", "/api/material-lots"),
        ("GET", "/api/material-lots"),
        ("GET", "/api/lookup/materials"),
        ("GET", "/api/lookup/suppliers"),
        ("GET", "/api/stock"),
        ("GET", "/api/lookup/products"),
        ("POST", "/api/orders/preview"),
        ("POST", "/api/orders"),
        ("GET", "/api/orders"),
        ("POST", "/api/orders/{order_id}/cancel"),
        ("GET", "/api/lookup/lines"),
        ("POST", "/api/orders/{order_id}/batches/preview"),
        ("POST", "/api/orders/{order_id}/batches"),
        ("POST", "/api/batches/{batch_id}/finish"),
        ("GET", "/api/batches/{batch_id}/checks"),
        ("POST", "/api/batches/{batch_id}/checks"),
        ("POST", "/api/batches/{batch_id}/release"),
        ("GET", "/api/batches"),
        ("GET", "/api/batches/{batch_id}"),
    }
    implemented_routes = {
        (method, route.path)
        for route in app.routes
        if isinstance(route, APIRoute) and route.path.startswith("/api/")
        for method in route.methods
    }
    assert implemented_routes == public_routes | authenticated_routes | restricted_routes
