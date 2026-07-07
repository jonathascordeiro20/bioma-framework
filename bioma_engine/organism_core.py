"""
`organism_core.py` — The living neural cell.

:class:`NeuralOrganism` is an ``nn.Module`` that behaves like a biological cell:

* it **metabolises** — every forward pass burns synthetic ATP proportional to the
  *actually measured* FLOPs (counted with forward hooks on its ``nn.Linear``
  layers) plus a token cost and an entropy penalty;
* it maintains **homeostasis** — a feedback controller nudges an internal
  ``temperature`` so its activation entropy tracks a setpoint;
* it **adapts** — a gradient step on a private optimizer lets the cell learn a
  representation that is later transferred to its parent (this is the only place
  autograd graphs are built, and each cell's graph is fully isolated);
* it undergoes **mitosis** — :meth:`divide` deep-copies the cell's ``state_dict``,
  perturbs it (mutation), splits the energy budget and specialises the children
  toward supplied semantic centroids;
* it undergoes **apoptosis** — :meth:`apoptose` detaches parameters, drops
  references and triggers ``gc.collect()`` + ``torch.cuda.empty_cache()`` so the
  VRAM/RAM it held is reclaimed immediately.

No autograd path is ever shared between a parent and a child: mitosis copies
*detached* tensor data into freshly-constructed leaf parameters, so a child's
learning can never corrupt its parent's graph (or vice-versa).
"""

from __future__ import annotations

import copy
import gc
import hashlib
import math
import uuid
from dataclasses import dataclass
from typing import Optional

import torch
import torch.nn as nn
import torch.nn.functional as F

from .config import BiomaConfig, DEFAULT_CONFIG, DEVICE


def derive_child_seed(parent_seed: int, index: int) -> int:
    """Deterministic SHA-256 derivation of a child's mutation seed (plan Fase 1)."""
    digest = hashlib.sha256(f"{int(parent_seed)}:{int(index)}".encode()).digest()
    return int.from_bytes(digest[:8], "little")


@dataclass
class Genome:
    """A cell's identity + lineage metadata (plan Fase 1 contract)."""

    id: str                       # UUID — globally unique per instance
    generation: int
    parent_id: Optional[str]
    lineage: str
    mutation_seed: int            # deterministic (SHA-derived down the lineage)
    device: str
    arch_signature: str           # canonical hash of topology + shapes + dtypes

    def as_dict(self) -> dict:
        return {
            "id": self.id, "generation": self.generation, "parent_id": self.parent_id,
            "lineage": self.lineage, "mutation_seed": self.mutation_seed,
            "device": self.device, "arch_signature": self.arch_signature,
        }


