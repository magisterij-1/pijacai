from datetime import datetime
from enum import Enum

from sqlalchemy import Boolean, DateTime, Enum as SQLAlchemyEnum, String, func, true
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Role(str, Enum):
    operator = "operator"
    quality = "quality"
    planner = "planner"
    warehouse = "warehouse"
    admin = "admin"


class User(Base):
    __tablename__ = "app_user"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(255), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[Role] = mapped_column(
        SQLAlchemyEnum(
            Role,
            name="user_role",
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
        )
    )
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
