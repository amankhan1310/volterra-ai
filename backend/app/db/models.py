"""ORM models: datasets, batteries, cycles and scenarios (Phase 3), dataset files (Phase 6).

Numeric measurements use ``DOUBLE PRECISION`` (IEEE-754 binary64) so values round-trip exactly
between Python, PostgreSQL and the v1 analytics; ``NUMERIC`` would alter the binary value.
``soh_pct`` is stored as produced by the data source rather than computed by the database.
Phase 6 (migration 0002) adds provenance columns and ``dataset_files``; every new column is
nullable, so rows that predate it (the synthetic dataset) are unchanged.
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
CHEMISTRY_BASES = ("stated_by_source", "not_stated")
SOH_REFERENCES = ("rated_capacity",)
FILE_KINDS = ("raw", "bundle_manifest", "batteries", "cycles", "samples", "impedance", "report")
FILE_FORMATS = ("zip", "parquet", "json", "mat", "xlsx")


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
    # Provenance of real datasets (Phase 6); null for the synthetic dataset.
    publisher: Mapped[str | None] = mapped_column(Text)
    landing_url: Mapped[str | None] = mapped_column(Text)
    doi: Mapped[str | None] = mapped_column(String(128))

    batteries: Mapped[list[Battery]] = relationship(
        back_populates="dataset", cascade="all, delete-orphan", passive_deletes=True
    )
    files: Mapped[list[DatasetFile]] = relationship(
        back_populates="dataset", cascade="all, delete-orphan", passive_deletes=True
    )


class Battery(TimestampMixin, Base):
    __tablename__ = "batteries"
    __table_args__ = (
        UniqueConstraint("dataset_id", "external_id"),
        CheckConstraint("nominal_capacity_ah > 0", name="nominal_capacity_positive"),
        CheckConstraint("eol_threshold_pct > 0 AND eol_threshold_pct < 100", name="eol_range"),
        CheckConstraint(_in("chemistry_basis", CHEMISTRY_BASES), name="chemistry_basis"),
        CheckConstraint(_in("soh_reference", SOH_REFERENCES), name="soh_reference"),
        CheckConstraint(
            "soh_reference_capacity_ah IS NULL OR soh_reference_capacity_ah > 0",
            name="soh_reference_capacity_positive",
        ),
        CheckConstraint(
            "first_capacity_ah IS NULL OR first_capacity_ah >= 0",
            name="first_capacity_non_negative",
        ),
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
    # Phase 6: how SOH is referenced (decision D1) and what the chemistry claim rests on.
    chemistry_basis: Mapped[str | None] = mapped_column(String(32))
    soh_reference: Mapped[str | None] = mapped_column(String(32))
    soh_reference_capacity_ah: Mapped[float | None] = mapped_column(Double)
    #: First measured discharge capacity and the cycle it comes from (null if none measured).
    first_capacity_ah: Mapped[float | None] = mapped_column(Double)
    first_capacity_cycle_index: Mapped[int | None] = mapped_column(Integer)

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
    # v1 analysis inputs (temperature and voltage nullable since 0004, decision D3)
    capacity_ah: Mapped[float] = mapped_column(Double, nullable=False)
    soh_pct: Mapped[float] = mapped_column(Double, nullable=False)
    temp_mean_c: Mapped[float | None] = mapped_column(Double)
    voltage_mean_v: Mapped[float | None] = mapped_column(Double)
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
    #: Position of this cycle in the source file's cycle array (Phase 6; null for synthetic).
    source_cycle_index: Mapped[int | None] = mapped_column(Integer)
    #: Where the cycle comes from (canonical schema v2 ``source_ref_json``; migration 0003).
    source_ref: Mapped[dict[str, Any] | None] = mapped_column(JSONB)

    battery: Mapped[Battery] = relationship(back_populates="cycles")


class DatasetFile(CreatedAtMixin, Base):
    """A raw or processed file behind a dataset, identified by path and SHA-256 (Phase 6).

    ``path`` is relative to the data directory (``VOLTERRA_DATA_DIR``) with forward slashes, so
    the database never stores machine-specific absolute paths.
    """

    __tablename__ = "dataset_files"
    __table_args__ = (
        UniqueConstraint("dataset_id", "path"),
        CheckConstraint(_in("kind", FILE_KINDS), name="kind"),
        CheckConstraint(_in("format", FILE_FORMATS), name="format"),
        CheckConstraint("bytes >= 0", name="bytes_non_negative"),
        CheckConstraint("sha256 ~ '^[0-9a-f]{64}$'", name="sha256_hex"),
        CheckConstraint("path NOT LIKE '/%' AND path NOT LIKE '%..%'", name="path_relative"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    dataset_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False
    )
    battery_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("batteries.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    path: Mapped[str] = mapped_column(Text, nullable=False)
    format: Mapped[str] = mapped_column(String(16), nullable=False)
    bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    rows: Mapped[int | None] = mapped_column(BigInteger)

    dataset: Mapped[Dataset] = relationship(back_populates="files")


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
