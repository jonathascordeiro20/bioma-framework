"""
orchestrator.py — the online, self-evolving LLM orchestrator.

An in-process **elastic orchestrator** that treats routing policies as living
cells.  For each task it:

  1. gauges complexity (a divergence proxy) → decides a single call or a MITOSIS
     fan-out into ``k`` specialist cells;
  2. routes via **contextual Thompson sampling** over the alive cells (online
     learning — which model/prompt wins for which task-type);
  3. calls the provider, scores the result (judge + objective cost/latency),
     and updates the winning cell's belief + energy;
  4. **apoptoses** cells whose reward decays (keeping a minimum population), and
     periodically spawns a mutated-prompt child of the current best (**prompt
     evolution**);
  5. tracks FinOps (tokens + cost) and can persist the evolved population.

Honest scope: what evolves is the ORCHESTRATION (routing + prompts + fan-out +
verification), learned online from real outcomes.  The vendor LLMs are the organs
the cells use — they are never modified.
"""

from __future__ import annotations

import json
import random
from collections import Counter
from typing import Optional

from .providers import LLMProvider, Completion
from .evolution import OrchestrationCell, Judge, MockJudge, fitness, blended_reward
from .context import ContextPruner, SYSTEM, USER


class EvolutionaryOrchestrator:
    _PROMPT_MUTATIONS = (
        "{task}",
        "{task}\n\nThink step by step, then give the final answer.",
        "{task}\n\nBe concise and precise.",
        "You are a senior expert. {task}",
        "{task}\n\nDouble-check correctness before answering.",
    )

    def __init__(self, provider: LLMProvider, models: list[str], *,
                 judge: Optional[Judge] = None, seed: int = 7,
                 fanout_threshold: float = 0.6, max_fanout: int = 3,
                 apoptosis_floor: float = 0.35, min_calls: int = 3,
                 min_population: int = 2, max_population: int = 8, mitosis_every: int = 30,
                 prune_context: bool = True, input_price_per_m: float = 3.0):
        self.provider = provider
        self.judge = judge or MockJudge()
        self.rng = random.Random(seed)
        # Context apoptosis (kernel-backed) trims the window before every route.
        self.prune_context = prune_context
        self.input_price_per_m = input_price_per_m
        self.ctx_full_tokens = 0
        self.ctx_pruned_tokens = 0
        self.cells: list[OrchestrationCell] = [
            OrchestrationCell(cell_id=f"cell:{m}", model=m) for m in models
        ]
        self.fanout_threshold = fanout_threshold
        self.max_fanout = max_fanout
        self.apoptosis_floor = apoptosis_floor
        self.min_calls = min_calls
        self.min_population = min_population
        self.max_population = max_population
        self.mitosis_every = mitosis_every
        # FinOps + lineage counters
        self.total_cost = 0.0
        self.total_in = 0
        self.total_out = 0
        self.calls_made = 0
        self.total_mitosis = 0
        self.total_apoptosis = 0
        self.route_log: list[tuple[str, str]] = []
        self._t = 0

    # -- helpers ---------------------------------------------------------- #
    def _alive(self) -> list[OrchestrationCell]:
        return [c for c in self.cells if c.alive]

    def _divergence(self, task: str) -> float:
        """Cheap complexity gauge: lexical variety × size → in [0, 1]."""
        words = task.split()
        if not words:
            return 0.0
        uniq = len(set(w.lower() for w in words))
        lexical = uniq / len(words)
        size = min(1.0, len(words) / 24.0)
        return round(0.5 * lexical + 0.5 * size, 4)

    def _select_k(self, task_type: str, k: int) -> list[OrchestrationCell]:
        alive = self._alive()
        ranked = sorted(alive, key=lambda c: c.sample(task_type, self.rng), reverse=True)
        # distinct models first (diverse specialists on a fan-out)
        chosen, seen = [], set()
        for c in ranked:
            if c.model not in seen:
                chosen.append(c)
                seen.add(c.model)
            if len(chosen) >= k:
                break
        return chosen or ranked[:k]

    def _finops(self, comp: Completion) -> None:
        self.total_cost += comp.cost_usd
        self.total_in += comp.in_tokens
        self.total_out += comp.out_tokens
        self.calls_made += 1

    # -- lifecycle -------------------------------------------------------- #
    def _apoptosis(self) -> int:
        """Kill cells whose learned value is clearly dominated.  Uses the posterior
        MEAN (stable with few samples) so a Thompson-starved bad cell still dies —
        while the population never drops below the floor."""
        dead = 0
        for c in list(self._alive()):
            if len(self._alive()) <= self.min_population:
                break
            means = [c.mean(tt) for tt in c.stats if c.calls(tt) >= self.min_calls]
            if means and (sum(means) / len(means) < self.apoptosis_floor or c.energy <= 0.0):
                c.alive = False
                self.total_apoptosis += 1
                dead += 1
        return dead

    def _mutate_prompt(self, template: str) -> str:
        return self.rng.choice(self._PROMPT_MUTATIONS)

    def _mitosis(self, task_type: str) -> int:
        alive = self._alive()
        if len(alive) >= self.max_population:
            return 0
        best = max(alive, key=lambda c: c.mean(task_type))
        mut = self._mutate_prompt(best.prompt_template)
        if mut == best.prompt_template:
            return 0
        child = OrchestrationCell(
            cell_id=f"{best.model}#g{best.generation + 1}.{self._t}",
            model=best.model, prompt_template=mut, role=best.role,
            generation=best.generation + 1, parent_id=best.cell_id,
        )
        child.stats = {tt: dict(s) for tt, s in best.stats.items()}   # warm-start belief
        self.cells.append(child)
        self.total_mitosis += 1
        return 1

    # -- main entry ------------------------------------------------------- #
    def _prune_context(self, context) -> str:
        """Apoptose low-relevance context (kernel-backed) → the pruned prefix.
        Accumulates the FinOps saving.  ``context`` items are strings or dicts
        ``{content, oxygen, signal}``."""
        p = ContextPruner()
        for item in context:
            if isinstance(item, str):
                p.add(item, oxygen=1.0, signal=0)
            else:
                p.add(item["content"], oxygen=float(item.get("oxygen", 1.0)),
                      signal=int(item.get("signal", 0)))
        full = p.full_tokens()
        if self.prune_context:
            p.prune_cycles(3, rate=0.34, reinforce_mask=SYSTEM | USER, reinforce_amount=0.35)
        self.ctx_full_tokens += full
        self.ctx_pruned_tokens += p.active_tokens()
        surviving = p.active_context()
        return (p.render() + "\n\n") if surviving else ""

    def handle(self, task: str, task_type: str = "general", context=None) -> dict:
        self._t += 1
        prefix = self._prune_context(context) if context else ""
        div = self._divergence(task)
        k = 1 if div < self.fanout_threshold else min(self.max_fanout, len(self._alive()))
        chosen = self._select_k(task_type, k)

        results = []
        for cell in chosen:
            comp = self.provider.complete(prefix + cell.render(task), cell.model,
                                          system=task_type, context={"task_type": task_type})
            fr = fitness(comp, task, self.judge)
            reward = blended_reward(fr)
            cell.update(task_type, reward)
            self._finops(comp)
            self.route_log.append((task_type, cell.model))
            results.append((cell, comp, fr, reward))

        best = max(results, key=lambda x: x[3])
        apoptosed = self._apoptosis()
        born = self._mitosis(task_type) if (self._t % self.mitosis_every == 0) else 0

        return {
            "answer": best[1].text, "model": best[0].model, "cell": best[0].cell_id,
            "reward": round(best[3], 4), "quality": best[2].quality,
            "cost_usd": round(sum(r[1].cost_usd for r in results), 6),
            "fanout": k, "divergence": div,
            "apoptosed": apoptosed, "born": born, "population": len(self._alive()),
        }

    # -- introspection / persistence ------------------------------------- #
    def best_route(self, task_type: str) -> Optional[str]:
        alive = self._alive()
        return max(alive, key=lambda c: c.mean(task_type)).model if alive else None

    def route_share(self, task_type: str, last_n: int = 50) -> dict:
        recent = [m for (tt, m) in self.route_log if tt == task_type][-last_n:]
        if not recent:
            return {}
        c = Counter(recent)
        return {m: round(n / len(recent), 3) for m, n in c.most_common()}

    def stats(self) -> dict:
        ctx_saved = self.ctx_full_tokens - self.ctx_pruned_tokens
        ctx_reduction = (100.0 * ctx_saved / self.ctx_full_tokens) if self.ctx_full_tokens else 0.0
        return {
            "calls": self.calls_made,
            "total_cost_usd": round(self.total_cost, 6),
            "total_in_tokens": self.total_in, "total_out_tokens": self.total_out,
            "population_alive": len(self._alive()),
            "total_mitosis": self.total_mitosis, "total_apoptosis": self.total_apoptosis,
            # Context apoptosis FinOps (kernel-backed) — accrued across every route.
            "context_full_tokens": self.ctx_full_tokens,
            "context_pruned_tokens": self.ctx_pruned_tokens,
            "context_reduction_pct": round(ctx_reduction, 1),
            "context_cost_saved_usd": round(ctx_saved / 1e6 * self.input_price_per_m, 6),
            "cells": [c.to_dict() for c in self.cells],
        }

    def save(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump({"cells": [c.to_dict() for c in self.cells],
                       "finops": {"total_cost_usd": round(self.total_cost, 6),
                                  "calls": self.calls_made}}, fh, indent=2, ensure_ascii=False)

    def load(self, path: str) -> None:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        self.cells = [OrchestrationCell.from_dict(d) for d in data["cells"]]
