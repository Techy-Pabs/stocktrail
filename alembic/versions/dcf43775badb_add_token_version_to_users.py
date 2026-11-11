"""add token_version to users

Revision ID: dcf43775badb
Revises: 748ce97199ba
Create Date: 2026-11-11

Slice B: every login token carries the user's token_version. Raising the
number (on a password change or reset) makes all older tokens invalid.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "dcf43775badb"
down_revision: str | Sequence[str] | None = "748ce97199ba"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # NOT NULL with a default of 0: existing users get 0, so the column can be
    # required straight away. PostgreSQL fills a constant default without
    # rewriting the table.
    op.add_column(
        "users",
        sa.Column("token_version", sa.Integer(), server_default=sa.text("0"), nullable=False),
    )
    # The version only ever goes up from 0
    op.create_check_constraint(op.f("ck_users_token_version_not_negative"), "users", "token_version >= 0")


def downgrade() -> None:
    op.drop_constraint(op.f("ck_users_token_version_not_negative"), "users", type_="check")
    op.drop_column("users", "token_version")
