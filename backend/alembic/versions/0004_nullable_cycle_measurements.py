"""Nullable cycle temperature and voltage (Phase 6 M5, decision D3).

Real datasets do not always measure every analysis input: the CALCE CS2/CX2 files have no
temperature channel. Missing values stay null instead of being filled in, and the API reports
``missing_measurement`` for analytics that need them. Capacity and SOH stay NOT NULL.

The downgrade restores NOT NULL and therefore refuses to run while any cycle has a null
temperature or voltage (it never deletes data).

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-16 14:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

COLUMNS = ("temp_mean_c", "voltage_mean_v")


def upgrade() -> None:
    for column in COLUMNS:
        op.alter_column("cycles", column, existing_type=sa.Double(), nullable=True)


def downgrade() -> None:
    if not op.get_context().as_sql:
        nulls = op.get_bind().scalar(
            sa.text(
                "SELECT count(*) FROM cycles WHERE temp_mean_c IS NULL OR voltage_mean_v IS NULL"
            )
        )
        if nulls:
            raise RuntimeError(
                f"{nulls} cycles have no temperature or voltage; remove those datasets before "
                "downgrading (this migration never deletes data)"
            )
    for column in COLUMNS:
        op.alter_column("cycles", column, existing_type=sa.Double(), nullable=False)
