"""Initial schema: datasets, batteries, cycles and scenarios (Phase 3).

Reviewed by hand after autogenerate. Numeric measurements are DOUBLE PRECISION for exact
IEEE-754 round trips; constraint names follow app.db.base.NAMING_CONVENTION.

Revision ID: 0001
Revises: (none)
Create Date: 2026-11-12 23:10:02.627411
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "datasets",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("slug", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("version", sa.String(length=32), nullable=False),
        sa.Column("licence", sa.Text(), nullable=True),
        sa.Column("citation", sa.Text(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=16), server_default="registered", nullable=False),
        sa.Column("checksum", sa.String(length=64), nullable=True),
        sa.Column(
            "meta",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "source IN ('nasa_pcoe', 'calce', 'severson', 'upload', 'synthetic')",
            name=op.f("ck_datasets_source"),
        ),
        sa.CheckConstraint(
            "status IN ('registered', 'importing', 'ready', 'failed')",
            name=op.f("ck_datasets_status"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_datasets")),
        sa.UniqueConstraint("slug", name=op.f("uq_datasets_slug")),
    )
    op.create_table(
        "batteries",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("dataset_id", sa.Uuid(), nullable=False),
        sa.Column("external_id", sa.String(length=64), nullable=False),
        sa.Column("chemistry", sa.String(length=32), nullable=True),
        sa.Column("form_factor", sa.String(length=32), nullable=True),
        sa.Column("nominal_capacity_ah", sa.Double(), nullable=False),
        sa.Column("nominal_voltage_v", sa.Double(), nullable=True),
        sa.Column("eol_threshold_pct", sa.Double(), server_default=sa.text("80"), nullable=False),
        sa.Column(
            "test_conditions",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("is_synthetic", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("cycles_checksum", sa.String(length=64), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "eol_threshold_pct > 0 AND eol_threshold_pct < 100", name=op.f("ck_batteries_eol_range")
        ),
        sa.CheckConstraint(
            "nominal_capacity_ah > 0", name=op.f("ck_batteries_nominal_capacity_positive")
        ),
        sa.ForeignKeyConstraint(
            ["dataset_id"],
            ["datasets.id"],
            name=op.f("fk_batteries_dataset_id_datasets"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_batteries")),
        sa.UniqueConstraint(
            "dataset_id", "external_id", name=op.f("uq_batteries_dataset_id_external_id")
        ),
    )
    op.create_index(op.f("ix_batteries_dataset_id"), "batteries", ["dataset_id"], unique=False)
    op.create_table(
        "cycles",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("battery_id", sa.Uuid(), nullable=False),
        sa.Column("cycle_index", sa.Integer(), nullable=False),
        sa.Column("cycle_type", sa.String(length=16), server_default="discharge", nullable=False),
        sa.Column("start_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("capacity_ah", sa.Double(), nullable=False),
        sa.Column("soh_pct", sa.Double(), nullable=False),
        sa.Column("temp_mean_c", sa.Double(), nullable=False),
        sa.Column("voltage_mean_v", sa.Double(), nullable=False),
        sa.Column("temp_min_c", sa.Double(), nullable=True),
        sa.Column("temp_max_c", sa.Double(), nullable=True),
        sa.Column("voltage_min_v", sa.Double(), nullable=True),
        sa.Column("voltage_max_v", sa.Double(), nullable=True),
        sa.Column("current_mean_a", sa.Double(), nullable=True),
        sa.Column("energy_wh", sa.Double(), nullable=True),
        sa.Column("charge_time_s", sa.Double(), nullable=True),
        sa.Column("discharge_time_s", sa.Double(), nullable=True),
        sa.Column("internal_resistance_ohm", sa.Double(), nullable=True),
        sa.Column("ambient_temp_c", sa.Double(), nullable=True),
        sa.Column("c_rate", sa.Double(), nullable=True),
        sa.Column("dod_pct", sa.Double(), nullable=True),
        sa.Column(
            "quality_flags",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "cycle_type IN ('charge', 'discharge', 'impedance', 'full')",
            name=op.f("ck_cycles_cycle_type"),
        ),
        sa.CheckConstraint("capacity_ah >= 0", name=op.f("ck_cycles_capacity_non_negative")),
        sa.CheckConstraint("cycle_index >= 0", name=op.f("ck_cycles_cycle_index_non_negative")),
        sa.ForeignKeyConstraint(
            ["battery_id"],
            ["batteries.id"],
            name=op.f("fk_cycles_battery_id_batteries"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_cycles")),
        sa.UniqueConstraint(
            "battery_id",
            "cycle_index",
            "cycle_type",
            name=op.f("uq_cycles_battery_id_cycle_index_cycle_type"),
        ),
    )
    op.create_index(
        "ix_cycles_start_time", "cycles", ["start_time"], unique=False, postgresql_using="brin"
    )
    op.create_table(
        "scenarios",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("battery_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("name", sa.String(length=60), nullable=False),
        sa.Column("params", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("simulator_version", sa.String(length=16), server_default="v1", nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("length(btrim(name)) > 0", name=op.f("ck_scenarios_name_not_blank")),
        sa.ForeignKeyConstraint(
            ["battery_id"],
            ["batteries.id"],
            name=op.f("fk_scenarios_battery_id_batteries"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_scenarios")),
    )
    op.create_index(op.f("ix_scenarios_battery_id"), "scenarios", ["battery_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_scenarios_battery_id"), table_name="scenarios")
    op.drop_table("scenarios")
    op.drop_index("ix_cycles_start_time", table_name="cycles", postgresql_using="brin")
    op.drop_table("cycles")
    op.drop_index(op.f("ix_batteries_dataset_id"), table_name="batteries")
    op.drop_table("batteries")
    op.drop_table("datasets")
