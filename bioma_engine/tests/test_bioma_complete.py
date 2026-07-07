"""
tests/test_bioma_complete.py — B.I.O.M.A. engineering-duress test suite.

Covers every core evolutionary mechanism:

  * Entropy & Fission        — high-workload prompts trigger parallel splitting;
                               low-workload prompts stay solo.
  * Hormonal-Bus races       — 50 concurrent async read/writes, zero deadlocks
                               and zero dimension mismatches.
  * Apoptosis memory profile — 100 spawned organisms, gc.collect(), RSS delta
                               returns to ≈ 0 (psutil).
  * Evolutionary Coder       — optimises a slow program, apoptoses hanging
                               variants (timeout), never regresses correctness.
  * Reverse Distillation     — a teacher organism's function is distilled into a
                               stem cell without leaking gradients into the teacher.

All tests are synchronous and drive async code via ``asyncio.run`` so no
pytest-asyncio plugin is required.
"""

from __future__ import annotations

import asyncio
import gc

import psutil
import pytest
import torch

from bioma_engine import (
    DEFAULT_CONFIG,
    MitosisEngine,
    HormonalBus,
    NeuralOrganism,
    EvolutionaryCoder,
    FitnessReport,
    workload_entropy,
    DEMO_SLOW_SQRT,
    DEMO_SQRT_TESTS,
    DEMO_SLOW_FIB,
    DEMO_FIB_TESTS,
    live_cells_global,
)

EMBED = DEFAULT_CONFIG.embed_dim

COMPLEX_PROMPT = (
    "Simulate a global financial market collapse cascading into a national energy grid "
    "failure while coordinating emergency medical logistics cybersecurity defense of "
    "critical infrastructure food supply chain rerouting water sanitation and public "
    "communication strategy optimizing every response matrix in parallel"
)
MONO_PROMPT = "energy energy energy energy energy"


# ============================================================================ #
#  1. Entropy-aware mitosis / test-time compute
# ============================================================================ #
def test_workload_entropy_bounds_and_ordering():
    """H(X) is in [0,1]; a spread workload has higher entropy than a collapsed one."""
    spread = torch.randn(24, EMBED)
    collapsed = torch.ones(24, EMBED) * torch.randn(EMBED)  # all rows ~identical direction
    h_spread = workload_entropy(spread)
    h_collapsed = workload_entropy(collapsed)
    assert 0.0 <= h_collapsed <= 1.0
    assert 0.0 <= h_spread <= 1.0
    assert h_spread > h_collapsed
    assert workload_entropy(torch.randn(1, EMBED)) == 0.0  # degenerate -> 0


def test_high_entropy_triggers_fission():
    """A high-workload, multi-domain prompt must fork into N>1 leaf micro-agents."""
    engine = MitosisEngine()
    result = asyncio.run(engine.synthesize(COMPLEX_PROMPT, request_id="t-fission"))
    assert result["total_mitosis"] >= 1, result
    assert result["peak_cells"] > 1, result
    assert result["dag_nodes"] > 1
    assert result["convergence"] is not None
    assert live_cells_global() == 0  # no leak after the run


def test_low_entropy_stays_solo():
    """A trivial mono-domain prompt must NOT divide."""
    engine = MitosisEngine()
    result = asyncio.run(engine.synthesize(MONO_PROMPT, request_id="t-solo"))
    assert result["total_mitosis"] == 0, result
    assert result["peak_cells"] == 1, result
    assert live_cells_global() == 0


def test_difficulty_scales_child_count():
    """The stem forks into exactly N children and N is bounded by max_children."""
    engine = MitosisEngine()
    events = []

    async def run():
        async for ev in engine.run(COMPLEX_PROMPT, request_id="t-scale"):
            events.append(ev)

    asyncio.run(run())
    mitosis = [e for e in events if e.kind == "mitosis" and e.cell_id == "stem"]
    assert mitosis, "stem never divided"
    k = mitosis[0].metrics["k"]
    assert 2 <= k <= DEFAULT_CONFIG.max_children


# ============================================================================ #
#  2. Hormonal bus — concurrent race conditions
# ============================================================================ #
def test_hormonal_bus_50_concurrent_no_races():
    """Fire 50 concurrent secrete+sense pairs; assert no deadlock / shape drift."""
    bus = HormonalBus()
    cfg = bus.config
    ids = [f"cell-{i}" for i in range(50)]
    for cid in ids:
        bus.register(cid)

    async def hammer():
        async def rw(cid: str, i: int):
            vec = torch.randn(cfg.embed_dim)
            await bus.secrete(cid, vec, gain=1.0 + 0.01 * i)
            ctx = await bus.sense(cid, vec)
            # sensing must always return an embed_dim vector, never a mismatch
            assert ctx.shape == (cfg.embed_dim,), ctx.shape
            return ctx

        # 50 concurrent read/writes in a single gather storm
        return await asyncio.gather(*[rw(cid, i) for i, cid in enumerate(ids)])

    results = asyncio.run(hammer())
    assert len(results) == 50
    assert all(r.shape == (cfg.embed_dim,) for r in results)
    assert bus.occupancy() == 50


def test_hormonal_bus_dimension_guard():
    """A wrong-dimension hormone must be rejected, not silently corrupt the manifold."""
    bus = HormonalBus()
    bus.register("x")
    with pytest.raises(ValueError):
        bus.secrete_sync("x", torch.randn(EMBED + 7))


def test_hormonal_bus_repeated_gather_storms():
    """Multiple back-to-back gather storms keep the manifold consistent (no lock loss)."""
    bus = HormonalBus()
    ids = [f"n{i}" for i in range(30)]
    for cid in ids:
        bus.register(cid)

    async def storm():
        for _ in range(5):
            await asyncio.gather(*[
                bus.secrete(cid, torch.randn(EMBED)) for cid in ids
            ])
            ctxs = await asyncio.gather(*[
                bus.sense(cid, torch.randn(EMBED)) for cid in ids
            ])
            assert all(c.shape == (EMBED,) for c in ctxs)

    asyncio.run(storm())
    assert bus.occupancy() == 30


