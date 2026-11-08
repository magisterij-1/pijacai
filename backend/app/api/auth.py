from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import (
    DUMMY_PASSWORD_HASH,
    TOKEN_LIFETIME_SECONDS,
    create_access_token,
    verify_password,
)
from app.database import get_db
from app.models import User
from app.schemas.auth import LoginIn, LoginOut, UserOut


router = APIRouter(prefix="/api/auth", tags=["Prijava"])


@router.post("/login", response_model=LoginOut)
def login(data: LoginIn, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == data.email.strip()))
    password_hash = user.password_hash if user else DUMMY_PASSWORD_HASH
    valid_password = verify_password(data.password.get_secret_value(), password_hash)
    if user is None or not valid_password or not user.active:
        raise HTTPException(
            status_code=401,
            detail="Napačna e-pošta ali geslo.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return LoginOut(
        access_token=create_access_token(user),
        expires_in=TOKEN_LIFETIME_SECONDS,
        user=UserOut.model_validate(user),
    )
