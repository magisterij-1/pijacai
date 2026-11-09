# — prijavni podatki, uporabnik in odgovor z JWT.
from pydantic import BaseModel, ConfigDict, SecretStr

from app.models import Role


class LoginIn(BaseModel):
    email: str
    password: SecretStr


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    email: str
    role: Role
    active: bool


class LoginOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    expires_at: int
    user: UserOut


class SessionOut(BaseModel):
    user: UserOut
    expires_at: int