# ============================================================================ #
#  3. Apoptosis — memory-leak profile
# ============================================================================ #
def test_apoptosis_memory_returns_to_baseline():
    """Spawn 100 organisms, exercise + apoptose each, assert RSS delta ≈ 0."""
    proc = psutil.Process()
    cfg = DEFAULT_CONFIG

    # Warm the allocator so we measure steady-state, not cold-start growth.
    for i in range(10):
        c = NeuralOrganism(f"warm-{i}", cfg)
        c.metabolic_step(torch.randn(EMBED), torch.zeros(EMBED))
        c.apoptose()
        del c
    gc.collect()
    baseline = proc.memory_info().rss

    for i in range(100):
        cell = NeuralOrganism(f"leaf-{i}", cfg)
        x = torch.randn(EMBED)
        ctx = torch.zeros(EMBED)
        cell.metabolic_step(x, ctx)
        cell.homeostasis(cfg.entropy_setpoint)
        report = cell.apoptose()
        assert report["reclaimed_bytes"] > 0
        del cell, x, ctx
    gc.collect()

    delta_mb = (proc.memory_info().rss - baseline) / 1e6
    # 100 live organisms would pin ~50MB+; a clean apoptosis path returns near 0.
    # Allow a generous margin for CPython allocator arena retention.
    assert delta_mb < 25.0, f"memory grew by {delta_mb:.1f} MB — possible leak"


def test_apoptose_is_idempotent_and_frees_hooks():
    """apoptose() twice is safe and removes the FlopMeter forward hooks."""
    cell = NeuralOrganism("solo", DEFAULT_CONFIG)
    first = cell.apoptose()
    assert first["reclaimed_bytes"] > 0
    assert cell.alive is False
    second = cell.apoptose()
    assert second.get("already_dead") is True
    # hooks removed -> no dangling forward hooks on the linear layers
    assert len(cell._flops._handles) == 0


# ============================================================================ #
#  4. Evolutionary Coder — lexicographic fitness + AST catalog + apoptosis (Fase 10)
# ============================================================================ #
def test_evolutionary_coder_optimises_and_never_regresses():
    """Evolve the slow sqrt; the winner stays correct and is measurably faster."""
    coder = EvolutionaryCoder(timeout_s=5.0, tolerance=1e-3, seed=7, repeats=3)
    try:
        result = asyncio.run(coder.evolve(
            DEMO_SLOW_SQRT, "solve", DEMO_SQRT_TESTS, generations=5, population=6
        ))
    finally:
        coder.shutdown()

    assert result["best_report"]["correct"] is True, result["best_report"]
    assert result["best_report"]["tests_passed"] == result["best_report"]["tests_total"]
    assert len(result["history"]) >= 2
    # Measured gain, with a labelled origin (not "the evolution discovered X").
    assert result["improved"] is True, result
    assert result["best_report"]["latency_ms"] < result["baseline_report"]["latency_ms"]
    assert result["winning_transform"].startswith("ast:")
    assert result["apoptosis_count"] >= 1
    # A winning transform was promoted to the reusable catalog.
    assert result["catalog_size"] >= 1 and result["promoted"] is not None


def test_fitness_is_lexicographic():
    """Correctness is a hard gate: a correct-but-slow variant always outranks a
    fast-but-incorrect one, no matter the latency (plan Fase 10)."""
    correct_slow = FitnessReport(tests_passed=5, tests_total=5, latency_ms=1000.0)
    wrong_fast = FitnessReport(tests_passed=2, tests_total=5, latency_ms=0.001)
    assert correct_slow.sort_key > wrong_fast.sort_key
    # Among two correct variants, the faster one wins.
    fast_correct = FitnessReport(tests_passed=5, tests_total=5, latency_ms=1.0)
    assert fast_correct.sort_key > correct_slow.sort_key


def test_lru_cache_catalog_transform_speeds_recursion():
    """The ``insert_lru_cache`` catalog transform memoises naive recursion — a
    genuine algorithmic transform (the plan's canonical example)."""
    coder = EvolutionaryCoder(timeout_s=10.0, seed=3, repeats=3)
    try:
        base = asyncio.run(coder.evaluate(DEMO_SLOW_FIB, "solve", DEMO_FIB_TESTS))
        memo_src = coder.apply_transform(DEMO_SLOW_FIB, "solve", "insert_lru_cache")
        assert memo_src is not None and "lru_cache" in memo_src
        memo = asyncio.run(coder.evaluate(memo_src, "solve", DEMO_FIB_TESTS,
                                          origin="ast:insert_lru_cache"))
    finally:
        coder.shutdown()
    assert base.correct and memo.correct
    assert memo.latency_ms < base.latency_ms * 0.5  # memoisation is dramatically faster


def test_evolutionary_coder_apoptoses_hanging_variant():
    """A variant that hangs is killed by the timeout (apoptosis) → fails the gate."""
    coder = EvolutionaryCoder(timeout_s=1.5, seed=1)
    hanging = "def solve(x):\n    while True:\n        pass\n    return x\n"
    try:
        report = asyncio.run(coder.evaluate(hanging, "solve", [[[1.0], 1.0]]))
    finally:
        coder.shutdown()
    assert report.alive is False
    assert report.error and "apoptosis" in report.error
    assert report.sort_key[0] == 0  # correctness gate failed


def test_evolutionary_coder_rejects_broken_mutation():
    """A syntactically-loadable but wrong program scores 0 tests passed (not correct)."""
    coder = EvolutionaryCoder(timeout_s=3.0, seed=2)
    wrong = "def solve(x):\n    return x + 999999.0\n"
    try:
        report = asyncio.run(coder.evaluate(wrong, "solve", DEMO_SQRT_TESTS))
    finally:
        coder.shutdown()
    assert report.alive is True
    assert report.correct is False
    assert report.tests_passed < report.tests_total


