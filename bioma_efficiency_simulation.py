#!/usr/bin/env python3
"""
bioma_efficiency_simulation.py — B.I.O.M.A. multi-model efficiency simulation
================================================================================
Shows, for a PANEL of real market models, what B.I.O.M.A. adds on top of each one:
pure baseline (single linear call, full context) vs the B.I.O.M.A. life-cycle
(hormonal bus → apoptosis → mitosis → convergence). Reuses the SAME engine that
serves the deployed `/v1/orchestrate` route (bioma_orchestrator.live_pipeline), so
the simulation can never drift from production.

Efficiency dimensions (all measured):
  • Apoptose (↓ contexto) — real input-token reduction per call (ContextPruner)
  • Qualidade            — real LLM-as-judge score, baseline vs B.I.O.M.A.
  • Custo                — real OpenRouter usage.cost, baseline vs B.I.O.M.A.
  • Latência             — real wall-clock, baseline vs B.I.O.M.A.

INTEGRITY: numbers are measured. Real when OPENROUTER_API_KEY is a valid sk-or
key; otherwise a clearly-labelled deterministic MOCK (model metrics modelled).

HONEST framing: B.I.O.M.A. fans out N sub-agents (mitosis) + a synthesis call, so
its ABSOLUTE cost/latency per request is higher than one baseline call. Its
efficiency is *quality-and-context per call* — more correct answers on a pruned
context — not "cheaper than a single shot". The table shows both sides.

Usage:
    python bioma_efficiency_simulation.py
    python bioma_efficiency_simulation.py --models openai/gpt-4o anthropic/claude-3.5-sonnet
    python bioma_efficiency_simulation.py --mitosis 3 --mock
    python bioma_efficiency_simulation.py --check
"""
from __future__ import annotations

import argparse
import asyncio
import os
import re
import sys
import time
from dataclasses import dataclass
from typing import Optional

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(_HERE, ".env"))
except Exception:
    pass

from bioma_orchestrator.openrouter_async import (  # noqa: E402
    AsyncOpenRouterProvider, MockAsyncProvider,
)
from bioma_orchestrator.live_pipeline import evolve  # noqa: E402
from bioma_orchestrator.context import (  # noqa: E402
    est_tokens, SYSTEM, FACT, USER, ASSISTANT, TOOL,
)

# --------------------------------------------------------------------------- #
#  Console
# --------------------------------------------------------------------------- #
if sys.platform == "win32":
    os.system("")
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
_COLOR = sys.stdout.isatty() and os.environ.get("NO_COLOR") is None


def _c(code, s):
    return f"\033[{code}m{s}\033[0m" if _COLOR else s


def log(msg):
    print(_c("90", "· ") + msg)


def rule(title=""):
    print(_c("90", "═" * 80))
    if title:
        print(_c("1;37", f"  {title}"))
        print(_c("90", "═" * 80))


PRETTY = {
    "openai/gpt-4o": "GPT-4o", "anthropic/claude-fable-5": "Fable-5",
    "anthropic/claude-opus-4.8": "Opus 4.8", "anthropic/claude-sonnet-4": "Sonnet 4",
    "x-ai/grok-4.3": "Grok-4.3", "meta-llama/llama-3.3-70b-instruct": "Llama-3.3-70B",
    "google/gemini-2.5-pro": "Gemini 2.5 Pro",
}


def pretty(m):
    return PRETTY.get(m, m.split("/")[-1])


# mock quality hints (used ONLY in --mock mode; real mode uses the live judge)
_MOCK_Q = {
    "anthropic/claude-opus-4.8": 0.94, "anthropic/claude-fable-5": 0.90,
    "openai/gpt-4o": 0.88, "x-ai/grok-4.3": 0.85,
    "meta-llama/llama-3.3-70b-instruct": 0.78, "google/gemini-2.5-pro": 0.89,
}

# A neutral, genuinely hard algorithmic task (no security framing that could trip
# a model's content filter — so all models compare fairly).
TASK = (
    "Refactor this function to run in O(n) time (it is currently O(n²)) and to be "
    "correct for all edge cases — empty input, `k` larger than the number of distinct "
    "values, and ties — keeping the signature `top_k_frequent(nums, k)`:\n"
    "```python\n"
    "def top_k_frequent(nums, k):\n"
    "    counts = {}\n"
    "    for x in nums:\n"
    "        counts[x] = nums.count(x)      # O(n) inside the loop → O(n^2) overall\n"
    "    ordered = sorted(counts, key=lambda v: counts[v], reverse=True)\n"
    "    return ordered[:k]\n"
    "```\n"
    "Explain the complexity fix and which edge cases you handle."
)


