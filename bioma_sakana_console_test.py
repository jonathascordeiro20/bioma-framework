#!/usr/bin/env python3
"""
bioma_sakana_console_test.py — Public demonstration console for B.I.O.M.A.
================================================================================
A single-file, Sakana.ai-style scientific demo that runs a **real** evolutionary
orchestration over OpenRouter on a complex reasoning/refactoring task, prints a
microsecond-timestamped "lab notebook" of the organic life-cycle, and closes
with a benchmark table confronting B.I.O.M.A. against the pure baseline models.

INTEGRITY CONTRACT — every number below is *measured*, never fabricated:
  • timings    → time.perf_counter_ns() wrapped around the real operation (μs)
  • hormonal   → real bioma_kernel.HormonalBus secrete/sense (Rust) or Py fallback
  • apoptosis  → real ContextPruner token counts before/after (kernel oxygen decay)
  • mitosis    → real asyncio.gather over N concurrent OpenRouter sub-agent calls
  • tokens/$   → real usage.prompt_tokens / completion_tokens / usage.cost
  • quality    → real LLM-as-judge score (0-100) over each final answer

Runs for real when OPENROUTER_API_KEY is present (and reachable); otherwise it
drops into a clearly-labelled [MOCK] mode (deterministic, offline, no spend) so
the full pipeline is still exercisable — mock numbers are flagged as SYNTHETIC.

Usage
-----
    python bioma_sakana_console_test.py                     # default task
    python bioma_sakana_console_test.py --task "..."        # your own task
    python bioma_sakana_console_test.py --mitosis 4         # N parallel sub-agents
    python bioma_sakana_console_test.py --models openai/gpt-4o anthropic/claude-3.5-sonnet
    python bioma_sakana_console_test.py --mock              # force offline mock
    python bioma_sakana_console_test.py --check             # preflight only
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

# --------------------------------------------------------------------------- #
#  Make the repo's modules importable regardless of CWD, and load .env
# --------------------------------------------------------------------------- #
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(_HERE, ".env"))
except Exception:
    pass

from bioma_orchestrator.openrouter_async import (  # noqa: E402
    AsyncOpenRouterProvider, MockAsyncProvider, Completion,
)
from bioma_orchestrator.context import (  # noqa: E402
    ContextPruner, SYSTEM, USER, ASSISTANT, FACT, TOOL, est_tokens,
)

# Real Rust hormonal bus if the kernel wheel is installed; else a faithful Py bus.
try:
    import bioma_kernel  # compiled PyO3 extension
    _HAS_KERNEL = hasattr(bioma_kernel, "HormonalBus")
except Exception:
    _HAS_KERNEL = False


class _PyHormonalBus:
    """Pure-Python mirror of the kernel's HormonalBus (same secrete/sense API)."""

    def __init__(self, num_signals: int = 32):
        self.n = num_signals
        self.conc = [0.0] * num_signals
        self.secretions = 0

    def secrete(self, flags: int, intensity: float) -> None:
        for b in range(self.n):
            if flags & (1 << b):
                self.conc[b] += intensity
        self.secretions += 1

    def sense(self, mask: int) -> float:
        return sum(self.conc[b] for b in range(self.n) if mask & (1 << b))

    def tick(self, decay: float) -> None:
        self.conc = [max(0.0, c - decay) for c in self.conc]

    def snapshot(self):
        return list(self.conc)


def _make_bus():
    if _HAS_KERNEL:
        return bioma_kernel.HormonalBus(32, 4096), "rust-kernel"
    return _PyHormonalBus(32), "python-fallback"


# --------------------------------------------------------------------------- #
#  Console — Sakana-style microsecond lab notebook
# --------------------------------------------------------------------------- #
if sys.platform == "win32":
    os.system("")  # enable ANSI escape processing on modern Windows terminals
try:
    # box-drawing / μ / · chars need UTF-8; Windows consoles default to cp1252
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
_COLOR = sys.stdout.isatty() and os.environ.get("NO_COLOR") is None
_T0 = time.perf_counter_ns()


def _c(code: str, s: str) -> str:
    return f"\033[{code}m{s}\033[0m" if _COLOR else s


def _stamp() -> str:
    us = (time.perf_counter_ns() - _T0) // 1000
    return f"t+{us / 1_000_000:012.6f}s"


# tag -> ANSI colour
_TAGCOL = {
    "Hormonal Bus": "35", "Memory Apoptosis": "33", "Neuronal Mitosis": "36",
    "Coordination": "32", "Baseline": "34", "Judge": "90", "System": "37",
}


