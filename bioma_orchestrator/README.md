# B.I.O.M.A. Orchestrator — online, self-evolving multi-LLM layer

The **online commercial surface** of B.I.O.M.A. — a dual-mode counterpart to the
sovereign, offline `bioma_engine` core. It orchestrates market LLMs, routes each
task to specialist **cells** that *multiply* (prompt mitosis) and *die*
(apoptosis), and **learns online** — from an automated judge + objective
cost/latency — which model/prompt wins for which task type.

> **Dual-mode by design.** This package lives OUTSIDE `bioma_engine/` so the
> sovereign core keeps its `FULLY AUTONOMOUS ✓` guarantee. Choosing the online
> orchestrator is an explicit decision: **data leaves the host** and vendor +
> token cost apply.

## What evolves (and what doesn't)
- ✅ **The orchestration evolves**: routing policy, prompts, fan-out, verification
  — learned online from real outcomes. Cells are `(model, prompt, role)` policies
  that are born, reinforced, and apoptosed.
- ❌ **The vendor LLMs never change** — they are the organs the cells use. "Self-
  evolving like a living cell" = the orchestration population adapts to your
  actual task distribution, not model retraining.

## Quickstart (offline / mock — no key)
```python
from bioma_orchestrator import MockProvider, MockJudge, EvolutionaryOrchestrator

skills = {"smart-pro": {"reason": 0.92}, "code-spec": {"code": 0.95}, "cheap": {"general": 0.55}}
prices = {"smart-pro": (5, 25), "code-spec": (2, 8), "cheap": (0.3, 1.2)}   # $/1M in,out
orch = EvolutionaryOrchestrator(MockProvider(skills, prices), list(skills), judge=MockJudge())

for i in range(200):
    orch.handle(f"reason task {i}", task_type="reason")
print(orch.best_route("reason"), orch.stats()["total_cost_usd"])
```

## Online (real — OpenRouter gateway)
```python
import os
from bioma_orchestrator import OpenRouterProvider, EvolutionaryOrchestrator

os.environ["OPENROUTER_API_KEY"] = "sk-or-..."
prices = {"openai/gpt-4o": (2.5, 10), "anthropic/claude-3.5-sonnet": (3, 15),
          "google/gemini-flash-1.5": (0.075, 0.3)}
provider = OpenRouterProvider(prices=prices)
orch = EvolutionaryOrchestrator(provider, list(prices))
result = orch.handle("Refactor this service for idempotent retries…", task_type="code")
```
The automated `MockJudge` is a stand-in — plug an `LLMJudge` (an OpenRouter call)
or a `RuleJudge`/test-runner for the objective signal in production.

## How a task flows
1. **Divergence gauge** → simple call, or **mitosis fan-out** into `k` specialists.
2. **Contextual Thompson sampling** routes to the cell most likely to win *for
   this task type* (online learning).
3. **Fitness** = judge quality + objective cost/latency (`blended_reward`).
4. **Apoptosis** prunes cells whose learned value is dominated (population-floored);
   periodic **prompt mitosis** spawns a mutated child of the current best.
5. **FinOps** tracks tokens + cost; `save()/load()` persist the evolved population.

## Status
- **v1 (this):** provider abstraction + OpenRouter adapter + evolutionary router +
  fitness/apoptosis + online routing + FinOps + persistence. **8/8 tests green**
  (offline, deterministic) — proving online convergence, cost-aware routing,
  fan-out, apoptosis, and persistence.
- **v2 (next):** real `LLMJudge`, prompt-evolution fitness from live feedback,
  A/B + rollback guardrails, richer contextual features.
- **v3:** multi-tenant FastAPI service, cost caps, observability, safety.

## Honest boundaries
- The offline test-suite uses a **mock provider** (simulated model skill) — the
  same way the sovereign core uses an analytic ground-truth to validate. No
  external model is called in tests.
- Online mode calls real vendors → cost, latency and data-egress are real; the
  fitness judge can itself be wrong and needs calibration + guardrails before it
  drives production behavior.
