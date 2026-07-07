"""
`mitosis_engine.py` — The Stem-Cell Orchestrator.

This module is the brain-stem of B.I.O.M.A.  It:

1. **embeds** an incoming prompt into per-token latent vectors (a deterministic,
   offline, hash-based embedder — no downloads, no external API);
2. measures the **semantic divergence** of that cloud of vectors;
3. if the divergence crosses the informational threshold, performs **mitosis** —
   k-means clusters the prompt into localized sub-domains and the stem cell
   divides into one specialised mini-agent per cluster;
4. runs every mini-agent **asynchronously** (heavy tensor compute is offloaded to
   a bounded ``ThreadPoolExecutor`` while manifold coordination stays on the
   event loop), letting them collaborate through the :class:`HormonalBus`;
5. lets a stressed sub-agent recursively **re-divide**, bounded by depth and a
   colony-wide cell budget;
6. on completion transfers each mini-agent's learned representation back to its
   parent and triggers **apoptosis** (memory reclaim);
7. **synthesises** the surviving stem cell's inherited memory into a final answer
   and reports a convergence metric.

Concurrency isolation
---------------------
All mutable per-request state lives in a :class:`Colony` object created fresh
inside :meth:`MitosisEngine.run`.  Two concurrent requests therefore operate on
completely disjoint DAGs, buses and cell registries — the dynamic sub-graph of
one request can never bleed into another.  Only the *stateless* prompt embedder
and the bounded thread pool are shared, both of which are read-only/safe under
concurrency.
"""

from __future__ import annotations

import asyncio
import atexit
import functools
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import AsyncIterator, Optional

import networkx as nx
import torch
import torch.nn as nn
import torch.nn.functional as F

try:
    import psutil
except Exception:  # pragma: no cover - psutil is a hard dep but degrade gracefully
    psutil = None

from .config import BiomaConfig, DEFAULT_CONFIG, DEVICE, seed_everything
from .hormonal_bus import HormonalBus
from .organism_core import NeuralOrganism
from .telemetry import (
    TelemetryEvent,
    KIND_GENESIS,
    KIND_DIVERGENCE,
    KIND_MITOSIS,
    KIND_FORWARD,
    KIND_SECRETE,
    KIND_SENSE,
    KIND_HOMEOSTASIS,
    KIND_ADAPT,
    KIND_APOPTOSIS,
    KIND_SYNTHESIS,
    KIND_CONVERGENCE,
    KIND_ERROR,
)


# We fan out across *cells* with the thread pool below, so each individual
# per-cell tensor op should stay single-threaded.  Letting every tiny matmul
# also spin up an OpenMP intra-op team would (a) oversubscribe the CPU
# (workers × intra-op threads) and (b) — critically on Windows — make the
# OpenMP runtime fault while tearing those idle teams down at interpreter exit
# (STATUS_STACK_BUFFER_OVERRUN / 0xC0000409).  One intra-op thread per op is
# both faster for these small (≤256-wide) matmuls and clean to shut down.
torch.set_num_threads(1)

# A single bounded pool shared across requests keeps total CPU/thread pressure
# under control no matter how many organisms spawn.  Disjoint cells never touch
# the same tensors, so parallel execution here is race-free by construction.
_MAX_WORKERS = max(2, min(8, (os.cpu_count() or 4) - 2))
_EXECUTOR = ThreadPoolExecutor(max_workers=_MAX_WORKERS, thread_name_prefix="bioma-cell")


@atexit.register
def _shutdown_executor() -> None:
    """Deterministically drain the pool before the interpreter finalizes torch."""
    _EXECUTOR.shutdown(wait=True, cancel_futures=True)


# Process-wide gauge of currently-living cells across *all* concurrent colonies,
# so the server's /health endpoint can report the true biomass under load.
_LIVE_LOCK = threading.Lock()
_LIVE_CELLS = 0


def _adjust_live(delta: int) -> None:
    global _LIVE_CELLS
    with _LIVE_LOCK:
        _LIVE_CELLS = max(0, _LIVE_CELLS + delta)


def live_cells_global() -> int:
    """Total living mini-agents across every in-flight request right now."""
    with _LIVE_LOCK:
        return _LIVE_CELLS


class BudgetSemaphore:
    """Cooperative, single-loop budget gate (plan Fase 5).

    The old ``live_count() + 2 <= cell_budget`` check was a **cooperative race**:
    sibling coroutines in a ``gather``/``TaskGroup`` could each pass the check and
    then divide, together overshooting ``cell_budget``.  This gate closes it with
    a *reserve-before-divide* protocol.  Because everything here runs on the
    single asyncio event loop and ``try_reserve`` performs its check-and-decrement
    **without any await in between**, the reservation is atomic with respect to
    sibling coroutines — the exact property the plan's ``asyncio.Semaphore`` buys,
    implemented directly for the cooperative model (Section 7).
    """

    def __init__(self, capacity: int) -> None:
        self.capacity = int(capacity)
        self.used = 0

    def available(self) -> int:
        return self.capacity - self.used

    def try_reserve(self, n: int) -> bool:
        """Atomically reserve ``n`` permits if available. Returns success."""
        if n <= 0:
            return True
        if self.used + n <= self.capacity:
            self.used += n
            return True
        return False

    def release(self, n: int = 1) -> None:
        self.used = max(0, self.used - n)


