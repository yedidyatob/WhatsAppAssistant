"""Add confirmation_message_id to scheduled messages.

Revision ID: 0003_add_confirmation_message_id
Revises: 0002_add_from_chat_id
Create Date: 2026-02-08
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0003_add_confirmation_message_id"
down_revision = "0002_add_from_chat_id"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "scheduled_messages",
        sa.Column("confirmation_message_id", sa.String(length=512), nullable=True),
    )
    op.create_index(
        "ix_scheduled_messages_confirmation_message_id",
        "scheduled_messages",
        ["confirmation_message_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_scheduled_messages_confirmation_message_id",
        table_name="scheduled_messages",
    )
    op.drop_column("scheduled_messages", "confirmation_message_id")
