"""
`hormonal_bus.py` — Vectorial Hormone Exudation on a shared latent manifold.

Agents in B.I.O.M.A. do **not** communicate through serialized text/API calls.
They communicate by writing raw activation tensors ("hormones") into a shared
latent matrix — the *Manifold Stream* — and by sensing that matrix through a
soft-attention read.  This gives collaboration without any serialization
overhead: one cell's thought is literally another cell's input vector.

Concurrency model
-----------------
Heavy compute (cell forward/adapt) is dispatched to a thread pool by the
mitosis engine, while manifold coordination happens on the asyncio event loop.
To remain correct under *both* access patterns every raw tensor mutation is
guarded by a short-lived ``threading.Lock`` (the critical sections are tiny —
a slice write or a matmul over ≤ ``manifold_slots`` rows).  The async methods
are thin awaitable wrappers so the engine can ``await`` secretion/sensing
inline with the rest of its coroutine flow.

The manifold also carries three scalar **endocrine fields** (cortisol,
dopamine, adrenaline) that act as global modulators read by the homeostasis
controller — e.g. rising cortisol raises every cell's entropy setpoint,
modelling a stressed colony that tolerates more exploratory disorder.
"""

from __future__ import annotations

import threading
from typing import Optional

import torch
import torch.nn.functional as F

from .config import BiomaConfig, DEFAULT_CONFIG, DEVICE, HORMONES