def test_coder_has_no_neural_or_gradient_references():
    """Static audit (plan Fase 10 acceptance): the Coder module manipulates source
    text only — it must contain no tensor/gradient/autograd references."""
    import bioma_engine.evolutionary_coder as ec

    src = open(ec.__file__, encoding="utf-8").read().lower()
    for token in ("gradient", "autograd", "backward", "distill", "torch", "nn."):
        assert token not in src, f"banned token {token!r} found in evolutionary_coder.py"


# ============================================================================ #
#  5. Neural knowledge distillation (organism→organism primitive, N1)
# ============================================================================ #
def test_distillation_moves_student_not_teacher():
    """distill_from drives the student organism toward the teacher and never
    mutates the teacher (isolated per-cell graphs, no cross-organism leak)."""
    cfg = DEFAULT_CONFIG
    student = NeuralOrganism("stem", cfg, generation=0)
    teacher = NeuralOrganism("teacher", cfg, generation=1)  # different random init

    student_before = {k: v.clone() for k, v in student.state_dict().items()}
    teacher_before = {k: v.clone() for k, v in teacher.state_dict().items()}

    probes = torch.randn(8, EMBED)
    report = student.distill_from(teacher, probes, epochs=40)

    assert report["final_loss"] < report["initial_loss"], report
    assert report["teacher_unchanged"] is True
    student_after = student.state_dict()
    changed = any(
        not torch.equal(student_before[k], student_after[k])
        for k in student_before if student_after[k].dtype.is_floating_point
    )
    assert changed, "student parameters did not move during distillation"
    for k, v in teacher.state_dict().items():
        assert torch.equal(teacher_before[k], v)


# ============================================================================ #
#  6. Bus hardening (Fase 2) — true cosine, dissipation, staleness, snapshot
# ============================================================================ #
def test_bus_true_cosine_scale_invariant_direction():
    """Attention uses true cosine (query AND keys normalised): the peer aligned
    with the query dominates the context, invariant to that peer's magnitude."""
    bus = HormonalBus()
    for c in ("r", "a", "b"):
        bus.register(c)
    da, db = torch.randn(EMBED), torch.randn(EMBED)
    bus.secrete_sync("a", da)
    bus.secrete_sync("b", db)
    ctx = bus.sense_sync("r", da)  # query aligned with peer a
    ca = torch.nn.functional.cosine_similarity(ctx, da, dim=0).item()
    cb = torch.nn.functional.cosine_similarity(ctx, db, dim=0).item()
    assert ca > cb  # aligned peer dominates
    # Scale peer a's secretion 6x; cosine ignores key magnitude → a still dominates.
    bus.secrete_sync("a", da * 6.0)
    ctx2 = bus.sense_sync("r", da)
    assert torch.nn.functional.cosine_similarity(ctx2, da, dim=0).item() > 0.5


def test_bus_temporal_dissipation():
    """tick() dissipates manifold vectors: an un-refreshed slot decays to ~0."""
    bus = HormonalBus()
    bus.register("x")
    bus.secrete_sync("x", torch.randn(EMBED) * 5.0)
    n0 = bus.active_field().norm().item()
    for _ in range(60):
        bus.tick()
    n1 = bus.active_field().norm().item()
    assert n1 < n0 * 0.05  # geometric decay drove the signal down


def test_bus_staleness_gate_and_all_zero_keys_no_nan():
    """Stale peers are masked from attention; all-zero keys never produce NaN."""
    bus = HormonalBus()
    bus.register("r")
    bus.register("p")
    bus.secrete_sync("p", torch.randn(EMBED))
    for _ in range(DEFAULT_CONFIG.staleness_ticks + 2):
        bus.tick()
    ctx = bus.sense_sync("r", torch.randn(EMBED))  # p is stale -> masked
    assert torch.isfinite(ctx).all()
    assert ctx.norm().item() < 1e-4  # no fresh peers -> zero context


def test_bus_norm_clamp_and_nonfinite_sanitized():
    """A blown-up / non-finite secretion is sanitized and norm-clamped."""
    bus = HormonalBus()
    bus.register("x")
    bad = torch.randn(EMBED)
    bad[0] = float("inf")
    bad = bad * 1e6
    bus.secrete_sync("x", bad)
    field = bus.active_field()
    assert torch.isfinite(field).all()
    assert field.norm().item() <= DEFAULT_CONFIG.hormone_norm_clamp + 1e-3


def test_bus_snapshot_reuse_above_floor():
    """Repeated reads without writes reuse the versioned snapshot (Fase 2 metric)."""
    from bioma_engine.config import THRESHOLD_REGISTRY

    bus = HormonalBus()
    bus.register("r")
    bus.register("p")
    bus.secrete_sync("p", torch.randn(EMBED))
    for _ in range(20):
        bus.sense_sync("r", torch.randn(EMBED))  # no writes between -> snapshot reused
    assert bus.snapshot_reuse_ratio() >= THRESHOLD_REGISTRY["snapshot_reuse_floor"]


# ============================================================================ #
#  7. Orchestration budget (Fase 5) — reserve-before-divide never overshoots
# ============================================================================ #
def test_budget_never_exceeds_cell_budget():
    """Under a high-difficulty prompt the live population never exceeds cell_budget."""
    engine = MitosisEngine()
    result = asyncio.run(engine.synthesize(COMPLEX_PROMPT, request_id="t-budget"))
    assert result["peak_cells"] <= DEFAULT_CONFIG.cell_budget
    assert live_cells_global() == 0