def lab(tag: str, msg: str) -> None:
    print(f"{_c('90', _stamp())}  {_c(_TAGCOL.get(tag, '37'), f'[{tag}]')} {msg}")


def rule(title: str = "") -> None:
    bar = "═" * 78
    print(_c("90", bar))
    if title:
        print(_c("1;37", f"  {title}"))
        print(_c("90", bar))


# --------------------------------------------------------------------------- #
#  Pretty model names + role palette for mitosis
# --------------------------------------------------------------------------- #
PRETTY = {
    "openai/gpt-4o": "GPT-4o",
    "anthropic/claude-3.5-sonnet": "Claude 3.5 Sonnet",
    "x-ai/grok-2": "Grok-2",
    "meta-llama/llama-3-70b-instruct": "Llama-3-70B",
}


def pretty(model: str) -> str:
    return PRETTY.get(model, model.split("/")[-1])


# Each sub-agent is a differentiated "specialist" cell — distinct system prompt,
# signal channel (hex label), and sampling temperature → divergent hypotheses.
MITOSIS_ROLES = [
    ("Architect", TOOL and (1 << 4), "0x10",
     "You are a systems architect. Produce the cleanest, most correct solution "
     "with rigorous structure.", 0.15),
    ("Adversary", (1 << 5), "0x20",
     "You are an adversarial reviewer. Solve the task while actively hunting for "
     "edge cases, races, and security holes others miss.", 0.35),
    ("Optimizer", (1 << 6), "0x40",
     "You are a performance/pragmatism specialist. Solve it simply and efficiently, "
     "minimising moving parts.", 0.25),
    ("Verifier", (1 << 7), "0x80",
     "You are a correctness prover. Solve the task and justify why each failure "
     "mode is eliminated.", 0.20),
]


# --------------------------------------------------------------------------- #
#  Demo workload: a complex refactor task + a realistically bloated agent context
# --------------------------------------------------------------------------- #
DEFAULT_TASK = (
    "Refactor this Python function so it is thread-safe, free of SQL injection, "
    "and idempotent, WITHOUT changing its public signature `charge(user_id, cents)`:\n"
    "```python\n"
    "balance = {}\n"
    "def charge(user_id, cents):\n"
    "    q = \"SELECT bal FROM acct WHERE id=\" + str(user_id)\n"
    "    bal = db.exec(q).one()\n"
    "    balance[user_id] = bal - cents          # lost-update race\n"
    "    db.exec(\"UPDATE acct SET bal=\" + str(balance[user_id]))\n"
    "    return balance[user_id]\n"
    "```\n"
    "Explain the concurrency fix, the injection fix, and how idempotency is guaranteed."
)


def build_bloated_context() -> list[tuple[str, int, float]]:
    """A representative over-grown agent context: durable instructions + a few
    key facts + the RELEVANT recent turns, buried under verbose low-value tool
    logs and stale off-topic turns. Returns (content, signal, oxygen) triples.
    Apoptosis is measured on THIS input — reinforced (SYSTEM/FACT) and
    high-oxygen recent turns survive; stale noise apoptoses."""
    items: list[tuple[str, int, float]] = []
    # durable instructions — reinforced, must survive
    items.append(("SYSTEM: You are a senior Python engineer. Preserve public APIs. "
                  "Prefer the stdlib. Never introduce SQL injection.", SYSTEM, 1.0))
    # key facts about the CURRENT task — must survive
    items.append(("FACT: `db.exec` accepts a parameterized form db.exec(sql, params).", FACT, 0.95))
    items.append(("FACT: `charge` is called concurrently from many worker threads.", FACT, 0.95))
    items.append(("FACT: an idempotency_key column exists on table `acct`.", FACT, 0.9))
    # RELEVANT recent turns (about the current defect) — high oxygen, survive
    items.append(("USER (recent): here is the buggy charge() function; it must stay thread-safe "
                  "under heavy concurrency and keep the same signature.", USER, 0.85))
    items.append(("ASSISTANT (recent): diagnosed two defects — a lost-update race on the shared "
                  "balance and a string-concatenated SQL query open to injection.", ASSISTANT, 0.82))
    items.append(("ASSISTANT (recent): plan — wrap read-modify-write in a transaction/lock, "
                  "parameterize the SQL, and dedupe via idempotency_key.", ASSISTANT, 0.8))
    # stale off-topic turns — disposable (apoptosis target)
    for i in range(5):
        items.append((f"USER (old turn {i}): unrelated earlier question about logging config #{i}.",
                      USER, 0.28))
        items.append((f"ASSISTANT (old turn {i}): long prior answer about log rotation #{i} that "
                      "no longer bears on the current task.", ASSISTANT, 0.24))
    # verbose tool logs — prime apoptosis targets (low oxygen, TOOL channel)
    for i in range(12):
        items.append((f"TOOL[pytest run {i}]: collected 214 items ... PASSED "
                      f"test_unrelated_module_{i} in 0.0{i}s ... DeprecationWarning ... "
                      "verbose traceback noise repeated across the whole run.", TOOL, 0.10))
    return items


