"""
run_elite_benchmark.py — B.I.O.M.A. Elite Multi-Model Benchmark (OpenRouter).

Drives the REAL B.I.O.M.A. flow across every market model through ONE unified
OpenRouter endpoint:

  * the Hormonal Bus (Rust kernel) sets per-cycle priority (stress);
  * Memory Apoptosis (Rust kernel) trims context noise every iteration;
  * when complexity is high, NEURONAL MITOSIS opens parallel async calls
    (`asyncio.gather`) to branch competing hypotheses;
  * the OpenRouter provider retries 429/5xx with exponential backoff and captures
    per-request RTT + real token usage + cost.

Set `OPENROUTER_API_KEY` to run against the real models; otherwise it runs the
offline MOCK provider (same pipeline, no network, no cost) so the flow is
verifiable end-to-end.

Run:  python run_elite_benchmark.py
"""

from __future__ import annotations

import asyncio
import os
import time

import bioma_kernel as bk
from bioma_orchestrator.context import ContextPruner, SYSTEM, USER, TOOL
from bioma_orchestrator.openrouter_async import (
    AsyncOpenRouterProvider, MockAsyncProvider, AsyncProvider,
)

# Auto-load OPENROUTER_API_KEY from a local `.env` file next to this script,
# regardless of the working directory (the .env is git-ignored, never committed).
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
except Exception:
    pass

CORTISOL = 1 << 0
MITOSIS_STRESS = 0.75

MODELS = [
    "anthropic/claude-3.5-sonnet",     # reference for logic / refactoring
    "openai/gpt-4o",                   # reference for agent consistency
    "x-ai/grok-2",                     # low-latency predator
    "meta-llama/llama-3-70b-instruct", # open-source giant
]

SYSTEM_DIRECTIVES = (
    "You are a senior security + systems engineer. Solve the task across multiple "
    "decision cycles: analyze, hypothesize fixes, verify invariants, and deliver a "
    "concrete, correct remediation. Be precise."
)

# 3 complex, multi-cycle engineering/cybersecurity problems.
DATASET = [
    {
        "id": "sqli-refactor",
        "statement": "A payment service builds SQL by string concatenation. Sweep for "
                     "injection and auto-refactor to a safe data-access layer.",
        "cycles": 3, "complexity": 0.92,
        "rubric": ["parameterized", "prepared statement", "input validation", "least privilege"],
        "hypotheses": ["ORM with bound parameters", "prepared statements + allowlist",
                       "stored procedures + WAF"],
    },
    {
        "id": "distributed-lock-race",
        "statement": "A distributed lock has a race causing double-spend under retries. "
                     "Diagnose and make the critical section correct.",
        "cycles": 3, "complexity": 0.86,
        "rubric": ["idempotency", "atomic", "fencing token", "timeout"],
        "hypotheses": ["Redlock + fencing token", "DB transaction + CAS", "idempotency key + dedup"],
    },
    {
        "id": "c-parser-memsafety",
        "statement": "Audit a C packet parser for buffer overflow and propose a "
                     "memory-safe rewrite path with test coverage.",
        "cycles": 3, "complexity": 0.80,
        "rubric": ["bounds check", "safe allocation", "fuzzing", "sanitizer"],
        "hypotheses": ["bounds-checked rewrite", "port to a safe subset", "add fuzzing + ASan"],
    },
]


def score_solution(problem: dict, answer: str, model: str, is_mock: bool) -> int:
    """Real: rubric coverage of the actual answer. Mock: the model's quality profile."""
    if is_mock:
        from bioma_orchestrator.openrouter_async import _MOCK_PROFILE
        q = _MOCK_PROFILE.get(model, {"quality": 0.7})["quality"]
        jitter = (abs(hash((model, problem["id"]))) % 9) - 4
        return max(0, min(100, round(q * 100 + jitter)))
    a = (answer or "").lower()
    hits = sum(1 for kw in problem["rubric"] if kw.lower() in a)
    return round(100 * hits / len(problem["rubric"]))


