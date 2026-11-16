"""EOL labels and censoring on the real Severson and NASA bundles (local only; skipped in CI).

Pins the facts verified during Phase 7: the source cycle life matches the per-cycle records
(joined cells included), the threshold rule agrees exactly where it applies, and the cells it
misses end at 80.0-80.3 % SOH because the tester stopped them at its own EOL trigger.
"""

from __future__ import annotations

import pytest

from volterra_ml.acquisition.cli import default_data_dir
from volterra_ml.acquisition.sources import NASA_PCOE, SEVERSON
from volterra_ml.modeling.data import load_bundle
from volterra_ml.modeling.targets import eol_cycle, starts_below_eol, threshold_eol_cycle

SEV = default_data_dir() / "processed" / SEVERSON.slug / SEVERSON.version
NAS = default_data_dir() / "processed" / NASA_PCOE.slug / NASA_PCOE.version
pytestmark = [
    pytest.mark.realdata,
    pytest.mark.skipif(
        not ((SEV / "bundle_manifest.json").is_file() and (NAS / "bundle_manifest.json").is_file()),
        reason="processed Severson/NASA bundles not found",
    ),
]

JOINED = {"b1c0": 1852.0, "b1c1": 2160.0, "b1c2": 2237.0, "b1c3": 1434.0, "b1c4": 1709.0}


def test_severson_labels_cover_every_usable_cell_and_agree_with_the_rule() -> None:
    cells = [c for c in load_bundle(SEV).cells if c.excluded is None]
    assert len(cells) == 124
    agree = missed = 0
    for cell in cells:
        assert cell.reported_cycle_life is not None
        label = eol_cycle(cell)
        assert label == min(cell.reported_cycle_life - 1, float(cell.cycle[-1]))
        rule = threshold_eol_cycle(cell)
        if rule is None:
            missed += 1
            assert 80.0 <= float(cell.soh[-1]) <= 80.31
            assert cell.reported_cycle_life - 1 >= float(cell.cycle[-1])  # stopped at its EOL
        else:
            agree += 1
            assert rule == label
    assert (agree, missed) == (43, 81)


def test_joined_cells_use_the_joined_life_and_reach_eol_at_their_last_record() -> None:
    cells = {c.external_id: c for c in load_bundle(SEV).cells}
    for eid, life in JOINED.items():
        cell = cells[eid]
        assert cell.reported_cycle_life == life
        assert float(cell.cycle[-1]) == life - 2  # records 0..life-2; cycle 0 placeholder dropped
        assert eol_cycle(cell) == cell.cycle[-1]


def test_nasa_censoring_and_cells_starting_below_eol() -> None:
    cells = [c for c in load_bundle(NAS).cells if len(c) > 10]
    censored = sorted(
        c.external_id for c in cells if not starts_below_eol(c) and eol_cycle(c) is None
    )
    assert censored == ["B0025", "B0026", "B0027", "B0028", "B0029", "B0031", "B0032"]
    assert sum(starts_below_eol(c) for c in cells) == 16
