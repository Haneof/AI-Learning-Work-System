"""Shared test fixtures for compiled skill packages."""

from pathlib import Path

import pytest

from tests.pvd_skill_fixture import make_compiled_pvd_skill_factory


@pytest.fixture
def compiled_pvd_skill_factory(tmp_path: Path):
    """Provide the same hand-authored package factory to all skill tests."""
    return make_compiled_pvd_skill_factory(tmp_path)
