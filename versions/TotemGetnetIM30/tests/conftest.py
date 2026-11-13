"""Fixtures compartidas para las pruebas del tótem (modo simulación)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pytest  # noqa: E402

from config import load_settings, override_settings  # noqa: E402
from orders import OrderStore  # noqa: E402


def make_sim_settings(tmp_path: Path, **overrides):
    base = load_settings()
    params = dict(
        mode="simulation",
        connector="usb",
        simulation_outcome="approved",
        simulation_delay_seconds=0.0,
        order_timeout_seconds=5,
        db_path=str(tmp_path / "orders.db"),
    )
    params.update(overrides)
    return override_settings(base, **params)


@pytest.fixture
def sim_settings(tmp_path):
    return make_sim_settings(tmp_path)


@pytest.fixture
def store(tmp_path):
    return OrderStore(tmp_path / "orders.db")