def _neutral_context() -> list[tuple[str, int, float]]:
    """A bloated working memory with NO security terms — durable facts + relevant
    recent turns buried under stale turns and verbose tool logs (apoptosis target)."""
    items = [
        ("SYSTEM: senior Python engineer; preserve public APIs; prefer the stdlib.", SYSTEM, 1.0),
        ("FACT: collections.Counter and heapq.nlargest are available.", FACT, 0.95),
        ("FACT: nums may hold up to 1e6 items; k is small relative to n.", FACT, 0.92),
        ("USER (recent): here is the slow top_k_frequent; make it O(n).", USER, 0.85),
        ("ASSISTANT (recent): the nested list.count() call is the O(n²) culprit.", ASSISTANT, 0.82),
    ]
    for i in range(4):
        items.append((f"ASSISTANT (old {i}): stale note about logging config #{i}.", ASSISTANT, 0.26))
    for i in range(10):
        items.append((f"TOOL[pytest {i}]: collected 214 items ... PASSED unrelated_{i} ... "
                      "verbose traceback noise repeated across the run.", TOOL, 0.10))
    return items


def _valid_key(k):
    return bool(k) and k.startswith("sk-or")


async def build_provider(force_mock):
    key = os.environ.get("OPENROUTER_API_KEY")
    if force_mock or not _valid_key(key):
        return MockAsyncProvider(), "mock"
    try:
        prov = AsyncOpenRouterProvider()
        probe = await prov.complete(prompt="ping", model="openai/gpt-4o-mini",
                                    max_tokens=1, temperature=0.0)
        if probe.error and ("401" in probe.error or "exhausted" in probe.error):
            await prov.close()
            log(_c("33", f"Key present but probe failed ({probe.error}); using MOCK."))
            return MockAsyncProvider(), "mock"
        return prov, "real"
    except Exception as exc:
        log(_c("33", f"Provider init failed ({exc}); using MOCK."))
        return MockAsyncProvider(), "mock"


async def judge(provider, answer, judge_model, mock_hint=None) -> Optional[int]:
    if isinstance(provider, MockAsyncProvider):
        return None if mock_hint is None else max(0, min(100, round(mock_hint * 100)))
    if not answer:
        return None
    c = await provider.complete(
        prompt=f"TASK:\n{TASK}\n\nCANDIDATE ANSWER:\n{answer}\n\n"
               "Rate correctness+completeness 0-100. Reply ONLY the integer.",
        model=judge_model, max_tokens=6, system="You are a strict evaluator.", temperature=0.0)
    m = re.search(r"\d{1,3}", c.text or "")
    return max(0, min(100, int(m.group()))) if m else None


@dataclass
class Eff:
    model: str
    reduction: float
    q_base: Optional[int]
    q_bioma: Optional[int]
    cost_base: float
    cost_bioma: float
    lat_base: float
    lat_bioma: float
    calls_bioma: int


async def run_model(provider, mode, model, judge_model, k, context) -> Eff:
    mq = _MOCK_Q.get(model, 0.7) if mode == "mock" else None
    raw_ctx = "\n".join(c for c, _s, _o in context)

    # ---- baseline: single linear call, full context ----
    t0 = time.perf_counter_ns()
    base = await provider.complete(
        prompt=f"Context:\n{raw_ctx}\n\nTask:\n{TASK}", model=model, max_tokens=2048,
        system="You are an expert software engineer.", temperature=0.2)
    lat_base = (time.perf_counter_ns() - t0) / 1e9
    q_base = await judge(provider, base.text, judge_model, mock_hint=mq)

    # ---- B.I.O.M.A.: shared production engine ----
    res = await evolve(TASK, model=model, mitosis=k, context=context, provider=provider)
    tel = res["telemetry"]
    q_hint = min(0.99, mq + 0.05 + 0.015 * (k - 1)) if mq is not None else None
    q_bioma = await judge(provider, res["answer"], judge_model, mock_hint=q_hint)

    log(f"{pretty(model):18s} baseline q={q_base} ${base.cost_usd:.4f} {lat_base:.2f}s "
        f"│ BIOMA q={q_bioma} ${tel['usage']['cost_usd']:.4f} {tel['seconds']:.2f}s "
        f"apoptose −{tel['apoptosis']['reduction']*100:.0f}%")
    return Eff(model, tel["apoptosis"]["reduction"], q_base, q_bioma,
               base.cost_usd, tel["usage"]["cost_usd"], lat_base, tel["seconds"],
               tel["usage"]["calls"])


def _dq(a, b):
    if a is None or b is None:
        return "—"
    d = b - a
    return f"{a} → {b} ({'+' if d >= 0 else ''}{d})"


