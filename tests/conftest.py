"""Shared fixtures: the built ROM (built once per session), the parsed
config, and a factory for emulator instances on private copies of the ROM."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

import gb as gbmod
from gb import GB, ROM, ROOT, SYM


def pytest_configure(config):
    config.addinivalue_line("markers", "slow: long emulator runs (still part of `make test`)")


@pytest.fixture(scope="session")
def rom() -> Path:
    """build/pandajump.gb, brought up to date with `make` first.

    `make test` has already built it, so this is a no-op there; running
    pytest on its own still tests the current sources. The Makefile only
    needs GBDK when something is out of date, which is exactly when testing
    the old ROM would be wrong. DEBUG=0 builds the release ROM the tests
    read even under `make DEBUG=1 test`."""
    if shutil.which("make"):
        r = subprocess.run(["make", "-s", "all", "DEBUG=0"], cwd=ROOT, capture_output=True, text=True)
        if r.returncode != 0:
            pytest.fail("make failed:\n" + r.stdout + r.stderr)
    if not ROM.exists() or not SYM.exists():
        pytest.fail("build/pandajump.gb and .sym are missing: run `make` first")
    return ROM


@pytest.fixture(scope="session")
def rom_bytes(rom) -> bytes:
    return rom.read_bytes()


@pytest.fixture(scope="session")
def cfg():
    return gbmod.load_config()


@pytest.fixture
def make_game(rom, tmp_path):
    """make_game(ram=None, sound=False, boot=True, name='gb') -> GB.

    Each call gets its own directory under the test's tmp_path (reuse a
    name to power-cycle with the same battery RAM file). Every instance is
    stopped at the end of the test."""
    made = []

    def factory(ram: bytes | None = None, sound: bool = False, boot: bool = True,
                name: str = "gb") -> GB:
        g = GB(tmp_path / name, ram=ram, sound=sound, rom=rom, sym=SYM)
        made.append(g)
        if boot:
            g.boot()
        return g

    yield factory
    for g in made:
        g.stop(save=False)


@pytest.fixture
def game(make_game):
    """A booted game on the title screen, blank save RAM."""
    return make_game()