def test_budget_semaphore_atomic_reserve():
    """The cooperative budget gate reserves atomically and rolls back on release."""
    from bioma_engine.mitosis_engine import BudgetSemaphore

    sem = BudgetSemaphore(3)
    assert sem.try_reserve(2) is True and sem.available() == 1
    assert sem.try_reserve(2) is False  # only 1 left -> refused (no overshoot)
    assert sem.try_reserve(1) is True and sem.available() == 0
    sem.release(1)
    assert sem.available() == 1


def test_zero_row_embeddings_rejected():
    """A zero-row injected embeddings tensor is rejected up front, not silently
    turned into a dishonest converged=True with NaN synthesis (finding #5)."""
    engine = MitosisEngine()
    with pytest.raises(ValueError):
        asyncio.run(engine.synthesize(embeddings=torch.empty(0, EMBED)))


# ============================================================================ #
#  8. Simulation harness (Fase 6) — ground-truth judge + confusion matrix
# ============================================================================ #
from bioma_engine.simulation_harness import (  # noqa: E402
    SimulationHarness, generate_scenario, curriculum,
)


def test_scenario_ground_truth_valid_and_detached():
    """Prototypes orthonormal, γC contractive, S* = (I−γC)⁻¹P, all detached."""
    sc = generate_scenario("s", K=4, M=16, d=EMBED, sigma=0.05, gamma=0.6, seed=1)
    # Orthonormal prototypes.
    gram = sc.P @ sc.P.t()
    assert torch.allclose(gram, torch.eye(sc.K), atol=1e-4)
    # Contractive coupling: spectral radius(γC) = γ < 1.
    radius = torch.linalg.eigvals(sc.gamma * sc.C).abs().max().item()
    assert radius < 1.0
    # Ground-truth actually solves the cascade equation (I−γC)S* = P.
    residual = ((torch.eye(sc.K) - sc.gamma * sc.C) @ sc.S_star - sc.P).norm().item()
    assert residual < 1e-3
    # Detached, outside any graph (never shown to the organism).
    assert sc.S_star.requires_grad is False and sc.X.requires_grad is False


def test_mitosis_decision_confusion_matrix():
    """PRIMARY metric: divide on multi-domain, suppress on uni-domain/adversarial."""
    harness = SimulationHarness()
    cm = harness.decision_confusion_matrix(curriculum(EMBED))
    assert cm["precision"] == 1.0 and cm["recall"] == 1.0, cm
    assert cm["fp"] == 0 and cm["fn"] == 0
    assert cm["accuracy"] == 1.0


def test_coverage_high_on_severe_multidomain():
    """Mitosis decomposition covers the domains (plan: coverage ≥ 0.9 severe)."""
    harness = SimulationHarness()
    sc = generate_scenario("severe", K=4, M=20, d=EMBED, sigma=0.05, gamma=0.6, seed=100)
    scored = harness.run_scenario(sc)
    assert scored["k_chosen"] == 4
    assert scored["coverage_hard"] >= 0.9, scored
    assert scored["survived"] is True and scored["gauge_after"] == 0


def test_identifiability_cos_decreases_with_gamma():
    """cos(P, S*) falls monotonically as coupling γ grows (task non-trivial)."""
    harness = SimulationHarness()
    sweep = harness.identifiability_sweep(gammas=(0.0, 0.2, 0.4, 0.6, 0.8))
    cosines = [row["cos_P_vs_Sstar"] for row in sweep]
    assert cosines[0] == pytest.approx(1.0, abs=1e-3)
    assert all(cosines[i] >= cosines[i + 1] for i in range(len(cosines) - 1)), cosines
    assert cosines[-1] < cosines[0]  # strictly diverged at high γ


def test_factorial_mitosis_helps_coverage():
    """The 2×2 shows mitosis materially improves coverage; monolithic is worse."""
    harness = SimulationHarness()
    sc = generate_scenario("fac", K=4, M=20, d=EMBED, sigma=0.05, gamma=0.5, seed=5)
    fac = harness.factorial_2x2(sc)
    assert fac["mitosis_effect_on_coverage"] > 0.2, fac
    mono = fac["cells"]["mitosis=False,bus=True"]["coverage_soft"]
    full = fac["cells"]["mitosis=True,bus=True"]["coverage_soft"]
    assert full > mono


def test_oracle_metrics_bounded():
    """All oracle components stay within their declared bounds."""
    harness = SimulationHarness()
    sc = generate_scenario("b", K=3, M=18, d=EMBED, sigma=0.05, gamma=0.4, seed=9)
    s = harness.run_scenario(sc)
    for key in ("coverage_soft", "coverage_hard", "cascade_score", "composite"):
        assert 0.0 <= s[key] <= 1.0, (key, s[key])
    assert s["cascade_residual"] >= 0.0


# ============================================================================ #
#  9. Energy, coordination & apoptosis FSM (Fase 4)
# ============================================================================ #
def test_energy_regeneration_by_progress():
    """Adaptation that reduces the sub-domain loss regenerates ATP (progress,
    not activity) — energy can go UP, and the accounting stays balanced."""
    cell = NeuralOrganism("t", DEFAULT_CONFIG)
    x, ctx, target = torch.randn(EMBED), torch.zeros(EMBED), torch.randn(EMBED)
    regens = [cell.adapt(x, ctx, target)["regen"] for _ in range(5)]
    assert any(r > 0.0 for r in regens), regens  # progress refilled energy
    assert cell.energy_audit()["balanced"] is True


def test_energy_accounting_audit_balances():
    """Auditoria de contabilidade (NOT physical conservation): the running balance
    equals initial − total_burn + total_regen within float error."""
    cell = NeuralOrganism("t", DEFAULT_CONFIG)
    x, ctx, target = torch.randn(EMBED), torch.zeros(EMBED), torch.randn(EMBED)
    for _ in range(3):
        cell.metabolic_step(x, ctx)
    for _ in range(3):
        cell.adapt(x, ctx, target)
    audit = cell.energy_audit()
    assert audit["balanced"] is True
    assert abs(audit["energy"] - audit["expected"]) < 1e-4


