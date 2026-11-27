"""Fixtures for the wire tier. See tests/conftest.py for the --wire options."""
import tempfile
from pathlib import Path

import pytest

from . import harness as H


@pytest.fixture(scope="session")
def wire_out(request) -> Path:
    """Where this run's logs, captures and reports go.

    Kept after the run on purpose: when a wire test fails, the backend's console
    log and the measurements are the evidence.
    """
    chosen = request.config.getoption("--wire-out")
    root = Path(chosen) if chosen else Path(tempfile.mkdtemp(prefix="ils-wire-"))
    root.mkdir(parents=True, exist_ok=True)
    return root


@pytest.fixture(scope="module")
def wire_config(request, wire_out) -> H.WireConfig:
    """A fresh database directory and free loopback ports for one test module."""
    return H.WireConfig.create(wire_out / request.module.__name__.rsplit(".", 1)[-1])