def render(effs: list[Eff], mode: str) -> str:
    o = ["## B.I.O.M.A. — Simulação de Eficiência Multi-Modelo\n"]
    if mode == "mock":
        o.append("> ⚠️ **[MOCK]** — sem OPENROUTER_API_KEY. Apoptose (contexto) é real; "
                 "qualidade/custo/latência dos modelos são **modelados**. Rode com chave "
                 "para métricas reais.\n")
    o.append("| Modelo | Apoptose (↓ Ctx) | Qualidade (Base → BIOMA) | "
             "Custo (Base → BIOMA) | Latência (Base → BIOMA) | Chamadas | Veredito |")
    o.append("| :--- | ---: | :---: | :---: | :---: | ---: | :--- |")
    for e in effs:
        dq = (e.q_bioma - e.q_base) if (e.q_base is not None and e.q_bioma is not None) else None
        verdict = (f"✅ +{dq} qualidade · −{e.reduction*100:.0f}% contexto"
                   if dq is not None and dq > 0 else
                   (f"≈ {dq:+d} qualidade · −{e.reduction*100:.0f}% contexto"
                    if dq is not None else f"−{e.reduction*100:.0f}% contexto"))
        o.append(f"| **{pretty(e.model)}** | {e.reduction*100:.0f}% | {_dq(e.q_base, e.q_bioma)} "
                 f"| ${e.cost_base:.4f} → ${e.cost_bioma:.4f} | {e.lat_base:.2f}s → {e.lat_bioma:.2f}s "
                 f"| 1 → {e.calls_bioma} | {verdict} |")
    o.append("")

    # aggregate efficiency
    red = [e.reduction for e in effs]
    dqs = [e.q_bioma - e.q_base for e in effs if e.q_base is not None and e.q_bioma is not None]
    o.append("### Eficiência agregada")
    o.append(f"- **Redução média de contexto (apoptose):** {sum(red)/len(red)*100:.0f}% "
             f"— tokens de entrada cortados por chamada, em todos os modelos.")
    if dqs:
        o.append(f"- **Ganho médio de qualidade:** {'+' if sum(dqs)>=0 else ''}{sum(dqs)/len(dqs):.1f} "
                 f"pts (juiz {'real' if mode=='real' else 'modelado'}).")
    tot_base = sum(e.cost_base for e in effs)
    tot_bioma = sum(e.cost_bioma for e in effs)
    o.append(f"- **Custo total do painel:** baseline ${tot_base:.4f} vs B.I.O.M.A. ${tot_bioma:.4f} "
             f"({tot_bioma/tot_base:.1f}× — a mitose paga por mais qualidade).")
    o.append("")
    o.append("> **Como ler:** a eficiência do B.I.O.M.A. é **qualidade e contexto por chamada** — "
             "respostas mais corretas sobre um contexto podado pela apoptose. A mitose dispara N "
             "sub-agentes + síntese, então o **custo/latência absolutos por requisição são maiores** "
             "que um único disparo (ver colunas). O ganho está na **qualidade** e na **economia de "
             "tokens de entrada por chamada**, não em ser mais barato que uma chamada só.")
    return "\n".join(o)


async def main() -> int:
    ap = argparse.ArgumentParser(description="B.I.O.M.A. multi-model efficiency simulation")
    ap.add_argument("--models", nargs="+", default=[
        "openai/gpt-4o", "anthropic/claude-fable-5", "anthropic/claude-opus-4.8",
        "x-ai/grok-4.3", "meta-llama/llama-3.3-70b-instruct"])
    ap.add_argument("--judge", default="openai/gpt-4o-mini")
    ap.add_argument("--mitosis", type=int, default=3)
    ap.add_argument("--mock", action="store_true")
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    k = max(2, min(4, args.mitosis))

    provider, mode = await build_provider(args.mock)
    rule("B.I.O.M.A. — MULTI-MODEL EFFICIENCY SIMULATION")
    log("Mode: " + (_c("32", "REAL (OpenRouter live)") if mode == "real"
                    else _c("33", "MOCK (offline, modelled)")))
    log(f"Painel: {', '.join(pretty(m) for m in args.models)} · mitose={k} · "
        f"juiz={args.judge if mode=='real' else 'modelado'}")
    if args.check:
        log(_c("32", "Preflight OK.") if mode == "real" else _c("33", "Preflight OK (mock)."))
        if mode == "real":
            await provider.close()
        return 0

    context = _neutral_context()
    log(f"Contexto compartilhado: {len(context)} itens, {est_tokens(chr(10).join(c for c,_,_ in context)):,} tokens (base usa cheio; BIOMA poda).")
    print()
    effs: list[Eff] = []
    try:
        for m in args.models:
            effs.append(await run_model(provider, mode, m, args.judge, k, context))
    finally:
        if mode == "real":
            await provider.close()

    print()
    rule("RESULTADO")
    print()
    print(render(effs, mode))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(main()))
    except KeyboardInterrupt:
        print("\ninterrupted.", file=sys.stderr)
        raise SystemExit(130)