def test_energy_accounting_balances_after_division():
    """The accounting identity holds for a cell that undergoes MITOSIS: the energy
    handed to children is recorded as a transfer, not lost (review finding #1)."""
    cell = NeuralOrganism("stem", DEFAULT_CONFIG)
    cell.metabolic_step(torch.randn(EMBED), torch.zeros(EMBED))
    assert cell.energy_audit()["balanced"] is True
    cell.divide(torch.randn(3, EMBED))          # transfers child_energy_fraction of energy
    audit = cell.energy_audit()
    assert audit["balanced"] is True, audit     # was False before the fix
    assert audit["total_transferred"] > 0


def test_apoptosis_fsm_triggers_logged_no_necrosis():
    """Every death is an ORDERED apoptosis with a logged trigger (4-way FSM);
    the trigger tally accounts for every death (zero necrosis)."""
    from bioma_engine.simulation_harness import SimulationHarness, generate_scenario

    harness = SimulationHarness()
    sc = generate_scenario("fsm", K=4, M=20, d=EMBED, sigma=0.05, gamma=0.6, seed=3)
    cfg = harness._config(mitosis=True, bus=True)
    engine = MitosisEngine(cfg)
    result = asyncio.run(engine.synthesize(embeddings=sc.X, request_id="fsm"))
    triggers = result["death_triggers"]
    assert sum(triggers.values()) == result["total_apoptosis"]  # every death accounted
    valid = {"task_solved", "energy_depleted", "marginal_contribution", "senescence"}
    assert set(triggers).issubset(valid)
    assert live_cells_global() == 0


def test_bus_coordination_improves_cascade_recovery():
    """THE Fase-4 headline: enabling the bus (coordination) raises the recovery of
    the cascade-coupled ground-truth S* — the bus main effect is positive."""
    from bioma_engine.simulation_harness import SimulationHarness, generate_scenario

    harness = SimulationHarness()
    sc = generate_scenario("cascade", K=4, M=20, d=EMBED, sigma=0.05, gamma=0.6, seed=5)
    fac = harness.factorial_2x2(sc)
    assert fac["bus_effect_on_cascade"] > 0.0, fac
    # With mitosis on, the bus strictly improves the cascade score.
    on = fac["cells"]["mitosis=True,bus=True"]["cascade_score"]
    off = fac["cells"]["mitosis=True,bus=False"]["cascade_score"]
    assert on > off


# ============================================================================ #
#  10. Observability: BioEvent + operational CSR (Fase 7)
# ============================================================================ #
from bioma_engine.observability import (  # noqa: E402
    record_run, compute_csr, csr_over_runs, wilson_lower_bound,
    count_live_organisms, leak_soak, race_probe, telemetry_overhead,
)

_OBS_PROMPT = ("global financial market collapse energy grid failure medical logistics "
               "cybersecurity food supply water sanitation communication strategy parallel")


def test_bioevent_schema_seq_and_dag_reconstruction():
    """BioEvents are versioned, seq-monotonic, and the DAG is reconstructable from
    the event stream alone (matching the engine's own DAG)."""
    engine = MitosisEngine()
    sink, summary = record_run(engine, prompt=_OBS_PROMPT, root_id="t")
    evs = sink.events()
    assert len(evs) > 0
    assert [e.seq for e in evs] == list(range(len(evs)))          # monotonic, gapless
    assert all(e.schema_version == "1.0" for e in evs)
    assert all(e.root_id == "t" for e in evs)
    dag = sink.reconstruct_dag()
    assert dag.number_of_nodes() == summary["dag_nodes"]
    assert dag.number_of_edges() == summary["dag_edges"]
    assert nx_is_dag(dag)


def nx_is_dag(dag):
    import networkx as nx
    return nx.is_directed_acyclic_graph(dag)


def test_wilson_lower_bound_math():
    """Wilson lower bound behaves correctly at the boundaries."""
    assert wilson_lower_bound(0, 0) == 1.0
    assert 0.9 < wilson_lower_bound(96, 96) < 1.0     # large clean sample → tight bound
    assert 0.5 < wilson_lower_bound(10, 10) < 1.0     # small clean sample → looser
    assert 0.15 < wilson_lower_bound(5, 10) < 0.35    # 50% → mid, below the point est.
    assert wilson_lower_bound(0, 20) < 0.2            # all-fail → low


def test_csr_single_run_no_necrosis():
    """A healthy run: CSR=1.0, zero necrosis, no NaN, no leak, gc live == 0."""
    engine = MitosisEngine()
    sink, _ = record_run(engine, prompt=_OBS_PROMPT, root_id="csr")
    rep = compute_csr(sink, gauge_after=live_cells_global(), gc_live=count_live_organisms())
    assert rep["csr"] == 1.0
    assert rep["necrosis_count"] == 0
    assert rep["no_nan_inf"] is True and rep["no_leak"] is True
    assert rep["gc_live_organisms"] == 0
    assert rep["births"] == rep["survivors"] > 0
    assert 0.0 < rep["wilson_lower_bound"] <= 1.0


def test_csr_over_runs_declared_denominator():
    """Aggregated CSR over R runs yields a Wilson bound over a declared N births."""
    agg = csr_over_runs(DEFAULT_CONFIG, [_OBS_PROMPT] * 4)
    assert agg["total_births"] > 0
    assert agg["total_survivors"] == agg["total_births"]  # zero necrosis across runs
    assert agg["csr"] == 1.0
    assert agg["wilson_lower_bound"] > 0.8               # tightens with N


