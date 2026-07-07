"""
live_pipeline.py — the ONLINE evolutionary orchestration, exposed for the API.

Runs the B.I.O.M.A. organic life-cycle over OpenRouter for a single task and
returns the final answer + REAL telemetry:

    Phase 1  Hormonal Bus     — real kernel signalling (priority gradients, μs)
    Phase 2  Memory Apoptosis — real ContextPruner token pruning (before/after)
    Phase 3  Neuronal Mitosis — N concurrent OpenRouter sub-agents (asyncio.gather)
    Converge Coordination     — synthesise surviving hypotheses into one answer

Real when ``OPENROUTER_API_KEY`` is a valid ``sk-or`` key; otherwise a clearly
labelled deterministic MOCK (``mode="mock"``) so the endpoint always answers.

This is the shared engine behind both ``bioma_sakana_console_test.py`` (the demo
console) and the server's ``POST /v1/orchestrate`` route — one code path, so the
console and the deployed API can never drift.
"""
from __future__ import annotations

import asyncio
import os
import re
import time
from typing import Optional

from bioma_orchestrator.openrouter_async import (
    AsyncOpenRouterProvider, MockAsyncProvider, Completion,
)
from bioma_orchestrator.context import (
    ContextPruner, SYSTEM, USER, ASSISTANT, FACT, TOOL, est_tokens,
)

try:
    import bioma_kernel
    _HAS_KERNEL = hasattr(bioma_kernel, "HormonalBus")
except Exception:
    _HAS_KERNEL = False


# Differentiated specialist cells: (name, signal_flag, hex_label, system, temperature)
ROLES = [
    ("Architect", 1 << 4, "0x10",
     "You are a systems architect. Produce the cleanest, most correct solution "
     "with rigorous structure.", 0.15),
    ("Adversary", 1 << 5, "0x20",
     "You are an adversarial reviewer. Solve the task while actively hunting for "
     "edge cases, races, and security holes others miss.", 0.35),
    ("Optimizer", 1 << 6, "0x40",
     "You are a performance/pragmatism specialist. Solve it simply and efficiently, "
     "minimising moving parts.", 0.25),
    ("Verifier", 1 << 7, "0x80",
     "You are a correctness prover. Solve the task and justify why each failure "
     "mode is eliminated.", 0.20),
]
_ROLE_PRIOR = {"Architect": 0.9, "Adversary": 0.8, "Optimizer": 0.6, "Verifier": 0.7}


class _PyHormonalBus:
    """Pure-Python mirror of the kernel's HormonalBus (secrete/sense API)."""

    def __init__(self, num_signals: int = 32):
        self.n = num_signals
        self.conc = [0.0] * num_signals

    def secrete(self, flags: int, intensity: float) -> None:
        for b in range(self.n):
            if flags & (1 << b):
                self.conc[b] += intensity

    def sense(self, mask: int) -> float:
        return sum(self.conc[b] for b in range(self.n) if mask & (1 << b))


def _make_bus():
    if _HAS_KERNEL:
        return bioma_kernel.HormonalBus(32, 4096), "rust-kernel"
    return _PyHormonalBus(32), "python-fallback"


def _valid_key(k: Optional[str]) -> bool:
    return bool(k) and k.startswith("sk-or")


class _Recorder:
    """Collects the microsecond lab-notebook lines returned to the client."""

    def __init__(self):
        self.events: list[str] = []
        self._t0 = time.perf_counter_ns()

    def log(self, tag: str, msg: str) -> None:
        us = (time.perf_counter_ns() - self._t0) / 1000.0
        self.events.append(f"t+{us / 1e6:.6f}s [{tag}] {msg}")


def _demo_context() -> list[tuple[str, int, float]]:
    """A representative bloated working memory so a bare {task} call still
    demonstrates apoptosis. Flagged as 'demo-synthetic' in telemetry."""
    items: list[tuple[str, int, float]] = [
        ("SYSTEM: senior engineer; preserve public APIs; never introduce SQL injection.", SYSTEM, 1.0),
        ("FACT: db.exec accepts a parameterized form db.exec(sql, params).", FACT, 0.95),
        ("FACT: the target function is called concurrently from many threads.", FACT, 0.95),
        ("USER (recent): here is the buggy function; keep the signature, make it safe.", USER, 0.85),
        ("ASSISTANT (recent): diagnosed a lost-update race + string-concatenated SQL.", ASSISTANT, 0.82),
    ]
    for i in range(4):
        items.append((f"ASSISTANT (old {i}): stale answer about log rotation #{i}.", ASSISTANT, 0.26))
    for i in range(10):
        items.append((f"TOOL[pytest {i}]: collected 214 items ... PASSED unrelated_{i} ... "
                      "verbose traceback noise repeated across the run.", TOOL, 0.10))
    return items