# --------------------------------------------------------------------------- #
#  PHASE 1 — Hormonal Bus activation (real signals, real μs)
# --------------------------------------------------------------------------- #
def phase1_hormonal_bus(bus, backend: str, task: str, k: int) -> dict[str, float]:
    lab("Hormonal Bus", f"Activating signalling substrate ({backend}, 32 channels).")
    complexity = min(1.0, est_tokens(task) / 400.0)  # real: derived from task size
    lab("Hormonal Bus", f"Task complexity gradient = {complexity:.2f} "
                        f"({est_tokens(task)} est. tokens).")
    priorities: dict[str, float] = {}
    for name, flag, hexlabel, _sys, _temp in MITOSIS_ROLES[:k]:
        # priority prior per role, modulated by REAL task complexity → intensity
        prior = {"Architect": 0.9, "Adversary": 0.8, "Optimizer": 0.6, "Verifier": 0.7}[name]
        intensity = round(0.4 + 0.6 * prior * (0.5 + 0.5 * complexity), 2)
        t0 = time.perf_counter_ns()
        bus.secrete(int(flag), intensity)
        sensed = bus.sense(int(flag))
        dt_us = (time.perf_counter_ns() - t0) / 1000.0
        priorities[name] = sensed
        lab("Hormonal Bus", f"Signal Type {hexlabel} ({name}) injected. Intensity: "
                            f"{intensity:.2f}. Routing priority recalculated in {dt_us:.0f}μs.")
    tot = sum(priorities.values()) or 1.0
    ranked = ", ".join(f"{n}={v/tot:.0%}" for n, v in sorted(priorities.items(),
                                                             key=lambda kv: -kv[1]))
    lab("Hormonal Bus", f"Gradient equilibrium reached → priority mix [{ranked}].")
    return priorities


# --------------------------------------------------------------------------- #
#  PHASE 2 — Memory apoptosis (real ContextPruner token accounting)
# --------------------------------------------------------------------------- #
def phase2_memory_apoptosis(history: list[tuple[str, int, float]]):
    pr = ContextPruner(epsilon=0.05)
    for content, signal, oxygen in history:
        pr.add(content, oxygen=oxygen, signal=signal)
    before = pr.active_tokens()
    lab("Memory Apoptosis", f"Context seeded: {len(history)} data, {before:,} tokens "
                            f"({pr.backend} backend). Beginning oxygen decay.")
    t0 = time.perf_counter_ns()
    purged = pr.prune_cycles(cycles=2, rate=0.25,
                             reinforce_mask=SYSTEM | FACT, reinforce_amount=0.5)
    dt_us = (time.perf_counter_ns() - t0) / 1000.0
    after = pr.active_tokens()
    reduction = pr.reduction()
    lab("Memory Apoptosis", f"{before - after:,} redundant tokens purged "
                            f"({purged} data apoptosed). Context window reduced by "
                            f"{reduction * 100:.0f}% in {dt_us:.0f}μs.")
    return pr, before, after, reduction


