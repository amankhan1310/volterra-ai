"""Smoke test: the backend package imports and the test tooling is wired up."""

import app


def test_app_package_imports() -> None:
    assert app.__doc__ is not None
