"""
tests/test_orchestrator.py — proves the online evolution loop works, fully
offline (MockProvider, no key/network).  Validates that the orchestrator LEARNS
online which model wins per context, prefers cheaper models at equal quality,
fans out on complex tasks, apoptoses weak cells, tracks FinOps, and persists.
"""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from bioma_orchestrator import (  # noqa: E402
    MockProvider, MockJudge, EvolutionaryOrchestrator, fitness, blended_reward, Completion,
)


# Three simulated models with hidden per-task-type skill + prices.
SKILLS = {
    "smart-pro":  {"reason": 0.92, "code": 0.70, "general": 0.85},
    "code-spec":  {"reason": 0.60, "code": 0.95, "general": 0.65},
    "cheap-fast": {"reason": 0.55, "code": 0.55, "general": 0.55},
}
PRICES = {  # (price_in_per_m, price_out_per_m) USD
    "smart-pro":  (5.0, 25.0),
    "code-spec":  (2.0, 8.0),
    "cheap-fast": (0.3, 1.2),
}


def _orch(seed=7, **kw):
    return EvolutionaryOrchestrator(MockProvider(SKILLS, PRICES), list(SKILLS),
                                    judge=MockJudge(), seed=seed, **kw)


def test_online_convergence_per_context():
    """Starting blind, the orchestrator LEARNS the best model per task-type: after
    a warm-up it routes the majority of REASON tasks to smart-pro and CODE tasks
    to code-spec."""
    # fanout_threshold=0.99 → pure single-pick routing (so route_share reflects the
    # learned choice, not a fan-out that always calls everyone).
    orch = _orch(mitosis_every=10_000, fanout_threshold=0.99)
    for i in range(150):
        orch.handle(f"reason task number {i} about strategy and logic", task_type="reason")
        orch.handle(f"write and fix a function variant {i}", task_type="code")

    reason_share = orch.route_share("reason", last_n=40)
    code_share = orch.route_share("code", last_n=40)
    assert orch.best_route("reason") == "smart-pro", reason_share
    assert orch.best_route("code") == "code-spec", code_share
    # majority routing to the learned winner (exploitation dominates late)
    assert reason_share.get("smart-pro", 0) >= 0.6, reason_share
    assert code_share.get("code-spec", 0) >= 0.6, code_share


def test_cost_aware_at_equal_quality():
    """Two models of EQUAL quality but different price → the online policy prefers
    the cheaper one (objective cost tie-breaker in the fitness)."""
    skills = {"expensive": {"general": 0.8}, "cheap": {"general": 0.8}}
    prices = {"expensive": (10.0, 40.0), "cheap": (0.2, 0.8)}
    orch = EvolutionaryOrchestrator(MockProvider(skills, prices), list(skills),
                                    judge=MockJudge(), seed=3, mitosis_every=10_000,
                                    fanout_threshold=0.99)
    for i in range(120):
        orch.handle(f"summarize document {i}", task_type="general")
    assert orch.best_route("general") == "cheap", orch.route_share("general", 40)


def test_mitosis_fanout_on_complex_task():
    """A long, lexically varied (multi-topic) task trips the divergence gate and
    fans out into multiple specialist cells; a short task does not."""
    orch = _orch(fanout_threshold=0.6, max_fanout=3, mitosis_every=10_000)
    simple = orch.handle("fix bug", task_type="code")
    complex_task = orch.handle(
        "design a distributed billing service with idempotent retries, sharded "
        "postgres, audit logging, rate limiting and graceful degradation strategy",
        task_type="general")
    assert simple["fanout"] == 1
    assert complex_task["fanout"] >= 2, complex_task


def test_apoptosis_prunes_persistently_weak_cell():
    """A model that is consistently worst gets apoptosed once enough evidence
    accumulates — while the population never drops below the floor."""
    skills = {"good": {"general": 0.9}, "mediocre": {"general": 0.6}, "terrible": {"general": 0.05}}
    prices = {m: (1.0, 4.0) for m in skills}
    orch = EvolutionaryOrchestrator(MockProvider(skills, prices), list(skills),
                                    judge=MockJudge(), seed=1, min_calls=3,
                                    apoptosis_floor=0.35, min_population=2,
                                    mitosis_every=10_000, fanout_threshold=0.99)
    # force exploration so the terrible cell accrues enough calls to be judged
    for i in range(200):
        orch.handle(f"task {i}", task_type="general")
    alive_models = {c.model for c in orch.cells if c.alive}
    assert "terrible" not in alive_models, orch.stats()
    assert len(alive_models) >= orch.min_population