class HormonalBus:
    """A shared, decaying latent matrix that cells read and write in place."""

    def __init__(
        self,
        config: BiomaConfig = DEFAULT_CONFIG,
        device: Optional[torch.device] = None,
        enabled: Optional[bool] = None,
    ) -> None:
        self.config = config
        self.device = device or DEVICE
        # No-hormone baseline (plan Fase 6): when disabled, sensing returns a zero
        # context and secretion is a no-op, so agents cannot coordinate.
        self.enabled = config.bus_enabled if enabled is None else enabled

        # The Manifold Stream: [slots, embed_dim].  Each living cell owns a row.
        self._manifold = torch.zeros(
            config.manifold_slots, config.embed_dim, device=self.device
        )
        # Occupancy mask + freshness (how many ticks since last secretion).
        self._occupied = torch.zeros(config.manifold_slots, dtype=torch.bool, device=self.device)
        self._age = torch.zeros(config.manifold_slots, device=self.device)

        # Endocrine scalar fields — global chemical mood of the colony.
        self._hormones = {name: 0.0 for name in HORMONES}

        # cell_id -> slot index bookkeeping.
        self._slot_of: dict[str, int] = {}

        # Guards every mutation of the tensors above.  Critical sections are
        # intentionally tiny so contention with the thread pool stays negligible.
        self._lock = threading.Lock()

        # Versioned snapshot-isolation (plan Fase 2, defeito #3): a monotonic
        # ``_version`` bumps on every mutation of the manifold/occupancy/age; a
        # cached snapshot is only re-cloned when a read observes a newer version,
        # so ``sense`` no longer clones unconditionally under the lock.
        self._version = 0
        self._snap_version = -1
        self._snap_manifold: Optional[torch.Tensor] = None
        self._snap_occupied: Optional[torch.Tensor] = None
        self._snap_age: Optional[torch.Tensor] = None
        # Snapshot-reuse telemetry (acceptance criterion: reuse >= floor).
        self._snap_hits = 0
        self._snap_misses = 0

    # ------------------------------------------------------------------ #
    #  Registration / release (cell lifecycle bookkeeping)
    # ------------------------------------------------------------------ #
    def register(self, cell_id: str) -> int:
        """Assign a free manifold slot to a cell.  Returns the slot index.

        Raises ``RuntimeError`` if the manifold is saturated — the engine's
        ``cell_budget`` is always <= ``manifold_slots`` so this is a hard safety
        assertion rather than an expected condition.
        """
        with self._lock:
            if cell_id in self._slot_of:
                return self._slot_of[cell_id]
            free = (~self._occupied).nonzero(as_tuple=False)
            if free.numel() == 0:
                raise RuntimeError(
                    "Hormonal manifold saturated: no free slots "
                    f"({self.config.manifold_slots} in use). Increase "
                    "config.manifold_slots or lower cell_budget."
                )
            slot = int(free[0].item())
            self._occupied[slot] = True
            self._manifold[slot].zero_()
            self._age[slot] = 0.0
            self._slot_of[cell_id] = slot
            self._version += 1
            return slot

    def release(self, cell_id: str) -> None:
        """Free a cell's slot on apoptosis so its hormones stop influencing peers."""
        with self._lock:
            slot = self._slot_of.pop(cell_id, None)
            if slot is None:
                return
            self._occupied[slot] = False
            self._manifold[slot].zero_()
            self._age[slot] = 0.0
            self._version += 1

    # ------------------------------------------------------------------ #
    #  Secretion (write) / Sensing (attention read)
    # ------------------------------------------------------------------ #
    def secrete_sync(self, cell_id: str, vector: torch.Tensor, gain: float = 1.0,
                     blend: Optional[float] = None) -> None:
        """Blend a cell's activation vector into its manifold slot (in place).

        The write is an EMA blend (``write_blend`` fraction of the new signal) so
        a cell's influence persists and decays rather than being overwritten —
        a chemical gradient, not a mailbox.  Numeric shielding (plan Fase 2):
        non-finite values are sanitized and the injected norm is clamped to
        ``hormone_norm_clamp`` so a single blow-up cannot poison the manifold.
        """
        vec = vector.detach().to(self.device).reshape(-1)
        if vec.shape[0] != self.config.embed_dim:
            raise ValueError(
                f"Hormone vector dim {vec.shape[0]} != embed_dim {self.config.embed_dim}"
            )
        if not self.enabled:
            return  # no-hormone baseline: secretion is a no-op
        # Sanitize non-finite entries, then clamp the L2 norm to c_max.
        vec = torch.nan_to_num(vec, nan=0.0, posinf=0.0, neginf=0.0)
        norm = float(vec.norm().item())
        c_max = self.config.hormone_norm_clamp
        if norm > c_max:
            vec = vec * (c_max / (norm + 1e-8))
        with self._lock:
            slot = self._slot_of.get(cell_id)
            if slot is None:
                # Cell secreting after apoptosis — ignore silently; it is dead.
                return
            # ``blend=1.0`` overwrites (direct coordination channel — current
            # estimate); the default EMA is the hormone-signalling channel.
            b = self.config.write_blend if blend is None else float(blend)
            self._manifold[slot] = (1.0 - b) * self._manifold[slot] + b * gain * vec
            self._age[slot] = 0.0
            self._version += 1

    def _read_snapshot(self):
        """Return a (manifold, occupied, age) snapshot, re-cloning only when the
        manifold changed since the last read (versioned snapshot-isolation)."""
        with self._lock:
            if self._snap_version != self._version or self._snap_manifold is None:
                self._snap_manifold = self._manifold.clone()
                self._snap_occupied = self._occupied.clone()
                self._snap_age = self._age.clone()
                self._snap_version = self._version
                self._snap_misses += 1
            else:
                self._snap_hits += 1
            own = dict(self._slot_of)  # cheap copy of the id->slot map
            return self._snap_manifold, self._snap_occupied, self._snap_age, own

    def sense_sync(self, cell_id: str, query: torch.Tensor) -> torch.Tensor:
        """Attention-read the manifold via **true cosine** over fresh peer slots.

        The reader's ``query`` attends (cosine of query AND keys, plan defeito #1)
        over every *other* occupied, **non-stale** slot; the returned context is
        the attention-weighted sum of its peers' secretions.  Self and slots older
        than ``staleness_ticks`` (plan defeito #2 — ``_age`` now actually gates
        attention) are masked, so the manifold is a pure, fresh inter-cellular
        medium.  Reads reuse a versioned snapshot instead of cloning every call.
        """
        if not self.enabled:
            return torch.zeros(self.config.embed_dim, device=self.device)  # no-hormone baseline
        q = query.detach().to(self.device).reshape(-1)
        q = torch.nan_to_num(q, nan=0.0, posinf=0.0, neginf=0.0)
        manifold, occupied, age, slot_of = self._read_snapshot()

        valid = occupied.clone()
        own_slot = slot_of.get(cell_id, -1)
        if own_slot >= 0:
            valid[own_slot] = False
        # Staleness gate: ignore slots that have not secreted for too long.
        valid = valid & (age <= float(self.config.staleness_ticks))
        if not bool(valid.any()):
            return torch.zeros(self.config.embed_dim, device=self.device)

        keys = manifold[valid]                                  # [n_peers, embed_dim]
        keys_n = F.normalize(keys, dim=1)                       # unit keys (true cosine)
        q_n = q / (q.norm() + 1e-8)                             # unit query
        scores = keys_n @ q_n                                   # cosine ∈ [-1, 1]
        weights = F.softmax(scores / self.config.attention_temp, dim=0)
        context = weights @ keys                                # weighted raw secretions
        return torch.nan_to_num(context, nan=0.0, posinf=0.0, neginf=0.0)

    def snapshot_reuse_ratio(self) -> float:
        """Fraction of ``sense`` reads that reused a cached snapshot (Fase 2 metric)."""
        total = self._snap_hits + self._snap_misses
        return (self._snap_hits / total) if total else 0.0

    async def secrete(self, cell_id: str, vector: torch.Tensor, gain: float = 1.0,
                      blend: Optional[float] = None) -> None:
        """Async wrapper around :meth:`secrete_sync` (loop-thread coordination)."""
        self.secrete_sync(cell_id, vector, gain=gain, blend=blend)

    async def sense(self, cell_id: str, query: torch.Tensor) -> torch.Tensor:
        """Async wrapper around :meth:`sense_sync`."""
        return self.sense_sync(cell_id, query)

    # ------------------------------------------------------------------ #
    #  Endocrine scalar fields (global modulators)
    # ------------------------------------------------------------------ #
    def emit_hormone(self, name: str, amount: float) -> float:
        """Add to a global scalar hormone level (clamped to [0, 10]). Returns new level."""
        if name not in self._hormones:
            raise KeyError(f"Unknown hormone '{name}'. Known: {tuple(self._hormones)}")
        with self._lock:
            self._hormones[name] = float(min(10.0, max(0.0, self._hormones[name] + amount)))
            return self._hormones[name]

    def hormone(self, name: str) -> float:
        with self._lock:
            return self._hormones[name]

    def hormone_panel(self) -> dict[str, float]:
        with self._lock:
            return dict(self._hormones)

    # ------------------------------------------------------------------ #
    #  Housekeeping
    # ------------------------------------------------------------------ #
    def tick(self) -> None:
        """Advance one global metabolic tick: dissipate hormone vectors, age
        occupied slots and decay the scalar endocrine fields — three separate
        time constants (plan Fase 2, defeitos #2 and #4)."""
        with self._lock:
            occ = self._occupied.float().unsqueeze(1)          # [slots, 1]
            # Real temporal dissipation of the manifold VECTORS on occupied slots.
            self._manifold = self._manifold * (1.0 - occ) + self._manifold * occ * self.config.decay_vec
            self._age += self._occupied.float()
            for name in self._hormones:
                self._hormones[name] *= self.config.decay_scalar
            self._version += 1

    def occupancy(self) -> int:
        with self._lock:
            return int(self._occupied.sum().item())

    def snapshot(self) -> torch.Tensor:
        """Return a detached copy of the full manifold (for synthesis/inspection)."""
        with self._lock:
            return self._manifold.clone()

    def active_field(self) -> torch.Tensor:
        """Mean of all currently-occupied hormone vectors (the colony 'mood')."""
        with self._lock:
            if not bool(self._occupied.any()):
                return torch.zeros(self.config.embed_dim, device=self.device)
            return self._manifold[self._occupied].mean(dim=0)
