from dataclasses import dataclass

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.security import decode_access_token
from app.database import get_db
from app.models import Role, User


bearer = HTTPBearer(auto_error=False)


@dataclass
class AuthenticatedSession:
    user: User
    expires_at: int


def get_current_session(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> AuthenticatedSession:
    unauthorized = HTTPException(
        status_code=401,
        detail="Prijava je potekla ali ni veljavna. Prijavi se znova.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if credentials is None:
        raise unauthorized
    try:
        payload = decode_access_token(credentials.credentials)
        user_id = int(payload["sub"])
        if user_id <= 0 or type(payload["exp"]) is not int:
            raise ValueError("Neveljavne trditve žetona.")
    except (jwt.InvalidTokenError, ValueError, TypeError, OverflowError):
        raise unauthorized from None
    user = db.get(User, user_id)
    if user is None or not user.active:
        raise unauthorized
    return AuthenticatedSession(user=user, expires_at=payload["exp"])


def get_current_user(session: AuthenticatedSession = Depends(get_current_session)) -> User:
    return session.user


def require_roles(*allowed_roles: Role):
    """Zahtevaj prijavo in eno od izrecno dovoljenih trenutnih vlog."""
    if not allowed_roles:
        raise ValueError("Navesti je treba vsaj eno dovoljeno vlogo.")
    allowed = frozenset(Role(role) for role in allowed_roles)

    def check_role(user: User = Depends(get_current_user)) -> User:
        if user.role not in allowed:
            raise HTTPException(status_code=403, detail="Nimate dostopa.")
        return user

    return check_role