class FlopMeter:
    """Counts FLOPs from the *real* runtime shapes of ``nn.Linear`` calls.

    A matmul of ``[B, in] x [in, out]`` costs ``2 * B * in * out`` FLOPs
    (multiply + add), plus ``B * out`` for the bias.  Registering a forward hook
    on every linear layer means the count reflects whatever the cell actually
    executed this step — not a static estimate — which is what ties "energy" to
    genuine tensor operations.
    """

    def __init__(self, module: nn.Module) -> None:
        self.total: float = 0.0
        self._handles = []
        for sub in module.modules():
            if isinstance(sub, nn.Linear):
                self._handles.append(sub.register_forward_hook(self._hook))

    def _hook(self, module: nn.Linear, inputs, output) -> None:
        x = inputs[0]
        batch = int(x.numel() // x.shape[-1]) if x.dim() > 0 else 1
        mac = 2.0 * batch * module.in_features * module.out_features
        if module.bias is not None:
            mac += batch * module.out_features
        self.total += mac

    def reset(self) -> float:
        spent, self.total = self.total, 0.0
        return spent

    def close(self) -> None:
        for h in self._handles:
            h.remove()
        self._handles.clear()


class NeuralOrganism(nn.Module):
    """A single self-replicating neural cell in the B.I.O.M.A. colony."""

    def __init__(
        self,
        cell_id: str,
        config: BiomaConfig = DEFAULT_CONFIG,
        *,
        generation: int = 0,
        lineage: str = "stem",
        energy: Optional[float] = None,
        device: Optional[torch.device] = None,
        specialization: Optional[torch.Tensor] = None,
        mutation_seed: Optional[int] = None,
    ) -> None:
        super().__init__()
        self.cell_id = cell_id
        self.config = config
        self.generation = generation
        self.lineage = lineage
        self.device = device or DEVICE
        if mutation_seed is None:
            mutation_seed = int.from_bytes(
                hashlib.sha256(f"{config.seed}:{cell_id}".encode()).digest()[:8], "little"
            )
        self._mutation_seed = mutation_seed

        d, h = config.embed_dim, config.hidden_dim

        # --- The genome: a small residual MLP + a hormone receptor ---------- #
        # Receptor fuses the cell's own input with the hormone context it senses.
        self.receptor = nn.Linear(2 * d, d)
        # Metabolic core (the "cytoplasm"): non-linear transform of the fused signal.
        self.core = nn.Sequential(
            nn.Linear(d, h),
            nn.GELU(),
            nn.Linear(h, d),
        )
        # Effector projects the internal state into a secretable hormone/answer.
        self.effector = nn.Linear(d, d)

        # --- Non-learned biological state (buffers travel with .to(device)) - #
        # Homeostatic temperature (scales logits before entropy is measured).
        self.register_buffer("temperature", torch.tensor(1.0))
        # Specialization identity — a unit vector marking this cell's domain.
        if specialization is None:
            specialization = F.normalize(torch.randn(d), dim=0)
        self.register_buffer("specialization", specialization.detach().reshape(d).clone())
        # Inherited memory — an attention-pooled trace of dead children.
        self.register_buffer("inherited_memory", torch.zeros(d))

        self.to(self.device)

        # --- Metabolic bookkeeping ----------------------------------------- #
        self.energy: float = float(energy if energy is not None else config.initial_energy)
        self.alive: bool = True
        self.age: int = 0
        self.last_entropy: float = 0.0
        self.last_latent: Optional[torch.Tensor] = None

        # FLOP meter + lazily-created private optimizer (for local adaptation).
        self._flops = FlopMeter(self)
        self._optim: Optional[torch.optim.Optimizer] = None

        # Energy accounting audit (plan Fase 4): the running balance must always
        # equal initial_energy − total_burn − total_transferred + total_regen
        # (no double-counting, no float drift).  ``total_transferred`` is the
        # energy handed to children at mitosis (a transfer, not a burn).
        # Regeneration is by *progress* (loss-drop), never mere activity, so a
        # cell that does not converge cannot refill.
        self._energy0: float = self.energy
        self._total_burn: float = 0.0
        self._total_regen: float = 0.0
        self._total_transferred: float = 0.0  # energy handed to children at mitosis
        self._prev_loss: float = 1.0   # previous adaptation loss (1.0 = worst)

        # --- Genome / identity (plan Fase 1) ------------------------------- #
        self.genome = Genome(
            id=str(uuid.uuid4()),
            generation=generation,
            parent_id=lineage.rsplit(".", 1)[0] if "." in lineage else None,
            lineage=lineage,
            mutation_seed=mutation_seed,
            device=str(self.device),
            arch_signature=self.arch_signature(),
        )

    # ====================================================================== #
    #  Identity / genome (plan Fase 1)
    # ====================================================================== #
    def arch_signature(self) -> str:
        """Canonical hash of topology + parameter shapes + dtypes.  A precondition
        of replication and of DAG connection (same signature ⇒ compatible)."""
        parts = [f"{n}:{tuple(p.shape)}:{p.dtype}" for n, p in self.named_parameters()]
        return hashlib.sha256("|".join(parts).encode()).hexdigest()[:16]

    def genome_signature(self) -> dict:
        return self.genome.as_dict()

    def mutate(self, mutation_rate: Optional[float] = None,
               generator: Optional[torch.Generator] = None) -> int:
        """In-place, reproducible, per-layer *relative* Gaussian mutation.

        σ_layer = mutation_rate · (std(θ_layer) + ε), so the perturbation scales
        with each layer's own weight magnitude.  A mutability mask freezes
        normalization parameters, and every candidate is finiteness-checked and
        **rejected** if non-finite (numerical stability).  Returns the number of
        tensors actually mutated.  Buffers (temperature/specialization/memory) are
        never touched — only learnable parameters.
        """
        rate = self.config.mutation_rate if mutation_rate is None else mutation_rate
        mutated = 0
        with torch.no_grad():
            for name, p in self.named_parameters():
                if not p.dtype.is_floating_point or "norm" in name.lower():
                    continue  # mutability mask
                sigma = rate * (float(p.detach().float().std().item()) + 1e-8)
                noise = torch.randn(p.shape, generator=generator) * sigma
                candidate = p + noise.to(dtype=p.dtype, device=p.device)
                if torch.isfinite(candidate).all():   # reject non-finite mutations
                    p.copy_(candidate)
                    mutated += 1
        return mutated

    def extract_representation(self) -> torch.Tensor:
        """The cell's learned representation for upward transfer."""
        if float(self.inherited_memory.norm().item()) > 1e-6:
            return self.inherited_memory.detach().clone()
        if self.last_latent is not None:
            return self.last_latent.detach().clone()
        return self.specialization.detach().clone()

    def release(self) -> None:
        """Light teardown primitive: remove FLOP hooks and drop the optimizer
        (a subset of apoptosis, used when recycling without full death)."""
        self._flops.close()
        self._optim = None
        self.last_latent = None

    # ====================================================================== #
    #  Forward metabolism
    # ====================================================================== #
    def forward(self, x: torch.Tensor, context: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        """Transform an input latent given a sensed hormone context.

        Returns ``(latent, logits)`` where ``latent`` is the cell's produced
        representation and ``logits`` is the temperature-scaled signal whose
        softmax entropy the homeostasis controller regulates.
        """
        x = x.to(self.device).reshape(-1)
        context = context.to(self.device).reshape(-1)

        # Blend hormone context + inherited memory into the receptor input.
        ctx = context + 0.5 * self.inherited_memory
        fused = torch.cat([x + self.specialization, ctx], dim=-1)
        received = torch.tanh(self.receptor(fused))
        # Residual metabolic transform.
        latent = received + self.core(received)
        # Standardize the effector output to unit variance *before* the
        # temperature divide.  This gives the homeostatic ``temperature`` real
        # authority over the softmax sharpness (and hence the activation
        # entropy): with unit-variance logits, temperature alone determines how
        # peaked the distribution is, so the feedback controller can actually
        # steer entropy toward its setpoint instead of being swamped by an
        # arbitrary logit scale.
        raw = self.effector(latent)
        raw = (raw - raw.mean()) / (raw.std() + 1e-6)
        logits = raw / self.temperature.clamp_min(1e-3)
        return latent, logits

    def _entropy(self, logits: torch.Tensor) -> float:
        p = F.softmax(logits, dim=-1)
        ent = -(p * (p + 1e-9).log()).sum()
        return float(ent.item())

    def metabolic_step(
        self, x: torch.Tensor, context: torch.Tensor, tokens: int = 1
    ) -> dict:
        """One inference-time metabolic cycle: compute, measure, burn energy.

        Runs under ``no_grad`` (this is the streaming simulation path — no graph
        is retained).  Returns a dict of biological metrics for telemetry.
        """
        self._flops.reset()
        with torch.no_grad():
            latent, logits = self.forward(x, context)
        flops = self._flops.reset()
        entropy = self._entropy(logits)

        burn = (
            flops * self.config.flop_energy_cost
            + tokens * self.config.token_energy_cost
            + entropy * self.config.uncertainty_kappa   # κ·H : uncertainty drain
        )
        self.energy -= burn
        self._total_burn += burn
        self.age += 1
        self.last_entropy = entropy
        self.last_latent = latent.detach()

        return {
            "latent": latent.detach(),
            "logits": logits.detach(),
            "flops": flops,
            "energy_burn": burn,
            "energy": self.energy,
            "entropy": entropy,
            "temperature": float(self.temperature.item()),
        }

    # ====================================================================== #
    #  Homeostasis
    # ====================================================================== #
    def homeostasis(self, setpoint: float) -> dict:
        """Nudge ``temperature`` so activation entropy drifts toward ``setpoint``.

        A proportional controller: entropy above the setpoint (too disordered)
        raises temperature-driven sharpening, below it relaxes.  Bounded to keep
        the cell numerically stable.
        """
        error = self.last_entropy - setpoint
        gain = self.config.homeostasis_gain
        with torch.no_grad():
            # logits = effector(latent) / temperature, so a *lower* temperature
            # sharpens the distribution and sheds entropy.  error>0 means the cell
            # is too disordered, so we cool it by lowering temperature; error<0
            # relaxes it by raising temperature.  This is the negative-feedback
            # loop that keeps activation entropy near the setpoint.
            new_temp = self.temperature * (1.0 - gain * math.tanh(error))
            self.temperature.copy_(new_temp.clamp(0.1, 10.0))
        return {
            "entropy": self.last_entropy,
            "setpoint": setpoint,
            "error": error,
            "temperature": float(self.temperature.item()),
        }

    # ====================================================================== #
    #  Local adaptation (the only autograd path — fully isolated per cell)
    # ====================================================================== #
    def adapt(self, x: torch.Tensor, context: torch.Tensor, target: torch.Tensor) -> dict:
        """One gradient step aligning this cell's output to a target latent.

        This is the "learned representation" a cell transfers to its parent on
        apoptosis.  The optimizer only ever touches ``self.parameters()`` — which
        are leaf tensors created fresh for this cell — so the gradient graph is
        provably isolated from every other organism in the colony.
        """
        if self._optim is None:
            self._optim = torch.optim.SGD(self.parameters(), lr=self.config.adapt_lr, momentum=0.5)

        target = target.detach().to(self.device).reshape(-1)
        self._flops.reset()
        self._optim.zero_grad(set_to_none=True)
        latent, _ = self.forward(x, context)          # grad enabled here
        loss = 1.0 - F.cosine_similarity(latent, target, dim=0)
        loss.backward()
        self._optim.step()
        flops = self._flops.reset() * 2.0             # fwd + bwd (~2x)

        loss_val = float(loss.item())
        burn = flops * self.config.flop_energy_cost
        # Regeneration by PROGRESS (plan Fase 4): ATP is regained only for a real
        # drop in the sub-domain loss since the last adaptation — never for mere
        # activity, so a cell that fails to improve cannot refill and will die.
        delta_util = max(0.0, self._prev_loss - loss_val)
        regen = self.config.progress_regen * delta_util
        self._prev_loss = loss_val

        self.energy += (regen - burn)
        self._total_burn += burn
        self._total_regen += regen
        return {
            "loss": loss_val,
            "flops": flops,
            "energy_burn": burn,
            "regen": regen,
            "delta_util": delta_util,
            "energy": self.energy,
        }

    def energy_audit(self) -> dict:
        """Accounting audit (NOT physical conservation): the balance must equal
        ``initial − total_burn − total_transferred + total_regen`` within float
        error.  Division debits ``total_transferred`` (the energy handed to
        children), so the identity holds for progenitor and stem cells too, not
        only leaves."""
        expected = self._energy0 - self._total_burn - self._total_transferred + self._total_regen
        return {
            "energy": round(self.energy, 6),
            "expected": round(expected, 6),
            "total_burn": round(self._total_burn, 6),
            "total_transferred": round(self._total_transferred, 6),
            "total_regen": round(self._total_regen, 6),
            "balanced": abs(self.energy - expected) < 1e-4,
        }

    # ====================================================================== #
    #  Reverse distillation (test-time learning — Pillar 4)
    # ====================================================================== #
    def distill_from(
        self,
        teacher: "NeuralOrganism",
        probes: torch.Tensor,
        *,
        epochs: int = 25,
        lr: Optional[float] = None,
    ) -> dict:
        """Knowledge distillation between two organisms: the student (``self``)
        learns to match a ``teacher`` organism's latent function.

        This is a **neural KD primitive** (N1) — organism→organism only.  It is
        NOT the evolutionary coder's mechanism: refactoring is discrete,
        non-differentiable search with no gradient, and the coder promotes a
        winning AST transform to a catalog (see ``evolutionary_coder.py`` and
        ``HONESTY.md``).  Do not describe this as "reverse-distilling a code agent
        into the stem cell" — that is the disavowed category error.

        The student runs gradient descent to match the teacher's detached latent
        outputs over a batch of ``probes`` (``[B, embed_dim]``).  The teacher is
        evaluated under ``no_grad`` and its parameters are never touched — the
        graph is fully isolated to the student, so no gradient can leak into the
        teacher (or any other organism).
        """
        lr = self.config.adapt_lr if lr is None else lr
        probes = probes.detach().to(self.device)
        if probes.dim() == 1:
            probes = probes.unsqueeze(0)
        zero_ctx = torch.zeros(self.config.embed_dim, device=self.device)

        # Teacher targets — detached, computed once (the teacher does not learn).
        teacher_was_training = teacher.training
        teacher.eval()
        with torch.no_grad():
            targets = torch.stack([teacher.forward(p, zero_ctx)[0] for p in probes]).detach()
        if teacher_was_training:
            teacher.train()

        # Snapshot the teacher's weights to *prove* isolation (no leak).
        teacher_before = {k: v.detach().clone() for k, v in teacher.state_dict().items()}

        optim = torch.optim.SGD(self.parameters(), lr=lr, momentum=0.5)
        initial_loss = None
        final_loss = None
        self.train()
        for epoch in range(max(1, epochs)):
            optim.zero_grad(set_to_none=True)
            preds = torch.stack([self.forward(p, zero_ctx)[0] for p in probes])
            # 1 - mean cosine similarity to the teacher's latents (KD objective).
            loss = (1.0 - F.cosine_similarity(preds, targets, dim=1)).mean()
            loss.backward()
            optim.step()
            if epoch == 0:
                initial_loss = float(loss.item())
            final_loss = float(loss.item())

        # Verify the teacher was untouched (defensive integrity check).
        teacher_after = teacher.state_dict()
        teacher_unchanged = all(
            torch.equal(teacher_before[k], teacher_after[k]) for k in teacher_before
        )

        return {
            "initial_loss": round(initial_loss if initial_loss is not None else 0.0, 6),
            "final_loss": round(final_loss if final_loss is not None else 0.0, 6),
            "improved": (final_loss is not None and initial_loss is not None and final_loss < initial_loss),
            "epochs": epochs,
            "probes": int(probes.shape[0]),
            "teacher_unchanged": teacher_unchanged,
            "student": self.cell_id,
            "teacher": teacher.cell_id,
        }

    # ====================================================================== #
    #  Mitosis (fission) — structural self-replication
    # ====================================================================== #
    def divide(self, centroids: torch.Tensor) -> list["NeuralOrganism"]:
        """Undergo mitosis into ``len(centroids)`` specialised child cells.

        ``centroids`` is a ``[k, embed_dim]`` tensor of semantic cluster centres.
        Each child (a) is constructed fresh, (b) receives an exact deep-copy of the
        parent's ``state_dict`` (independent leaf tensors — no aliasing), (c) is
        perturbed by a **deterministic, per-layer relative** mutation seeded from
        the parent genome + child index (reproducible down the lineage), and (d)
        is specialised toward its centroid.  The parent's autograd graph is never
        shared — every child owns disjoint leaf parameters.
        """
        if not self.alive:
            raise RuntimeError(f"Dead cell {self.cell_id} cannot divide.")
        centroids = centroids.to(self.device)
        k = centroids.shape[0]

        parent_state = copy.deepcopy(self.state_dict())
        children: list[NeuralOrganism] = []
        energy_per_child = self.energy * self.config.child_energy_fraction / max(1, k)

        for i in range(k):
            centroid = F.normalize(centroids[i].reshape(-1), dim=0)
            spec = F.normalize(0.4 * self.specialization + 0.6 * centroid, dim=0)
            child_seed = derive_child_seed(self.genome.mutation_seed, i)
            child = NeuralOrganism(
                cell_id=f"{self.cell_id}.{i}",
                config=self.config,
                generation=self.generation + 1,
                lineage=f"{self.lineage}.{i}",
                energy=energy_per_child,
                device=self.device,
                specialization=spec,
                mutation_seed=child_seed,
            )
            # Exact copy of the parent genome into the child's own tensors …
            child.load_state_dict({k: v.detach().clone() for k, v in parent_state.items()})
            # … then a reproducible per-layer relative mutation …
            gen = torch.Generator().manual_seed(int(child_seed))
            child.mutate(generator=gen)
            # … and re-assert the child-specific buffers.
            with torch.no_grad():
                child.specialization.copy_(spec.detach())
                child.inherited_memory.zero_()
                child.temperature.copy_(self.temperature.detach())
            children.append(child)

        # The parent pays the metabolic price of replication: the energy handed to
        # the children is recorded as a TRANSFER (not a burn), keeping the
        # accounting identity exact for the dividing cell (review finding #1).
        handed = self.energy * self.config.child_energy_fraction
        self._total_transferred += handed
        self.energy *= (1.0 - self.config.child_energy_fraction)
        return children

    # ====================================================================== #
    #  Representation transfer + apoptosis
    # ====================================================================== #
    def absorb(self, latent: torch.Tensor, weight: float = 1.0) -> None:
        """Fold a (dying) child's learned latent into this cell's memory.

        A decaying running blend: the parent inherits each child's final
        representation just before that child's resources are reclaimed, with
        older contributions geometrically discounted so the memory trace stays
        bounded rather than growing without limit as many children die.
        """
        latent = latent.detach().to(self.device).reshape(-1)
        with torch.no_grad():
            self.inherited_memory.mul_(0.6).add_(weight * latent)

    def apoptose(self) -> dict:
        """Programmed cell death: detach params, drop refs, reclaim memory.

        Returns a small report used by the telemetry stream.  After this call the
        cell is inert (``alive == False``) and its parameter storage is eligible
        for immediate garbage collection.
        """
        if not self.alive:
            return {"cell_id": self.cell_id, "already_dead": True}
        self.alive = False
        param_bytes = sum(
            p.numel() * p.element_size() for p in self.parameters()
        ) + sum(b.numel() * b.element_size() for b in self.buffers())

        # Break autograd references and free hooks.
        self._flops.close()
        self._optim = None
        self.last_latent = None
        with torch.no_grad():
            for p in self.parameters():
                p.detach_()
                p.grad = None
        # Move storage off the accelerator so empty_cache can actually reclaim it.
        self.to("cpu")

        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

        return {
            "cell_id": self.cell_id,
            "reclaimed_bytes": int(param_bytes),
            "age": self.age,
            "residual_energy": self.energy,
        }

    # ====================================================================== #
    #  Introspection
    # ====================================================================== #
    def param_count(self) -> int:
        return sum(p.numel() for p in self.parameters())

    def vitals(self) -> dict:
        return {
            "cell_id": self.cell_id,
            "generation": self.generation,
            "lineage": self.lineage,
            "alive": self.alive,
            "energy": round(self.energy, 3),
            "age": self.age,
            "entropy": round(self.last_entropy, 4),
            "temperature": round(float(self.temperature.item()), 4),
            "params": self.param_count(),
        }

    def __repr__(self) -> str:  # pragma: no cover - cosmetic
        state = "alive" if self.alive else "apoptotic"
        return (
            f"<NeuralOrganism {self.cell_id} gen={self.generation} "
            f"{state} E={self.energy:.1f} H={self.last_entropy:.2f}>"
        )