def _coerce_context(context) -> tuple[list[tuple[str, int, float]], str]:
    """Accept client context as list[str] (tagged as recent user turns) or the
    typed triples; fall back to the demo memory when none is supplied."""
    if not context:
        return _demo_context(), "demo-synthetic"
    items: list[tuple[str, int, float]] = []
    for c in context:
        if isinstance(c, str):
            items.append((c, USER, 0.8))
        elif isinstance(c, (list, tuple)) and len(c) == 3:
            items.append((str(c[0]), int(c[1]), float(c[2])))
    return (items or _demo_context()), ("client" if items else "demo-synthetic")


async def _coordinate(provider, task: str, viable: list[Completion], model: str,
                      rec: _Recorder) -> Completion:
    if not viable:
        return Completion("", model, 0, 0, 0.0, 0.0, error="no viable hypotheses")
    if len(viable) == 1:
        return viable[0]
    joined = "\n\n".join(f"[Hypothesis {i+1}]\n{c.text}" for i, c in enumerate(viable))
    prompt = (f"Task:\n{task}\n\nCandidate solutions from parallel specialists:\n{joined}\n\n"
              "Synthesise the single best, fully-correct consolidated solution. "
              "Merge the strongest ideas; drop anything wrong.")
    rec.log("Coordination", f"Converging {len(viable)} hypotheses via synthesis.")
    c = await provider.complete(prompt=prompt, model=model, max_tokens=2560,
                                system="You are a rigorous synthesis agent.", temperature=0.1)
    if not c.error:
        rec.log("Coordination", f"Consensus reached: out {c.out_tokens} tok, rtt {c.rtt_ms:.0f}ms.")
    return c


_CONF_INSTR = ("\n\nAfter your solution, end with a line exactly 'CONFIDENCE: N' where "
               "N (0-100) is how likely your solution is fully correct AND complete.")
_CONF_RE = re.compile(r"CONFIDENCE:\s*(\d{1,3})", re.I)


def _parse_confidence(text: Optional[str]) -> Optional[int]:
    m = _CONF_RE.search(text or "")
    return max(0, min(100, int(m.group(1)))) if m else None


def _strip_confidence(text: Optional[str]) -> str:
    return _CONF_RE.sub("", text or "").rstrip()


