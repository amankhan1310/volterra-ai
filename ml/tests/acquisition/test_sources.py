"""The registry must carry complete, honest provenance for every real dataset."""

from __future__ import annotations

import re
from typing import Any

import pytest

from volterra_ml.acquisition.sources import (
    CALCE,
    NASA_PCOE,
    REGISTRY,
    SEVERSON,
    DatasetSpec,
    Licence,
    RemoteFile,
    get,
)

BACKEND_SOURCES = {"nasa_pcoe", "calce", "severson", "upload", "synthetic"}


def test_three_planned_datasets_in_order():
    assert list(REGISTRY) == ["nasa-pcoe-battery", "calce-cs2-cx2", "severson-2019"]
    assert get("calce-cs2-cx2") is CALCE
    with pytest.raises(KeyError, match="unknown dataset 'x'"):
        get("x")


@pytest.mark.parametrize("spec", list(REGISTRY.values()), ids=list(REGISTRY))
def test_every_dataset_has_complete_provenance(spec: DatasetSpec):
    assert spec.source in BACKEND_SOURCES - {"upload", "synthetic"}
    assert spec.is_synthetic is False
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", spec.version)
    assert spec.landing_url.startswith("https://")
    assert spec.citation and spec.publisher and spec.description
    assert spec.licence.statement and spec.licence.usage_requirements
    for f in spec.files:
        assert f.url.startswith("https://") and f.description


def test_chemistry_is_recorded_only_where_the_publisher_states_it():
    assert NASA_PCOE.chemistry_stated is None  # NASA says "Li-ion 18650" only
    assert CALCE.chemistry_stated is not None and "LiCoO2" in CALCE.chemistry_stated
    assert SEVERSON.chemistry_stated is not None and "LiFePO4" in SEVERSON.chemistry_stated


def test_licences_are_recorded_as_published_not_guessed():
    # NASA: the catalogue record says "License not specified".
    assert NASA_PCOE.licence.status == "not_stated"
    assert NASA_PCOE.licence.redistribution_permitted is False
    # CALCE: "All Rights Reserved" plus a citation requirement.
    assert CALCE.licence.status == "all_rights_reserved"
    assert CALCE.licence.redistribution_permitted is False
    # Severson: data.matr.io releases all data under CC BY 4.0 (attribution required).
    assert SEVERSON.licence.status == "cc_by_4_0"
    assert SEVERSON.licence.redistribution_permitted is True
    assert "creativecommons.org/licenses/by/4.0" in SEVERSON.licence.statement
    assert "credit" in SEVERSON.licence.usage_requirements


def test_selected_files():
    assert [f.name for f in NASA_PCOE.files] == ["5_Battery_Data_Set.zip"]
    assert [f.name for f in CALCE.files] == [
        f"{lot}_{n}.zip" for lot in ("CS2", "CX2") for n in range(33, 39)
    ]
    assert len(SEVERSON.files) == 3
    assert SEVERSON.doi == "10.1038/s41560-019-0356-8"


def test_pins_when_present_are_well_formed():
    for spec in REGISTRY.values():
        for f in spec.files:
            assert (f.bytes is None) == (f.sha256 is None), f"{f.name}: pin both or neither"


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"name": "../evil.zip"}, "unsafe raw file name"),
        ({"name": "a b.zip"}, "unsafe raw file name"),
        ({"name": ".hidden"}, "unsafe raw file name"),
        ({"url": "http://insecure/x"}, "must use https"),
        ({"bytes": 0}, "must be positive"),
        ({"sha256": "ABC"}, "64 lowercase hex"),
    ],
)
def test_remote_file_validation(kwargs, message):
    base = {"name": "a.zip", "url": "https://x/a.zip", "description": "d"}
    with pytest.raises(ValueError, match=message):
        RemoteFile(**{**base, **kwargs})


def test_dataset_spec_validation():
    lic = Licence("not_stated", "s", False, "u")
    f = RemoteFile("a.zip", "https://x/a.zip", "d")
    common: dict[str, Any] = dict(
        source="calce", name="n", version="2000-01-01", publisher="p",
        landing_url="https://x", citation="c", doi=None, licence=lic,
        chemistry_stated=None, description="d",
    )  # fmt: skip
    with pytest.raises(ValueError, match="unsafe dataset slug"):
        DatasetSpec(slug="../x", files=(f,), **common)
    with pytest.raises(ValueError, match="no files"):
        DatasetSpec(slug="x", files=(), **common)
    with pytest.raises(ValueError, match="duplicate"):
        DatasetSpec(slug="x", files=(f, f), **common)
    with pytest.raises(ValueError, match="real data only"):
        DatasetSpec(slug="x", files=(f,), is_synthetic=True, **common)
    with pytest.raises(KeyError, match="has no file"):
        DatasetSpec(slug="x", files=(f,), **common).file("b.zip")