class HysteresisGate:
    """Double-band fission trigger with EMA smoothing + cooldown (plan Fase 3).

    Prevents fission↔apoptosis oscillation.  A cell fires **only on the rising
    edge** when its EMA-smoothed difficulty crosses the UPPER band ``tau_up``; it
    then *latches* and will not re-fire until the signal falls below the LOWER
    band ``tau_down`` and rises again.  After each fire a ``cooldown`` suppresses
    re-triggering for a number of assessments.  Contract: ``tau_up > tau_down``.
    """

    def __init__(self, tau_up: float, tau_down: float, alpha: float = 0.5, cooldown: int = 2):
        if not (tau_up > tau_down):
            raise ValueError(f"hysteresis requires tau_up > tau_down, got {tau_up} <= {tau_down}")
        self.tau_up = float(tau_up)
        self.tau_down = float(tau_down)
        self.alpha = float(alpha)
        self.cooldown = int(cooldown)
        self._ema: dict[str, float] = {}
        self._latched: dict[str, bool] = {}
        self._cool: dict[str, int] = {}

    def update(self, cid: str, signal: float) -> tuple[bool, dict]:
        """Feed one difficulty sample for cell ``cid``; return (fire?, telemetry)."""
        prev = self._ema.get(cid)
        ema = float(signal) if prev is None else self.alpha * float(signal) + (1.0 - self.alpha) * prev
        self._ema[cid] = ema
        latched = self._latched.get(cid, False)
        cool = self._cool.get(cid, 0)
        fire = False
        if cool > 0:
            self._cool[cid] = cool - 1                      # cooling down → suppress
        elif not latched and ema >= self.tau_up:
            latched = True
            fire = True                                     # rising edge above upper band
            self._cool[cid] = self.cooldown
        elif latched and ema <= self.tau_down:
            latched = False                                 # fell below lower band → re-arm
        self._latched[cid] = latched
        return fire, {"ema": round(ema, 4), "latched": latched,
                      "cooldown_left": self._cool.get(cid, 0),
                      "tau_up": self.tau_up, "tau_down": self.tau_down}


class DagScheduler:
    """Explicit topological scheduler with a per-parent join-counter (plan Fase 5).

    A parent's reduction (synthesis / upward transfer) is admitted **only when
    ``pending[parent] == 0``** — every child subtree has completed.  Making the
    join-counter explicit turns the "reduce-after-children" ordering into a
    checkable invariant, and the reduce order is recorded for verification."""

    def __init__(self) -> None:
        self._pending: dict[str, int] = {}
        self._done: dict[str, int] = {}
        self.reduce_order: list[str] = []

    def expect(self, parent: str, n: int) -> None:
        self._pending[parent] = self._pending.get(parent, 0) + int(n)

    def child_done(self, parent: Optional[str]) -> None:
        if parent is not None and parent in self._pending:
            self._pending[parent] -= 1
            self._done[parent] = self._done.get(parent, 0) + 1

    def is_ready(self, parent: str) -> bool:
        return self._pending.get(parent, 0) <= 0

    def mark_reduced(self, parent: str) -> None:
        self.reduce_order.append(parent)

    def pending_total(self) -> int:
        return sum(max(0, v) for v in self._pending.values())


def resource_snapshot() -> dict:
    """VRAM (CUDA) or RAM (CPU) usage snapshot for health/telemetry."""
    if torch.cuda.is_available():
        return {
            "backend": "cuda",
            "allocated_mb": round(torch.cuda.memory_allocated() / 1e6, 3),
            "reserved_mb": round(torch.cuda.memory_reserved() / 1e6, 3),
        }
    if psutil is not None:
        proc = psutil.Process()
        vm = psutil.virtual_memory()
        return {
            "backend": "cpu",
            "rss_mb": round(proc.memory_info().rss / 1e6, 3),
            "available_mb": round(vm.available / 1e6, 3),
            "percent": vm.percent,
        }
    return {"backend": "cpu", "rss_mb": -1.0, "available_mb": -1.0, "percent": -1.0}


# --------------------------------------------------------------------------- #
#  Deterministic, offline prompt embedder
# --------------------------------------------------------------------------- #
class PromptEmbedder(nn.Module):
    """Hash-based tokenizer + fixed random embedding table.

    Fully offline and deterministic (seeded), so the whole simulation is
    reproducible and needs no model downloads.  The embedding table is frozen —
    it is the colony's shared "sensory cortex", never trained.
    """

    _SPLIT = str.maketrans({c: " " for c in ",.;:!?()[]{}\"'`/\\|<>@#$%^&*+=~\n\t"})

    def __init__(self, config: BiomaConfig = DEFAULT_CONFIG, device: Optional[torch.device] = None):
        super().__init__()
        self.config = config
        self.device = device or DEVICE
        g = torch.Generator().manual_seed(config.seed)
        table = torch.randn(config.vocab_size, config.embed_dim, generator=g)
        table = F.normalize(table, dim=1)
        self.register_buffer("table", table)
        self.to(self.device)

    @staticmethod
    def _token_id(token: str, vocab: int) -> int:
        # Stable, process-independent hash (Python's built-in hash is salted).
        import hashlib

        digest = hashlib.md5(token.encode("utf-8")).digest()
        return int.from_bytes(digest[:4], "little") % vocab

    def tokenize(self, prompt: str) -> list[str]:
        cleaned = prompt.lower().translate(self._SPLIT)
        toks = [t for t in cleaned.split() if t]
        return toks or ["<empty>"]

    @torch.no_grad()
    def embed(self, prompt: str) -> tuple[torch.Tensor, list[str]]:
        """Return ``([n_tokens, embed_dim] embeddings, tokens)``."""
        tokens = self.tokenize(prompt)
        ids = torch.tensor(
            [self._token_id(t, self.config.vocab_size) for t in tokens],
            dtype=torch.long,
            device=self.device,
        )
        return self.table[ids], tokens


# --------------------------------------------------------------------------- #
#  Pure-tensor analytics: divergence + k-means
# --------------------------------------------------------------------------- #
def semantic_divergence(embeddings: torch.Tensor) -> float:
    """Spread of a token-embedding cloud around its centroid, in ``[0, 1]``.

    ``0`` means every token points the same way (a mono-domain prompt); values
    approaching ``1`` mean the tokens fan out across unrelated directions (a
    multi-domain prompt that warrants specialised sub-agents).
    """
    if embeddings.shape[0] < 2:
        return 0.0
    centroid = embeddings.mean(dim=0, keepdim=True)
    sims = F.cosine_similarity(embeddings, centroid.expand_as(embeddings), dim=1)
    return float((1.0 - sims.mean()).clamp(0.0, 1.0).item())


