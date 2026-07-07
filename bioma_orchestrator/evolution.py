"""
evolution.py — the living, evolving unit of the online orchestrator.

  * ``Judge`` / ``MockJudge`` / ``RuleJudge`` — automated quality signal
    (LLM-judge + rules), per the chosen fitness strategy.
  * ``fitness`` + ``blended_reward`` — combine judged **quality** with the
    objective **cost** and **latency** signals into one reward in ``[0, 1]``.
  * ``OrchestrationCell`` — a "living cell": a policy ``(model, prompt, role)``
    with a genome, an energy budget, and a **contextual Thompson-sampling** stat
    per task-type.  Cells are what MULTIPLY (mitosis of a mutated prompt) and DIE
    (apoptosis when their reward decays) — the LLMs themselves never change.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional

from .providers import Completion


# --------------------------------------------------------------------------- #
#  Fitness — automated judge + objective metrics
# --------------------------------------------------------------------------- #
@dataclass
class FitnessReport:
    quality: float
    cost_usd: float
    latency_s: float


class Judge(ABC):
    @abstractmethod
    def evaluate(self, completion: Completion, task: str) -> float:
        """Return a quality score in ``[0, 1]``."""


class MockJudge(Judge):
    """Offline stand-in for an LLM-judge: reads the simulated answer quality."""
    def evaluate(self, completion: Completion, task: str) -> float:
        return float(completion.meta.get("quality", 0.5))


class RuleJudge(Judge):
    """Objective rule score: non-empty output that contains required markers.
    Composable with an LLM-judge in production (min/mean of the two)."""
    def __init__(self, required: tuple = ()):
        self.required = required

    def evaluate(self, completion: Completion, task: str) -> float:
        text = completion.text or ""
        if not text.strip():
            return 0.0
        if not self.required:
            return 1.0
        hits = sum(1 for k in self.required if k in text)
        return hits / len(self.required)


def fitness(completion: Completion, task: str, judge: Judge) -> FitnessReport:
    return FitnessReport(quality=round(judge.evaluate(completion, task), 4),
                         cost_usd=completion.cost_usd, latency_s=completion.latency_s)


def blended_reward(fr: FitnessReport, *, cost_ref: float = 0.002, lat_ref: float = 1.5,
                   weights: tuple = (0.8, 0.15, 0.05)) -> float:
    """Fitness the online policy optimises: quality-dominant, with cost & latency
    as objective tie-breakers (so equal-quality routes prefer the cheaper/faster
    model).  Returns a reward in ``[0, 1]``."""
    wq, wc, wl = weights
    r = (wq * fr.quality
         + wc * (1.0 - min(1.0, fr.cost_usd / cost_ref))
         + wl * (1.0 - min(1.0, fr.latency_s / lat_ref)))
    return max(0.0, min(1.0, r))


# --------------------------------------------------------------------------- #
#  OrchestrationCell — the living, multiplying, apoptosing policy
# --------------------------------------------------------------------------- #
@dataclass
class OrchestrationCell:
    cell_id: str
    model: str
    prompt_template: str = "{task}"
    role: str = "generalist"
    generation: int = 0
    parent_id: Optional[str] = None
    energy: float = 100.0
    alive: bool = True
    # contextual bandit: per task-type Beta(a, b) + reward EMA + call count
    stats: dict = field(default_factory=dict)

    def _s(self, task_type: str) -> dict:
        return self.stats.setdefault(task_type, {"a": 1.0, "b": 1.0, "ema": 0.5, "n": 0})

    def sample(self, task_type: str, rng) -> float:
        s = self._s(task_type)
        return rng.betavariate(s["a"], s["b"])          # Thompson draw

    def mean(self, task_type: str) -> float:
        s = self._s(task_type)
        return s["a"] / (s["a"] + s["b"])

    def calls(self, task_type: str) -> int:
        return self._s(task_type)["n"]

    def ema(self, task_type: str) -> float:
        return self._s(task_type)["ema"]

    def update(self, task_type: str, reward01: float) -> None:
        s = self._s(task_type)
        r = max(0.0, min(1.0, reward01))
        s["a"] += r
        s["b"] += (1.0 - r)
        s["n"] += 1
        s["ema"] = 0.85 * s["ema"] + 0.15 * r
        # energy: earns on good outcomes, drains on poor ones → drives apoptosis
        self.energy = max(0.0, min(200.0, self.energy - 1.0 + 2.0 * r))

    def render(self, task: str) -> str:
        return self.prompt_template.replace("{task}", task)

    def to_dict(self) -> dict:
        return {"cell_id": self.cell_id, "model": self.model, "prompt_template": self.prompt_template,
                "role": self.role, "generation": self.generation, "parent_id": self.parent_id,
                "energy": round(self.energy, 3), "alive": self.alive, "stats": self.stats}

    @classmethod
    def from_dict(cls, d: dict) -> "OrchestrationCell":
        c = cls(d["cell_id"], d["model"], d.get("prompt_template", "{task}"),
                d.get("role", "generalist"), d.get("generation", 0), d.get("parent_id"),
                d.get("energy", 100.0), d.get("alive", True))
        c.stats = d.get("stats", {})
        return c
