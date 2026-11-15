"""Builders for NASA-style raw archives (generated values, never real data)."""

from __future__ import annotations

import io
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pytest
import scipy.io

from volterra_ml.acquisition import manifest as mf
from volterra_ml.acquisition.fetch import Fetcher
from volterra_ml.acquisition.sources import DatasetSpec, Licence, RemoteFile

ARCHIVE_NAME = "5_Battery_Data_Set.zip"
_DT = [("type", "O"), ("ambient_temperature", "O"), ("time", "O"), ("data", "O")]


def row(values: Any) -> np.ndarray:
    return np.asarray(values, dtype=float).reshape(1, -1)


def discharge(
    n: int = 5,
    capacity: Any = 1.8,
    ambient: float = 24.0,
    *,
    voltage: Any = None,
    temp: Any = None,
    time: Any = None,
    current: Any = None,
) -> dict[str, Any]:
    v = np.linspace(4.2, 2.7, n) if voltage is None else voltage
    data = {
        "Voltage_measured": row(v),
        "Current_measured": row(np.full(n, -2.0) if current is None else current),
        "Temperature_measured": row(np.linspace(24.5, 34.25, n) if temp is None else temp),
        "Current_load": row(np.full(n, -1.998)),
        "Voltage_load": row(np.linspace(4.1, 2.6, n)),
        "Time": row(np.arange(n) * 9.375 if time is None else time),
        "Capacity": np.zeros((0, 0)) if capacity is None else np.asarray([[capacity]]),
    }
    return {"type": "discharge", "ambient": ambient, "data": data}


def charge(n: int = 4) -> dict[str, Any]:
    data = {
        "Voltage_measured": row(np.linspace(3.5, 4.2, n)),
        "Current_measured": row(np.full(n, 1.5)),
        "Temperature_measured": row(np.linspace(25.0, 27.0, n)),
        "Current_charge": row(np.full(n, 1.49)),
        "Voltage_charge": row(np.linspace(3.6, 4.3, n)),
        "Time": row(np.arange(n) * 2.5),
    }
    return {"type": "charge", "ambient": 24.0, "data": data}


def impedance(re: complex = 0.0446, rct: complex = 0.0694) -> dict[str, Any]:
    data = {
        "Sense_current": np.asarray([[1 + 1j, 2 + 0j]]),
        "Battery_current": np.asarray([[1 + 1j, 2 + 0j]]),
        "Current_ratio": np.asarray([[1 + 0j, 1 + 0j]]),
        "Battery_impedance": np.asarray([[0.25 - 0.125j], [0.5 + 0.0625j]]),
        "Rectified_Impedance": np.asarray([[0.0625 - 0.25j]]),
        "Re": np.asarray([[re]]),
        "Rct": np.asarray([[rct]]),
    }
    return {"type": "impedance", "ambient": 24.0, "data": data}


def mat_bytes(name: str, cycles: list[dict[str, Any]], *, struct_name: str | None = None) -> bytes:
    arr = np.zeros((1, len(cycles)), dtype=_DT)
    for k, c in enumerate(cycles):
        arr[0, k] = (
            c["type"],
            np.asarray([[c["ambient"]]]),
            row([2008, 4, 2, 13, 8 + k, 17.921]),
            c["data"],
        )
    buf = io.BytesIO()
    scipy.io.savemat(buf, {struct_name or name: {"cycle": arr}})
    return buf.getvalue()


def readme(cells: list[str]) -> bytes:
    files = "\n".join(f"{c}.mat Data for Battery #{int(c[1:])}" for c in cells)
    return (
        "Data Description:\nTest cells (generated) run at room temperature (24 deg C).\n\n"
        f"Files:\n{files}\n"
    ).encode("latin-1")


def archive_bytes(groups: dict[str, dict[str, bytes]]) -> bytes:
    outer = io.BytesIO()
    with zipfile.ZipFile(outer, "w") as z:
        for group, members in groups.items():
            inner = io.BytesIO()
            with zipfile.ZipFile(inner, "w") as iz:
                for member, data in members.items():
                    iz.writestr(member, data)
            z.writestr(f"5. Battery Data Set/{group}", inner.getvalue())
    return outer.getvalue()


def nasa_spec(slug: str = "nasa-test") -> DatasetSpec:
    return DatasetSpec(
        slug=slug,
        source="nasa_pcoe",
        name="NASA-style test archive (generated values, not real data)",
        version="2000-01-01",
        publisher="tests",
        landing_url="https://example.invalid/",
        citation="test citation",
        doi=None,
        licence=Licence("not_stated", "test", False, "none"),
        chemistry_stated=None,
        description="generated",
        files=(RemoteFile(ARCHIVE_NAME, "https://example.invalid/a.zip", "test archive"),),
    )


@dataclass
class NasaEnv:
    data: Path
    spec: DatasetSpec

    @property
    def raw(self) -> Path:
        return self.data / "raw"

    @property
    def processed(self) -> Path:
        return self.data / "processed"

    @property
    def bundle(self) -> Path:
        return self.processed / self.spec.slug / self.spec.version

    def install(self, groups: dict[str, dict[str, bytes]]) -> None:
        """Acquire the archive exactly as the real tool does (manifest, read-only)."""
        manual = self.data / "manual"
        manual.mkdir(parents=True, exist_ok=True)
        (manual / ARCHIVE_NAME).write_bytes(archive_bytes(groups))
        directory = mf.dataset_dir(self.raw, self.spec)
        record = Fetcher(progress=None).copy_local(self.spec.files[0], manual, directory)
        m = mf.Manifest.for_spec(self.spec)
        m.files[record.name] = record
        mf.save(directory, m)


@pytest.fixture
def nasa(tmp_path: Path) -> NasaEnv:
    return NasaEnv(tmp_path / "data", nasa_spec())


def standard_groups() -> dict[str, dict[str, bytes]]:
    """Two groups; B0025 is duplicated byte for byte, like the real archive."""
    b5 = mat_bytes(
        "B0005",
        [charge(), discharge(capacity=1.8564874208181574), impedance(), discharge(capacity=1.75)],
    )
    b25 = mat_bytes("B0025", [discharge(capacity=1.9), charge(), discharge(capacity=1.85)])
    return {
        "1. Group_A.zip": {"B0005.mat": b5, "README.txt": readme(["B0005"])},
        "2. Group_B.zip": {"B0025.mat": b25, "README.txt": readme(["B0025"])},
        "3. Group_C.zip": {"B0025.mat": b25, "README_25.txt": readme(["B0025"])},
    }