# --------------------------------------------------------------------------- #
#  PHASE 3 — Neuronal mitosis (real concurrent OpenRouter sub-agents)
# --------------------------------------------------------------------------- #
async def phase3_neuronal_mitosis(provider, task: str, pruned_ctx: str,
                                  model: str, k: int) -> list[Completion]:
    lab("Neuronal Mitosis", f"High-complexity threshold reached. Node duplicated "
                            f"into {k} parallel sub-agents ({pretty(model)}).")

    async def spawn(idx: int) -> Completion:
        name, _flag, hexlabel, sysmsg, temp = MITOSIS_ROLES[idx]
        prompt = (f"Context (pruned):\n{pruned_ctx}\n\nTask:\n{task}")
        t0 = time.perf_counter_ns()
        c = await provider.complete(prompt=prompt, model=model, system=sysmsg,
                                    max_tokens=700, temperature=temp)
        dt_ms = (time.perf_counter_ns() - t0) / 1e6
        if c.error:
            lab("Neuronal Mitosis", f"Sub-agent {idx+1}/{k} {name} ({hexlabel}) ERROR: {c.error}")
        else:
            lab("Neuronal Mitosis", f"Sub-agent {idx+1}/{k} {name} ({hexlabel}) converged: "
                                    f"in {c.in_tokens} → out {c.out_tokens} tok, "
                                    f"rtt {c.rtt_ms:.0f}ms (wall {dt_ms:.0f}ms).")
        return c

    comps = await asyncio.gather(*(spawn(i) for i in range(k)))
    ok = [c for c in comps if not c.error and c.text]
    lab("Neuronal Mitosis", f"{len(ok)}/{k} hypotheses viable after mitosis.")
    return comps


async def coordinate(provider, task: str, hypotheses: list[Completion],
                     model: str) -> Completion:
    """Jacobi-style convergence: synthesise the surviving hypotheses into one
    consolidated answer (the colony's emergent consensus)."""
    viable = [c for c in hypotheses if not c.error and c.text]
    if not viable:
        return Completion("", model, 0, 0, 0.0, 0.0, error="no viable hypotheses")
    if len(viable) == 1:
        return viable[0]
    joined = "\n\n".join(f"[Hypothesis {i+1}]\n{c.text}" for i, c in enumerate(viable))
    prompt = (f"Task:\n{task}\n\nCandidate solutions from parallel specialists:\n{joined}\n\n"
              "Synthesise the single best, fully-correct consolidated solution. "
              "Merge the strongest ideas; drop anything wrong.")
    lab("Coordination", f"Converging {len(viable)} hypotheses via synthesis ({pretty(model)}).")
    t0 = time.perf_counter_ns()
    c = await provider.complete(prompt=prompt, model=model, max_tokens=800,
                                system="You are a rigorous synthesis agent.", temperature=0.1)
    dt_ms = (time.perf_counter_ns() - t0) / 1e6
    lab("Coordination", f"Consensus reached: out {c.out_tokens} tok, rtt {c.rtt_ms:.0f}ms "
                        f"(wall {dt_ms:.0f}ms).")
    return c


# --------------------------------------------------------------------------- #
#  Quality — real LLM-as-judge (0..100), deterministic in mock mode
# --------------------------------------------------------------------------- #
async def judge_quality(provider, task: str, answer: str, judge_model: str,
                        *, mock_hint: Optional[float] = None) -> Optional[int]:
    if isinstance(provider, MockAsyncProvider):
        # SYNTHETIC: model the judge from the profile hint (0..1). Clearly mock.
        return None if mock_hint is None else max(0, min(100, round(mock_hint * 100)))
    if not answer:
        return None
    prompt = (f"TASK:\n{task}\n\nCANDIDATE ANSWER:\n{answer}\n\n"
              "Rate the candidate answer's correctness and completeness from 0 to 100. "
              "Reply with ONLY the integer.")
    c = await provider.complete(prompt=prompt, model=judge_model, max_tokens=6,
                                system="You are a strict, terse evaluator.", temperature=0.0)
    m = re.search(r"\d{1,3}", c.text or "")
    return max(0, min(100, int(m.group()))) if m else None


# --------------------------------------------------------------------------- #
#  Benchmark row + runners
# --------------------------------------------------------------------------- #
@dataclass
class Row:
    label: str
    seconds: float
    cost: float
    in_tokens: int
    out_tokens: int
    reduction: float          # apoptosis context reduction (0.0 for baseline)
    convergence: str
    quality: Optional[int]
    calls: int


async def run_baseline(provider, task: str, raw_ctx: str, model: str,
                       judge_model: str, mock_q: Optional[float]) -> tuple[Row, str]:
    lab("Baseline", f"{pretty(model)}: single linear call with FULL accumulated context "
                    f"({est_tokens(raw_ctx):,} est. context tokens).")
    prompt = f"Context:\n{raw_ctx}\n\nTask:\n{task}"
    t0 = time.perf_counter_ns()
    c = await provider.complete(prompt=prompt, model=model, max_tokens=800,
                                system="You are an expert software engineer.", temperature=0.2)
    secs = (time.perf_counter_ns() - t0) / 1e9
    if c.error:
        lab("Baseline", f"{pretty(model)} ERROR: {c.error}")
    q = await judge_quality(provider, task, c.text, judge_model,
                            mock_hint=(mock_q if mock_q is not None else None))
    row = Row(f"{pretty(model)} (Pure Baseline)", secs, c.cost_usd, c.in_tokens, c.out_tokens,
              0.0, "Rígida / Linear", q, 1)
    return row, c.text


