"""
bioma_vs_market_benchmark.py — A/B elite benchmark: Traditional vs B.I.O.M.A.

For each of the 4 market models (via ONE unified OpenRouter endpoint), the SAME
complex problem is solved twice:

  * Motor A — Traditional (linear): sequential calls; the message history
    accumulates RAW, token by token, with NO memory pruning.
  * Motor B — B.I.O.M.A. (organic): the Hormonal Bus sets priority; Memory
    Apoptosis (Rust kernel) trims the cognitive noise every iteration; and on a
    branching decision the system fires NEURONAL MITOSIS — concurrent async calls
    (`asyncio.gather`) branching hypotheses in parallel.

Both engines do the SAME model work (same hypotheses explored); only the
orchestration differs — so the Speedup is honest (parallelism + fewer tokens).

Set OPENROUTER_API_KEY (in `.env` — never `.env.example`) to run live; otherwise
the offline MOCK provider runs the full pipeline with no network / no cost.

Run:
    python bioma_vs_market_benchmark.py            # full A/B sweep
    python bioma_vs_market_benchmark.py --check    # preflight one call, then exit
"""

from __future__ import annotations

import asyncio
import os
import time

import bioma_kernel as bk
from bioma_orchestrator.context import ContextPruner, est_tokens, SYSTEM, USER, TOOL
from bioma_orchestrator.openrouter_async import (
    AsyncOpenRouterProvider, MockAsyncProvider, AsyncProvider,
)

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
except Exception:
    pass

CORTISOL = 1 << 0
MITOSIS_STRESS = 0.75

MODELS = [
    ("anthropic/claude-3.5-sonnet", "Claude 3.5 Sonnet"),
    ("openai/gpt-4o", "GPT-4o"),
    ("x-ai/grok-2", "Grok-2"),
    ("meta-llama/llama-3-70b-instruct", "Llama-3-70B"),
]

SYS = ("You are a senior distributed-systems + security engineer. Work across multiple "
       "decision cycles: map the failure, branch hypotheses, verify invariants, and "
       "deliver a concrete, correct remediation. Be precise.")

# The extreme challenge — a cascading failure across distributed microservices.
PROBLEM = {
    "statement": ("A cascading failure is propagating across distributed microservices: an "
                  "auth-service latency spike trips circuit breakers in payments, orders and "
                  "inventory, and retry storms amplify the load. Map the failure chain and "
                  "deliver a correct remediation (isolation, backpressure, idempotency, recovery)."),
    "cycles": 3,
    "complexity": 0.9,
    "hypotheses": ["circuit-breaker + bulkhead isolation",
                   "backpressure + rate-limit + jittered retry",
                   "idempotency keys + saga compensation"],
}
NOISE = "[tool-log] " + "verbose trace stack json blob detail noise entry value payload " * 10


# --------------------------------------------------------------------------- #
#  Motor A — Traditional (linear, raw-accumulating context)
# --------------------------------------------------------------------------- #
async def motor_traditional(provider: AsyncProvider, model: str) -> dict:
    t0 = time.perf_counter()
    history = [SYS, PROBLEM["statement"]]
    calls = 0
    rtts: list[float] = []
    cost = 0.0
    cycles, hyps = PROBLEM["cycles"], PROBLEM["hypotheses"]
    for cycle in range(cycles):
        steps = hyps if cycle < cycles - 1 else ["synthesize the final remediation"]
        for step in steps:                              # explored SEQUENTIALLY, one after another
            prompt = "\n".join(history) + f"\n\n[cycle {cycle}] {step}"
            c = await provider.complete(prompt, model, system=SYS, max_tokens=512, temperature=0.3)
            calls += 1
            rtts.append(c.rtt_ms)
            cost += c.cost_usd
            history.append(f"[c{cycle}] {step[:24]}: {c.text[:180]}")
            history.append(NOISE)                        # RAW accumulation — never pruned
    wall = time.perf_counter() - t0
    return {"arch": "Tradicional (Linear)", "time_s": wall,
            "avg_rtt": (sum(rtts) / len(rtts)) if rtts else 0.0,
            "loops": calls, "mitoses": 0,
            "final_tokens": est_tokens("\n".join(history)), "cost": cost}


