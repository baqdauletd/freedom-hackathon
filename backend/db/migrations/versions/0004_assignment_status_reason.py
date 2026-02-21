"""add assignment status and unassigned reason

Revision ID: 0004_assignment_status_reason
Revises: 0003_processing_jobs_queue
Create Date: 2026-02-22
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0004_assignment_status_reason"
down_revision = "0003_processing_jobs_queue"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "assignments",
        sa.Column("assignment_status", sa.String(length=32), nullable=False, server_default="assigned"),
    )
    op.add_column(
        "assignments",
        sa.Column("unassigned_reason", sa.String(length=64), nullable=True),
    )
    op.create_index(op.f("ix_assignments_assignment_status"), "assignments", ["assignment_status"], unique=False)
    op.create_index(op.f("ix_assignments_unassigned_reason"), "assignments", ["unassigned_reason"], unique=False)
    op.alter_column("assignments", "assignment_status", server_default=None)


def downgrade() -> None:
    op.drop_index(op.f("ix_assignments_unassigned_reason"), table_name="assignments")
    op.drop_index(op.f("ix_assignments_assignment_status"), table_name="assignments")
    op.drop_column("assignments", "unassigned_reason")
    op.drop_column("assignments", "assignment_status")

