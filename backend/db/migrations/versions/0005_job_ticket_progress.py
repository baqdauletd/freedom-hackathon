"""add per-ticket job progress table

Revision ID: 0005_job_ticket_progress
Revises: 0004_assignment_status_reason
Create Date: 2026-02-22
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0005_job_ticket_progress"
down_revision = "0004_assignment_status_reason"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "processing_job_tickets",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("job_id", sa.String(length=36), nullable=False),
        sa.Column("ticket_id", sa.Integer(), nullable=False),
        sa.Column("external_ticket_id", sa.String(length=255), nullable=False),
        sa.Column("stage", sa.String(length=32), nullable=False, server_default="queued"),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("retries", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["job_id"], ["processing_jobs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["ticket_id"], ["tickets.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("job_id", "ticket_id", name="uq_job_ticket_stage"),
    )
    op.create_index(op.f("ix_processing_job_tickets_job_id"), "processing_job_tickets", ["job_id"], unique=False)
    op.create_index(op.f("ix_processing_job_tickets_ticket_id"), "processing_job_tickets", ["ticket_id"], unique=False)
    op.create_index(op.f("ix_processing_job_tickets_external_ticket_id"), "processing_job_tickets", ["external_ticket_id"], unique=False)
    op.create_index(op.f("ix_processing_job_tickets_stage"), "processing_job_tickets", ["stage"], unique=False)
    op.create_index(op.f("ix_processing_job_tickets_status"), "processing_job_tickets", ["status"], unique=False)
    op.create_index(op.f("ix_processing_job_tickets_updated_at"), "processing_job_tickets", ["updated_at"], unique=False)

    op.alter_column("processing_job_tickets", "stage", server_default=None)
    op.alter_column("processing_job_tickets", "status", server_default=None)
    op.alter_column("processing_job_tickets", "retries", server_default=None)


def downgrade() -> None:
    op.drop_index(op.f("ix_processing_job_tickets_updated_at"), table_name="processing_job_tickets")
    op.drop_index(op.f("ix_processing_job_tickets_status"), table_name="processing_job_tickets")
    op.drop_index(op.f("ix_processing_job_tickets_stage"), table_name="processing_job_tickets")
    op.drop_index(op.f("ix_processing_job_tickets_external_ticket_id"), table_name="processing_job_tickets")
    op.drop_index(op.f("ix_processing_job_tickets_ticket_id"), table_name="processing_job_tickets")
    op.drop_index(op.f("ix_processing_job_tickets_job_id"), table_name="processing_job_tickets")
    op.drop_table("processing_job_tickets")
