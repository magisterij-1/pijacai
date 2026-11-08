from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.dependencies import require_roles
from app.core.security import hash_password
from app.database import get_db
from app.models import Role, User
from app.schemas.auth import UserOut
from app.schemas.users import UserCreate


router = APIRouter(prefix="/api/users", tags=["Uporabniki"])


def duplicate_email() -> HTTPException:
    return HTTPException(status_code=409, detail="Uporabnik s to e-pošto že obstaja.")


@router.get("", response_model=list[UserOut])
def list_users(
    admin: User = Depends(require_roles(Role.admin)),
    db: Session = Depends(get_db),
):
    return db.scalars(select(User).order_by(User.id)).all()


@router.post("/{user_id}/deactivate", response_model=UserOut)
def deactivate_user(
    user_id: Annotated[int, Path(gt=0, le=2147483647)],
    admin: User = Depends(require_roles(Role.admin)),
    db: Session = Depends(get_db),
):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Uporabnik ni najden.")
    if user.active:
        user.active = False
        db.commit()
        db.refresh(user)
    return user


@router.post("", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def create_user(
    data: UserCreate,
    admin: User = Depends(require_roles(Role.admin)),
    db: Session = Depends(get_db),
):
    if db.scalar(select(User).where(User.email == data.email)) is not None:
        raise duplicate_email()
    user = User(
        name=data.name,
        email=data.email,
        password_hash=hash_password(data.password.get_secret_value()),
        role=data.role,
        active=True,
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        # Enoličnost v PostgreSQL prepreči tudi sočasno ustvarjanje iste e-pošte.
        constraint = getattr(getattr(error.orig, "diag", None), "constraint_name", None)
        if getattr(error.orig, "sqlstate", None) == "23505" and constraint == "app_user_email_key":
            raise duplicate_email() from None
        raise
    db.refresh(user)
    return user
