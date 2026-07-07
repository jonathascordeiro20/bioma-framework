"""
B.I.O.M.A. — Biologically Inspired Orchestration of Mutating Agents
==================================================================

A PyTorch framework that treats autonomous agents as living neural organisms
which undergo mitosis (fission), homeostasis (entropy balance) and apoptosis
(programmed death) driven by the semantic complexity of the incoming prompt.

Public surface
--------------
    from bioma_engine import MitosisEngine, BiomaConfig
    engine = MitosisEngine()
    async for event in engine.run("your complex scenario"):
        ...  # stream of TelemetryEvent
"""

from __future__ import annotations

from .config import BiomaConfig, DEFAULT_CONFIG, DEVICE, resolve_device, seed_everything
from .organism_core import NeuralOrganism, FlopMeter
from .hormonal_bus import HormonalBus
from .mitosis_engine import (
    MitosisEngine,
    Colony,
    PromptEmbedder,
    semantic_divergence,
    workload_entropy,
    kmeans,
    resource_snapshot,
    live_cells_global,
)
from .evolutionary_coder import (
    EvolutionaryCoder,
    FitnessReport,
    DEMO_SLOW_SQRT,
    DEMO_SQRT_TESTS,
    DEMO_SLOW_FIB,
    DEMO_FIB_TESTS,
)
from .observability import (
    BioEvent,
    BioEventSink,
    record_run,
    compute_csr,
    csr_over_runs,
    wilson_lower_bound,
    count_live_organisms,
    leak_soak,
    race_probe,
)
from .telemetry import TelemetryEvent, render, banner

__all__ = [
    "BiomaConfig",
    "DEFAULT_CONFIG",
    "DEVICE",
    "resolve_device",
    "seed_everything",
    "NeuralOrganism",
    "FlopMeter",
    "HormonalBus",
    "MitosisEngine",
    "Colony",
    "PromptEmbedder",
    "semantic_divergence",
    "workload_entropy",
    "kmeans",
    "resource_snapshot",
    "live_cells_global",
    "EvolutionaryCoder",
    "FitnessReport",
    "DEMO_SLOW_SQRT",
    "DEMO_SQRT_TESTS",
    "DEMO_SLOW_FIB",
    "DEMO_FIB_TESTS",
    "BioEvent",
    "BioEventSink",
    "record_run",
    "compute_csr",
    "csr_over_runs",
    "wilson_lower_bound",
    "count_live_organisms",
    "leak_soak",
    "race_probe",
    "TelemetryEvent",
    "render",
    "banner",
]

__version__ = "1.0.0"
