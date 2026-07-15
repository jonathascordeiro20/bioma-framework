"""Unit tests for bioma.esg — the energy-per-token KPI (offline, deterministic)."""
from __future__ import annotations

import os
import sys

import pytest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from bioma.esg import (GRID_GCO2_PER_KWH, KWH_PER_MTOK, cache_multiplier,
                       estimate_saving, kpi_energy_per_token, wh_from_tokens)


def test_wh_from_tokens_at_one_million():
    low, mid, high = wh_from_tokens(1_000_000)
    assert (low, mid, high) == (500.0, 900.0, 1300.0)  # kWh/Mtok × 1000 → Wh


def test_bounds_are_ordered():
    low, mid, high = wh_from_tokens(45_868)
    assert low < mid < high


def test_estimate_saving_session_mid():
    est = estimate_saving(45_868)  # measured: 16-round session, 47,890 → 2,022
    assert est["wh"][1] == pytest.approx(41.28, rel=1e-3)
    assert est["gco2e"][1] == pytest.approx(41.28 / 1000.0 * 445.0, rel=1e-3)
    assert est["cache_multiplier"] == 1.0


def test_cache_multiplier_shrinks_claim():
    assert cache_multiplier(0.0) == 1.0
    assert cache_multiplier(0.75, 0.10) == pytest.approx(0.325)
    assert cache_multiplier(1.0, 0.10) == pytest.approx(0.10)
    # clamped inputs never inflate the claim
    assert cache_multiplier(2.0, 0.10) == pytest.approx(0.10)
    assert cache_multiplier(-1.0, 0.10) == 1.0


def test_estimate_saving_applies_cache_adjustment():
    plain = estimate_saving(1_000_000)
    cached = estimate_saving(1_000_000, cache_hit=0.75, cache_cost=0.10)
    assert cached["wh"][1] == pytest.approx(plain["wh"][1] * 0.325)


def test_kpi_reduction_is_coefficient_independent():
    kpi = kpi_energy_per_token(7_481, 212)  # measured local bench values
    assert kpi["reduction"] == pytest.approx(1 - 212 / 7481)
    for lo, hi in zip(kpi["wh_after"], kpi["wh_before"]):
        assert lo / hi == pytest.approx(212 / 7481)


def test_unknown_grid_raises():
    with pytest.raises(ValueError):
        estimate_saving(1, grid="mars")
    assert set(GRID_GCO2_PER_KWH) == {"world", "eu", "us", "br"}
    assert set(KWH_PER_MTOK) == {"low", "mid", "high"}


def test_zero_tokens_before_raises():
    with pytest.raises(ValueError):
        kpi_energy_per_token(0, 0)