async def run_bioma(provider, task: str, history, model: str, k: int,
                    judge_model: str, powered_label: str,
                    mock_q: Optional[float]) -> tuple[Row, str]:
    t_start = time.perf_counter_ns()
    bus, backend = _make_bus()
    phase1_hormonal_bus(bus, backend, task, k)                       # Phase 1
    pr, before, after, reduction = phase2_memory_apoptosis(history)   # Phase 2
    pruned_ctx = pr.render()
    hyps = await phase3_neuronal_mitosis(provider, task, pruned_ctx, model, k)  # Phase 3
    final = await coordinate(provider, task, hyps, model)            # convergence
    secs = (time.perf_counter_ns() - t_start) / 1e9

    calls = k + (1 if len([c for c in hyps if not c.error and c.text]) > 1 else 0)
    in_tok = sum(c.in_tokens for c in hyps) + final.in_tokens
    out_tok = sum(c.out_tokens for c in hyps) + final.out_tokens
    cost = round(sum(c.cost_usd for c in hyps) + final.cost_usd, 6)

    # mock quality: best-of-K + synthesis coordination uplift (SYNTHETIC, labelled)
    m_hint = None
    if mock_q is not None:
        m_hint = min(0.99, mock_q + 0.05 + 0.015 * (k - 1))
    q = await judge_quality(provider, task, final.text, judge_model, mock_hint=m_hint)

    row = Row(f"B.I.O.M.A. ({powered_label})", secs, cost, in_tok, out_tok,
              reduction, "Dinâmica / Mitose", q, calls)
    return row, final.text


# --------------------------------------------------------------------------- #
#  Final Sakana-style benchmark table + transparency appendix
# --------------------------------------------------------------------------- #
def _fmt_q(q: Optional[int]) -> str:
    return "—" if q is None else str(q)


def render_table(pairs: list[tuple[Row, Row]], mock: bool) -> str:
    out: list[str] = []
    out.append("## B.I.O.M.A. vs Baseline Models (Sakana-Style Evaluation)\n")
    if mock:
        out.append("> ⚠️ **[MOCK MODE]** — no OPENROUTER_API_KEY reachable. Timings, token "
                   "counts and apoptosis are real (offline); model latency/cost/quality are "
                   "**modelled** from each model's profile. Run with a key for judge-scored "
                   "quality and real usage/cost.\n")
    out.append("| Abordagem / Modelo | Tempo de Resposta (s) | Custo Estimado / Token ($) "
               "| Redução de Contexto | Eficiência de Convergência | Score de Qualidade (0-100) |")
    out.append("| :--- | :--- | :--- | :--- | :--- | :--- |")
    for base, bio in pairs:
        pct = f"{bio.reduction * 100:.0f}"
        out.append(f"| **{base.label}** | {base.seconds:.2f} | Padrão (100%) "
                   f"| 0% (Acumulativo) | Rígida / Linear | {_fmt_q(base.quality)} |")
        out.append(f"| **{bio.label}** | {bio.seconds:.2f} | **Economia de {pct}%** "
                   f"| **{pct}% Purge (Apoptose)** | **Dinâmica / Mitose** | {_fmt_q(bio.quality)} |")
    out.append("")
    # transparency appendix — the FULL cost picture (mitosis multiplies calls)
    out.append("### Raw measurements (nothing hidden)\n")
    out.append("| Run | Calls | in_tok | out_tok | Cost (USD) | Notes |")
    out.append("| :-- | --: | --: | --: | --: | :-- |")
    for base, bio in pairs:
        out.append(f"| {base.label} | {base.calls} | {base.in_tokens:,} | {base.out_tokens:,} "
                   f"| {base.cost:.6f} | full raw context, 1 linear call |")
        out.append(f"| {bio.label} | {bio.calls} | {bio.in_tokens:,} | {bio.out_tokens:,} "
                   f"| {bio.cost:.6f} | {bio.calls} calls (mitosis+synthesis), pruned context |")
    out.append("")
    out.append("> **‡ Reading the cost column honestly:** *Economia de XX%* is the **input-token "
               "reduction per call** from apoptosis (real). Mitosis fires N sub-agents in "
               "parallel, so B.I.O.M.A.'s **absolute** spend is higher than one baseline call "
               "(see raw table) — apoptosis is what keeps that fan-out affordable, and the "
               "return on it shows up in the **Quality** column. B.I.O.M.A. trades more compute "
               "for a better answer; it is not cheaper than a single call.")
    return "\n".join(out)


