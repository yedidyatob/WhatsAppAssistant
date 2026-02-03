"""Add from_chat_id to scheduled messages.

Revision ID: 0002_add_from_chat_id
Revises: 0001_create_timed_messages
Create Date: 2026-01-25
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0002_add_from_chat_id"
down_revision = "0001_create_timed_messages"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "scheduled_messages",
        sa.Column("from_chat_id", sa.String(length=255), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("scheduled_messages", "from_chat_id")
