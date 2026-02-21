"""add processing jobs queue table

Revision ID: 0003_processing_jobs_queue
Revises: 0002_analytics_indexes
Create Date: 2026-02-22
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0003_processing_jobs_queue"
down_revision = "0002_analytics_indexes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "processing_jobs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("idempotency_key", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("locked_by", sa.String(length=128), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["run_id"], ["processing_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key"),
        sa.UniqueConstraint("run_id"),
    )
    op.create_index(op.f("ix_processing_jobs_run_id"), "processing_jobs", ["run_id"], unique=True)
    op.create_index(op.f("ix_processing_jobs_idempotency_key"), "processing_jobs", ["idempotency_key"], unique=True)
    op.create_index(op.f("ix_processing_jobs_status"), "processing_jobs", ["status"], unique=False)
    op.create_index(op.f("ix_processing_jobs_next_attempt_at"), "processing_jobs", ["next_attempt_at"], unique=False)
    op.create_index(op.f("ix_processing_jobs_created_at"), "processing_jobs", ["created_at"], unique=False)
    op.create_index(op.f("ix_processing_jobs_updated_at"), "processing_jobs", ["updated_at"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_processing_jobs_updated_at"), table_name="processing_jobs")
    op.drop_index(op.f("ix_processing_jobs_created_at"), table_name="processing_jobs")
    op.drop_index(op.f("ix_processing_jobs_next_attempt_at"), table_name="processing_jobs")
    op.drop_index(op.f("ix_processing_jobs_status"), table_name="processing_jobs")
    op.drop_index(op.f("ix_processing_jobs_idempotency_key"), table_name="processing_jobs")
    op.drop_index(op.f("ix_processing_jobs_run_id"), table_name="processing_jobs")
    op.drop_table("processing_jobs")
