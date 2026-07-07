"""
B.I.O.M.A. — Biologically Inspired Orchestration of Mutating Agents
==================================================================

`config.py` — Global constants, device policy and the biophysical parameters
that govern the artificial-life simulation.

Every "magic number" that shapes cellular behaviour lives here so that the
metabolism of the whole organism colony can be re-tuned from a single place.
The values are deliberately expressed in biological vocabulary (setpoints,
budgets, drain coefficients) because the rest of the engine reasons about them
that way.

Nothing in this module has side effects beyond selecting a compute device, so
it is safe to import from anywhere (workers, servers, notebooks).
"""

from __future__ import annotations

import os
from dataclasses import dataclass

# --------------------------------------------------------------------------- #
#  OpenMP / MKL threading MUST be pinned BEFORE torch is imported.  We fan out
#  across cells with our own thread pool, so each per-cell tensor op (and every
#  torch.linalg QR/SVD/eig the harness runs) should stay single-threaded.  On
#  Windows the teardown of many idle OpenMP/MKL teams at interpreter exit can
#  fault (STATUS_STACK_BUFFER_OVERRUN / 0xC0000409); pinning to 1 and allowing a
#  duplicate OpenMP runtime avoids that crash.  ``config`` is the first module to
#  import torch, so setting these here covers the whole process.
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

import torch  # noqa: E402  (import after env pinning is intentional)


# --------------------------------------------------------------------------- #
#  Device policy — CUDA when present, graceful CPU fallback otherwise.
#  Every tensor allocation in the engine funnels through `resolve_device` so a
#  GPU host lights up "VRAM" telemetry while a CPU host degrades to RAM without
#  a single code change.
# --------------------------------------------------------------------------- #
def resolve_device(prefer: str | None = None) -> torch.device:
    """Return the best available device, honouring an optional preference.

    Order of resolution:
      1. An explicit ``prefer`` argument ("cuda"/"cpu") if it is actually usable.
      2. The ``BIOMA_DEVICE`` environment variable (same rules).
      3. CUDA if the runtime reports it available.
      4. CPU as the universal fallback.
    """
    candidate = prefer or os.environ.get("BIOMA_DEVICE")
    if candidate:
        candidate = candidate.strip().lower()
        if candidate.startswith("cuda") and torch.cuda.is_available():
            return torch.device(candidate)
        if candidate == "cpu":
            return torch.device("cpu")
    if torch.cuda.is_available():
        return torch.device("cuda")
    return torch.device("cpu")


DEVICE: torch.device = resolve_device()
IS_CUDA: bool = DEVICE.type == "cuda"