async def run_problem(provider: AsyncProvider, model: str, problem: dict, is_mock: bool) -> dict:
    bus = bk.HormonalBus(8)
    ctx = ContextPruner()
    ctx.add(SYSTEM_DIRECTIVES, oxygen=50.0, signal=SYSTEM)
    ctx.add(problem["statement"], oxygen=8.0, signal=USER)

    loops = mitoses = 0
    tok_init = tok_final = 0
    rtts: list[float] = []
    cost = 0.0
    last_answer = ""
    cycles = problem["cycles"]

    for cycle in range(cycles):
        # --- Hormonal priority: stress ∝ complexity of the unresolved task --- #
        bus.secrete(CORTISOL, problem["complexity"])
        stress = bus.sense(CORTISOL)

        # --- New cycle inputs (a step + verbose tool noise) --- #
        ctx.add(f"[cycle {cycle}] refine the fix and verify the invariants", oxygen=2.0, signal=USER)
        ctx.add(f"[tool-log {cycle}] " + "verbose scan trace stack json blob detail noise " * 12,
                oxygen=0.5, signal=TOOL)

        # --- Memory apoptosis: cut the noise before the call --- #
        tok_init += ctx.active_tokens()                       # what a naive agent would send
        ctx.prune_cycles(2, rate=0.34, reinforce_mask=SYSTEM | USER, reinforce_amount=0.3)
        tok_final += ctx.active_tokens()                      # what B.I.O.M.A. actually sends
        prompt = ctx.render()

        if cycle < cycles - 1 and stress >= MITOSIS_STRESS:
            # --- NEURONAL MITOSIS: branch hypotheses in parallel --- #
            comps = await asyncio.gather(*[
                provider.complete(f"{prompt}\n\nHYPOTHESIS: {h}", model, system=SYSTEM_DIRECTIVES,
                                  max_tokens=512, temperature=0.4)
                for h in problem["hypotheses"]
            ])
            mitoses += 1
            for c in comps:
                rtts.append(c.rtt_ms)
                cost += c.cost_usd
            best = max(comps, key=lambda c: (c.error is None, len(c.text)))
        else:
            # --- Single agent step (synthesis) --- #
            best = await provider.complete(prompt, model, system=SYSTEM_DIRECTIVES,
                                           max_tokens=768, temperature=0.2)
            loops += 1
            rtts.append(best.rtt_ms)
            cost += best.cost_usd

        last_answer = best.text
        ctx.add(f"[result {cycle}] {best.text[:180]}", oxygen=2.5, signal=USER)
        bus.tick(0.85)  # dissipate stress between cycles

    return {
        "loops": loops, "mitoses": mitoses,
        "tok_init": tok_init, "tok_final": tok_final,
        "rtts": rtts, "cost": cost,
        "score": score_solution(problem, last_answer, model, is_mock),
    }


async def run_model(provider: AsyncProvider, model: str, is_mock: bool) -> dict:
    t0 = time.perf_counter()
    per = []
    for problem in DATASET:                          # one session, problems in sequence
        per.append(await run_problem(provider, model, problem, is_mock))
    wall = time.perf_counter() - t0
    rtts = [r for p in per for r in p["rtts"]]
    return {
        "model": model,
        "time_s": round(wall, 2),
        "avg_rtt_ms": round(sum(rtts) / len(rtts), 1) if rtts else 0.0,
        "loops": sum(p["loops"] for p in per),
        "mitoses": sum(p["mitoses"] for p in per),
        "tok_init": sum(p["tok_init"] for p in per),
        "tok_final": sum(p["tok_final"] for p in per),
        "cost": round(sum(p["cost"] for p in per), 6),
        "score": round(sum(p["score"] for p in per) / len(per), 1),
    }


