"""create pharmacies and users

Revision ID: 748ce97199ba
Revises:
Create Date: 2026-11-10

Slice A: the tenant table (pharmacies) and the people who log in (users).
Every user belongs to exactly one pharmacy.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "748ce97199ba"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # gen_random_uuid() is built into PostgreSQL 13 and later (no extension needed)
    op.create_table(
        "pharmacies",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("address", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_pharmacies")),
        # A name made only of spaces is not a name
        sa.CheckConstraint("length(trim(name)) > 0", name=op.f("ck_pharmacies_name_not_blank")),
    )

    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("pharmacy_id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(length=254), nullable=False),
        sa.Column("full_name", sa.String(length=200), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        # RESTRICT: a pharmacy can't be deleted while it still has users
        sa.ForeignKeyConstraint(
            ["pharmacy_id"],
            ["pharmacies.id"],
            name=op.f("fk_users_pharmacy_id_pharmacies"),
            ondelete="RESTRICT",
        ),
        # One account per email, across all pharmacies
        sa.UniqueConstraint("email", name=op.f("uq_users_email")),
        # Stored lowercase, so the unique constraint is effectively case-insensitive
        sa.CheckConstraint("email = lower(email)", name=op.f("ck_users_email_lowercase")),
        # Must match app.models.user.Role
        sa.CheckConstraint("role IN ('owner', 'manager', 'staff')", name=op.f("ck_users_role_valid")),
    )
    # Finding a pharmacy's users (and checking the foreign key) stays fast
    op.create_index(op.f("ix_users_pharmacy_id"), "users", ["pharmacy_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_users_pharmacy_id"), table_name="users")
    op.drop_table("users")
    op.drop_table("pharmacies")