@dataclass(frozen=True)
class BiomaConfig:
    """Immutable bundle of every biophysical constant in the simulation.

    A frozen dataclass is used so a running engine cannot accidentally mutate
    the physics of its own universe mid-flight (which would create irreproducible
    telemetry).  Per-request overrides are produced with ``dataclasses.replace``.
    """

    # -- Latent geometry ---------------------------------------------------- #
    embed_dim: int = 128            # dimensionality of every cell's latent space
    vocab_size: int = 1 << 15       # hashing space for the tokenizer (32768)
    hidden_mult: int = 2            # width multiplier inside an organism's MLP

    # -- Manifold / hormonal bus -------------------------------------------- #
    # Three SEPARATE time constants (plan Fase 2, defeito #4): the old single
    # ``hormone_decay`` conflated write blending, vector dissipation and scalar
    # decay.  They are now distinct with documented half-lives.
    manifold_slots: int = 64        # max simultaneously-secreting cells
    write_blend: float = 0.08       # EMA fraction of a *new* secretion folded in per write
    decay_vec: float = 0.90         # per-tick dissipation of manifold hormone VECTORS
    decay_scalar: float = 0.92      # per-tick decay of the scalar endocrine fields
    hormone_norm_clamp: float = 8.0  # c_max: max L2 norm a single secretion may inject
    staleness_ticks: int = 8        # slots older than this are ignored by attention
    attention_temp: float = 0.5     # temperature for hormone-sensing attention
    # Deprecated alias kept for backward-compat; equals decay_scalar. Do not use.
    hormone_decay: float = 0.92

    # -- Mitosis (fission) -------------------------------------------------- #
    divergence_threshold: float = 0.35   # semantic spread above which we divide
    max_children: int = 6                # widest fan-out of a single division
    max_depth: int = 2                   # recursion depth limit for sub-mitosis
    cell_budget: int = 24                # hard ceiling on simultaneously-live cells
    mutation_rate: float = 0.02          # std-dev of Gaussian weight perturbation
    # Fission decision mode (plan Fase 3):
    #   "difficulty"  — divergence+H(X) heuristic (demo path for unstructured text)
    #   "silhouette"  — rigorous cluster-structure detection (for domain-structured
    #                   input; correctly suppresses mitosis on uni-domain / noise)
    fission_mode: str = "difficulty"
    silhouette_threshold: float = 0.15   # min silhouette to accept a k>1 partition
    min_cluster_size: int = 3            # reject partitions with a smaller cluster
    # Fase 3 — hysteresis on the fission trigger (anti-oscillation): fire only on
    # the rising edge above tau_up (EMA-smoothed), re-arm below tau_down, and hold
    # a cooldown after each division.  Contract: tau_up > tau_down.
    hysteresis_tau_up: float = 0.35      # upper band — division fires above this
    hysteresis_tau_down: float = 0.25    # lower band — re-arm below this
    fission_ema_alpha: float = 0.5       # EMA smoothing of the difficulty signal
    fission_cooldown: int = 2            # assessments suppressed after a division
    # Ablation / baseline switches (plan Fase 6 factorial controls):
    mitosis_enabled: bool = True         # False → monolithic baseline (never divides)
    bus_enabled: bool = True             # False → no-hormone baseline (sense→0)

    # Input hygiene (plan Fase 8): sanitize injected embeddings at the boundary.
    # A vulnerable config (False) lets malformed input (NaN/Inf) propagate — the
    # self-correction loop detects the NAN_INF symptom and patches this to True.
    sanitize_input: bool = True

    # -- Metabolism / energy ------------------------------------------------ #
    initial_energy: float = 1_000.0      # ATP granted to the stem cell
    flop_energy_cost: float = 1e-7       # energy burned per FLOP
    token_energy_cost: float = 0.05      # energy burned per processed token
    entropy_drain: float = 4.0           # extra drain per nat of activation entropy
    child_energy_fraction: float = 0.45  # share of parent energy handed to a child

    # -- Homeostasis -------------------------------------------------------- #
    entropy_setpoint: float = 2.0        # target activation entropy (nats)
    homeostasis_gain: float = 0.3        # feedback strength toward the setpoint
    high_stress_entropy: float = 3.2     # entropy above which a cell may re-divide

    # -- Coordination (plan Fase 4): bus-mediated cascade propagation ------- #
    # Each leaf agent updates its committed domain estimate as
    #   estimate_k ← centroid_k + coordination_gamma · (bus attention over peers),
    # a Jacobi iteration for (I − γC)⁻¹P whose coupling C is exactly the bus's
    # attention pattern.  With the bus enabled this recovers the cascade-coupled
    # ground-truth; disabled, the estimate stays at the prototype.
    # Tuned via benchmark_result_quality.py: cascade recovery of S* peaks near
    # γ≈1.7 then collapses (inverted-U as the bus over-weights context); 1.2 is a
    # robust operating point (+38% coordination benefit vs the old 0.6) with a
    # comfortable margin below the collapse.  Coverage is γ-invariant.
    coordination_gamma: float = 1.2

    # -- Energy regeneration by progress (plan Fase 4) ---------------------- #
    energy_basal_decay: float = 0.0      # λ_basal · E per step (0 = off by default)
    progress_regen: float = 60.0         # η: ATP regained per unit of loss-drop (Δutil)
    uncertainty_kappa: float = 4.0       # κ: entropy-drain coefficient (== entropy_drain)

    # -- Metabolic cycles / convergence ------------------------------------- #
    metabolic_cycles: int = 4            # sense→act→secrete iterations per cell
    convergence_target: float = 0.985    # cosine self-similarity that ends the run
    adapt_lr: float = 0.05               # learning-rate of a cell's local adaptation

    # -- Orchestration / scheduler (plan Fase 5) ---------------------------- #
    telemetry_queue_max: int = 1024      # bounded telemetry queue (backpressure)

    # -- Reproducibility ---------------------------------------------------- #
    seed: int = 1337

    # Derived helpers ------------------------------------------------------- #
    @property
    def hidden_dim(self) -> int:
        return self.embed_dim * self.hidden_mult


DEFAULT_CONFIG = BiomaConfig()


def seed_everything(seed: int = DEFAULT_CONFIG.seed) -> None:
    """Make the colony's stochastic biology reproducible across runs.

    Extended (plan Fase 0) to seed ``random`` and ``numpy`` in addition to
    ``torch``, so every stochastic source used across the framework — k-means
    reseeding, AST mutation, Gaussian weight perturbation — is reproducible.
    """
    import random as _random

    _random.seed(seed)
    try:
        import numpy as _np

        _np.random.seed(seed % (2**32 - 1))
    except Exception:
        pass
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


# ---------------------------------------------------------------------------- #
#  Versioned threshold registry (plan Fase 0).  Single source of truth for the
#  acceptance/decision thresholds referenced across phases, so they are auditable
#  and versioned rather than scattered magic numbers.
# ---------------------------------------------------------------------------- #
THRESHOLD_REGISTRY: dict = {
    "version": "1.1.0",
    "divergence_threshold": 0.35,     # Fase 3: difficulty above which mitosis fires
    "hysteresis_tau_up": 0.35,        # Fase 3: upper band of the fission hysteresis
    "hysteresis_tau_down": 0.25,      # Fase 3: lower band (re-arm) — tau_up > tau_down
    "fission_cooldown": 2,            # Fase 3: assessments suppressed after a division
    "snapshot_reuse_floor": 0.30,     # Fase 2: min fraction of sense() reusing a snapshot
    "hormone_norm_clamp": 8.0,        # Fase 2: c_max on secretion norm
    "staleness_ticks": 8,             # Fase 2: attention ignores slots older than this
    "mitosis_precision_floor": 0.90,  # Fase 3: min precision of the fission decision
    "leak_slope_max": 0.05,           # Fase 7: max RSS growth slope (MB/cycle) in soak
    "convergence_target": 0.985,      # cosine self-similarity ending a sub-run
}


# Human-facing labels for the biological telemetry dashboard.
HORMONES = ("cortisol", "dopamine", "adrenaline")  # stress, reward, urgency
LIFECYCLE = ("stem", "dividing", "leaf", "adapting", "apoptotic")
