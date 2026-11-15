"""Cycle source reference (Phase 6 M4, canonical schema v2): cycles.source_ref.

Additive only: one nullable JSONB column holding the canonical bundle's ``source_ref_json``
(where each cycle comes from: archive member, worksheet rows or batch entry). Existing rows keep
null. ``internal_resistance_ohm`` and ``charge_time_s`` already exist in ``cycles`` (0001).

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-16 12:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "cycles",
        sa.Column("source_ref", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("cycles", "source_ref")
