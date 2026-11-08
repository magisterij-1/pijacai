from datetime import datetime, timedelta, timezone
import os

import bcrypt
import jwt

from app.models import User


JWT_SECRET = os.environ["JWT_SECRET"]
if len(JWT_SECRET.encode("utf-8")) < 32:
    raise RuntimeError("JWT_SECRET mora vsebovati najmanj 32 bajtov.")

TOKEN_LIFETIME_SECONDS = 60 * 60


def hash_password(password: str) -> str:
    encoded = password.encode("utf-8")
    if len(encoded) > 72:
        raise ValueError("Geslo za bcrypt ne sme presegati 72 bajtov.")
    return bcrypt.hashpw(encoded, bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    encoded = password.encode("utf-8")
    if len(encoded) > 72:
        return False
    try:
        return bcrypt.checkpw(encoded, password_hash.encode("utf-8"))
    except ValueError:
        return False


# Za neobstoječ račun vseeno izvedemo bcrypt preverjanje.
DUMMY_PASSWORD_HASH = hash_password("dummy-password-for-login-timing")


def create_access_token(user: User) -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {
            "sub": str(user.id),
            "role": user.role.value,
            "iat": now,
            "exp": now + timedelta(seconds=TOKEN_LIFETIME_SECONDS),
        },
        JWT_SECRET,
        algorithm="HS256",
    )
