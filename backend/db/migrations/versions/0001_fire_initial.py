"""initial FIRE schema

Revision ID: 0001_fire_initial
Revises: None
Create Date: 2026-02-21
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0001_fire_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "processing_runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("tickets_total", sa.Integer(), nullable=False),
        sa.Column("tickets_success", sa.Integer(), nullable=False),
        sa.Column("tickets_failed", sa.Integer(), nullable=False),
        sa.Column("avg_processing_ms", sa.Integer(), nullable=False),
        sa.Column("elapsed_ms", sa.Integer(), nullable=False),
        sa.Column("tickets_filename", sa.String(length=255), nullable=True),
        sa.Column("managers_filename", sa.String(length=255), nullable=True),
        sa.Column("business_units_filename", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_processing_runs_status"), "processing_runs", ["status"], unique=False)

    op.create_table(
        "business_units",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("office", sa.String(length=128), nullable=False),
        sa.Column("address", sa.String(length=512), nullable=False),
        sa.Column("latitude", sa.Float(), nullable=True),
        sa.Column("longitude", sa.Float(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_business_units_office"), "business_units", ["office"], unique=True)

    op.create_table(
        "tickets",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=True),
        sa.Column("external_id", sa.String(length=255), nullable=False),
        sa.Column("gender", sa.String(length=32), nullable=True),
        sa.Column("birth_date", sa.String(length=64), nullable=True),
        sa.Column("segment", sa.String(length=32), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("attachments", sa.String(length=512), nullable=True),
        sa.Column("country", sa.String(length=128), nullable=True),
        sa.Column("region", sa.String(length=128), nullable=True),
        sa.Column("city", sa.String(length=128), nullable=True),
        sa.Column("street", sa.String(length=256), nullable=True),
        sa.Column("house", sa.String(length=64), nullable=True),
        sa.Column("normalized_address", sa.String(length=512), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["processing_runs.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_tickets_city"), "tickets", ["city"], unique=False)
    op.create_index(op.f("ix_tickets_external_id"), "tickets", ["external_id"], unique=False)
    op.create_index(op.f("ix_tickets_run_id"), "tickets", ["run_id"], unique=False)
    op.create_index(op.f("ix_tickets_segment"), "tickets", ["segment"], unique=False)

    op.create_table(
        "managers",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("full_name", sa.String(length=255), nullable=False),
        sa.Column("position", sa.String(length=128), nullable=False),
        sa.Column("skills", sa.JSON(), nullable=False),
        sa.Column("current_load", sa.Integer(), nullable=False),
        sa.Column("office_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["office_id"], ["business_units.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_managers_full_name"), "managers", ["full_name"], unique=False)
    op.create_index(op.f("ix_managers_office_id"), "managers", ["office_id"], unique=False)

    op.create_table(
        "ai_analysis",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("ticket_id", sa.Integer(), nullable=False),
        sa.Column("ticket_type", sa.String(length=64), nullable=False),
        sa.Column("tone", sa.String(length=32), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("language", sa.String(length=8), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("recommendation", sa.Text(), nullable=False),
        sa.Column("ticket_lat", sa.Float(), nullable=True),
        sa.Column("ticket_lon", sa.Float(), nullable=True),
        sa.Column("processing_ms", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["ticket_id"], ["tickets.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_ai_analysis_language"), "ai_analysis", ["language"], unique=False)
    op.create_index(op.f("ix_ai_analysis_priority"), "ai_analysis", ["priority"], unique=False)
    op.create_index(op.f("ix_ai_analysis_ticket_id"), "ai_analysis", ["ticket_id"], unique=True)
    op.create_index(op.f("ix_ai_analysis_ticket_type"), "ai_analysis", ["ticket_type"], unique=False)
    op.create_index(op.f("ix_ai_analysis_tone"), "ai_analysis", ["tone"], unique=False)

    op.create_table(
        "assignments",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("ticket_id", sa.Integer(), nullable=False),
        sa.Column("office_id", sa.Integer(), nullable=False),
        sa.Column("manager_id", sa.Integer(), nullable=True),
        sa.Column("selected_pair_snapshot", sa.JSON(), nullable=False),
        sa.Column("rr_turn", sa.Integer(), nullable=False),
        sa.Column("decision_trace", sa.JSON(), nullable=True),
        sa.Column("assigned_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["manager_id"], ["managers.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["office_id"], ["business_units.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["ticket_id"], ["tickets.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_assignments_manager_id"), "assignments", ["manager_id"], unique=False)
    op.create_index(op.f("ix_assignments_office_id"), "assignments", ["office_id"], unique=False)
    op.create_index(op.f("ix_assignments_ticket_id"), "assignments", ["ticket_id"], unique=True)

    op.create_table(
        "rr_state",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("office_id", sa.Integer(), nullable=False),
        sa.Column("eligible_pair_hash", sa.String(length=255), nullable=False),
        sa.Column("next_turn", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["office_id"], ["business_units.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("office_id", "eligible_pair_hash", name="uq_rr_office_pair"),
    )
    op.create_index(op.f("ix_rr_state_eligible_pair_hash"), "rr_state", ["eligible_pair_hash"], unique=False)
    op.create_index(op.f("ix_rr_state_office_id"), "rr_state", ["office_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_rr_state_office_id"), table_name="rr_state")
    op.drop_index(op.f("ix_rr_state_eligible_pair_hash"), table_name="rr_state")
    op.drop_table("rr_state")

    op.drop_index(op.f("ix_assignments_ticket_id"), table_name="assignments")
    op.drop_index(op.f("ix_assignments_office_id"), table_name="assignments")
    op.drop_index(op.f("ix_assignments_manager_id"), table_name="assignments")
    op.drop_table("assignments")

    op.drop_index(op.f("ix_ai_analysis_tone"), table_name="ai_analysis")
    op.drop_index(op.f("ix_ai_analysis_ticket_type"), table_name="ai_analysis")
    op.drop_index(op.f("ix_ai_analysis_ticket_id"), table_name="ai_analysis")
    op.drop_index(op.f("ix_ai_analysis_priority"), table_name="ai_analysis")
    op.drop_index(op.f("ix_ai_analysis_language"), table_name="ai_analysis")
    op.drop_table("ai_analysis")

    op.drop_index(op.f("ix_managers_office_id"), table_name="managers")
    op.drop_index(op.f("ix_managers_full_name"), table_name="managers")
    op.drop_table("managers")

    op.drop_index(op.f("ix_tickets_run_id"), table_name="tickets")
    op.drop_index(op.f("ix_tickets_segment"), table_name="tickets")
    op.drop_index(op.f("ix_tickets_external_id"), table_name="tickets")
    op.drop_index(op.f("ix_tickets_city"), table_name="tickets")
    op.drop_table("tickets")

    op.drop_index(op.f("ix_business_units_office"), table_name="business_units")
    op.drop_table("business_units")

    op.drop_index(op.f("ix_processing_runs_status"), table_name="processing_runs")
    op.drop_table("processing_runs")
