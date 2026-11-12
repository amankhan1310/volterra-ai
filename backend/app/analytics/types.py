"""Shared types for analytics results."""

from __future__ import annotations

from typing import Literal

#: Where a value comes from. Every value surfaced to users carries one (ARCHITECTURE_PLAN §6.3).
Provenance = Literal["measured", "simulated", "fitted", "predicted", "assumed"]