def render_table(rows: list[dict], mock: bool) -> str:
    L = ["## B.I.O.M.A. Elite Multi-Model Benchmark (OpenRouter Unified API)", ""]
    if mock:
        L += ["> **MODO MOCK (offline)** — nenhuma chamada real; defina "
              "`OPENROUTER_API_KEY` para rodar contra os modelos reais.", ""]
    L += ["| Modelo Online | Tempo Total (s) | Média RTT/Agente (ms) | Loops/Mitoses | "
          "Tokens Iniciais | Tokens Finais (Pós-Apoptose) | Custo Real da Sessão ($) | "
          "Score de Sucesso (0-100) |",
          "| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |"]
    for r in rows:
        L.append(f"| {r['model']} | {r['time_s']:.2f} | {r['avg_rtt_ms']:.1f} | "
                 f"{r['loops']}/{r['mitoses']} | {r['tok_init']:,} | {r['tok_final']:,} | "
                 f"${r['cost']:.4f} | {r['score']:.1f} |")
    return "\n".join(L)


async def preflight(provider: AsyncProvider, model: str) -> bool:
    """One cheap call to verify key + connectivity + real usage/cost before the sweep."""
    print(f"  preflight → {model} ...", flush=True)
    c = await provider.complete("Reply with the single word: OK.", model,
                                system="You are a terse assistant.", max_tokens=5, temperature=0)
    if c.error:
        print(f"  ❌ PREFLIGHT FAILED: {c.error}")
        print("     Check OPENROUTER_API_KEY, credit balance, and the model slug.")
        return False
    print(f"  ✅ OK · reply={c.text.strip()[:40]!r} · rtt={c.rtt_ms:.0f}ms · "
          f"tokens {c.in_tokens}+{c.out_tokens} · cost ${c.cost_usd:.6f}")
    return True


async def main(args) -> None:
    key = os.environ.get("OPENROUTER_API_KEY")
    mock = key is None
    provider: AsyncProvider = MockAsyncProvider() if mock else AsyncOpenRouterProvider(key)
    models = [m.strip() for m in args.models.split(",")] if args.models else MODELS

    banner = "MOCK · offline" if mock else "LIVE · OpenRouter"
    print(f"\n  B.I.O.M.A. elite benchmark — {banner} — {len(models)} models × "
          f"{len(DATASET)} problems\n")

    rows = []
    try:
        if args.check:                               # preflight only, then exit
            ok = await preflight(provider, args.model)
            print("  → key/connectivity verified. Run without --check for the full sweep."
                  if ok else "  → fix the issue above, then retry.")
            return
        for model in models:                         # one model (brain) at a time
            print(f"  → {model} ...", flush=True)
            rows.append(await run_model(provider, model, mock))
    finally:
        await provider.close()

    print()
    table = render_table(rows, mock)
    print(table)
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "ELITE_BENCHMARK.md"),
              "w", encoding="utf-8") as fh:
        fh.write(table + "\n")
    print("\n  written: ELITE_BENCHMARK.md")
    print("  RTT = network round-trip (AI time) · isolado do barramento local (µs).")
    if mock:
        print("  Custo/tokens/score em MOCK são simulados pelo perfil de cada modelo; "
              "com a chave, vêm reais do OpenRouter (usage + cost).")


def _cli():
    import argparse
    ap = argparse.ArgumentParser(description="B.I.O.M.A. elite multi-model benchmark (OpenRouter).")
    ap.add_argument("--check", action="store_true",
                    help="preflight: one cheap call to verify key/connectivity/cost, then exit")
    ap.add_argument("--model", default="meta-llama/llama-3-70b-instruct",
                    help="model slug used by --check (default: the cheapest)")
    ap.add_argument("--models", default=None,
                    help="comma-separated model slugs to override the default 4 for the full run")
    return ap.parse_args()


if __name__ == "__main__":
    asyncio.run(main(_cli()))