def workload_entropy(embeddings: torch.Tensor) -> float:
    """Normalized spectral entropy ``H(X)`` of the token-embedding workload, in ``[0, 1]``.

    We take the eigenspectrum of the (centered) embedding covariance and treat
    the normalized eigenvalues as a probability distribution — a von-Neumann /
    effective-rank style entropy.  Low ``H`` means the workload collapses onto a
    few dominant directions (an easy, mono-facet task); high ``H`` means it
    spreads energy across many independent directions (a hard, multi-domain task
    that warrants more parallel compute).  This is the signal that makes mitosis
    *entropy-aware*: the number of leaf micro-agents scales with ``H(X)``.
    """
    n = embeddings.shape[0]
    if n < 2:
        return 0.0
    x = embeddings - embeddings.mean(dim=0, keepdim=True)
    # Degenerate guard: (near-)identical tokens have zero spread → entropy 0.
    # This also avoids feeding a rank-deficient/zero matrix to the decomposition.
    if float(x.abs().max().item()) < 1e-6:
        return 0.0
    # Use singular values of the centered data (robust) instead of eigvalsh of
    # the covariance, which can raise _LinAlgError on ill-conditioned inputs.
    # s_i^2 are proportional to the covariance eigenvalues → same spectral entropy.
    try:
        s = torch.linalg.svdvals(x)
    except Exception:
        return 0.0
    power = s ** 2
    total = power.sum()
    if float(total.item()) <= 1e-12:
        return 0.0
    p = power / total
    p = p[p > 1e-12]
    entropy = -(p * p.log()).sum()
    # Normalize by the maximum possible entropy (uniform over the component count).
    max_entropy = torch.log(torch.tensor(float(p.numel()), device=embeddings.device)).clamp_min(1e-9)
    return float((entropy / max_entropy).clamp(0.0, 1.0).item())


def kmeans(x: torch.Tensor, k: int, iters: int = 12) -> tuple[torch.Tensor, torch.Tensor, float]:
    """Minimal, robust Lloyd's k-means with empty-cluster reseeding.

    Returns ``(centroids [k, d], assignments [n], inertia)``.
    """
    n = x.shape[0]
    k = max(1, min(k, n))
    # k-means++-ish seeding: first centroid random, rest by farthest point.
    idx0 = int(torch.randint(0, n, (1,)).item())
    centroids = x[idx0:idx0 + 1].clone()
    while centroids.shape[0] < k:
        d = torch.cdist(x, centroids).min(dim=1).values
        centroids = torch.cat([centroids, x[int(d.argmax().item())].unsqueeze(0)], dim=0)

    assign = torch.zeros(n, dtype=torch.long, device=x.device)
    for _ in range(iters):
        dists = torch.cdist(x, centroids)          # [n, k]
        assign = dists.argmin(dim=1)
        new = centroids.clone()
        for j in range(k):
            mask = assign == j
            if bool(mask.any()):
                new[j] = x[mask].mean(dim=0)
            else:
                new[j] = x[int(torch.randint(0, n, (1,)).item())]
        shift = float((new - centroids).norm().item())
        centroids = new
        if shift < 1e-5:
            break
    inertia = float(torch.cdist(x, centroids).min(dim=1).values.mean().item())
    return centroids, assign, inertia


def silhouette_score(x: torch.Tensor, assign: torch.Tensor, k: int, min_cluster_size: int = 1) -> float:
    """Mean silhouette of a partition, in ``[-1, 1]`` (higher = better separated).

    Returns ``-1.0`` if any cluster is smaller than ``min_cluster_size`` (rejects
    spurious singleton partitions on small samples).  Silhouette ~0 for a single
    blob / isotropic noise and high for genuinely separated clusters, which is
    what makes it a well-conditioned fission signal (plan Fase 3).
    """
    if k < 2 or x.shape[0] < 2 * k:
        return -1.0
    for c in range(k):
        if int((assign == c).sum().item()) < min_cluster_size:
            return -1.0
    d = torch.cdist(x, x)
    n = x.shape[0]
    scores = []
    for i in range(n):
        ci = int(assign[i].item())
        same = assign == ci
        same[i] = False
        a = float(d[i, same].mean().item()) if bool(same.any()) else 0.0
        b = float("inf")
        for c in range(k):
            if c == ci:
                continue
            m = assign == c
            if bool(m.any()):
                b = min(b, float(d[i, m].mean().item()))
        if b == float("inf"):
            continue
        scores.append((b - a) / max(a, b, 1e-9))
    return sum(scores) / len(scores) if scores else -1.0


