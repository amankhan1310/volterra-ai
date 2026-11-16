"""ML runs and RUL predictions (Phase 7): ``ml_models`` and ``ml_predictions``.

Additive: two new tables, nothing existing changes. The downgrade drops only these tables
(imported model evaluations and predictions, which can be re-imported from their run directory).

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-16 20:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ml_models",
        sa.Column("id", sa.Uuid(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("run_id", sa.String(length=32), nullable=False),
        sa.Column("task", sa.String(length=64), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("selected_model", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("trained_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("artifact_sha256", sa.String(length=64), nullable=True),
        sa.Column("metrics", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("run_meta", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "artifact_sha256 IS NULL OR artifact_sha256 ~ '^[0-9a-f]{64}$'",
            name=op.f("ck_ml_models_sha256_hex"),
        ),
        sa.CheckConstraint("kind IN ('rul', 'forecast', 'soh')", name=op.f("ck_ml_models_kind")),
        sa.CheckConstraint("status IN ('experimental')", name=op.f("ck_ml_models_status")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ml_models")),
        sa.UniqueConstraint("run_id", "task", name=op.f("uq_ml_models_run_id_task")),
    )
    op.create_index(op.f("ix_ml_models_run_id"), "ml_models", ["run_id"], unique=False)
    op.create_table(
        "ml_predictions",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("model_id", sa.Uuid(), nullable=False),
        sa.Column("battery_id", sa.Uuid(), nullable=False),
        sa.Column("split", sa.String(length=16), nullable=False),
        sa.Column("interval_basis", sa.String(length=16), nullable=False),
        sa.Column("cycle_index", sa.Integer(), nullable=False),
        sa.Column("soh_pct", sa.Double(), nullable=False),
        sa.Column("rul", sa.Double(), nullable=False),
        sa.Column("lower_rul", sa.Double(), nullable=False),
        sa.Column("upper_rul", sa.Double(), nullable=False),
        sa.Column("actual_rul", sa.Double(), nullable=True),
        sa.Column("past_eol", sa.Boolean(), nullable=False),
        sa.Column("eol_cycle", sa.Double(), nullable=True),
        sa.Column("censored", sa.Boolean(), nullable=False),
        sa.CheckConstraint(
            "interval_basis IN ('dataset', 'pooled')",
            name=op.f("ck_ml_predictions_interval_basis"),
        ),
        sa.CheckConstraint(
            "lower_rul <= rul AND rul <= upper_rul", name=op.f("ck_ml_predictions_interval_ordered")
        ),
        sa.CheckConstraint(
            "rul >= 0 AND lower_rul >= 0", name=op.f("ck_ml_predictions_rul_non_negative")
        ),
        sa.CheckConstraint(
            "split IN ('train', 'calibration', 'test')", name=op.f("ck_ml_predictions_split")
        ),
        sa.ForeignKeyConstraint(
            ["battery_id"],
            ["batteries.id"],
            name=op.f("fk_ml_predictions_battery_id_batteries"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["model_id"],
            ["ml_models.id"],
            name=op.f("fk_ml_predictions_model_id_ml_models"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ml_predictions")),
        sa.UniqueConstraint(
            "model_id",
            "battery_id",
            "cycle_index",
            name=op.f("uq_ml_predictions_model_id_battery_id_cycle_index"),
        ),
    )
    op.create_index(
        op.f("ix_ml_predictions_battery_id"), "ml_predictions", ["battery_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_ml_predictions_battery_id"), table_name="ml_predictions")
    op.drop_table("ml_predictions")
    op.drop_index(op.f("ix_ml_models_run_id"), table_name="ml_models")
    op.drop_table("ml_models")
