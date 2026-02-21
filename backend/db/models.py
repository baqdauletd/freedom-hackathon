from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy import (
    JSON,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class ProcessingRun(Base):
    __tablename__ = "processing_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    status: Mapped[str] = mapped_column(String(32), default="processing", index=True)
    tickets_total: Mapped[int] = mapped_column(Integer, default=0)
    tickets_success: Mapped[int] = mapped_column(Integer, default=0)
    tickets_failed: Mapped[int] = mapped_column(Integer, default=0)
    avg_processing_ms: Mapped[int] = mapped_column(Integer, default=0)
    elapsed_ms: Mapped[int] = mapped_column(Integer, default=0)

    tickets_filename: Mapped[str | None] = mapped_column(String(255))
    managers_filename: Mapped[str | None] = mapped_column(String(255))
    business_units_filename: Mapped[str | None] = mapped_column(String(255))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )

    tickets: Mapped[list["Ticket"]] = relationship(back_populates="run")
    job: Mapped["ProcessingJob | None"] = relationship(back_populates="run", uselist=False)


class ProcessingJob(Base):
    __tablename__ = "processing_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    run_id: Mapped[str] = mapped_column(ForeignKey("processing_runs.id", ondelete="CASCADE"), unique=True, index=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(255), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(32), default="queued", index=True)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    locked_by: Mapped[str | None] = mapped_column(String(128))
    last_error: Mapped[str | None] = mapped_column(Text)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
        index=True,
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    run: Mapped[ProcessingRun] = relationship(back_populates="job")


class Ticket(Base):
    __tablename__ = "tickets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str | None] = mapped_column(ForeignKey("processing_runs.id", ondelete="SET NULL"), index=True)
    external_id: Mapped[str] = mapped_column(String(255), index=True)
    gender: Mapped[str | None] = mapped_column(String(32))
    birth_date: Mapped[str | None] = mapped_column(String(64))
    segment: Mapped[str] = mapped_column(String(32), index=True)
    description: Mapped[str] = mapped_column(Text)
    attachments: Mapped[str | None] = mapped_column(String(512))

    country: Mapped[str | None] = mapped_column(String(128))
    region: Mapped[str | None] = mapped_column(String(128))
    city: Mapped[str | None] = mapped_column(String(128), index=True)
    street: Mapped[str | None] = mapped_column(String(256))
    house: Mapped[str | None] = mapped_column(String(64))
    normalized_address: Mapped[str | None] = mapped_column(String(512))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )

    run: Mapped["ProcessingRun | None"] = relationship(back_populates="tickets")
    ai_analysis: Mapped["AIAnalysis | None"] = relationship(back_populates="ticket", uselist=False)
    assignment: Mapped["Assignment | None"] = relationship(back_populates="ticket", uselist=False)


class BusinessUnit(Base):
    __tablename__ = "business_units"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    office: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    address: Mapped[str] = mapped_column(String(512))
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)

    managers: Mapped[list["Manager"]] = relationship(back_populates="office")
    assignments: Mapped[list["Assignment"]] = relationship(back_populates="office")


class Manager(Base):
    __tablename__ = "managers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    full_name: Mapped[str] = mapped_column(String(255), index=True)
    position: Mapped[str] = mapped_column(String(128))
    skills: Mapped[list[str]] = mapped_column(JSON, default=list)
    current_load: Mapped[int] = mapped_column(Integer, default=0)

    office_id: Mapped[int] = mapped_column(ForeignKey("business_units.id", ondelete="CASCADE"), index=True)
    office: Mapped[BusinessUnit] = relationship(back_populates="managers")
    assignments: Mapped[list["Assignment"]] = relationship(back_populates="manager")


class AIAnalysis(Base):
    __tablename__ = "ai_analysis"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey("tickets.id", ondelete="CASCADE"), unique=True, index=True)

    ticket_type: Mapped[str] = mapped_column(String(64), index=True)
    tone: Mapped[str] = mapped_column(String(32), index=True)
    priority: Mapped[int] = mapped_column(Integer, index=True)
    language: Mapped[str] = mapped_column(String(8), index=True)
    summary: Mapped[str] = mapped_column(Text)
    recommendation: Mapped[str] = mapped_column(Text)

    ticket_lat: Mapped[float | None] = mapped_column(Float)
    ticket_lon: Mapped[float | None] = mapped_column(Float)
    processing_ms: Mapped[int | None] = mapped_column(Integer)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )

    ticket: Mapped[Ticket] = relationship(back_populates="ai_analysis")


class Assignment(Base):
    __tablename__ = "assignments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey("tickets.id", ondelete="CASCADE"), unique=True, index=True)
    office_id: Mapped[int] = mapped_column(ForeignKey("business_units.id", ondelete="RESTRICT"), index=True)
    manager_id: Mapped[int | None] = mapped_column(ForeignKey("managers.id", ondelete="SET NULL"), index=True)

    selected_pair_snapshot: Mapped[list[str]] = mapped_column(JSON, default=list)
    rr_turn: Mapped[int] = mapped_column(Integer, default=0)
    decision_trace: Mapped[dict | None] = mapped_column(JSON)

    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        index=True,
    )

    ticket: Mapped[Ticket] = relationship(back_populates="assignment")
    office: Mapped[BusinessUnit] = relationship(back_populates="assignments")
    manager: Mapped[Manager | None] = relationship(back_populates="assignments")


class RRState(Base):
    __tablename__ = "rr_state"
    __table_args__ = (UniqueConstraint("office_id", "eligible_pair_hash", name="uq_rr_office_pair"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    office_id: Mapped[int] = mapped_column(ForeignKey("business_units.id", ondelete="CASCADE"), index=True)
    eligible_pair_hash: Mapped[str] = mapped_column(String(255), index=True)
    next_turn: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