# --------------------------------------------------------------------------- #
#  Motor B — B.I.O.M.A. (hormonal bus + apoptosis + neuronal mitosis)
# --------------------------------------------------------------------------- #
async def motor_bioma(provider: AsyncProvider, model: str) -> dict:
    t0 = time.perf_counter()
    bus = bk.HormonalBus(8)
    ctx = ContextPruner()
    ctx.add(SYS, oxygen=50.0, signal=SYSTEM)
    ctx.add(PROBLEM["statement"], oxygen=8.0, signal=USER)
    loops = mitoses = 0
    rtts: list[float] = []
    cost = 0.0
    cycles, hyps = PROBLEM["cycles"], PROBLEM["hypotheses"]

    for cycle in range(cycles):
        bus.secrete(CORTISOL, PROBLEM["complexity"])     # hormonal priority ∝ complexity
        stress = bus.sense(CORTISOL)
        ctx.add(f"[cycle {cycle}] refine the fix and verify invariants", oxygen=2.0, signal=USER)
        ctx.add(NOISE, oxygen=0.5, signal=TOOL)
        ctx.prune_cycles(2, rate=0.34, reinforce_mask=SYSTEM | USER, reinforce_amount=0.3)  # apoptosis
        prompt = ctx.render()

        if cycle < cycles - 1 and stress >= MITOSIS_STRESS:
            # NEURONAL MITOSIS — branch hypotheses concurrently (non-blocking).
            comps = await asyncio.gather(*[
                provider.complete(f"{prompt}\n\nHYPOTHESIS: {h}", model, system=SYS,
                                  max_tokens=512, temperature=0.4)
                for h in hyps
            ])
            mitoses += 1
            for c in comps:
                rtts.append(c.rtt_ms)
                cost += c.cost_usd
            best = max(comps, key=lambda c: (c.error is None, len(c.text)))
        else:
            best = await provider.complete(prompt, model, system=SYS, max_tokens=768, temperature=0.2)
            loops += 1
            rtts.append(best.rtt_ms)
            cost += best.cost_usd

        ctx.add(f"[result {cycle}] {best.text[:180]}", oxygen=2.5, signal=USER)
        bus.tick(0.85)                                    # dissipate stress between cycles

    wall = time.perf_counter() - t0
    return {"arch": "B.I.O.M.A. (Orgânico)", "time_s": wall,
            "avg_rtt": (sum(rtts) / len(rtts)) if rtts else 0.0,
            "loops": loops, "mitoses": mitoses,
            "final_tokens": ctx.active_tokens(), "cost": cost}


# --------------------------------------------------------------------------- #
#  Report
# --------------------------------------------------------------------------- #
def render_table(results: list[dict], mock: bool) -> str:
    L = ["## B.I.O.M.A. vs Traditional Architecture - Elite Benchmark Report", ""]
    if mock:
        L += ["> **MODO MOCK (offline)** — nenhuma chamada real; defina `OPENROUTER_API_KEY` "
              "no `.env` para rodar contra os modelos reais.", ""]
    L += ["| Modelo Comparado | Arquitetura | Tempo Total (s) | Média Latência (ms) | "
          "Loops/Mitoses | Contexto Final (Tokens) | Custo Sessão ($) | Fator de Aceleração (Speedup) |",
          "| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |"]
    for r in results:
        a, b, name = r["trad"], r["bioma"], r["name"]
        speedup = (a["time_s"] / b["time_s"]) if b["time_s"] > 0 else float("inf")
        L.append(f"| **{name}** | Tradicional (Linear) | {a['time_s']:.2f} | {a['avg_rtt']:.1f} | "
                 f"{a['loops']}/{a['mitoses']} | {a['final_tokens']:,} | ${a['cost']:.4f} | (Referência) |")
        L.append(f"| **{name}** | B.I.O.M.A. (Orgânico) | {b['time_s']:.2f} | {b['avg_rtt']:.1f} | "
                 f"{b['loops']}/{b['mitoses']} | {b['final_tokens']:,} | ${b['cost']:.4f} | "
                 f"**{speedup:.1f}x mais rápido** |")
    return "\n".join(L)


async def preflight(provider: AsyncProvider, model: str) -> bool:
    print(f"  preflight → {model} ...", flush=True)
    c = await provider.complete("Reply with the single word: OK.", model,
                                system="You are terse.", max_tokens=5, temperature=0)
    if c.error:
        print(f"  ❌ PREFLIGHT FAILED: {c.error}\n     Verifique OPENROUTER_API_KEY, saldo e o slug do modelo.")
        return False
    print(f"  ✅ OK · rtt={c.rtt_ms:.0f}ms · tokens {c.in_tokens}+{c.out_tokens} · cost ${c.cost_usd:.6f}")
    return True


async def main(args) -> None:
    key = os.environ.get("OPENROUTER_API_KEY")
    mock = key is None
    provider: AsyncProvider = MockAsyncProvider() if mock else AsyncOpenRouterProvider(key)
    banner = "MOCK · offline" if mock else "LIVE · OpenRouter"
    print(f"\n  B.I.O.M.A. vs Traditional — {banner} — {len(MODELS)} models · A/B\n")

    results = []
    try:
        if args.check:
            await preflight(provider, args.model)
            return
        for slug, name in MODELS:
            print(f"  → {name} · Motor A (linear) ...", flush=True)
            a = await motor_traditional(provider, slug)
            print(f"  → {name} · Motor B (B.I.O.M.A.) ...", flush=True)
            b = await motor_bioma(provider, slug)
            results.append({"name": name, "slug": slug, "trad": a, "bioma": b})
    finally:
        await provider.close()

    print()
    table = render_table(results, mock)
    print(table)
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "BIOMA_VS_MARKET.md")
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(table + "\n")
    print(f"\n  written: {os.path.basename(out)}")
    print("  Latência = RTT de rede real por chamada · A e B fazem o MESMO trabalho de modelo")
    print("  (mesmas hipóteses); só a orquestração muda — speedup = paralelismo + apoptose.")
    if mock:
        print("  MOCK: RTT/custo/tokens simulados por perfil; com a chave vêm reais do OpenRouter.")


def _cli():
    import argparse
    ap = argparse.ArgumentParser(description="B.I.O.M.A. vs Traditional A/B benchmark (OpenRouter).")
    ap.add_argument("--check", action="store_true", help="preflight one call to verify the key, then exit")
    ap.add_argument("--model", default="meta-llama/llama-3-70b-instruct", help="model slug for --check")
    return ap.parse_args()


if __name__ == "__main__":
    asyncio.run(main(_cli()))