def test_leak_soak_no_growth():
    """A soak shows no significant RSS growth trend and returns gc live to zero."""
    rep = leak_soak(DEFAULT_CONFIG, _OBS_PROMPT, cycles=8, b_max=1.0)
    assert rep["gc_live_organisms"] == 0
    assert rep["gauge_after"] == 0
    assert rep["leak_free"] is True


def test_race_probe_read_after_write():
    """Concurrent read-after-write on the bus: zero errors, shapes stable, finite."""
    rep = race_probe(DEFAULT_CONFIG, n=64)
    assert rep["errors"] == 0
    assert rep["shape_consistent"] is True
    assert rep["manifold_finite"] is True
    assert rep["race_free"] is True


def test_telemetry_overhead_bounded():
    """Recording BioEvents does not dominate the run time (instrumentation is cheap)."""
    oh = telemetry_overhead(DEFAULT_CONFIG, _OBS_PROMPT, repeats=2)
    assert oh["overhead_ratio"] < 0.75  # generous bound; typically near zero


# ============================================================================ #
#  11. Self-correction loop (Fase 8) — OODA repair over a finite patch catalog
# ============================================================================ #
import dataclasses  # noqa: E402
from bioma_engine.repair import (  # noqa: E402
    RepairController, REPAIR_CATALOG, CATALOG_SYMPTOMS, Patch,
    structured_embeddings, inject_nan, NAN_INF,
    SHAPE_MISMATCH, CUDA_OOM, CPU_LEAK, VRAM_LEAK, ASYNC_RACE, GRAD_BREAK, DEADLOCK,
)


def _healthy_and_faulty():
    healthy = structured_embeddings(4, 20, EMBED, 0.05, seed=1)
    faulty = inject_nan(structured_embeddings(4, 20, EMBED, 0.05, seed=1), rows=3)
    vulnerable = dataclasses.replace(DEFAULT_CONFIG, fission_mode="silhouette", sanitize_input=False)
    return healthy, faulty, vulnerable


def test_repair_recovers_injected_nan():
    """Injected NAN_INF fault: the loop detects, patches, and reaches FIXPOINT."""
    healthy, faulty, vulnerable = _healthy_and_faulty()
    ctrl = RepairController(max_iter=4)
    rep = ctrl.repair(vulnerable, faulty, healthy_scenario=healthy)
    assert rep.status == "FIXPOINT", rep.as_dict()
    assert any(a["symptom"] == NAN_INF for a in rep.actions)
    assert any(a["patch"] == "enable_input_sanitization" for a in rep.actions)
    assert rep.final_csr["csr"] == 1.0 and rep.final_csr["necrosis_count"] == 0


def test_repair_honest_failure_on_unfixable():
    """With no patch for the symptom, the loop reports FAILURE — never fake success."""
    healthy, faulty, vulnerable = _healthy_and_faulty()
    no_nan_catalog = [p for p in REPAIR_CATALOG if p.symptom != NAN_INF]
    ctrl = RepairController(catalog=no_nan_catalog, max_iter=3)
    rep = ctrl.repair(vulnerable, faulty, healthy_scenario=healthy)
    assert rep.status == "FAILURE"
    assert NAN_INF in rep.final_symptoms
    assert "no applicable patch" in rep.reason


def test_repair_catalog_covers_eight_classes():
    """The catalog defines a patch for each of the 8 symptom classes."""
    expected = {SHAPE_MISMATCH, CUDA_OOM, CPU_LEAK, VRAM_LEAK, ASYNC_RACE, NAN_INF,
                GRAD_BREAK, DEADLOCK}
    assert CATALOG_SYMPTOMS == expected


def test_repair_patches_are_pure_config_transforms():
    """Every patch is a pure BiomaConfig→BiomaConfig transform (no blind suppression)."""
    for patch in REPAIR_CATALOG:
        assert isinstance(patch, Patch)
        out = patch.apply(DEFAULT_CONFIG)
        assert isinstance(out, type(DEFAULT_CONFIG))  # returns a config, not an exception swallow


def test_repair_regression_guard_blocks_bad_patch():
    """A patch that regresses the canonical healthy scenario is rejected (FAILURE)."""
    healthy, faulty, vulnerable = _healthy_and_faulty()
    # A deliberately harmful 'patch' that guarantees NaN even on healthy input.
    bad = Patch(
        name="break_everything", symptom=NAN_INF, category="malicious",
        description="regresses the healthy scenario (should be rejected)",
        precondition=lambda c: True,
        transform=lambda c: dataclasses.replace(c, sanitize_input=False, hormone_norm_clamp=0.0),
    )
    ctrl = RepairController(catalog=[bad], max_iter=2)
    # Feed a faulty scenario so NAN_INF is detected and the bad patch is selected.
    rep = ctrl.repair(vulnerable, faulty, healthy_scenario=inject_nan(healthy, rows=2))
    assert rep.status == "FAILURE"


# ============================================================================ #
#  12. Property-based invariants (Hypothesis) — plan Fase 8
# ============================================================================ #
from hypothesis import given, settings, strategies as st  # noqa: E402


@given(steps=st.integers(min_value=1, max_value=8), seed=st.integers(0, 10_000))
@settings(max_examples=12, deadline=None)
def test_property_energy_accounting_always_balances(steps, seed):
    """Invariant: the energy balance always equals initial − burn + regen."""
    torch.manual_seed(seed)
    cell = NeuralOrganism("p", DEFAULT_CONFIG)
    x, ctx = torch.randn(EMBED), torch.zeros(EMBED)
    for _ in range(steps):
        cell.metabolic_step(x, ctx)
        cell.adapt(x, ctx, torch.randn(EMBED))
    assert cell.energy_audit()["balanced"] is True


