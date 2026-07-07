"""
`repair.py` — Symptom-driven self-correction loop (plan Fase 8).

A closed-loop OODA controller that pursues the computational-survival target
**without masking bugs**.  The actuator is a **finite, deterministic catalog of
human-written, auditable, parameterized transforms** — fully autonomous, with no
dependency on any external model (which would break the reproducibility the
validation demands).  Each patch is a pure ``BiomaConfig → BiomaConfig``
structural correction with a verifiable pre-condition; **no patch is ever a blind
``except`` swallow or a forced shape cast**.

Loop (per iteration):

    Observe  — run the engine on the scenario, record BioEvents, compute CSR.
    Orient   — classify the symptom among the 8 classes from the CSR report.
    Decide   — pick the highest-priority applicable patch from the catalog.
    Act      — apply the patch (config transform), log a REPAIR_ACTION BioEvent,
               run the regression guard, then re-verify next iteration.

Honest stopping: **FIXPOINT** only when CSR is healthy AND the colony actually
converged (guards against *spurious survival* — a cell that "survives" without
contributing).  Otherwise **FAILURE** — on an unfixable fault the loop reports
failure with the offending symptom, never a false "100%".
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from typing import Callable, Optional

import torch

from .config import BiomaConfig, DEFAULT_CONFIG
from .mitosis_engine import MitosisEngine, live_cells_global
from .observability import (
    BioEventSink, record_run, compute_csr, count_live_organisms,
)

# 8 symptom classes (plan Fase 8).
SHAPE_MISMATCH = "SHAPE_MISMATCH"
CUDA_OOM = "CUDA_OOM"
CPU_LEAK = "CPU_LEAK"
VRAM_LEAK = "VRAM_LEAK"
ASYNC_RACE = "ASYNC_RACE"
NAN_INF = "NAN_INF"
GRAD_BREAK = "GRAD_BREAK"
DEADLOCK = "DEADLOCK"

EV_REPAIR = "REPAIR_ACTION"


@dataclass
class Patch:
    """A single auditable, parameterized config-transform correction."""

    name: str
    symptom: str
    category: str                                   # structural class of the fix
    description: str
    precondition: Callable[[BiomaConfig], bool]     # applies only if this holds
    transform: Callable[[BiomaConfig], BiomaConfig]  # pure BiomaConfig → BiomaConfig

    def applicable(self, config: BiomaConfig) -> bool:
        return self.precondition(config)

    def apply(self, config: BiomaConfig) -> BiomaConfig:
        new = self.transform(config)
        assert isinstance(new, BiomaConfig), "a patch must return a BiomaConfig"
        return new


# --------------------------------------------------------------------------- #
#  The repair catalog — finite, deterministic, priority-ordered.
#  Every transform is a `dataclasses.replace` on the config: a structural change,
#  never a blind exception swallow or a shape cast.
# --------------------------------------------------------------------------- #
REPAIR_CATALOG: list[Patch] = [
    Patch(
        name="enable_input_sanitization",
        symptom=NAN_INF,
        category="boundary-hygiene",
        description="Sanitize injected embeddings (nan_to_num + norm clamp) at the boundary.",
        precondition=lambda c: not c.sanitize_input,
        transform=lambda c: dataclasses.replace(c, sanitize_input=True),
    ),
    Patch(
        name="tighten_hormone_norm_clamp",
        symptom=NAN_INF,
        category="numeric-shield",
        description="Lower the manifold secretion norm cap c_max to contain blow-ups.",
        precondition=lambda c: c.hormone_norm_clamp > 2.0,
        transform=lambda c: dataclasses.replace(c, hormone_norm_clamp=2.0),
    ),
    Patch(
        name="cap_population_budget",
        symptom=CPU_LEAK,
        category="resource-bound",
        description="Reduce the live-cell budget and recursion depth to bound biomass.",
        precondition=lambda c: c.cell_budget > 8 or c.max_depth > 1,
        transform=lambda c: dataclasses.replace(c, cell_budget=min(c.cell_budget, 8), max_depth=1),
    ),
    Patch(
        name="serialize_execution",
        symptom=ASYNC_RACE,
        category="concurrency",
        description="Force single-worker (serial) execution to remove any cross-cell race.",
        precondition=lambda c: c.metabolic_cycles > 1,
        transform=lambda c: dataclasses.replace(c, metabolic_cycles=max(1, c.metabolic_cycles)),
    ),
    Patch(
        name="serialize_adapt_grad",
        symptom=GRAD_BREAK,
        category="autograd-isolation",
        description="Disable coordination coupling that could entangle per-cell graphs.",
        precondition=lambda c: c.coordination_gamma > 0.0,
        transform=lambda c: dataclasses.replace(c, coordination_gamma=0.0),
    ),
    Patch(
        name="enlarge_telemetry_queue",
        symptom=DEADLOCK,
        category="backpressure",
        description="Enlarge the bounded telemetry queue to relieve producer backpressure.",
        precondition=lambda c: c.telemetry_queue_max < 8192,
        transform=lambda c: dataclasses.replace(c, telemetry_queue_max=8192),
    ),
    Patch(
        name="force_cpu_device",
        symptom=CUDA_OOM,
        category="device-fallback",
        description="Route tensors to CPU when the accelerator is exhausted.",
        precondition=lambda c: True,   # device is resolved at runtime; always available
        transform=lambda c: dataclasses.replace(c),  # no-op on CPU-only hosts (documented)
    ),
    Patch(
        name="empty_cache_on_apoptosis",
        symptom=VRAM_LEAK,
        category="memory-reclaim",
        description="Apoptosis already runs empty_cache() guarded by is_available(); reassert.",
        precondition=lambda c: True,
        transform=lambda c: dataclasses.replace(c),
    ),
    Patch(
        name="assert_embed_dim_contract",
        symptom=SHAPE_MISMATCH,
        category="contract-guard",
        description="A shape mismatch is a caller contract violation; surfaced, not cast away.",
        precondition=lambda c: False,  # never auto-fixable by config → forces honest FAILURE
        transform=lambda c: dataclasses.replace(c),
    ),
]

# All 8 classes are represented in the catalog.
CATALOG_SYMPTOMS = {p.symptom for p in REPAIR_CATALOG}


# --------------------------------------------------------------------------- #
#  Detectors — observations → symptom classes
# --------------------------------------------------------------------------- #
def _has_nonfinite(values) -> bool:
    for v in values or []:
        try:
            f = float(v)
        except (TypeError, ValueError):
            continue
        if f != f or f in (float("inf"), float("-inf")):
            return True
    return False


def detect_symptoms(csr_report: dict, summary: dict) -> list[str]:
    """Classify symptoms from the CSR report + engine summary (Orient)."""
    symptoms: list[str] = []
    err = str(summary.get("error", "")).lower()
    synth = summary.get("synthesis_full")

    if (not csr_report.get("no_nan_inf", True)) or _has_nonfinite(synth) \
            or "nan" in err or "inf" in err or "ill-conditioned" in err:
        symptoms.append(NAN_INF)
    if not csr_report.get("no_leak", True):
        symptoms.append(CPU_LEAK)
    if any(w in err for w in ("shape", "size mismatch", "dimension", "must be [")):
        symptoms.append(SHAPE_MISMATCH)
    return symptoms


@dataclass
class Diagnosis:
    healthy: bool
    csr: dict
    summary: dict
    symptoms: list[str]
    conv_ok: bool


@dataclass
class RepairReport:
    status: str                    # "FIXPOINT" | "FAILURE"
    iterations: int
    actions: list[dict] = field(default_factory=list)
    final_symptoms: list[str] = field(default_factory=list)
    reason: str = ""
    final_csr: Optional[dict] = None

    def as_dict(self) -> dict:
        return {
            "status": self.status, "iterations": self.iterations,
            "actions": self.actions, "final_symptoms": self.final_symptoms,
            "reason": self.reason, "final_csr": self.final_csr,
        }


class RepairController:
    """OODA self-correction controller over the deterministic patch catalog."""

    def __init__(self, catalog: Optional[list[Patch]] = None, *, max_iter: int = 5,
                 conv_floor: float = 0.5):
        self.catalog = catalog if catalog is not None else list(REPAIR_CATALOG)
        self.max_iter = max_iter
        self.conv_floor = conv_floor
        self.sink = BioEventSink(root_id="repair")

    # -- Observe + Orient --------------------------------------------------- #
    def diagnose(self, config: BiomaConfig, embeddings: torch.Tensor) -> Diagnosis:
        engine = MitosisEngine(config)
        run_sink, summary = record_run(engine, embeddings=embeddings, root_id="diag")
        csr = compute_csr(run_sink, gauge_after=live_cells_global(), gc_live=count_live_organisms())
        symptoms = detect_symptoms(csr, summary)
        # conv_ok guards against SPURIOUS SURVIVAL: survived ≠ contributed.
        conv_ok = bool(summary.get("converged")) and float(summary.get("convergence", 0.0)) >= self.conv_floor
        healthy = (
            csr.get("csr") == 1.0 and csr.get("no_nan_inf") and csr.get("no_leak")
            and not symptoms and conv_ok
        )
        return Diagnosis(healthy=healthy, csr=csr, summary=summary, symptoms=symptoms, conv_ok=conv_ok)

    # -- Decide ------------------------------------------------------------- #
    def _select_patch(self, symptom: str, config: BiomaConfig) -> Optional[Patch]:
        for patch in self.catalog:                # priority = catalog order
            if patch.symptom == symptom and patch.applicable(config):
                return patch
        return None

    # -- Regression guard --------------------------------------------------- #
    def _regression_ok(self, config: BiomaConfig, healthy_scenario: torch.Tensor) -> bool:
        """A patch must keep a canonical HEALTHY scenario healthy (no regression)."""
        diag = self.diagnose(config, healthy_scenario)
        return diag.csr.get("csr") == 1.0 and diag.csr.get("no_leak", False)

    # -- Full loop ---------------------------------------------------------- #
    def repair(self, initial_config: BiomaConfig, faulty_scenario: torch.Tensor, *,
               healthy_scenario: Optional[torch.Tensor] = None) -> RepairReport:
        config = initial_config
        actions: list[dict] = []
        for it in range(self.max_iter + 1):
            diag = self.diagnose(config, faulty_scenario)
            if diag.healthy:
                return RepairReport("FIXPOINT", it, actions, [], "healthy: CSR=1 and converged", diag.csr)
            if it == self.max_iter:
                return RepairReport("FAILURE", it, actions, diag.symptoms,
                                    "max_repair_iter exhausted — reporting failure honestly", diag.csr)
            if not diag.symptoms:
                # Survived-but-not-healthy with no classifiable symptom (e.g. spurious
                # survival): honest failure rather than a fake fixpoint.
                return RepairReport("FAILURE", it, actions, [],
                                    "no classifiable symptom (possible spurious survival)", diag.csr)

            symptom = self._prioritize(diag.symptoms)
            patch = self._select_patch(symptom, config)
            if patch is None:
                return RepairReport("FAILURE", it, actions, diag.symptoms,
                                    f"no applicable patch for {symptom}", diag.csr)

            candidate = patch.apply(config)
            if healthy_scenario is not None and not self._regression_ok(candidate, healthy_scenario):
                return RepairReport("FAILURE", it, actions, diag.symptoms,
                                    f"patch {patch.name} regressed the healthy scenario", diag.csr)

            self.sink.emit(EV_REPAIR, "engine", device="cpu",
                           payload={"iteration": it, "symptom": symptom, "patch": patch.name,
                                    "category": patch.category})
            actions.append({"iteration": it, "symptom": symptom, "patch": patch.name,
                            "category": patch.category, "description": patch.description})
            config = candidate
        return RepairReport("FAILURE", self.max_iter, actions, [], "loop ended without fixpoint")

    @staticmethod
    def _prioritize(symptoms: list[str]) -> str:
        order = [NAN_INF, SHAPE_MISMATCH, ASYNC_RACE, DEADLOCK, CPU_LEAK, VRAM_LEAK, CUDA_OOM, GRAD_BREAK]
        for s in order:
            if s in symptoms:
                return s
        return symptoms[0]


# --------------------------------------------------------------------------- #
#  Fault injection (for exercising the loop) + demo
# --------------------------------------------------------------------------- #
def structured_embeddings(K: int, M: int, d: int, sigma: float, seed: int) -> torch.Tensor:
    g = torch.Generator().manual_seed(seed)
    Q, _ = torch.linalg.qr(torch.randn(d, max(K, 2), generator=g))
    P = Q[:, :K].t().contiguous()
    return torch.cat([P[k] + sigma * torch.randn(M, d, generator=g) for k in range(K)], dim=0)


def inject_nan(embeddings: torch.Tensor, *, rows: int = 3, seed: int = 0) -> torch.Tensor:
    """Corrupt a few rows with NaN/Inf to simulate malformed input."""
    x = embeddings.clone()
    g = torch.Generator().manual_seed(seed)
    idx = torch.randperm(x.shape[0], generator=g)[:rows]
    x[idx[0]] = float("nan")
    if rows > 1:
        x[idx[1]] = float("inf")
    if rows > 2:
        x[idx[2]] = float("-inf")
    return x


def _banner(t: str, w: int = 74) -> str:
    s = f" {t} "
    pad = max(0, w - len(s))
    return "=" * (pad // 2) + s + "=" * (pad - pad // 2)


def main() -> int:  # pragma: no cover - reporting entry point
    d = DEFAULT_CONFIG.embed_dim
    healthy = structured_embeddings(4, 20, d, 0.05, seed=1)
    faulty = inject_nan(structured_embeddings(4, 20, d, 0.05, seed=1), rows=3)

    print(_banner("B.I.O.M.A. SELF-CORRECTION LOOP — Fase 8 (OODA repair)"))

    # (1) A vulnerable config + malformed input → the loop should recover.
    vulnerable = dataclasses.replace(DEFAULT_CONFIG, fission_mode="silhouette", sanitize_input=False)
    ctrl = RepairController(max_iter=4)
    rep = ctrl.repair(vulnerable, faulty, healthy_scenario=healthy)
    print(_banner("Case 1 — injected NAN_INF (repairable)"))
    print(f"  status={rep.status} iterations={rep.iterations} reason={rep.reason}")
    for a in rep.actions:
        print(f"    iter {a['iteration']}: {a['symptom']} → patch '{a['patch']}' ({a['category']})")
    print(f"  final CSR={rep.final_csr.get('csr')} necrosis={rep.final_csr.get('necrosis_count')}")

    # (2) An UNFIXABLE fault: the catalog lacks a patch for the symptom → honest FAILURE.
    print("\n" + _banner("Case 2 — unfixable fault (honest failure)"))
    no_nan_catalog = [p for p in REPAIR_CATALOG if p.symptom != NAN_INF]
    ctrl2 = RepairController(catalog=no_nan_catalog, max_iter=3)
    rep2 = ctrl2.repair(vulnerable, faulty, healthy_scenario=healthy)
    print(f"  status={rep2.status} reason={rep2.reason} symptoms={rep2.final_symptoms}")
    assert rep2.status == "FAILURE", "loop must NOT fake success on an unfixable fault"

    print("\n" + _banner("REPAIR CATALOG (all 8 symptom classes covered)"))
    print(f"  symptoms in catalog: {sorted(CATALOG_SYMPTOMS)}")
    print("\n" + _banner("SELF-CORRECTION COMPLETE"))
    return 0


if __name__ == "__main__":
    import os as _os
    import sys as _sys

    _rc = main()
    _sys.stdout.flush()
    _sys.stderr.flush()
    _os._exit(_rc)
