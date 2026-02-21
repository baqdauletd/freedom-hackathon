"""add analytics performance indexes

Revision ID: 0002_analytics_indexes
Revises: 0001_fire_initial
Create Date: 2026-02-22
"""

from __future__ import annotations

from alembic import op


revision = "0002_analytics_indexes"
down_revision = "0001_fire_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index("ix_tickets_created_at", "tickets", ["created_at"], unique=False)
    op.create_index("ix_ai_analysis_created_at", "ai_analysis", ["created_at"], unique=False)
    op.create_index("ix_assignments_assigned_at", "assignments", ["assigned_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_assignments_assigned_at", table_name="assignments")
    op.drop_index("ix_ai_analysis_created_at", table_name="ai_analysis")
    op.drop_index("ix_tickets_created_at", table_name="tickets")
