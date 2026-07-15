"""
`bioma/esg.py` — the official Frugal-AI KPI of the project: **energy per token**.

Converts MEASURED token savings (the kernel's per-dispatch audit) into energy
(Wh) and emissions (gCO2e) estimates using DECLARED literature coefficients.
The tokens are ground truth; the conversion is an estimate — every function
returns (low, mid, high) bounds and never a single unqualified number.

Coefficients (declared, replace with your own measurements when available):

* Datacenter LLM inference energy: **0.5–1.3 kWh per million tokens**
  (mid 0.9). Range adopted from the public literature — consistent with
  Epoch AI's ~0.3 Wh per GPT-4o query (~500-token answer) and 2024–2025
  meta-analyses of production frontier-model inference. Our own CPU-laptop
  measurement (reports/BIOMA_ENERGY_LOCAL.md: 0.754 Wh / 7,481 tok ≈
  0.10 kWh/M tok, MARGINAL — idle and PUE excluded, 1B-parameter model,
  prefill-heavy) sits below that range, as expected for a tiny model
  measured marginally; the literature range targets production-scale
  frontier inference. The KPI's reduction % is coefficient-independent.
* Grid carbon intensity presets (gCO2e/kWh): world ≈ 445 (IEA 2024),
  EU ≈ 230 (EEA), US ≈ 385 (EPA eGRID), BR ≈ 100 (hydro-heavy, EPE/ONS).
* Prompt-caching adjustment: cached prefill tokens are not free — they are
  billed/computed at a fraction of full price. `cache_adjust` shrinks the
  claimed saving accordingly: saving × ((1−hit) + hit·cache_cost).

Usage:
    from bioma.esg import estimate_saving, DEFAULTS
    est = estimate_saving(tokens_saved=45_868)          # one 16-round session
    est["wh"]      # (low, mid, high) Wh saved
    est["gco2e"]   # (low, mid, high) gCO2e saved, world grid
"""
from __future__ import annotations

from typing import TypedDict

# kWh per MILLION tokens — declared literature range (see module docstring).
KWH_PER_MTOK = {"low": 0.5, "mid": 0.9, "high": 1.3}

# gCO2e per kWh — grid presets (replace with your grid's factor).
GRID_GCO2_PER_KWH = {"world": 445.0, "eu": 230.0, "us": 385.0, "br": 100.0}

DEFAULTS = {"grid": "world", "cache_hit": 0.0, "cache_cost": 0.10}


class Estimate(TypedDict):
    tokens_saved: int
    cache_multiplier: float
    wh: tuple[float, float, float]
    gco2e: tuple[float, float, float]
    grid: str
    kwh_per_mtok: dict


def cache_multiplier(cache_hit: float, cache_cost: float = 0.10) -> float:
    """Fraction of the nominal saving that survives an honest caching baseline.

    If `cache_hit` of the resent context would have been a cache hit anyway
    (costing `cache_cost` of a full prefill), the counterfactual baseline is
    cheaper and the claimable saving shrinks: (1−hit) + hit·cost."""
    hit = min(max(cache_hit, 0.0), 1.0)
    cost = min(max(cache_cost, 0.0), 1.0)
    return (1.0 - hit) + hit * cost


def wh_from_tokens(tokens: float) -> tuple[float, float, float]:
    """Energy (Wh) for `tokens` at the declared low/mid/high coefficients."""
    return tuple(tokens / 1e6 * KWH_PER_MTOK[k] * 1000.0 for k in ("low", "mid", "high"))  # type: ignore[return-value]


def estimate_saving(tokens_saved: int, *, grid: str = "world",
                    cache_hit: float = 0.0, cache_cost: float = 0.10) -> Estimate:
    """Convert measured tokens saved into bounded Wh / gCO2e estimates."""
    if grid not in GRID_GCO2_PER_KWH:
        raise ValueError(f"unknown grid preset {grid!r}; options: {sorted(GRID_GCO2_PER_KWH)}")
    mult = cache_multiplier(cache_hit, cache_cost)
    wh = tuple(v * mult for v in wh_from_tokens(tokens_saved))
    g = GRID_GCO2_PER_KWH[grid]
    return Estimate(
        tokens_saved=tokens_saved,
        cache_multiplier=round(mult, 4),
        wh=wh,  # type: ignore[typeddict-item]
        gco2e=tuple(v / 1000.0 * g for v in wh),  # type: ignore[typeddict-item]
        grid=grid,
        kwh_per_mtok=dict(KWH_PER_MTOK),
    )


def kpi_energy_per_token(tokens_before: int, tokens_after: int) -> dict:
    """The project KPI: energy per dispatch, before vs after apoptosis.

    Returns Wh (low, mid, high) for both sides plus the reduction fraction —
    which is exact (independent of the coefficient, since it cancels out)."""
    if tokens_before <= 0:
        raise ValueError("tokens_before must be positive")
    return {
        "wh_before": wh_from_tokens(tokens_before),
        "wh_after": wh_from_tokens(tokens_after),
        "reduction": 1.0 - tokens_after / tokens_before,
    }
