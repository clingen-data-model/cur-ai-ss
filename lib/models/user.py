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
    max_papers: Mapped[int | None] = mapped_column(nullable=True, server_default='10')
    # Opt-in: email is intrusive, and existing users never asked for it.
    notify_on_paper_complete: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default='0'
    )
    # NULL means "no avatar". Doubles as the cache-buster: the file always lives
    # at the same path, so without a changing query parameter a browser would keep
    # showing the old image after an upload.
    avatar_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    __table_args__ = (Index('ix_users_email', 'email', unique=True),)


class UserResp(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    first_name: str
    last_name: str
    is_active: bool
    is_admin: bool
    description_of_use_case: str
    max_papers: int | None
    notify_on_paper_complete: bool
    avatar_updated_at: datetime | None
    updated_at: datetime

    @computed_field  # type: ignore[misc]
    @property
    def avatar_url(self) -> str | None:
        """Path to the avatar, or None when the user has not set one.

        Carries avatar_updated_at as a query parameter because the file path is
        stable: the static mount sends a 24-hour Cache-Control, so a fresh upload
        would otherwise stay invisible until that expired.
        """
        if self.avatar_updated_at is None:
            return None
        from lib.misc.avatars import avatar_path

        return f'{avatar_path(self.id)}?v={int(self.avatar_updated_at.timestamp())}'


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
    avatar_updated_at: datetime | None = None

    @computed_field  # type: ignore[misc]
    @property
    def avatar_url(self) -> str | None:
        """Same contract as UserResp.avatar_url; see that docstring.

        Present here too because attribution renders an avatar wherever it
        appears, not only for the signed-in user.
        """
        if self.avatar_updated_at is None:
            return None
        version = int(self.avatar_updated_at.timestamp() * 1_000_000)
        return f'/users/{self.id}/avatar?v={version}'

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


class UserSettingsUpdateRequest(BaseModel):
    """Self-service account settings. Deliberately narrow.

    Only fields a user may change about themselves live here -- is_admin,
    is_active and max_papers are administrative and must not be settable by the
    account they apply to.

    extra='forbid' so an unknown field is a 422 rather than a silent no-op.
    Pydantic's default would drop it, which for a settings toggle is the worst
    outcome: a misspelled field name returns 200 and changes nothing, and the UI
    reports success.
    """

    model_config = ConfigDict(extra='forbid')

    notify_on_paper_complete: bool | None = None


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
