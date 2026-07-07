"""
bioma_orchestrator — the ONLINE, self-evolving multi-LLM orchestrator (dual-mode).

The commercial online surface that complements the sovereign, offline
``bioma_engine`` core.  It orchestrates market LLMs (via a single OpenRouter
gateway or any provider adapter), routes tasks to specialist "cells" that
MULTIPLY (prompt mitosis) and DIE (apoptosis), and learns online — from an
automated judge + objective cost/latency — which model/prompt wins for which
task-type.  What evolves is the orchestration; the vendor models are unchanged.

Kept OUTSIDE ``bioma_engine`` on purpose: the sovereign core keeps its
``FULLY AUTONOMOUS`` guarantee; choosing this online layer is explicit.
"""

from .providers import Completion, ModelSpec, LLMProvider, MockProvider, OpenRouterProvider
from .evolution import (
    Judge, MockJudge, RuleJudge, FitnessReport, fitness, blended_reward, OrchestrationCell,
)
from .orchestrator import EvolutionaryOrchestrator

__all__ = [
    "Completion", "ModelSpec", "LLMProvider", "MockProvider", "OpenRouterProvider",
    "Judge", "MockJudge", "RuleJudge", "FitnessReport", "fitness", "blended_reward",
    "OrchestrationCell", "EvolutionaryOrchestrator",
]
