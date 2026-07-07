"""tests/test_context.py — the kernel-backed context pruner cuts input tokens
while preserving durable (system) content."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from bioma_orchestrator.context import ContextPruner, SYSTEM, TOOL  # noqa: E402
from bioma_orchestrator.finops_benchmark import single_window       # noqa: E402


def test_pruner_cuts_tokens_and_keeps_system():
    p = ContextPruner()
    p.add("SYSTEM: durable rule that must survive", oxygen=50.0, signal=SYSTEM)
    for i in range(12):
        p.add(f"verbose tool log {i} " + "noise " * 30, oxygen=0.5, signal=TOOL)
    before = p.active_tokens()
    apoptosed = p.prune_cycles(3, rate=0.4, reinforce_mask=SYSTEM, reinforce_amount=0.6)
    after = p.active_tokens()
    assert apoptosed >= 12                      # every noisy log died
    assert after < before                       # tokens cut
    assert any("SYSTEM: durable rule" in c for c in p.active_context())  # system survived
    assert p.reduction() > 0.3                  # meaningful reduction


def test_single_window_reduction_in_band():
    r = single_window(n=50)
    assert 25.0 <= r["reduction_pct"] <= 65.0    # realistic apoptosis band
    assert r["usd_saved_per_1M_requests"] > 0


if __name__ == "__main__":
    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
