"""Registry of the real battery datasets VOLTERRA AI acquires (Phase 6).

Every entry records where the data comes from, how it must be cited and what is known about its
licence. All values were checked against the publishers' own pages on 2026-11-15; see
``docs/datasets/`` for the dataset cards and the evidence behind each statement.

Rules this registry encodes:

* The data is **real experimental data** (``is_synthetic = False``); nothing here is generated.
* Raw files are preserved exactly as published. Size and SHA-256 pins, once observed on a
  verified download, make any later change at the source visible instead of silently accepted.
* **This project never redistributes the data** (approved decision D8): raw and processed data
  stay out of Git and out of any release, whatever the licence allows. ``Licence`` records what
  each publisher actually permits; only Severson's CC BY 4.0 would allow redistribution.
* A licence the publisher does not state is recorded as ``not_stated``, never guessed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

#: Allowed values for ``datasets.source`` in the backend database (``app/db/models.py``).
DatasetSource = Literal["nasa_pcoe", "calce", "severson"]
LicenceStatus = Literal["not_stated", "all_rights_reserved", "cc_by_4_0"]

#: Safe raw file names: no directories, no traversal, no hidden files.
_SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class RemoteFile:
    """One file exactly as the publisher distributes it."""

    name: str
    url: str
    description: str
    #: Size in bytes, pinned from a verified download (``None`` until first retrieval).
    bytes: int | None = None
    #: SHA-256 hex digest, pinned from a verified download (``None`` until first retrieval).
    sha256: str | None = None

    def __post_init__(self) -> None:
        if not _SAFE_NAME.fullmatch(self.name):
            raise ValueError(f"unsafe raw file name: {self.name!r}")
        if not self.url.startswith("https://"):
            raise ValueError(f"{self.name}: source URL must use https")
        if self.bytes is not None and self.bytes <= 0:
            raise ValueError(f"{self.name}: pinned size must be positive")
        if self.sha256 is not None and not _SHA256.fullmatch(self.sha256):
            raise ValueError(f"{self.name}: pinned SHA-256 must be 64 lowercase hex digits")


@dataclass(frozen=True)
class Licence:
    status: LicenceStatus
    #: What the publisher actually says, quoted or summarised from its own pages.
    statement: str
    #: Whether the publisher's licence permits redistribution. This project still never
    #: redistributes data (decision D8); this field records the licence, not the policy.
    redistribution_permitted: bool
    #: Obligations when the data is used (citations, acknowledgements).
    usage_requirements: str


@dataclass(frozen=True)
class DatasetSpec:
    slug: str
    source: DatasetSource
    name: str
    #: Version label: the publisher's release date of the files we pin.
    version: str
    publisher: str
    landing_url: str
    citation: str
    doi: str | None
    licence: Licence
    #: Cell chemistry exactly as the publisher states it, or ``None`` when it is not stated.
    chemistry_stated: str | None
    description: str
    files: tuple[RemoteFile, ...]
    is_synthetic: bool = False

    def __post_init__(self) -> None:
        if not _SAFE_NAME.fullmatch(self.slug):
            raise ValueError(f"unsafe dataset slug: {self.slug!r}")
        if not self.files:
            raise ValueError(f"{self.slug}: no files")
        names = [f.name for f in self.files]
        if len(names) != len(set(names)):
            raise ValueError(f"{self.slug}: duplicate file names")
        if self.is_synthetic:
            raise ValueError(f"{self.slug}: the acquisition registry holds real data only")

    def file(self, name: str) -> RemoteFile:
        for f in self.files:
            if f.name == name:
                return f
        raise KeyError(f"{self.slug} has no file {name!r}")


_NASA_URL = "https://phm-datasets.s3.amazonaws.com/NASA/5.+Battery+Data+Set.zip"

NASA_PCOE = DatasetSpec(
    slug="nasa-pcoe-battery",
    source="nasa_pcoe",
    name="NASA PCoE Li-ion Battery Aging Datasets",
    version="2022-09-18",
    publisher="NASA Ames Research Center, Prognostics Center of Excellence (PCoE)",
    landing_url=(
        "https://www.nasa.gov/intelligent-systems-division/discovery-and-systems-health/"
        "pcoe/pcoe-data-set-repository/"
    ),
    citation=(
        'B. Saha and K. Goebel (2007). "Battery Data Set", NASA Prognostics Data Repository, '
        "NASA Ames Research Center, Moffett Field, CA"
    ),
    doi=None,
    licence=Licence(
        status="not_stated",
        statement=(
            "The data.nasa.gov catalogue record (identifier DASHLINK_133) lists the licence as "
            '"License not specified" with access level "public".'
        ),
        redistribution_permitted=False,
        usage_requirements="Cite the data set as given by the NASA PCoE repository.",
    ),
    chemistry_stated=None,
    description=(
        "Commercial Li-ion 18650 cells (rated 2 Ah) run through charge, discharge and impedance "
        "(EIS) profiles at several ambient temperatures until 30% fade in rated capacity "
        "(2 Ah to 1.4 Ah). MATLAB .mat files inside a zip archive of zip archives. The "
        "publisher does not state the cell chemistry."
    ),
    files=(
        RemoteFile(
            name="5_Battery_Data_Set.zip",
            url=_NASA_URL,
            description=(
                'Complete archive as published as "5. Battery Data Set.zip" (all battery '
                "groups); stored under a name without spaces, content byte-identical."
            ),
            # Pinned from the verified download of 2026-11-15 (Last-Modified 2022-09-18).
            bytes=209_708_670,
            sha256="82302a7db4fc1b34e0b6676326610438d43b816bdf11a69d1d012a464ef2f92e",
        ),
    ),
)

_CALCE_BASE = "https://web.calce.umd.edu/batteries/data/"
_CS2 = "CS2 cell cycled at constant current of {}."
_CX2 = "CX2 cell cycled at a constant current discharge of {}."
_CALCE_CELLS = (
    # (cell, description from the CALCE data page, size and SHA-256 pinned from the verified
    # download of 2026-11-15; the server's Last-Modified dates are all 2015-08-10)
    ("CS2_33", _CS2.format("0.5C"), 45_345_047,
     "ce375e3826e840ff0986ceade0d324ba6515f0446697c947353aca097f232505"),
    ("CS2_34", _CS2.format("0.5C"), 43_836_986,
     "229dcdc836f140f746c26316569c357b346994fddd3be1223b1e457805c484b4"),
    ("CS2_35", _CS2.format("1C"), 37_056_519,
     "84d88cb98a43c02049f16c78806a78ec19084776ea5df8a4b7c2f8f7ba4589e5"),
    ("CS2_36", _CS2.format("1C"), 37_881_685,
     "2e674f58bb6dc005c73bef10e87edbbd97afd041dde77a1d461a3c4ecac1b027"),
    ("CS2_37", _CS2.format("1C"), 41_513_048,
     "8ed8aecbcbea2bcb17f455923a974be01ea21d7389210e1912d177de5b6af4a5"),
    ("CS2_38", _CS2.format("1C"), 42_811_100,
     "98787427c10478425efd4f54d823805724daff1d2fcbd822b3a2d7006a1051d8"),
    ("CX2_33", _CX2.format("0.5C"), 86_700_450,
     "f4dbca063a3731045b8a631f69532f7f43f0b3ada9736c0cfe3e07302d10b5da"),
    ("CX2_34", _CX2.format("1C"), 65_932_032,
     "6e4be14140071843891b6a7395c9561754b45036b17e840bae33d253f615939d"),
    ("CX2_35", _CX2.format("0.5C"), 96_794_651,
     "043e84ccd518f5e00fcee94ae8d2765ffe25fd11a87e028ad6903a8c61a8f15e"),
    ("CX2_36", _CX2.format("1C"), 73_909_895,
     "45b9249cd0353ea0285484868e5a74c54d43c8ed153bf2d40e9376e9a1daf6ad"),
    ("CX2_37", _CX2.format("1C"), 53_311_138,
     "d7989beff30881e1d0d50bc2d7c028e8237ca402004ffcefe693bbce35b9776d"),
    ("CX2_38", _CX2.format("1C"), 69_995_480,
     "2bd64c8cc9ffe4f63664caf9ec51889ca32245c321151a361147755ad6f00e3f"),
)  # fmt: skip

CALCE = DatasetSpec(
    slug="calce-cs2-cx2",
    source="calce",
    name="CALCE CS2 and CX2 prismatic LiCoO2 cells (constant-current cycling)",
    version="2015-08-10",
    publisher="Center for Advanced Life Cycle Engineering (CALCE), University of Maryland",
    landing_url="https://web.calce.umd.edu/batteries/data/",
    citation=(
        "CALCE Battery Research Group, University of Maryland, Battery Data, "
        "https://web.calce.umd.edu/batteries/data.htm"
    ),
    doi=None,
    licence=Licence(
        status="all_rights_reserved",
        statement=(
            'The CALCE data page states "Copyright (c) 2014 by CALCE and the University of '
            'Maryland, All Rights Reserved".'
        ),
        redistribution_permitted=False,
        usage_requirements=(
            '"Usage of this data for publication purposes should include references to the '
            "CALCE battery data base and at least 3 articles referenced by CALCE and/or other "
            'contributors to this data collective."'
        ),
    ),
    chemistry_stated="LiCoO2 cathode (CALCE: EDS also showed trace manganese)",
    description=(
        "Small prismatic cells: CS2 rated 1100 mAh, CX2 rated 1350 mAh. Charged CC 0.5C to "
        "4.2 V then CV until the current fell below 0.05 A; discharged at constant current to "
        "2.7 V. Arbin tester exports (xlsx) inside one zip per cell; file names carry the date "
        "each file was downloaded, which gives their chronological order. The 12 "
        "constant-current cells listed on the CALCE page with xlsx data are selected; the "
        "variable-current, partial-cycle and pulsed tests are not."
    ),
    files=tuple(
        RemoteFile(
            name=f"{cell}.zip",
            url=f"{_CALCE_BASE}{cell}.zip",
            description=desc,
            bytes=size,
            sha256=digest,
        )
        for cell, desc, size, digest in _CALCE_CELLS
    ),
)

_MATR = "https://data.matr.io/1/api/v1/file/{}/download"

SEVERSON = DatasetSpec(
    slug="severson-2019",
    source="severson",
    name="Severson et al. 2019: data-driven prediction of battery cycle life (124 LFP cells)",
    version="2019-03-11",
    publisher="Toyota Research Institute, Stanford University and MIT (hosted on data.matr.io)",
    landing_url="https://data.matr.io/1/projects/5c48dd2bc625d700019f3204",
    citation=(
        "K. A. Severson, P. M. Attia, N. Jin, N. Perkins, B. Jiang, Z. Yang, M. H. Chen, "
        "M. Aykol, P. K. Herring, D. Fraggedakis, M. Z. Bazant, S. J. Harris, W. C. Chueh and "
        'R. D. Braatz, "Data-driven prediction of battery cycle life before capacity '
        'degradation", Nature Energy 4, 383-391 (2019)'
    ),
    doi="10.1038/s41560-019-0356-8",
    licence=Licence(
        status="cc_by_4_0",
        statement=(
            'data.matr.io states on every page "All data is released under CC BY 4", linking '
            "to https://creativecommons.org/licenses/by/4.0/ (platform configuration, "
            "/1/api/v1/edp/configuration, checked 2026-11-15). The paper's Data availability "
            "statement points to https://data.matr.io/1; the authors' code repository licenses "
            "only code (modelling code under an academic licence on request)."
        ),
        redistribution_permitted=True,
        usage_requirements=(
            "CC BY 4.0: give appropriate credit (cite Severson et al., Nature Energy 4, 383-391 "
            "(2019), doi:10.1038/s41560-019-0356-8, and the data.matr.io source), link to the "
            "licence and indicate if changes were made."
        ),
    ),
    chemistry_stated="LiFePO4/graphite (A123 APR18650M1A, 1.1 Ah nominal)",
    description=(
        "124 commercial LFP/graphite 18650 cells cycled to failure under 72 fast-charging "
        "policies in a 30 C chamber, in three batches (as described in the paper). One MATLAB "
        "7.3 (HDF5) .mat file per batch; the internal structure is examined in M2."
    ),
    # Sizes and SHA-256 pinned from the verified download of 2026-11-15; the sizes equal those
    # data.matr.io's file metadata reported before download. Each file is a MATLAB 7.3 MAT-file
    # (HDF5 signature at offset 512).
    files=(
        RemoteFile(
            name="2017-05-12_batchdata_updated_struct_errorcorrect.mat",
            url=_MATR.format("5c86c0b5fa2ede00015ddf66"),
            description="Batch 1 (2017-05-12).",
            bytes=3_025_320_241,
            sha256="9d928ab978f0e3c70b31cb833a749fedd35094d01af76475d69b40aa3497f5ba",
        ),
        RemoteFile(
            name="2017-06-30_batchdata_updated_struct_errorcorrect.mat",
            url=_MATR.format("5c86bf13fa2ede00015ddd82"),
            description="Batch 2 (2017-06-30).",
            bytes=2_007_331_155,
            sha256="63ab200d09ecb237fee5ef3a5c5db76e3212e3206a0bd92f769e1427fed338b8",
        ),
        RemoteFile(
            name="2018-04-12_batchdata_updated_struct_errorcorrect.mat",
            url=_MATR.format("5c86bd64fa2ede00015ddbb2"),
            description="Batch 3 (2018-04-12).",
            bytes=3_236_690_412,
            sha256="62c30e413b63e6144720e016deed3661fac8468641794a5807b123fe84717998",
        ),
    ),
)

REGISTRY: dict[str, DatasetSpec] = {d.slug: d for d in (NASA_PCOE, CALCE, SEVERSON)}


def get(slug: str) -> DatasetSpec:
    try:
        return REGISTRY[slug]
    except KeyError:
        known = ", ".join(sorted(REGISTRY))
        raise KeyError(f"unknown dataset {slug!r}; known: {known}") from None