@given(k=st.integers(min_value=2, max_value=4), seed=st.integers(0, 10_000))
@settings(max_examples=10, deadline=None)
def test_property_mitosis_children_have_independent_storage(k, seed):
    """Invariant: deep-copy mitosis yields children with distinct storage; mutating
    a child never changes the parent (no shared storage / aliasing)."""
    torch.manual_seed(seed)
    parent = NeuralOrganism("stem", DEFAULT_CONFIG)
    parent_before = [p.clone() for p in parent.parameters()]
    children = parent.divide(torch.randn(k, EMBED))
    parent_ptrs = {p.data_ptr() for p in parent.parameters()}
    for child in children:
        for cp in child.parameters():
            assert cp.data_ptr() not in parent_ptrs
    with torch.no_grad():
        for cp in children[0].parameters():
            cp.add_(1.0)
    for a, b in zip(parent.parameters(), parent_before):
        assert torch.equal(a, b)


@given(seed=st.integers(0, 10_000))
@settings(max_examples=10, deadline=None)
def test_property_apoptosis_frees_and_is_idempotent(seed):
    """Invariant: apoptosis reclaims storage, flips alive→False, and is idempotent."""
    torch.manual_seed(seed)
    cell = NeuralOrganism("p", DEFAULT_CONFIG)
    first = cell.apoptose()
    assert cell.alive is False and first["reclaimed_bytes"] > 0
    assert cell.apoptose().get("already_dead") is True


@given(seed=st.integers(0, 10_000))
@settings(max_examples=10, deadline=None)
def test_property_distillation_never_mutates_teacher(seed):
    """Invariant: distilling into a student never breaks/mutates the teacher's graph."""
    torch.manual_seed(seed)
    student = NeuralOrganism("s", DEFAULT_CONFIG)
    teacher = NeuralOrganism("t", DEFAULT_CONFIG)
    before = {k: v.clone() for k, v in teacher.state_dict().items()}
    student.distill_from(teacher, torch.randn(4, EMBED), epochs=5)
    for k, v in teacher.state_dict().items():
        assert torch.equal(before[k], v)


# ============================================================================ #
#  13. Experimental validation (Fase 9) — causal 2×2 + statistics
# ============================================================================ #
from bioma_engine.validation import (  # noqa: E402
    cohens_d, cliffs_delta, holm_bonferroni, power_analysis_n, bootstrap_ci_diff,
    run_factorial, analyze_factorial, logical_reproducibility, final_invariant_audit,
)


def test_statistical_primitives():
    """Effect sizes, correction and power analysis behave correctly."""
    assert cohens_d([2, 3, 2, 3], [1, 0, 1, 0]) > 3.0        # large separation
    assert cliffs_delta([3, 4, 5], [1, 2]) == 1.0            # complete dominance
    adj = holm_bonferroni([0.01, 0.04, 0.03])
    assert abs(adj[0] - 0.03) < 1e-9                         # smallest × m
    assert all(0.0 <= p <= 1.0 for p in adj)
    assert power_analysis_n(0.8) == 25                       # d=0.8 → N≈25/group
    lo, hi = bootstrap_ci_diff([1, 1, 1, 1], [0, 0, 0, 0], reps=500, seed=1)
    assert lo <= 1.0 <= hi


def test_factorial_causal_effects_significant():
    """The 2×2 factorial proves BOTH mechanisms add value after correction."""
    cells = run_factorial(DEFAULT_CONFIG, K=4)
    res = analyze_factorial(cells)
    h1 = next(t for t in res["tests"] if t["hypothesis"] == "H1_mitosis_coverage")
    h2 = next(t for t in res["tests"] if t["hypothesis"] == "H2_bus_cascade")
    # Mitosis materially improves coverage; bus materially improves cascade.
    assert h1["mean_diff"] > 0.2 and h1["significant_after_correction"], h1
    assert h2["mean_diff"] > 0.05 and h2["significant_after_correction"], h2
    # Positive interaction: the bus helps cascade MORE when mitosis is on —
    # now tested with a bootstrap CI, not just a point estimate (finding #8).
    assert res["interaction_cascade"] > 0.0
    assert res["interaction_significant"] is True, res["interaction_ci95"]
    # Effect sizes point the same way (complete separation).
    assert h1["cliffs_delta"] == 1.0 and h2["cliffs_delta"] == 1.0


def test_logical_reproducibility_same_seed():
    """Same seed ⇒ identical decisions/topology/verdict (logical determinism)."""
    rep = logical_reproducibility(DEFAULT_CONFIG, K=4, runs=3)
    assert rep["logically_deterministic"] is True
    assert len(set(rep["signatures"])) == 1


def test_final_invariant_audit_passes():
    """The terminal acceptance certificate passes on all invariants."""
    audit = final_invariant_audit(DEFAULT_CONFIG)
    assert audit["mitosis_decision_accuracy"] == 1.0
    assert audit["leak_free"] and audit["gauge_zero"]
    assert audit["division_deep_copy_independent"] and audit["energy_accounting_balanced"]
    assert audit["all_pass"] is True


# ============================================================================ #
#  14. Hardened core (Fase 1) — genome, deterministic seed, reproducible mutation
# ============================================================================ #
from bioma_engine.organism_core import Genome, derive_child_seed  # noqa: E402


def test_genome_identity_and_lineage():
    """Each cell has a unique UUID, a stable arch signature, and derived lineage."""
    a = NeuralOrganism("stem", DEFAULT_CONFIG)
    b = NeuralOrganism("stem", DEFAULT_CONFIG)
    assert isinstance(a.genome, Genome)
    assert a.genome.id != b.genome.id                       # unique identity
    assert a.genome.arch_signature == b.genome.arch_signature  # same topology
    child = a.divide(torch.randn(2, EMBED))[0]
    assert child.genome.parent_id == "stem"
    assert child.genome.generation == 1


def test_deterministic_child_seed_derivation():
    """Child seeds are a deterministic SHA function of (parent seed, index)."""
    assert derive_child_seed(123, 0) == derive_child_seed(123, 0)
    assert derive_child_seed(123, 0) != derive_child_seed(123, 1)
    assert derive_child_seed(123, 0) != derive_child_seed(124, 0)


