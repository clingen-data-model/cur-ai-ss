import re
from datetime import datetime

from pydantic import BaseModel, ConfigDict, SecretStr, computed_field, field_validator
from sqlalchemy import Boolean, DateTime, Index, String, func
from sqlalchemy.orm import Mapped, mapped_column

from lib.models.base import Base

_EMAIL_RE = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')


class UserDB(Base):
    __tablename__ = 'users'

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    hashed_password: Mapped[str] = mapped_column(String, nullable=False)
    first_name: Mapped[str] = mapped_column(String, nullable=False)
    last_name: Mapped[str] = mapped_column(String, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default='1')
    is_admin: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default='0')
    description_of_use_case: Mapped[str] = mapped_column(
        String, nullable=False, server_default=''
    )
    max_papers: Mapped[int | None] = mapped_column(nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    __table_args__ = (Index('ix_users_email', 'email', unique=True),)


class UserResp(BaseModel):
    id: int
    email: str
    first_name: str
    last_name: str
    is_active: bool
    is_admin: bool
    description_of_use_case: str
    max_papers: int | None
    updated_at: datetime


class UserSummaryResp(BaseModel):
    """Minimal user identity for attribution on other entities' responses.

    Built directly from the ``updated_by`` ORM relationship; deliberately omits
    sensitive/account fields exposed by ``UserResp``.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    first_name: str
    last_name: str

    @computed_field  # type: ignore[misc]
    @property
    def name(self) -> str:
        return f'{self.first_name} {self.last_name}'.strip() or self.email


class UserCreateRequest(BaseModel):
    email: str
    first_name: str
    last_name: str
    description_of_use_case: str

    @field_validator('email')
    @classmethod
    def validate_email(cls, v: str) -> str:
        v = v.strip().lower()
        if not _EMAIL_RE.match(v):
            raise ValueError('Invalid email address')
        return v


class ChangePasswordRequest(BaseModel):
    current_password: SecretStr
    new_password: SecretStr

    @field_validator('new_password')
    @classmethod
    def validate_new_password(cls, v: SecretStr) -> SecretStr:
        if len(v.get_secret_value()) < 8:
            raise ValueError('Password must be at least 8 characters')
        return v


class LoginRequest(BaseModel):
    email: str
    password: SecretStr

    @field_validator('email')
    @classmethod
    def normalize_email(cls, v: str) -> str:
        return v.strip().lower()


class TokenResp(BaseModel):
    access_token: str
    token_type: str = 'bearer'
