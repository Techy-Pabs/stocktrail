import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, String, Uuid, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.user import User


class Pharmacy(Base):
    """A pharmacy: the tenant. Every user, and later every product and batch,
    belongs to exactly one pharmacy."""

    __tablename__ = "pharmacies"
    __table_args__ = (CheckConstraint("length(trim(name)) > 0", name="name_not_blank"),)

    # default: Python makes the id; server_default: so do raw SQL inserts
    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()")
    )
    name: Mapped[str] = mapped_column(String(200))
    address: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    users: Mapped[list["User"]] = relationship(back_populates="pharmacy")
