from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, SecretStr, StringConstraints, field_validator

from app.models import Role


class UserCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
    email: Annotated[str, StringConstraints(
        strip_whitespace=True, max_length=255,
        pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$",
    )]
    password: SecretStr = Field(min_length=8)
    role: Role

    @field_validator("password")
    @classmethod
    def validate_password_bytes(cls, password: SecretStr) -> SecretStr:
        if len(password.get_secret_value().encode("utf-8")) > 72:
            raise ValueError("Geslo ne sme presegati 72 UTF-8 bajtov.")
        return password
