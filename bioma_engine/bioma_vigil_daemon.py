"""
`bioma_vigil_daemon.py` — Central orchestration broker (the "vigil daemon").

A warm, long-lived facade that holds ready instances of the B.I.O.M.A.
evolutionary runtime and brokers external requests into it.  The integration
hook (`bioma_integration_hook.py`) routes ingested prompts here; this module
owns the actual orchestration.

Honesty (see ``HONESTY.md``)
---------------------------
* **`DigitalForager` is OFFLINE and deterministic.**  It does **not** perform
  live ArXiv/GitHub harvesting.  The whole framework is offline & reproducible by
  design (no downloads, no external API).  The forager derives a *reproducible*
  "scientific nutrient" context vector from the request text (a seeded
  hash-embedding) and injects it into a :class:`HormonalBus`.  A live-web
  harvesting mode would be network-gated and non-reproducible, and is
  deliberately excluded from the validated runtime.
* **The optimizer is the framework's own deterministic AST-transform catalog**
  (Fase 10) run in isolated subprocess sandboxes with hard timeouts — fully
  autonomous, with no dependency on any external model, API or network.
"""

from __future__ import annotations

import collections
import dataclasses
import hashlib
import os
from dataclasses import dataclass
from typing import Optional

import torch
import torch.nn.functional as F

from .config import BiomaConfig, DEFAULT_CONFIG, DEVICE
from .hormonal_bus import HormonalBus
from .evolutionary_coder import EvolutionaryCoder


class DigitalForager:
    """Offline, deterministic scientific-nutrient forager.

    Derives a reproducible context tensor from request text.  Does NOT touch the
    network — live ArXiv/GitHub harvesting is intentionally not part of the
    validated, reproducible runtime (see module docstring / ``HONESTY.md``).
    """

    def __init__(self, config: BiomaConfig = DEFAULT_CONFIG, device: Optional[torch.device] = None):
        self.config = config
        self.device = device or DEVICE

    def forage(self, text: str) -> torch.Tensor:
        """Return a unit ``[embed_dim]`` nutrient vector, reproducible for a given text."""
        tokens = [t for t in (text or "").lower().split() if t] or ["<empty>"]
        acc = torch.zeros(self.config.embed_dim)
        for tok in tokens:
            seed = int.from_bytes(hashlib.sha256(tok.encode("utf-8")).digest()[:8], "little")
            gen = torch.Generator().manual_seed(seed % (2**31))
            acc += torch.randn(self.config.embed_dim, generator=gen)
        return F.normalize(acc, dim=0).to(self.device)


@dataclass
class OrchestrationResult:
    """Structured result of one brokered evolutionary optimization."""

    best_source: str
    winning_transform: str
    improved: bool
    latency_gain_pct: float
    lineages_mutated: int
    apoptosis_cleans: int
    nutrient_norm: float
    baseline_report: dict
    best_report: dict
    cached: bool = False   # served from the offline nutrient cache (no evolution run)


class VigilDaemon:
    """Concurrency-safe orchestration broker into the evolutionary runtime.

    Each :meth:`orchestrate` call spins up its **own** :class:`EvolutionaryCoder`
    (bounded pool sized to the host cores) and tears it down in a ``finally`` — so
    concurrent requests are fully isolated (no shared mutable state to race on)
    and the host stays flat in memory.  A bounded **offline result cache** serves
    repeat requests sub-second without re-running the sandboxes.
    """

    def __init__(self, config: BiomaConfig = DEFAULT_CONFIG, *, timeout_s: float = 8.0,
                 cache_size: int = 128):
        self.config = config
        self.forager = DigitalForager(config)
        self.max_workers = max(2, min(10, (os.cpu_count() or 4) - 2))  # e.g. 10 on a 12-core host
        self.default_timeout_s = timeout_s
        self._cache: "collections.OrderedDict[str, OrchestrationResult]" = collections.OrderedDict()
        self._cache_size = cache_size

    def inject_nutrient(self, text: str) -> float:
        """Forage a nutrient from ``text`` and secrete it into a FRESH hormonal
        bus (released immediately), returning the injected field norm.  A fresh
        bus per call guarantees no cross-request accumulation."""
        bus = HormonalBus(self.config)
        bus.register("forager")
        try:
            vec = self.forager.forage(text)
            bus.secrete_sync("forager", vec, blend=1.0)
            return round(float(bus.active_field().norm().item()), 4)
        finally:
            bus.release("forager")

    @staticmethod
    def _cache_key(source: str, entrypoint: str, test_cases, generations: int, population: int) -> str:
        raw = f"{source}|{entrypoint}|{test_cases!r}|{generations}|{population}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    async def orchestrate(
        self, *, source: str, entrypoint: str, test_cases: list,
        generations: int, population: int, nutrient_text: str,
        timeout_s: Optional[float] = None, use_cache: bool = True,
    ) -> OrchestrationResult:
        """Inject the nutrient, then serve from cache or run the optimizer.

        A cache hit (offline gate) returns instantly; otherwise a fresh, isolated
        coder runs the AST-catalog evolution to convergence and the result is
        cached.  ``timeout_s`` bounds each sandbox execution (rogue variants like
        an infinite loop are apoptosed at this deadline)."""
        nutrient_norm = self.inject_nutrient(nutrient_text)
        key = self._cache_key(source, entrypoint, test_cases, generations, population)

        if use_cache and key in self._cache:
            self._cache.move_to_end(key)
            return dataclasses.replace(self._cache[key], cached=True, nutrient_norm=nutrient_norm)

        coder = EvolutionaryCoder(
            self.config, max_workers=self.max_workers,
            timeout_s=self.default_timeout_s if timeout_s is None else float(timeout_s),
        )
        try:
            result = await coder.evolve(
                source, entrypoint, test_cases, generations=generations, population=population,
            )
        finally:
            coder.shutdown()  # drain this request's pool → isolated + leak-free

        lineages = sum(int(h.get("population", 0)) for h in result["history"])
        out = OrchestrationResult(
            best_source=result["best_source"],
            winning_transform=result["winning_transform"],
            improved=result["improved"],
            latency_gain_pct=result["latency_gain_pct"],
            lineages_mutated=lineages,
            apoptosis_cleans=result["apoptosis_count"],
            nutrient_norm=nutrient_norm,
            baseline_report=result["baseline_report"],
            best_report=result["best_report"],
            cached=False,
        )
        if use_cache:
            self._cache[key] = out
            self._cache.move_to_end(key)
            while len(self._cache) > self._cache_size:
                self._cache.popitem(last=False)
        return out

    def clear_cache(self) -> None:
        self._cache.clear()

    def shutdown(self) -> None:
        self._cache.clear()


# --------------------------------------------------------------------------- #
#  Process-wide warm daemon (the "vigil" stays resident between requests)
# --------------------------------------------------------------------------- #
_DAEMON: Optional[VigilDaemon] = None


def get_daemon(config: BiomaConfig = DEFAULT_CONFIG) -> VigilDaemon:
    """Return the resident daemon, instantiating it on first use."""
    global _DAEMON
    if _DAEMON is None:
        _DAEMON = VigilDaemon(config)
    return _DAEMON


def shutdown_daemon() -> None:
    """Tear down the resident daemon (drains its thread pool)."""
    global _DAEMON
    if _DAEMON is not None:
        _DAEMON.shutdown()
        _DAEMON = None