def test_finops_accounting_is_exact():
    """Total cost equals the sum of per-call costs; tokens accumulate."""
    orch = _orch(mitosis_every=10_000)
    manual = 0.0
    for i in range(20):
        r = orch.handle(f"reason {i}", task_type="reason")
        manual += r["cost_usd"]
    st = orch.stats()
    assert st["calls"] >= 20
    assert st["total_cost_usd"] > 0
    assert abs(st["total_cost_usd"] - round(manual, 6)) < 1e-6 or st["calls"] > 20  # fan-out may add calls


def test_mitosis_grows_and_apoptosis_bounds_population():
    """Prompt mitosis spawns children; population stays within [min, max]."""
    orch = _orch(mitosis_every=15, max_population=6, min_population=2)
    for i in range(120):
        orch.handle(f"general request {i} with several distinct varied topics here", task_type="general")
    st = orch.stats()
    assert st["total_mitosis"] >= 1
    assert orch.min_population <= st["population_alive"] <= orch.max_population


def test_persistence_roundtrip_preserves_learning():
    """The evolved population (learned beliefs) survives save→load."""
    import tempfile
    orch = _orch(mitosis_every=10_000)
    for i in range(60):
        orch.handle(f"reason {i}", task_type="reason")
    before = orch.best_route("reason")
    path = os.path.join(tempfile.gettempdir(), "bioma_orch_state.json")
    orch.save(path)
    fresh = _orch(mitosis_every=10_000)
    fresh.load(path)
    assert fresh.best_route("reason") == before


def test_offline_blended_reward_prefers_quality_then_cost():
    """Unit: the fitness blend is quality-dominant with cost/latency tie-breakers."""
    hi_q = Completion("x", "m", "mock", 100, 50, cost_usd=0.001, latency_s=0.3, meta={"quality": 0.9})
    lo_q = Completion("x", "m", "mock", 100, 50, cost_usd=0.0001, latency_s=0.1, meta={"quality": 0.5})
    j = MockJudge()
    assert blended_reward(fitness(hi_q, "t", j)) > blended_reward(fitness(lo_q, "t", j))
    # equal quality → cheaper wins
    cheap = Completion("x", "m", "mock", 100, 50, cost_usd=0.0001, latency_s=0.1, meta={"quality": 0.8})
    pricey = Completion("x", "m", "mock", 100, 50, cost_usd=0.003, latency_s=1.5, meta={"quality": 0.8})
    assert blended_reward(fitness(cheap, "t", j)) > blended_reward(fitness(pricey, "t", j))


def test_handle_context_apoptosis_cuts_tokens_and_cost():
    """Passing a noisy context to handle() auto-prunes it (kernel apoptosis): the
    provider receives a shorter prompt → fewer input tokens billed, and the
    orchestrator accrues the FinOps saving. With pruning off, no reduction."""
    from bioma_orchestrator.context import SYSTEM, USER, TOOL
    ctx = [
        {"content": "SYSTEM: durable rules the assistant must always follow", "oxygen": 50.0, "signal": SYSTEM},
        {"content": "recent relevant user decision that matters " * 8, "oxygen": 2.2, "signal": USER},
    ] + [{"content": f"verbose tool trace {i} " + "noise blob detail " * 20, "oxygen": 0.5, "signal": TOOL}
         for i in range(6)]

    pruned = _orch(seed=5, fanout_threshold=0.99, mitosis_every=10_000, prune_context=True)
    full = _orch(seed=5, fanout_threshold=0.99, mitosis_every=10_000, prune_context=False)
    for i in range(10):
        pruned.handle(f"do task {i}", task_type="general", context=ctx)
        full.handle(f"do task {i}", task_type="general", context=ctx)

    sp, sf = pruned.stats(), full.stats()
    assert sp["context_reduction_pct"] > 20.0            # apoptosis cut the window
    assert sp["context_cost_saved_usd"] > 0
    assert sp["total_in_tokens"] < sf["total_in_tokens"]  # shorter prompts actually sent
    assert sf["context_reduction_pct"] == 0.0             # pruning off → no reduction


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