async def evolve(task: str, *, model: str = "openai/gpt-4o", mitosis: int = 3,
                 context=None, provider=None, adaptive: bool = True,
                 confidence_threshold: int = 80) -> dict:
    """Run the full life-cycle for ``task`` and return answer + telemetry + events.

    When ``adaptive`` (default), a single scout cell probes the task first; only if
    its self-assessed confidence is below ``confidence_threshold`` does the colony
    escalate to full N-way mitosis + synthesis. Easy tasks return in one call
    (no wasted fan-out); hard/uncertain tasks get the full organism.
    """
    rec = _Recorder()
    k = max(2, min(len(ROLES), mitosis))

    own = False
    if provider is None:
        key = os.environ.get("OPENROUTER_API_KEY")
        if _valid_key(key):
            provider, mode, own = AsyncOpenRouterProvider(), "real", True
        else:
            provider, mode, own = MockAsyncProvider(), "mock", True
    else:
        mode = "mock" if isinstance(provider, MockAsyncProvider) else "real"

    try:
        t_start = time.perf_counter_ns()

        # ---- Phase 1: Hormonal Bus ---------------------------------------- #
        bus, backend = _make_bus()
        complexity = min(1.0, est_tokens(task) / 400.0)
        priorities: dict[str, float] = {}
        for name, flag, hexlabel, _sys, _temp in ROLES[:k]:
            intensity = round(0.4 + 0.6 * _ROLE_PRIOR[name] * (0.5 + 0.5 * complexity), 2)
            tt = time.perf_counter_ns()
            bus.secrete(int(flag), intensity)
            sensed = bus.sense(int(flag))
            dt_us = (time.perf_counter_ns() - tt) / 1000.0
            priorities[name] = round(sensed, 4)
            rec.log("Hormonal Bus", f"Signal Type {hexlabel} ({name}) injected. "
                                    f"Intensity: {intensity:.2f}. Priority recalculated in {dt_us:.0f}μs.")

        # ---- Phase 2: Memory Apoptosis ------------------------------------ #
        history, ctx_source = _coerce_context(context)
        pr = ContextPruner(epsilon=0.05)
        for content, signal, oxygen in history:
            pr.add(content, oxygen=oxygen, signal=signal)
        before = pr.active_tokens()
        tt = time.perf_counter_ns()
        purged = pr.prune_cycles(cycles=2, rate=0.25,
                                 reinforce_mask=SYSTEM | FACT, reinforce_amount=0.5)
        dt_us = (time.perf_counter_ns() - tt) / 1000.0
        after = pr.active_tokens()
        reduction = pr.reduction()
        pruned_ctx = pr.render()
        rec.log("Memory Apoptosis", f"{before - after} redundant tokens purged "
                                    f"({purged} data apoptosed). Context reduced "
                                    f"{reduction * 100:.0f}% in {dt_us:.0f}μs.")

        # ---- Phase 3: Neuronal Mitosis (adaptive) ------------------------- #
        async def spawn(idx: int, elicit: bool = False):
            name, _flag, hexlabel, sysmsg, temp = ROLES[idx]
            # Stagger premium-model fan-out slightly to avoid burst rate-limits, and
            # give reasoning models enough budget to think AND answer (else content
            # can come back empty when reasoning tokens exhaust a low max_tokens).
            if idx:
                await asyncio.sleep(0.25 * idx)
            comp = await provider.complete(
                prompt=f"Context (pruned):\n{pruned_ctx}\n\nTask:\n{task}",
                model=model, system=sysmsg + (_CONF_INSTR if elicit else ""),
                max_tokens=3072, temperature=temp)
            if comp.error:
                rec.log("Neuronal Mitosis", f"Sub-agent {idx+1} {name} ({hexlabel}) ERROR: {comp.error}")
            else:
                rec.log("Neuronal Mitosis", f"Sub-agent {idx+1} {name} ({hexlabel}) converged: "
                                            f"in {comp.in_tokens} → out {comp.out_tokens} tok, "
                                            f"rtt {comp.rtt_ms:.0f}ms.")
            return name, comp

        confidence: Optional[int] = None
        if adaptive:
            rec.log("Neuronal Mitosis", f"Scout probe ({model}) — assessing difficulty before fan-out.")
            _n, scout = await spawn(0, elicit=True)
            confidence = _parse_confidence(scout.text)
            scout.text = _strip_confidence(scout.text)  # keep the answer clean of the tag
            rec.log("Neuronal Mitosis", f"Scout confidence: "
                                        f"{confidence if confidence is not None else 'n/a'} "
                                        f"(threshold {confidence_threshold}).")
            if (scout.text and not scout.error and confidence is not None
                    and confidence >= confidence_threshold):
                escalated = False
                results = [("Architect", scout)]
                hyps = [scout]
                viable = [scout]
                final = scout
                rec.log("Neuronal Mitosis", f"High confidence → DIRECT answer; mitosis skipped "
                                            f"(saved ~{k - 1} sub-agent calls + synthesis).")
            else:
                escalated = True
                rec.log("Neuronal Mitosis", f"Low/uncertain confidence → escalating to {k}-way mitosis.")
                rest = await asyncio.gather(*(spawn(i) for i in range(1, k)))
                results = [("Architect", scout)] + list(rest)
                hyps = [c for _n, c in results]
                viable = [c for c in hyps if not c.error and c.text]
                rec.log("Neuronal Mitosis", f"{len(viable)}/{k} hypotheses viable after mitosis.")
                final = await _coordinate(provider, task, viable, model, rec)
        else:
            escalated = True
            rec.log("Neuronal Mitosis", f"Node duplicated into {k} parallel sub-agents ({model}).")
            results = await asyncio.gather(*(spawn(i) for i in range(k)))
            hyps = [c for _n, c in results]
            viable = [c for c in hyps if not c.error and c.text]
            rec.log("Neuronal Mitosis", f"{len(viable)}/{k} hypotheses viable after mitosis.")
            final = await _coordinate(provider, task, viable, model, rec)

        seconds = (time.perf_counter_ns() - t_start) / 1e9

        # Count only the DISTINCT model calls actually made (scout, sub-agents, synthesis).
        used = list(hyps)
        if all(final is not c for c in used):
            used.append(final)
        in_tok = sum(c.in_tokens for c in used)
        out_tok = sum(c.out_tokens for c in used)
        cost = round(sum(c.cost_usd for c in used), 6)
        calls = len(used)

        return {
            "answer": final.text,
            "model": model,
            "mode": mode,
            "error": final.error,
            "telemetry": {
                "hormonal": {"backend": backend, "priorities": priorities},
                "apoptosis": {"backend": pr.backend, "context_source": ctx_source,
                              "tokens_before": before, "tokens_after": after,
                              "reduction": round(reduction, 4), "purged_items": purged},
                "mitosis": {"width": k, "adaptive": adaptive, "escalated": escalated,
                            "confidence": confidence, "viable": len(viable),
                            "roles": [n for n, _ in results]},
                "usage": {"in_tokens": in_tok, "out_tokens": out_tok,
                          "cost_usd": cost, "calls": calls},
                "seconds": round(seconds, 3),
            },
            "events": rec.events,
        }
    finally:
        if own and mode == "real":
            await provider.close()
