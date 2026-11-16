"""Sample-level data of one cycle, read from the imported bundle's Parquet files (decision E).

Samples are not stored in PostgreSQL. The importer records every bundle file in
``dataset_files`` (path relative to ``VOLTERRA_DATA_DIR``, SHA-256), so the API reads them
from there. Long series are downsampled deterministically for charts: evenly spaced positions
that always keep the first and the last sample. Values are copied, never interpolated; a
non-finite source value (NaN) is returned as null, which JSON can represent.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pyarrow.compute as pc
import pyarrow.parquet as pq

#: Core sample columns shared by every canonical bundle (canonical schema, SAMPLE_COLUMNS).
SAMPLE_FIELDS = ("time_s", "voltage_v", "current_a", "temp_c")
DEFAULT_MAX_POINTS = 2000
MAX_POINTS_LIMIT = 20000


class SamplesUnavailableError(Exception):
    """The battery's sample files are not readable here (no data directory, file missing)."""


@dataclass(frozen=True)
class CycleSamples:
    cycle_types: tuple[str, ...]
    total: int
    #: Position of each returned sample in the full, time-ordered series.
    positions: tuple[int, ...]
    values: dict[str, tuple[float | None, ...]]

    @property
    def downsampled(self) -> bool:
        return len(self.positions) < self.total


def downsample_positions(n: int, max_points: int) -> list[int]:
    """Evenly spaced positions in ``range(n)``; keeps 0 and ``n - 1``; all if ``n <= max``."""
    if max_points < 2:
        raise ValueError("max_points must be at least 2")
    if n <= max_points:
        return list(range(n))
    return [(i * (n - 1)) // (max_points - 1) for i in range(max_points)]


def read_cycle_samples(
    data_dir: Path,
    files: Sequence[str],
    *,
    cycle_index: int,
    source_cycle_index: int | None,
    max_points: int,
) -> CycleSamples:
    """Samples of canonical cycle ``cycle_index`` from a battery's sample files.

    ``files`` are paths relative to ``data_dir`` as recorded in ``dataset_files``.

    Bundles with a ``canonical_cycle_index`` column (CALCE, Severson) are filtered on it; the
    NASA bundle links discharge samples through ``source_cycle_index``.
    """
    tables = []
    for rel in files:
        path = data_dir / rel
        if not path.is_file():
            raise SamplesUnavailableError(f"sample file not found: {path.name}")
        names = pq.read_schema(path).names
        if "canonical_cycle_index" in names:
            flt: Any = pc.field("canonical_cycle_index") == cycle_index
        elif source_cycle_index is not None:
            flt = (pc.field("cycle_type") == "discharge") & (
                pc.field("source_cycle_index") == source_cycle_index
            )
        else:
            continue
        table = pq.read_table(
            path, columns=["cycle_type", "sample_index", *SAMPLE_FIELDS], filters=flt
        )
        if table.num_rows:
            tables.append(table.sort_by("sample_index"))
    if not tables:
        return CycleSamples((), 0, (), {f: () for f in SAMPLE_FIELDS})
    rows: dict[str, list[Any]] = {f: [] for f in ("cycle_type", *SAMPLE_FIELDS)}
    for table in tables:
        for name in rows:
            rows[name].extend(table.column(name).to_pylist())
    total = len(rows["time_s"])
    keep = downsample_positions(total, max_points)
    return CycleSamples(
        cycle_types=tuple(dict.fromkeys(rows["cycle_type"])),
        total=total,
        positions=tuple(keep),
        values={f: tuple(_finite_or_none(rows[f][i]) for i in keep) for f in SAMPLE_FIELDS},
    )


def _finite_or_none(value: float | None) -> float | None:
    return value if value is not None and math.isfinite(value) else None
