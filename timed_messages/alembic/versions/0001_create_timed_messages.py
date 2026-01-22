"""Create scheduled messages table.

Revision ID: 0001_create_timed_messages
Revises: 
Create Date: 2026-01-18
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0001_create_timed_messages"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "scheduled_messages",
        sa.Column(
            "id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("chat_id", sa.String(length=255), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("send_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "status",
            sa.Enum("SCHEDULED", "LOCKED", "SENT", "CANCELLED", "FAILED", name="message_status"),
            nullable=False,
            server_default="SCHEDULED",
        ),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempt_count", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("idempotency_key", sa.String(length=255), nullable=False),
        sa.Column("source", sa.String(length=255), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_scheduled_messages_status_send_at",
        "scheduled_messages",
        ["status", "send_at"],
    )
    op.create_index(
        "ix_scheduled_messages_send_at",
        "scheduled_messages",
        ["send_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_scheduled_messages_send_at", table_name="scheduled_messages")
    op.drop_index("ix_scheduled_messages_status_send_at", table_name="scheduled_messages")
    op.drop_table("scheduled_messages")
    op.execute("DROP TYPE message_status")