def select_k_silhouette(
    x: torch.Tensor, k_max: int, *, min_cluster_size: int = 3, threshold: float = 0.15
) -> tuple[int, float, dict]:
    """Choose the number of clusters by silhouette (rigorous fission decision).

    Sweeps ``k`` in ``2..k_max`` and picks the ``k`` with the highest silhouette.
    Returns ``(k, silhouette, per_k)`` where ``k == 1`` (no division) if no
    partition clears ``threshold`` — the honest suppression of mitosis on
    uni-domain / unstructured input.
    """
    n = x.shape[0]
    per_k: dict = {}
    best_k, best_sil = 1, -1.0
    upper = max(2, min(k_max, n // max(1, min_cluster_size)))
    for k in range(2, upper + 1):
        _, assign, _ = kmeans(x, k)
        sil = silhouette_score(x, assign, k, min_cluster_size=min_cluster_size)
        per_k[k] = round(sil, 4)
        if sil > best_sil:
            best_sil, best_k = sil, k
    if best_sil < threshold:
        return 1, best_sil, per_k
    return best_k, best_sil, per_k


# --------------------------------------------------------------------------- #
#  Per-request colony context (isolation boundary)
# --------------------------------------------------------------------------- #
@dataclass
class Colony:
    """All mutable state for a single ``run`` — the isolation unit."""

    request_id: str
    config: BiomaConfig
    device: torch.device
    bus: HormonalBus
    dag: nx.DiGraph
    queue: "asyncio.Queue[Optional[TelemetryEvent]]"
    cells: dict[str, NeuralOrganism] = field(default_factory=dict)
    transferred: list[torch.Tensor] = field(default_factory=list)
    centroids: Optional[torch.Tensor] = None  # k-means centroids of the division
    k_chosen: int = 1                          # number of clusters the stem forked into
    estimates: dict = field(default_factory=dict)      # cell_id → live domain estimate
    reconstructions: list = field(default_factory=list)  # final per-domain estimates (coordinated)
    death_triggers: dict = field(default_factory=dict)   # apoptosis FSM trigger tally
    # Exactly-once global-gauge accounting: a cell id is added to ``counted`` when
    # its +1 lands, and moved to ``retired`` when its single -1 fires.  This makes
    # the process-wide gauge robust to sibling-cancellation races (a cell can
    # never be decremented twice, nor leaked).
    counted: set[str] = field(default_factory=set)
    retired: set[str] = field(default_factory=set)
    budget: Optional["BudgetSemaphore"] = None  # reserve-before-divide gate (Fase 5)
    t0: float = field(default_factory=time.time)
    # Aggregate telemetry counters.
    peak_cells: int = 0
    total_mitosis: int = 0
    total_apoptosis: int = 0
    total_flops: float = 0.0
    total_burn: float = 0.0
    scheduler: "DagScheduler" = field(default_factory=DagScheduler)  # join-counter (Fase 5)
    hysteresis: Optional["HysteresisGate"] = None                    # fission latch (Fase 3)

    def live_count(self) -> int:
        return sum(1 for c in self.cells.values() if c.alive)

    def register_cell(self, cell: NeuralOrganism, parent_id: Optional[str]) -> None:
        self.cells[cell.cell_id] = cell
        self.dag.add_node(cell.cell_id, generation=cell.generation, lineage=cell.lineage)
        if parent_id is not None:
            self.dag.add_edge(parent_id, cell.cell_id)
        self.bus.register(cell.cell_id)  # may raise if manifold saturated — before +1
        _adjust_live(+1)
        self.counted.add(cell.cell_id)
        self.peak_cells = max(self.peak_cells, self.live_count())


class MitosisEngine:
    """Stem-cell orchestrator.  One instance can serve many requests: every
    call to :meth:`run` builds its own :class:`Colony`, so state never leaks."""

    def __init__(self, config: BiomaConfig = DEFAULT_CONFIG, device: Optional[torch.device] = None):
        self.config = config
        self.device = device or DEVICE
        seed_everything(config.seed)
        # The sensory cortex is stateless/read-only → safe to share across runs.
        self.embedder = PromptEmbedder(config, self.device)
        self.last_result: Optional[dict] = None

    # ------------------------------------------------------------------ #
    #  Public streaming API
    # ------------------------------------------------------------------ #
    async def run(
        self,
        prompt: Optional[str] = None,
        request_id: str = "req",
        *,
        embeddings: Optional[torch.Tensor] = None,
    ) -> AsyncIterator[TelemetryEvent]:
        """Stream :class:`TelemetryEvent`\\ s describing the whole cellular run.

        Either a text ``prompt`` (embedded by the hash cortex) or a pre-computed
        ``embeddings`` tensor ``[N, embed_dim]`` may be injected — the latter is
        the stimulus-injection path used by the simulation harness (Fase 6).

        The producer coroutine drives the simulation and pushes events onto a
        queue; this generator drains the queue so callers see events in real time.
        """
        if embeddings is not None:
            emb = embeddings.detach().to(self.device)
            if emb.dim() != 2 or emb.shape[0] < 1 or emb.shape[1] != self.config.embed_dim:
                raise ValueError(
                    f"Injected embeddings must be [N>=1, {self.config.embed_dim}], got {list(emb.shape)}"
                )
            if self.config.sanitize_input:
                # Boundary hygiene (Fase 8 patch target): replace non-finite entries
                # and clamp per-row norm so malformed input cannot poison the run.
                emb = torch.nan_to_num(emb, nan=0.0, posinf=0.0, neginf=0.0)
                norms = emb.norm(dim=1, keepdim=True)
                cap = float(self.config.hormone_norm_clamp)
                emb = torch.where(norms > cap, emb * (cap / (norms + 1e-8)), emb)
            tokens = [f"v{i}" for i in range(emb.shape[0])]
        elif prompt is not None:
            emb, tokens = self.embedder.embed(prompt)
        else:
            raise ValueError("run() requires either `prompt` or `embeddings`")

        colony = Colony(
            request_id=request_id,
            config=self.config,
            device=self.device,
            bus=HormonalBus(self.config, self.device, enabled=self.config.bus_enabled),
            dag=nx.DiGraph(),
            # Bounded telemetry queue (plan Fase 5): strict backpressure — the
            # producer awaits put() when the consumer lags; the sentinel is never
            # dropped, so no event loss on the happy path.
            queue=asyncio.Queue(maxsize=self.config.telemetry_queue_max),
            budget=BudgetSemaphore(self.config.cell_budget),
            hysteresis=HysteresisGate(
                self.config.hysteresis_tau_up, self.config.hysteresis_tau_down,
                self.config.fission_ema_alpha, self.config.fission_cooldown,
            ),
        )
        producer = asyncio.create_task(self._orchestrate(colony, emb, tokens))
        try:
            while True:
                event = await colony.queue.get()
                if event is None:  # sentinel — simulation finished
                    break
                yield event
        finally:
            # Ensure the producer is always awaited (surface any late error).
            if not producer.done():
                producer.cancel()
            try:
                await producer
            except asyncio.CancelledError:
                pass

    async def synthesize(
        self, prompt: Optional[str] = None, request_id: str = "req",
        *, embeddings: Optional[torch.Tensor] = None,
    ) -> dict:
        """Run to completion and return the summary captured **locally** from the
        event stream — not the shared ``self.last_result`` — so concurrent calls
        on one engine instance cannot race on each other's result (finding #7)."""
        result: dict = {}
        async for ev in self.run(prompt, request_id=request_id, embeddings=embeddings):
            if ev.kind == KIND_CONVERGENCE:
                result = dict(ev.metrics)
            elif ev.kind == KIND_ERROR and ev.metrics.get("fatal"):
                result = {"error": ev.message}
        return result or (self.last_result or {})

    # ------------------------------------------------------------------ #
    #  Producer: the full life-cycle
    # ------------------------------------------------------------------ #
    async def _emit(self, colony: Colony, event: TelemetryEvent) -> None:
        await colony.queue.put(event)

    async def _orchestrate(self, colony: Colony, embeddings: torch.Tensor, tokens: list) -> None:
        cfg = colony.config
        try:
            # --- Genesis: the stem cell is born ---------------------------- #
            stem = NeuralOrganism(
                cell_id="stem",
                config=cfg,
                generation=0,
                lineage="stem",
                energy=cfg.initial_energy,
                device=self.device,
            )
            colony.register_cell(stem, parent_id=None)
            colony.budget.try_reserve(1)  # the stem occupies one budget permit
            await self._emit(colony, TelemetryEvent(
                KIND_GENESIS, "Stem cell instantiated", cell_id="stem", generation=0,
                metrics={"energy": stem.energy, "params": stem.param_count(),
                         "device": str(self.device), **resource_snapshot()},
            ))

            # --- Perception: both signals always measured (telemetry) ------ #
            divergence = semantic_divergence(embeddings)
            entropy_hx = workload_entropy(embeddings)
            n_unique = int(torch.unique(embeddings, dim=0).shape[0])

            # --- Fission decision (plan Fase 3): mode-dependent ------------ #
            decision: dict = {"divergence": divergence, "workload_entropy": entropy_hx}
            if not cfg.mitosis_enabled:
                k, decision["mode"] = 1, "monolithic"  # Fase 6 monolithic baseline
            elif cfg.fission_mode == "silhouette":
                k_sel, sil, per_k = select_k_silhouette(
                    embeddings, cfg.max_children,
                    min_cluster_size=cfg.min_cluster_size, threshold=cfg.silhouette_threshold,
                )
                k = k_sel
                decision.update({"mode": "silhouette", "silhouette": round(sil, 4),
                                 "silhouette_threshold": cfg.silhouette_threshold, "per_k": per_k})
            else:  # "difficulty" — divergence+H(X) heuristic with hysteresis (Fase 3)
                difficulty = 0.5 * divergence + 0.5 * entropy_hx
                # Double-band latch (tau_up/tau_down) + EMA + cooldown: fire on the
                # rising edge above tau_up, suppressing fission↔apoptosis oscillation.
                fire, htel = colony.hysteresis.update("stem", difficulty)
                kk = max(2, min(cfg.max_children, int(round(difficulty * cfg.max_children)), n_unique))
                k = kk if (fire and n_unique >= 2) else 1
                decision.update({"mode": "difficulty", "difficulty": round(difficulty, 4),
                                 "threshold": cfg.divergence_threshold, "hysteresis": htel})

            # Clamp by distinct-point count and the reserve-before-divide budget.
            k = min(k, n_unique, colony.budget.available())
            await self._emit(colony, TelemetryEvent(
                KIND_DIVERGENCE,
                f"Workload measured over {len(tokens)} vectors (mode={decision.get('mode')})",
                cell_id="stem",
                metrics={**decision, "n_tokens": len(tokens), "n_unique": n_unique,
                         "chosen_k": k, "embed_shape": list(embeddings.shape)},
            ))

            # --- Branch: mitosis or solo ----------------------------------- #
            if k < 2 or not colony.budget.try_reserve(k):
                await self._run_solo(colony, stem, embeddings)
            else:
                await self._do_mitosis(colony, stem, embeddings, k)

            # --- Done ------------------------------------------------------ #
        except Exception as exc:  # never hide a fault — stream it (incl. ExceptionGroup)
            await self._emit(colony, TelemetryEvent(
                KIND_ERROR, f"{type(exc).__name__}: {exc}", cell_id="engine",
                metrics={"fatal": True},
            ))
            self.last_result = {"error": f"{type(exc).__name__}: {exc}"}
        finally:
            # Retire every cell still on the books exactly once (the stem, which
            # never passes through _run_cell, plus any that a cancellation left
            # behind).  _retire_cell is idempotent, so cells already retired in
            # their own finally are skipped — no double-decrement, no leak.
            for survivor in list(colony.cells.values()):
                self._retire_cell(colony, survivor)
            # Blocking sentinel — guaranteed delivery (review finding #6): a slow
            # but present consumer will drain and receive it; an *abandoned*
            # consumer causes run()'s finally to cancel this producer, so a full
            # queue here surfaces as CancelledError (handled), never a deadlock.
            await colony.queue.put(None)  # sentinel closes the stream

    async def _do_mitosis(self, colony: Colony, stem: NeuralOrganism, embeddings: torch.Tensor, k: int) -> None:
        """Execute a stem division into ``k`` specialised children and run them.

        ``k`` budget permits have already been reserved by the caller.
        """
        centroids, assign, inertia = kmeans(embeddings, k)
        colony.centroids = centroids.detach()
        colony.k_chosen = k

        # Per-cluster member clouds + internal spread (proxy for cognitive load).
        members: list[torch.Tensor] = []
        spreads: list[float] = []
        for j in range(k):
            mask = assign == j
            mem = embeddings[mask] if bool(mask.any()) else centroids[j:j + 1]
            spread = (
                float(torch.cdist(mem, centroids[j:j + 1]).mean().item())
                if mem.shape[0] > 1 else 0.0
            )
            members.append(mem)
            spreads.append(spread)
        mean_spread = sum(spreads) / max(1, len(spreads))

        await self._emit(colony, TelemetryEvent(
            KIND_MITOSIS,
            f"Stem cell dividing into {k} specialised mini-agents",
            cell_id="stem", generation=0,
            metrics={"k": k, "inertia": inertia,
                     "cluster_sizes": [int(m.shape[0]) for m in members],
                     "cluster_spreads": [round(s, 4) for s in spreads]},
        ))
        colony.total_mitosis += 1
        children = stem.divide(centroids)
        colony.scheduler.expect("stem", len(children))  # join-counter (Fase 5)

        # A TaskGroup cancels siblings on the first fault (no orphaned tasks).
        async with asyncio.TaskGroup() as tg:
            for i, child in enumerate(children):
                colony.register_cell(child, parent_id="stem")
                allow = members[i].shape[0] >= 4 and spreads[i] > mean_spread
                tg.create_task(
                    self._run_cell(colony, child, stem, members[i], depth=1, allow_subdivide=allow)
                )

        # Explicit topological barrier (plan Fase 5): the stem reduces ONLY once
        # every child subtree has joined (pending["stem"] == 0).
        assert colony.scheduler.is_ready("stem"), "stem reduced before children joined"
        colony.scheduler.mark_reduced("stem")
        await self._synthesize(colony, stem, embeddings)

    def _retire_cell(self, colony: Colony, cell: NeuralOrganism) -> None:
        """Release a cell's bus slot, drop its reference and decrement the global
        gauge — exactly once, whatever path (apoptosis, fault or cancellation)
        the cell exited through."""
        cid = cell.cell_id
        if cid in colony.retired:
            return
        colony.retired.add(cid)
        colony.bus.release(cid)
        colony.cells.pop(cid, None)  # drop the ref so GC can reclaim the dead cell
        if colony.budget is not None:
            colony.budget.release(1)  # return the permit reserved at division time
        if cid in colony.counted:
            colony.counted.discard(cid)
            _adjust_live(-1)

    # ------------------------------------------------------------------ #
    #  A single mini-agent's life
    # ------------------------------------------------------------------ #
    async def _run_cell(
        self,
        colony: Colony,
        cell: NeuralOrganism,
        parent: NeuralOrganism,
        members: torch.Tensor,
        depth: int,
        allow_subdivide: bool = False,
    ) -> None:
        """Live out one mini-agent's life on its sub-domain ``members`` cloud.

        A cell adopts one of two developmental fates after a single assessment
        metabolic step:

        * **progenitor** — if its sub-domain is internally complex and it is
          allowed to divide, it k-means-splits its own member cloud into two
          finer sub-domains and spawns a daughter per sub-cluster (recursion via
          the call tree), then hands its aggregate representation upward.
        * **differentiated leaf** — otherwise it runs a full sense→metabolise→
          homeostasis→secrete loop until it converges or starves, adapts to its
          sub-domain target, and transfers its learned latent upward.

        Either way it finishes by transferring to its parent and apoptosing.
        """
        cfg = colony.config
        loop = asyncio.get_running_loop()
        members = members.to(self.device)
        x = F.normalize(members.mean(dim=0), dim=0)
        target = x.clone()
        # Committed domain estimate (coordination channel) starts at the centroid.
        colony.estimates[cell.cell_id] = x.clone()

        # Eligibility hint; the *actual* budget gate is the atomic try_reserve(2)
        # at dispatch time (Fase 5), which closes the sibling cooperative race.
        will_divide = (
            allow_subdivide
            and depth < cfg.max_depth
            and members.shape[0] >= 4
            and colony.budget is not None
            and colony.budget.available() >= 2
        )

        # The try/finally guarantees this cell releases its bus slot and retires
        # its global-gauge count exactly once — whether it dies of apoptosis,
        # raises a fault, or is cancelled because a sibling faulted.
        try:
            # --- Assessment: sense load + one metabolic step (both fates) --- #
            context = await colony.bus.sense(cell.cell_id, x)
            await self._emit(colony, TelemetryEvent(
                KIND_SENSE, "Assessed sub-domain load", cell_id=cell.cell_id, generation=cell.generation,
                metrics={"members": int(members.shape[0]), "ctx_norm": round(float(context.norm().item()), 4),
                         "occupancy": colony.bus.occupancy()},
            ))
            info = await loop.run_in_executor(
                _EXECUTOR, functools.partial(cell.metabolic_step, x, context, int(members.shape[0]))
            )
            colony.total_flops += info["flops"]
            colony.total_burn += info["energy_burn"]
            await self._emit(colony, TelemetryEvent(
                KIND_FORWARD, "Assessment metabolic step", cell_id=cell.cell_id, generation=cell.generation,
                metrics={"flops": info["flops"], "energy": round(info["energy"], 3),
                         "entropy": round(info["entropy"], 4), "latent_shape": list(info["latent"].shape)},
            ))
            cell.homeostasis(cfg.entropy_setpoint + 0.4 * colony.bus.hormone("cortisol"))  # prime controller
            # Secrete the committed ESTIMATE (coordination channel, direct write);
            # scalar hormones carry mood separately.
            await colony.bus.secrete(cell.cell_id, colony.estimates[cell.cell_id], blend=1.0)
            colony.bus.tick()

            converged = False
            adapt_loss: Optional[float] = None
            if will_divide and colony.budget.try_reserve(2):
                # Reserved 2 permits atomically → safe to spawn 2 grandchildren.
                await self._divide_and_delegate(colony, cell, members, depth)
            else:
                converged, adapt_loss = await self._differentiate(colony, cell, x, target)
                # A leaf commits its coordinated domain estimate to the solution.
                colony.reconstructions.append(colony.estimates[cell.cell_id].detach().to(self.device))

            # --- Transfer representation upward (TRANSFERRING state) ------- #
            if float(cell.inherited_memory.norm().item()) > 1e-6:
                final_latent = cell.inherited_memory
            elif cell.last_latent is not None:
                final_latent = cell.last_latent
            else:
                final_latent = x
            parent.absorb(final_latent, weight=1.0 / max(1, cell.generation))
            colony.transferred.append(final_latent.detach().to(self.device))
            colony.bus.emit_hormone("dopamine", 0.3)  # reward: a sub-problem is solved

            # --- Apoptosis FSM: classify the death trigger (DYING → DEAD) -- #
            trigger = self._death_trigger(cell, converged, adapt_loss)
            colony.death_triggers[trigger] = colony.death_triggers.get(trigger, 0) + 1
            report = cell.apoptose()
            colony.total_apoptosis += 1
            await self._emit(colony, TelemetryEvent(
                KIND_APOPTOSIS, f"Programmed cell death — trigger={trigger}", cell_id=cell.cell_id,
                generation=cell.generation,
                metrics={"trigger": trigger, "fsm": "ALIVE→DYING→TRANSFERRING→DEAD",
                         "reclaimed_bytes": report.get("reclaimed_bytes", 0),
                         "residual_energy": round(report.get("residual_energy", 0.0), 3),
                         "energy_audit_ok": cell.energy_audit()["balanced"],
                         "live_cells": colony.live_count(), "converged": converged,
                         **resource_snapshot()},
            ))
        finally:
            # This cell's whole subtree is complete → decrement the parent's
            # join-counter (plan Fase 5), then retire exactly once.
            colony.scheduler.child_done(parent.cell_id)
            self._retire_cell(colony, cell)

    @staticmethod
    def _death_trigger(cell: NeuralOrganism, converged: bool, adapt_loss: Optional[float]) -> str:
        """Classify which of the 4 apoptosis triggers fired (plan Fase 4)."""
        if cell.energy <= 0:
            return "energy_depleted"
        if converged or (adapt_loss is not None and adapt_loss < 0.4):
            return "task_solved"
        if adapt_loss is not None and adapt_loss > 0.9:
            return "marginal_contribution"
        return "senescence"

    async def _differentiate(
        self, colony: Colony, cell: NeuralOrganism, x: torch.Tensor, target: torch.Tensor
    ) -> tuple[bool, Optional[float]]:
        """Run a leaf worker's full metabolic loop + bus coordination + adaptation.

        Returns ``(converged, adapt_loss)``.  Each cycle performs one Jacobi step
        of bus-mediated cascade propagation on the cell's committed domain
        estimate, so with the bus enabled a colony of leaves converges on the
        cascade-coupled ground-truth.
        """
        cfg = colony.config
        loop = asyncio.get_running_loop()
        prev_latent: Optional[torch.Tensor] = None
        converged = False

        # Cycle 0 was the assessment step; run the remaining metabolic cycles.
        for cycle in range(1, cfg.metabolic_cycles):
            if cell.energy <= 0:
                break

            # Sense peers via attention over their committed estimates.
            context = await colony.bus.sense(cell.cell_id, colony.estimates[cell.cell_id])
            await self._emit(colony, TelemetryEvent(
                KIND_SENSE, f"Sensed manifold (cycle {cycle})", cell_id=cell.cell_id,
                generation=cell.generation,
                metrics={"ctx_norm": round(float(context.norm().item()), 4), "occupancy": colony.bus.occupancy()},
            ))

            info = await loop.run_in_executor(
                _EXECUTOR, functools.partial(cell.metabolic_step, x, context, 1)
            )
            colony.total_flops += info["flops"]
            colony.total_burn += info["energy_burn"]
            await self._emit(colony, TelemetryEvent(
                KIND_FORWARD, f"Metabolic step (cycle {cycle})", cell_id=cell.cell_id,
                generation=cell.generation,
                metrics={"flops": info["flops"], "energy_burn": round(info["energy_burn"], 4),
                         "energy": round(info["energy"], 3), "entropy": round(info["entropy"], 4)},
            ))

            setpoint = cfg.entropy_setpoint + 0.4 * colony.bus.hormone("cortisol")
            homeo = cell.homeostasis(setpoint)
            await self._emit(colony, TelemetryEvent(
                KIND_HOMEOSTASIS, "Entropy corrected toward setpoint", cell_id=cell.cell_id,
                generation=cell.generation, metrics={k: round(v, 4) for k, v in homeo.items()},
            ))

            # Coordination: one Jacobi step of cascade propagation via the bus,
            # then commit + secrete the updated estimate (direct-write channel).
            new_estimate = x + cfg.coordination_gamma * context
            colony.estimates[cell.cell_id] = new_estimate
            await colony.bus.secrete(cell.cell_id, new_estimate, blend=1.0)
            if info["entropy"] > cfg.high_stress_entropy:
                colony.bus.emit_hormone("cortisol", 0.5)
            await self._emit(colony, TelemetryEvent(
                KIND_SECRETE, "Committed domain estimate to the manifold", cell_id=cell.cell_id,
                generation=cell.generation,
                metrics={"estimate_norm": round(float(new_estimate.norm().item()), 4),
                         "ctx_norm": round(float(context.norm().item()), 4),
                         "hormones": {k: round(v, 3) for k, v in colony.bus.hormone_panel().items()}},
            ))
            colony.bus.tick()

            if prev_latent is not None:
                stab = float(F.cosine_similarity(info["latent"], prev_latent, dim=0).item())
                if stab >= cfg.convergence_target:
                    converged = True
                    break
            prev_latent = info["latent"]

        # Gradient adaptation (skipped by a starved cell, which still transfers).
        adapt_loss: Optional[float] = None
        if cell.alive and cell.energy > 0:
            try:
                context = await colony.bus.sense(cell.cell_id, colony.estimates[cell.cell_id])
                adapt_info = await loop.run_in_executor(
                    _EXECUTOR, functools.partial(cell.adapt, x, context, target)
                )
                colony.total_flops += adapt_info["flops"]
                adapt_loss = adapt_info["loss"]
                await self._emit(colony, TelemetryEvent(
                    KIND_ADAPT, "Gradient adaptation + progress regeneration", cell_id=cell.cell_id,
                    generation=cell.generation,
                    metrics={"loss": round(adapt_info["loss"], 5), "regen": round(adapt_info["regen"], 4),
                             "delta_util": round(adapt_info["delta_util"], 5),
                             "energy": round(adapt_info["energy"], 3), "converged": converged},
                ))
            except Exception as exc:
                await self._emit(colony, TelemetryEvent(
                    KIND_ERROR, f"adapt failed: {type(exc).__name__}: {exc}", cell_id=cell.cell_id,
                    metrics={"fatal": False},
                ))
        return converged, adapt_loss

    async def _divide_and_delegate(
        self, colony: Colony, cell: NeuralOrganism, members: torch.Tensor, depth: int
    ) -> None:
        """A progenitor recursively splits its own member cloud via k-means and
        spawns a leaf daughter per finer sub-cluster (bounded to leaves)."""
        sub_centroids, sub_assign, _ = kmeans(members, 2)
        sub_sizes = [int((sub_assign == j).sum().item()) for j in range(2)]
        await self._emit(colony, TelemetryEvent(
            KIND_MITOSIS, f"Sub-mitosis: splitting complex sub-domain (depth {depth}→{depth + 1})",
            cell_id=cell.cell_id, generation=cell.generation,
            metrics={"k": 2, "members": int(members.shape[0]), "sub_sizes": sub_sizes},
        ))
        colony.total_mitosis += 1
        grandchildren = cell.divide(sub_centroids)
        colony.scheduler.expect(cell.cell_id, len(grandchildren))  # join-counter (Fase 5)
        # TaskGroup: recursion via the call tree, with sibling cancellation on fault.
        async with asyncio.TaskGroup() as tg:
            for j, gc_cell in enumerate(grandchildren):
                colony.register_cell(gc_cell, parent_id=cell.cell_id)
                submask = sub_assign == j
                submembers = members[submask] if bool(submask.any()) else sub_centroids[j:j + 1]
                tg.create_task(
                    self._run_cell(colony, gc_cell, cell, submembers, depth + 1, allow_subdivide=False)
                )

        # Barrier: this progenitor only hands its representation upward once all
        # grandchildren have joined (pending[cell_id] == 0).
        assert colony.scheduler.is_ready(cell.cell_id), "progenitor reduced before grandchildren joined"
        colony.scheduler.mark_reduced(cell.cell_id)

    # ------------------------------------------------------------------ #
    #  Solo path (low divergence) + synthesis
    # ------------------------------------------------------------------ #
    async def _run_solo(self, colony: Colony, stem: NeuralOrganism, embeddings: torch.Tensor) -> None:
        """Mono-domain prompt: the stem cell solves it alone (no mitosis)."""
        cfg = colony.config
        loop = asyncio.get_running_loop()
        x = F.normalize(embeddings.mean(dim=0), dim=0)
        prev = None
        for cycle in range(cfg.metabolic_cycles):
            context = await colony.bus.sense(stem.cell_id, stem.last_latent if stem.last_latent is not None else x)
            info = await loop.run_in_executor(
                _EXECUTOR, functools.partial(stem.metabolic_step, x, context, embeddings.shape[0])
            )
            colony.total_flops += info["flops"]
            colony.total_burn += info["energy_burn"]
            await self._emit(colony, TelemetryEvent(
                KIND_FORWARD, f"Solo metabolic step (cycle {cycle})", cell_id="stem",
                metrics={"flops": info["flops"], "energy": round(info["energy"], 3),
                         "entropy": round(info["entropy"], 4)},
            ))
            stem.homeostasis(cfg.entropy_setpoint)
            await colony.bus.secrete(stem.cell_id, info["latent"])
            if prev is not None and float(F.cosine_similarity(info["latent"], prev, dim=0).item()) >= cfg.convergence_target:
                break
            prev = info["latent"]
        stem.absorb(stem.last_latent if stem.last_latent is not None else x)
        colony.transferred.append((stem.last_latent if stem.last_latent is not None else x).detach())
        await self._synthesize(colony, stem, embeddings)

    async def _synthesize(self, colony: Colony, stem: NeuralOrganism, embeddings: torch.Tensor) -> None:
        """Fuse the stem cell's inherited memory + manifold into a final answer."""
        manifold_field = colony.bus.active_field()
        synthesis = F.normalize(stem.inherited_memory + 0.5 * manifold_field + 1e-6, dim=0)

        # Convergence = how coherently the synthesis represents every transferred
        # sub-representation (mean cosine similarity), in [0, 1].
        if colony.transferred:
            stacked = torch.stack([F.normalize(t.reshape(-1), dim=0) for t in colony.transferred])
            coherence = float(F.cosine_similarity(stacked, synthesis.unsqueeze(0).expand_as(stacked), dim=1).mean().item())
        else:
            coherence = 1.0
        coherence = max(0.0, min(1.0, (coherence + 1.0) / 2.0))  # map [-1,1]→[0,1]

        # Decode a human-readable ranking: which prompt tokens the synthesis most
        # resembles (a latent "attention" over the original prompt).
        token_scores = F.cosine_similarity(
            embeddings, synthesis.unsqueeze(0).expand_as(embeddings), dim=1
        )
        top = torch.topk(token_scores, k=min(5, embeddings.shape[0]))
        dominant = [int(i) for i in top.indices.tolist()]

        await self._emit(colony, TelemetryEvent(
            KIND_SYNTHESIS, "Stem cell fused inherited representations", cell_id="stem",
            metrics={"synthesis_norm": round(float(synthesis.norm().item()), 4),
                     "transferred": len(colony.transferred),
                     "dominant_token_idx": dominant,
                     "manifold_field_norm": round(float(manifold_field.norm().item()), 4)},
        ))

        elapsed = time.time() - colony.t0
        summary = {
            "request_id": colony.request_id,
            "convergence": round(coherence, 4),
            "converged": coherence >= 0.5,
            "peak_cells": colony.peak_cells,
            "total_mitosis": colony.total_mitosis,
            "total_apoptosis": colony.total_apoptosis,
            "total_flops": colony.total_flops,
            "gflops": round(colony.total_flops / 1e9, 4),
            "energy_burned": round(colony.total_burn, 3),
            "stem_residual_energy": round(stem.energy, 3),
            "live_cells_final": colony.live_count(),
            "dag_nodes": colony.dag.number_of_nodes(),
            "dag_edges": colony.dag.number_of_edges(),
            "elapsed_s": round(elapsed, 4),
            "synthesis_vector": [round(v, 5) for v in synthesis[:8].tolist()],
            # Full-dimensional artifacts for the simulation harness (Fase 6).
            "k_chosen": colony.k_chosen,
            "synthesis_full": synthesis.detach().cpu().tolist(),
            "centroids": colony.centroids.detach().cpu().tolist() if colony.centroids is not None else None,
            # Coordinated per-domain reconstructions + apoptosis-trigger tally (Fase 4).
            "reconstructions": [r.detach().cpu().tolist() for r in colony.reconstructions],
            "death_triggers": dict(colony.death_triggers),
            "resources": resource_snapshot(),
        }
        self.last_result = summary
        await self._emit(colony, TelemetryEvent(
            KIND_CONVERGENCE, "Colony reached synthesis convergence", cell_id="stem",
            metrics=summary,
        ))
