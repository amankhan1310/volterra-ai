from __future__ import annotations

import io
import runpy
import sys

import pytest

from tests.loaders.conftest import NasaEnv, standard_groups
from volterra_ml.loaders import cli, nasa


@pytest.fixture
def registered(nasa: NasaEnv, monkeypatch: pytest.MonkeyPatch) -> NasaEnv:
    monkeypatch.setitem(cli.LOADERS, nasa.spec.slug, (nasa.spec, nasa_build))
    return nasa


def nasa_build(raw, processed, spec):  # the real builder, with the test spec
    return nasa.build_bundle(raw, processed, spec)


def run(argv: list[str]) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    return cli.main(argv, out=out, err=err), out.getvalue(), err.getvalue()


def test_build_then_verify(registered: NasaEnv):
    registered.install(standard_groups())
    args = [registered.spec.slug, "--data-dir", str(registered.data)]
    code, out, _ = run(["build", *args])
    assert code == 0 and "bundle written to" in out and "batteries 2, cycles 4" in out
    code, out, _ = run(["verify", *args])
    assert code == 0 and "bundle OK" in out


def test_failures_exit_1(registered: NasaEnv):
    args = [registered.spec.slug, "--data-dir", str(registered.data)]
    code, _, err = run(["build", *args])  # nothing acquired
    assert code == 1 and "raw data failed verification" in err
    code, _, err = run(["verify", *args])
    assert code == 1 and "no bundle_manifest.json" in err


def test_unknown_dataset_exits_2():
    code, _, err = run(["build", "no-such-dataset"])
    assert code == 2 and "no loader for 'no-such-dataset'" in err


def test_real_registry_has_the_three_loaders():
    assert list(cli.LOADERS) == ["nasa-pcoe-battery", "calce-cs2-cx2", "severson-2019"]


def test_module_entry_point(monkeypatch: pytest.MonkeyPatch, capsys):
    monkeypatch.setattr(sys, "argv", ["volterra_ml.loaders", "build", "unknown"])
    with pytest.raises(SystemExit) as exit_info:
        runpy.run_module("volterra_ml.loaders", run_name="__main__")
    assert exit_info.value.code == 2
    assert "no loader for 'unknown'" in capsys.readouterr().err
