"""Real-dataset provenance (Phase 6 M3): dataset_files and provenance columns.

Additive only. Every new column is nullable without a default, so existing rows (the
synthetic-v1 dataset, battery and cycles) keep exactly their current values; the NOT NULL
analysis inputs of ``cycles`` are unchanged (relaxing them is a later milestone, D3).

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-15 18:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("datasets", sa.Column("publisher", sa.Text(), nullable=True))
    op.add_column("datasets", sa.Column("landing_url", sa.Text(), nullable=True))
    op.add_column("datasets", sa.Column("doi", sa.String(length=128), nullable=True))

    op.add_column("batteries", sa.Column("chemistry_basis", sa.String(length=32), nullable=True))
    op.add_column("batteries", sa.Column("soh_reference", sa.String(length=32), nullable=True))
    op.add_column("batteries", sa.Column("soh_reference_capacity_ah", sa.Double(), nullable=True))
    op.add_column("batteries", sa.Column("first_capacity_ah", sa.Double(), nullable=True))
    op.add_column("batteries", sa.Column("first_capacity_cycle_index", sa.Integer(), nullable=True))
    op.create_check_constraint(
        op.f("ck_batteries_chemistry_basis"),
        "batteries",
        "chemistry_basis IN ('stated_by_source', 'not_stated')",
    )
    op.create_check_constraint(
        op.f("ck_batteries_soh_reference"), "batteries", "soh_reference IN ('rated_capacity')"
    )
    op.create_check_constraint(
        op.f("ck_batteries_soh_reference_capacity_positive"),
        "batteries",
        "soh_reference_capacity_ah IS NULL OR soh_reference_capacity_ah > 0",
    )
    op.create_check_constraint(
        op.f("ck_batteries_first_capacity_non_negative"),
        "batteries",
        "first_capacity_ah IS NULL OR first_capacity_ah >= 0",
    )

    op.add_column("cycles", sa.Column("source_cycle_index", sa.Integer(), nullable=True))

    op.create_table(
        "dataset_files",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("dataset_id", sa.Uuid(), nullable=False),
        sa.Column("battery_id", sa.Uuid(), nullable=True),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("path", sa.Text(), nullable=False),
        sa.Column("format", sa.String(length=16), nullable=False),
        sa.Column("bytes", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("rows", sa.BigInteger(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("bytes >= 0", name=op.f("ck_dataset_files_bytes_non_negative")),
        sa.CheckConstraint(
            "format IN ('zip', 'parquet', 'json', 'mat', 'xlsx')",
            name=op.f("ck_dataset_files_format"),
        ),
        sa.CheckConstraint(
            "kind IN ('raw', 'bundle_manifest', 'batteries', 'cycles', 'samples', 'impedance', "
            "'report')",
            name=op.f("ck_dataset_files_kind"),
        ),
        sa.CheckConstraint(
            "path NOT LIKE '/%' AND path NOT LIKE '%..%'",
            name=op.f("ck_dataset_files_path_relative"),
        ),
        sa.CheckConstraint("sha256 ~ '^[0-9a-f]{64}$'", name=op.f("ck_dataset_files_sha256_hex")),
        sa.ForeignKeyConstraint(
            ["battery_id"],
            ["batteries.id"],
            name=op.f("fk_dataset_files_battery_id_batteries"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["dataset_id"],
            ["datasets.id"],
            name=op.f("fk_dataset_files_dataset_id_datasets"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_dataset_files")),
        sa.UniqueConstraint("dataset_id", "path", name=op.f("uq_dataset_files_dataset_id_path")),
    )
    op.create_index(
        op.f("ix_dataset_files_battery_id"), "dataset_files", ["battery_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_dataset_files_battery_id"), table_name="dataset_files")
    op.drop_table("dataset_files")
    op.drop_column("cycles", "source_cycle_index")
    for name in (
        "first_capacity_non_negative",
        "soh_reference_capacity_positive",
        "soh_reference",
        "chemistry_basis",
    ):
        op.drop_constraint(op.f(f"ck_batteries_{name}"), "batteries", type_="check")
    for column in (
        "first_capacity_cycle_index",
        "first_capacity_ah",
        "soh_reference_capacity_ah",
        "soh_reference",
        "chemistry_basis",
    ):
        op.drop_column("batteries", column)
    for column in ("doi", "landing_url", "publisher"):
        op.drop_column("datasets", column)
