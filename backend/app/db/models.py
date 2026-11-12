"""ORM models for the Phase 3 schema: datasets, batteries, cycles and scenarios.

Numeric measurements use ``DOUBLE PRECISION`` (IEEE-754 binary64) so values round-trip exactly
between Python, PostgreSQL and the v1 analytics; ``NUMERIC`` would alter the binary value.
``soh_pct`` is stored as produced by the data source rather than computed by the database.
Further tables (models, predictions, jobs, ...) arrive in the phases that need them.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Double,
    ForeignKey,
    Identity,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, CreatedAtMixin, TimestampMixin

DATASET_SOURCES = ("nasa_pcoe", "calce", "severson", "upload", "synthetic")
DATASET_STATUSES = ("registered", "importing", "ready", "failed")
CYCLE_TYPES = ("charge", "discharge", "impedance", "full")


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()")
    )


def _jsonb_object() -> Mapped[dict[str, Any]]:
    return mapped_column(JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb"))


class Dataset(TimestampMixin, Base):
    __tablename__ = "datasets"
    __table_args__ = (
        CheckConstraint(_in("source", DATASET_SOURCES), name="source"),
        CheckConstraint(_in("status", DATASET_STATUSES), name="status"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    slug: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    version: Mapped[str] = mapped_column(String(32), nullable=False)
    licence: Mapped[str | None] = mapped_column(Text)
    citation: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="registered", server_default="registered"
    )
    checksum: Mapped[str | None] = mapped_column(String(64))
    #: Internal metadata (e.g. synthetic ground truth). Not exposed by public dataset endpoints.
    meta: Mapped[dict[str, Any]] = _jsonb_object()

    batteries: Mapped[list[Battery]] = relationship(
        back_populates="dataset", cascade="all, delete-orphan", passive_deletes=True
    )


class Battery(TimestampMixin, Base):
    __tablename__ = "batteries"
    __table_args__ = (
        UniqueConstraint("dataset_id", "external_id"),
        CheckConstraint("nominal_capacity_ah > 0", name="nominal_capacity_positive"),
        CheckConstraint("eol_threshold_pct > 0 AND eol_threshold_pct < 100", name="eol_range"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    dataset_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    external_id: Mapped[str] = mapped_column(String(64), nullable=False)
    chemistry: Mapped[str | None] = mapped_column(String(32))
    form_factor: Mapped[str | None] = mapped_column(String(32))
    nominal_capacity_ah: Mapped[float] = mapped_column(Double, nullable=False)
    nominal_voltage_v: Mapped[float | None] = mapped_column(Double)
    eol_threshold_pct: Mapped[float] = mapped_column(
        Double, nullable=False, default=80.0, server_default=text("80")
    )
    test_conditions: Mapped[dict[str, Any]] = _jsonb_object()
    is_synthetic: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    #: SHA-256 of the cycle data (see app.db.seed.cycles_checksum); identifies a data version.
    cycles_checksum: Mapped[str | None] = mapped_column(String(64))

    dataset: Mapped[Dataset] = relationship(back_populates="batteries")
    cycles: Mapped[list[Cycle]] = relationship(
        back_populates="battery", cascade="all, delete-orphan", passive_deletes=True
    )
    scenarios: Mapped[list[Scenario]] = relationship(
        back_populates="battery", cascade="all, delete-orphan", passive_deletes=True
    )


class Cycle(CreatedAtMixin, Base):
    __tablename__ = "cycles"
    __table_args__ = (
        UniqueConstraint("battery_id", "cycle_index", "cycle_type"),
        CheckConstraint("cycle_index >= 0", name="cycle_index_non_negative"),
        CheckConstraint("capacity_ah >= 0", name="capacity_non_negative"),
        CheckConstraint(_in("cycle_type", CYCLE_TYPES), name="cycle_type"),
        Index("ix_cycles_start_time", "start_time", postgresql_using="brin"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=False), primary_key=True)
    battery_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("batteries.id", ondelete="CASCADE"), nullable=False
    )
    cycle_index: Mapped[int] = mapped_column(Integer, nullable=False)
    cycle_type: Mapped[str] = mapped_column(
        String(16), nullable=False, default="discharge", server_default="discharge"
    )
    start_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # v1 analysis inputs
    capacity_ah: Mapped[float] = mapped_column(Double, nullable=False)
    soh_pct: Mapped[float] = mapped_column(Double, nullable=False)
    temp_mean_c: Mapped[float] = mapped_column(Double, nullable=False)
    voltage_mean_v: Mapped[float] = mapped_column(Double, nullable=False)
    # Optional measurements for real datasets (Phase 6)
    temp_min_c: Mapped[float | None] = mapped_column(Double)
    temp_max_c: Mapped[float | None] = mapped_column(Double)
    voltage_min_v: Mapped[float | None] = mapped_column(Double)
    voltage_max_v: Mapped[float | None] = mapped_column(Double)
    current_mean_a: Mapped[float | None] = mapped_column(Double)
    energy_wh: Mapped[float | None] = mapped_column(Double)
    charge_time_s: Mapped[float | None] = mapped_column(Double)
    discharge_time_s: Mapped[float | None] = mapped_column(Double)
    internal_resistance_ohm: Mapped[float | None] = mapped_column(Double)
    ambient_temp_c: Mapped[float | None] = mapped_column(Double)
    c_rate: Mapped[float | None] = mapped_column(Double)
    dod_pct: Mapped[float | None] = mapped_column(Double)
    quality_flags: Mapped[dict[str, Any]] = _jsonb_object()

    battery: Mapped[Battery] = relationship(back_populates="cycles")


class Scenario(TimestampMixin, Base):
    __tablename__ = "scenarios"
    __table_args__ = (CheckConstraint("length(btrim(name)) > 0", name="name_not_blank"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    battery_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("batteries.id", ondelete="CASCADE"), nullable=False, index=True
    )
    #: Owner; becomes a foreign key when the users table arrives (Phase 9).
    user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    name: Mapped[str] = mapped_column(String(60), nullable=False)
    params: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    simulator_version: Mapped[str] = mapped_column(
        String(16), nullable=False, default="v1", server_default="v1"
    )

    battery: Mapped[Battery] = relationship(back_populates="scenarios")
