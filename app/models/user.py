import uuid
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
    func,
    text,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.pharmacy import Pharmacy


class Role(StrEnum):
    OWNER = "owner"
    MANAGER = "manager"
    STAFF = "staff"


# The CHECK constraint below must list the same roles as Role. The migration
# repeats this list by hand, and tests/test_models.py checks they all agree.
ROLE_CHECK_SQL = "role IN ('owner', 'manager', 'staff')"


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(ROLE_CHECK_SQL, name="role_valid"),
        # Emails are compared exactly, so they must be stored lowercase for
        # "Ada@x.com" and "ada@x.com" to count as the same account
        CheckConstraint("email = lower(email)", name="email_lowercase"),
        UniqueConstraint("email"),
        CheckConstraint("token_version >= 0", name="token_version_not_negative"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()")
    )
    # RESTRICT: a pharmacy can't be deleted while it still has users
    pharmacy_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("pharmacies.id", ondelete="RESTRICT"), index=True)
    email: Mapped[str] = mapped_column(String(254))
    full_name: Mapped[str] = mapped_column(String(200))
    password_hash: Mapped[str] = mapped_column(String(255))
    # No default: whoever creates a user must choose the role on purpose
    role: Mapped[str] = mapped_column(String(20))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())
    # Goes up by one when the password changes or is reset. Every token carries
    # the version it was made with, so raising it revokes all older tokens.
    token_version: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # lazy="joined": loading a user loads their pharmacy in the same query
    pharmacy: Mapped["Pharmacy"] = relationship(back_populates="users", lazy="joined")

    @validates("role")
    def _validate_role(self, key: str, value: str) -> str:
        # The same rule as the CHECK constraint, enforced in Python before the
        # database ever sees the value. Role(value) raises ValueError if unknown.
        return Role(value).value

    @validates("email")
    def _lowercase_email(self, key: str, value: str) -> str:
        return value.strip().lower()