def test_mutate_is_reproducible_and_masks_buffers():
    """mutate() is reproducible under a seeded generator and never touches buffers."""
    c1 = NeuralOrganism("s", DEFAULT_CONFIG)
    c2 = NeuralOrganism("s", DEFAULT_CONFIG)
    c2.load_state_dict({k: v.clone() for k, v in c1.state_dict().items()})
    temp_before = c1.temperature.clone()
    spec_before = c1.specialization.clone()
    g1 = torch.Generator().manual_seed(999)
    g2 = torch.Generator().manual_seed(999)
    c1.mutate(generator=g1)
    c2.mutate(generator=g2)
    assert all(torch.equal(p1, p2) for p1, p2 in zip(c1.parameters(), c2.parameters()))
    # Buffers (temperature/specialization) are frozen by the mutability mask.
    assert torch.equal(c1.temperature, temp_before)
    assert torch.equal(c1.specialization, spec_before)


def test_mutate_finiteness_rejection_keeps_params_finite():
    """Even with an extreme mutation rate, no non-finite parameter is ever written."""
    cell = NeuralOrganism("s", DEFAULT_CONFIG)
    cell.mutate(mutation_rate=1e6)
    assert all(torch.isfinite(p).all() for p in cell.parameters())


def test_extract_representation_and_release():
    """extract_representation returns an embed-dim vector; release drops the hooks."""
    cell = NeuralOrganism("s", DEFAULT_CONFIG)
    rep = cell.extract_representation()
    assert rep.shape == (EMBED,)
    cell.release()
    assert len(cell._flops._handles) == 0 and cell._optim is None


# ============================================================================ #
#  Plan Fase 3 — fission hysteresis (double band + EMA + cooldown)
#  Plan Fase 5 — explicit DAG scheduler with a join-counter (pending[p]==0)
# ============================================================================ #
from bioma_engine.mitosis_engine import HysteresisGate, DagScheduler  # noqa: E402


def test_hysteresis_double_band_ema_cooldown():
    """Fission fires only on the rising edge above tau_up, latches, respects a
    cooldown, re-arms below tau_down, then can fire again — no oscillation."""
    g = HysteresisGate(tau_up=0.35, tau_down=0.25, alpha=1.0, cooldown=2)
    # below the upper band → suppressed
    fire0, t0 = g.update("stem", 0.30)
    assert fire0 is False and t0["latched"] is False
    # rising edge above tau_up → single fire, latches, starts cooldown
    fire1, t1 = g.update("stem", 0.50)
    assert fire1 is True and t1["latched"] is True
    # still high but in cooldown → no re-fire (anti-oscillation)
    assert g.update("stem", 0.60)[0] is False   # cooldown 2→1
    assert g.update("stem", 0.60)[0] is False   # cooldown 1→0
    # cooldown expired but still latched (never dropped below tau_down) → no fire
    assert g.update("stem", 0.60)[0] is False
    # fall below tau_down → re-arm (unlatch)
    fire5, t5 = g.update("stem", 0.10)
    assert fire5 is False and t5["latched"] is False
    # rise again above tau_up → fires again (a full hysteresis cycle)
    assert g.update("stem", 0.50)[0] is True
    # contract: tau_up must strictly exceed tau_down
    with pytest.raises(ValueError):
        HysteresisGate(tau_up=0.2, tau_down=0.3)


def test_dag_scheduler_join_counter_and_topological_order():
    """A parent is only ready to reduce when pending==0; reduce order is recorded
    and an unknown parent is a safe no-op."""
    s = DagScheduler()
    s.expect("stem", 2)
    assert s.is_ready("stem") is False          # two children outstanding
    s.child_done("stem")
    assert s.is_ready("stem") is False
    s.child_done("stem")
    assert s.is_ready("stem") is True           # both joined → ready to reduce
    s.mark_reduced("stem")
    # nested progenitor with two grandchildren
    s.expect("p3", 2)
    assert s.pending_total() == 2
    s.child_done("p3"); s.child_done("p3")
    assert s.pending_total() == 0
    s.mark_reduced("p3")
    assert s.reduce_order == ["stem", "p3"]      # children-before-parent order
    s.child_done("ghost")                        # unknown parent → no crash / no effect
    assert s.pending_total() == 0


def test_mitosis_run_respects_join_barrier():
    """A real division completes: the internal `assert pending==0` before every
    reduction (Fase 5) never trips, so synthesis returns without a fault."""
    import asyncio as _aio
    import torch as _t
    from bioma_engine.mitosis_engine import MitosisEngine
    cfg = dataclasses.replace(DEFAULT_CONFIG, fission_mode="difficulty")
    eng = MitosisEngine(cfg)
    emb = _t.randn(24, cfg.embed_dim)            # spread cloud → mitosis fires
    res = _aio.run(eng.synthesize(embeddings=emb, request_id="join"))
    assert "error" not in res and bool(res)


# ============================================================================ #
#  M8 acceptance regression (plan Seção 12) — fast profile guards every change
# ============================================================================ #
from bioma_engine.certify_m8 import certify  # noqa: E402


def test_m8_certificate_stays_accepted_fast():
    """A fast M8 profile must remain ACCEPTED: mitosis/bus causal effects hold,
    CSR=1.0, no leak, reproducible, invariants + autonomy pass."""
    rep = certify(K=4, soak_cycles=8, runs=3)
    failed = [c["name"] for c in rep["criteria"] if c["critical"] and not c["pass"]]
    assert rep["verdict"] == "ACCEPTED", f"failed critical criteria: {failed}"
    assert rep["summary"]["critical_failed"] == 0


if __name__ == "__main__":  # allow `python tests/test_bioma_complete.py`
    import sys
    sys.exit(pytest.main([__file__, "-v"]))