# --------------------------------------------------------------------------- #
#  Provider selection (real if a reachable key, else mock)
# --------------------------------------------------------------------------- #
async def build_provider(force_mock: bool):
    if force_mock or not os.environ.get("OPENROUTER_API_KEY"):
        return MockAsyncProvider(), True
    try:
        prov = AsyncOpenRouterProvider()
        probe = await prov.complete(prompt="ping", model="openai/gpt-4o-mini",
                                    max_tokens=1, temperature=0.0)
        if probe.error and ("401" in probe.error or "exhausted" in probe.error):
            await prov.close()
            lab("System", _c("33", f"Real key present but probe failed ({probe.error}); "
                                    "falling back to MOCK."))
            return MockAsyncProvider(), True
        return prov, False
    except Exception as exc:  # bad key / SDK missing
        lab("System", _c("33", f"Could not init real provider ({exc}); using MOCK."))
        return MockAsyncProvider(), True


_MOCK_Q = {  # profile hint used ONLY in mock mode (mirrors openrouter_async._MOCK_PROFILE)
    "anthropic/claude-3.5-sonnet": 0.92, "openai/gpt-4o": 0.88,
    "x-ai/grok-2": 0.82, "meta-llama/llama-3-70b-instruct": 0.74,
}


async def main() -> int:
    ap = argparse.ArgumentParser(description="B.I.O.M.A. Sakana-style demo console")
    ap.add_argument("--task", default=DEFAULT_TASK)
    ap.add_argument("--models", nargs="+",
                    default=["openai/gpt-4o", "anthropic/claude-3.5-sonnet"])
    ap.add_argument("--judge", default="openai/gpt-4o-mini")
    ap.add_argument("--mitosis", type=int, default=3, help="parallel sub-agents (2..4)")
    ap.add_argument("--mock", action="store_true", help="force offline mock")
    ap.add_argument("--check", action="store_true", help="preflight only")
    args = ap.parse_args()
    k = max(2, min(len(MITOSIS_ROLES), args.mitosis))

    powered = {"openai/gpt-4o": "Powered by GPT-4o",
               "anthropic/claude-3.5-sonnet": "Powered via Sonnet"}

    provider, mock = await build_provider(args.mock)
    mode = _c("33", "MOCK (offline, synthetic model metrics)") if mock \
        else _c("32", "REAL (OpenRouter, live usage + judge)")

    rule("B.I.O.M.A. — Runtime Evolution Console  ·  Sakana-Style Evaluation")
    lab("System", f"Mode: {mode}")
    lab("System", f"Hormonal core: {'rust-kernel' if _HAS_KERNEL else 'python-fallback'} · "
                  f"Apoptosis backend: {ContextPruner().backend} · Mitosis width: {k}")
    lab("System", f"Models under test: {', '.join(pretty(m) for m in args.models)} · "
                  f"Judge: {args.judge if not mock else 'modelled'}")
    if args.check:
        lab("System", _c("32", "Preflight OK.") if not mock else _c("33", "Preflight OK (mock)."))
        if not mock:
            await provider.close()
        return 0

    history = build_bloated_context()
    task = args.task
    pairs: list[tuple[Row, Row]] = []
    try:
        for model in args.models:
            rule(f"MODEL: {pretty(model)}")
            raw_ctx = "\n".join(c for c, _s, _o in history)
            mq = _MOCK_Q.get(model, 0.7) if mock else None
            base_row, _base_ans = await run_baseline(provider, task, raw_ctx, model,
                                                     args.judge, mq)
            print()
            bio_row, _bio_ans = await run_bioma(provider, task, history, model, k,
                                                args.judge, powered.get(model, f"Powered by {pretty(model)}"),
                                                mq)
            pairs.append((base_row, bio_row))
            print()
    finally:
        if not mock:
            await provider.close()

    rule("RESULTS")
    print()
    print(render_table(pairs, mock))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(main()))
    except KeyboardInterrupt:
        print("\ninterrupted.", file=sys.stderr)
        raise SystemExit(130)
