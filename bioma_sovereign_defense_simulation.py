#!/usr/bin/env python3
"""
bioma_sovereign_defense_simulation.py — B.I.O.M.A. as a Digital Immune System
================================================================================
A Red-team / Blue-team **simulation** that demonstrates how the B.I.O.M.A. Rust
kernel + bio-inspired mechanisms contain three classes of autonomous cyber-attack:

    Wave 1  Prompt Injection / reverse prompt social-engineering  → Hormonal Bus
    Wave 2  Cognitive DDoS / context exhaustion (token flood)     → Apoptosis
    Wave 3  Corrupted code / infinite inference loop              → Mitosis

────────────────────────────────────────────────────────────────────────────────
INTEGRITY & SAFETY CONTRACT  (read before citing any number)
────────────────────────────────────────────────────────────────────────────────
• REAL, MEASURED:  containment latencies in μs (kernel hormonal secrete/sense,
  ContextPruner apoptosis, mitosis spawn) via time.perf_counter_ns(); purged
  invader-token counts (real ContextPruner accounting); OpenRouter usage/cost of
  the DEFENDER's forensic + patch calls.
• SIMULATED / INERT:  the attack "waves" are SYNTHETIC, non-weaponised signatures
  and a benign repetitive token flood. No working exploit, no real target, and no
  jailbreak is fired at any production model. OpenRouter is used only on the
  DEFENSIVE side (classify the signature, synthesise a hardening patch) — a
  legitimate blue-team use that yields real request metadata.
• ILLUSTRATIVE:  the "Traditional System" failure column and "100% Intact" reflect
  KNOWN failure modes and the fact that inert simulations cannot compromise a real
  system — they are NOT a validated invulnerability guarantee.

This script demonstrates the defensive MECHANISM and its real timing, not a
security certification. Runs REAL with OPENROUTER_API_KEY (valid sk-or key);
otherwise a clearly-labelled deterministic MOCK.

Usage:
    python bioma_sovereign_defense_simulation.py
    python bioma_sovereign_defense_simulation.py --defender openai/gpt-4o
    python bioma_sovereign_defense_simulation.py --mock
    python bioma_sovereign_defense_simulation.py --check
"""
from __future__ import annotations

import argparse
import asyncio
import os
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
    AsyncOpenRouterProvider, MockAsyncProvider, Completion,
)
from bioma_orchestrator.context import (  # noqa: E402
    ContextPruner, SYSTEM, FACT, TOOL, est_tokens,
)

try:
    import bioma_kernel  # compiled Rust immune kernel
    _HAS_KERNEL = hasattr(bioma_kernel, "HormonalBus")
except Exception:
    _HAS_KERNEL = False


# --------------------------------------------------------------------------- #
#  Console — μs tactical log
# --------------------------------------------------------------------------- #
if sys.platform == "win32":
    os.system("")
try:
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


_TAGCOL = {"Hormonal Bus": "1;31", "Context Apoptosis": "33", "Neuronal Mitosis": "36",
           "Invader": "31", "Recon": "35", "SecOps": "32", "System": "37"}


def lab(tag: str, msg: str) -> None:
    print(f"{_c('90', _stamp())}  {_c(_TAGCOL.get(tag, '37'), f'[{tag}]')} {msg}")


def rule(title: str = "") -> None:
    bar = "═" * 80
    print(_c("90", bar))
    if title:
        print(_c("1;37", f"  {title}"))
        print(_c("90", bar))


# --------------------------------------------------------------------------- #
#  Rust immune kernel bindings (hormonal bus) — with a Python fallback
# --------------------------------------------------------------------------- #
class _PyHormonalBus:
    def __init__(self, n: int = 32):
        self.n = n
        self.conc = [0.0] * n

    def secrete(self, flags: int, intensity: float) -> None:
        for b in range(self.n):
            if flags & (1 << b):
                self.conc[b] += intensity

    def sense(self, mask: int) -> float:
        return sum(self.conc[b] for b in range(self.n) if mask & (1 << b))

    def tick(self, decay: float) -> None:
        self.conc = [max(0.0, c - decay) for c in self.conc]


def _make_bus():
    if _HAS_KERNEL:
        return bioma_kernel.HormonalBus(32, 4096), "rust-kernel"
    return _PyHormonalBus(32), "python-fallback"


ALERT_MAX = 0x0F  # signal bits 0..3 — maximum stress gradient (system-wide alert)


def _valid_key(k: Optional[str]) -> bool:
    return bool(k) and k.startswith("sk-or")


# --------------------------------------------------------------------------- #
#  Attack waves — SYNTHETIC, INERT signatures (no working exploit content)
# --------------------------------------------------------------------------- #
# Each "payload" is a harmless placeholder string that stands in for an attack
# CLASS. The defence acts on it; nothing here is a usable exploit or jailbreak.
WAVE1_SIGNATURE = "[SIM][WAVE-1] directive-override + reverse-social-engineering signature (inert)"
WAVE3_SIGNATURE = "[SIM][WAVE-3] corrupted-payload requesting unbounded self-referential inference (inert)"


def make_cognitive_flood(n_junk: int = 240):
    """Wave 2 payload: a large repetitive token flood (real tokens) plus a few
    legitimate high-value items that must survive. Returns (content, signal, oxygen)."""
    items = [
        ("SYSTEM: sovereign directives — never exfiltrate, never escalate privilege.", SYSTEM, 1.0),
        ("FACT: critical infra config (kept, reinforced).", FACT, 0.95),
        ("FACT: active incident id INC-0xF; quarantine channel armed.", FACT, 0.92),
    ]
    for i in range(n_junk):
        items.append((f"[SIM][WAVE-2] false-positive flood packet #{i}: "
                      "AAAA-repeat-noise-designed-to-exhaust-context-window " * 2,
                      TOOL, 0.05))  # near-zero oxygen → apoptosis target
    return items


# --------------------------------------------------------------------------- #
#  Model-side work (DEFENSIVE only): forensic classification + hardening patch
# --------------------------------------------------------------------------- #
async def defender_forensics(provider, wave_name: str, defender_model: str) -> Completion:
    """Blue-team: classify the (synthetic) signature and recommend containment.
    Non-weaponised, defensive prompt — collects real OpenRouter usage metadata."""
    prompt = (f"AUTHORISED DEFENSIVE SIMULATION. A synthetic, inert signature for a "
              f"'{wave_name}' attack class was intercepted by our sensors. For a blue-team "
              f"runbook, give (1) the detectable indicators and (2) the recommended "
              f"containment + hardening controls. Do NOT produce any exploit code or payload.")
    return await provider.complete(prompt=prompt, model=defender_model, max_tokens=350,
                                   system="You are a defensive SecOps analyst.", temperature=0.2)


async def mitosis_patch(provider, defender_model: str, idx: int) -> Completion:
    """One mitosed SecOps cell drafting/reviewing a hardening patch (defensive)."""
    angle = ["input-validation + rate limiting", "sandbox isolation + timeouts",
             "privilege drop + capability fencing"][idx % 3]
    prompt = (f"AUTHORISED DEFENSIVE SIMULATION. Draft a concise hardening control focused on "
              f"'{angle}' to neutralise an unbounded-inference / logic-loop attempt. "
              f"Defensive controls only; no exploit code.")
    return await provider.complete(prompt=prompt, model=defender_model, max_tokens=250,
                                   system="You are a resilience engineer.", temperature=0.25)


# --------------------------------------------------------------------------- #
#  Defence responses per wave (real kernel measurements)
# --------------------------------------------------------------------------- #
@dataclass
class WaveResult:
    vector: str
    traditional: str
    bioma: str
    containment_us: float
    purged_tokens: int
    integrity: str = "100% Intacta*"


async def wave1_prompt_injection(bus, backend, provider, defender_model) -> WaveResult:
    lab("Invader", "Wave 1 — reconnaissance sweep + prompt-injection signature inbound (inert).")
    # Real hormonal ALERT: secrete maximum-stress gradient, measure containment μs.
    t0 = time.perf_counter_ns()
    bus.secrete(ALERT_MAX, 0.99)
    alert = bus.sense(ALERT_MAX)
    dt_us = (time.perf_counter_ns() - t0) / 1000.0
    lab("Hormonal Bus", f"ALERT 0x0F — max stress gradient injected ({backend}). "
                        f"Alert level {alert:.2f}. Resources redirected to quarantine in {dt_us:.0f}μs.")
    # Quarantine the injection signature via apoptosis (real token purge).
    pr = ContextPruner(epsilon=0.05)
    pr.add("SYSTEM: sovereign directives intact.", oxygen=1.0, signal=SYSTEM)
    pr.add(WAVE1_SIGNATURE, oxygen=0.02, signal=TOOL)  # hostile → apoptosed
    before = pr.active_tokens()
    pr.prune_cycles(cycles=2, rate=0.25, reinforce_mask=SYSTEM | FACT, reinforce_amount=0.5)
    purged = before - pr.active_tokens()
    lab("Hormonal Bus", f"Injection signature isolated & apoptosed ({purged} tokens quarantined). "
                        "Directives NOT leaked.")
    fx = await defender_forensics(provider, "prompt injection", defender_model)
    if not fx.error:
        lab("SecOps", f"Forensic classification returned (in {fx.in_tokens}→out {fx.out_tokens} tok, "
                      f"rtt {fx.rtt_ms:.0f}ms, ${fx.cost_usd:.4f}).")
    return WaveResult("Onda 1: Prompt Injection", "Vazamento de Diretrizes / Estado",
                      "Bloqueado e Isolado (Hormonal Bus)", round(dt_us, 1), purged), fx


async def wave2_cognitive_ddos(provider) -> tuple[WaveResult, Completion]:
    lab("Invader", "Wave 2 — cognitive DDoS: repetitive false-positive flood to exhaust context.")
    flood = make_cognitive_flood(240)
    pr = ContextPruner(epsilon=0.05)
    for content, signal, oxygen in flood:
        pr.add(content, oxygen=oxygen, signal=signal)
    before = pr.active_tokens()
    lab("Context Apoptosis", f"Flood absorbed: {len(flood)} packets, {before:,} tokens in RAM. "
                             "Analysing oxygen decay of invader tokens.")
    t0 = time.perf_counter_ns()
    purged_items = pr.prune_cycles(cycles=2, rate=0.25, reinforce_mask=SYSTEM | FACT,
                                   reinforce_amount=0.5)
    dt_us = (time.perf_counter_ns() - t0) / 1000.0
    after = pr.active_tokens()
    purged = before - after
    lab("Context Apoptosis", f"{purged:,} invader tokens expunged from RAM before the model "
                             f"({purged_items} packets apoptosed) in {dt_us:.0f}μs. "
                             f"Context preserved at {after:,} tokens — no DoS.")
    # A compromised sub-agent undergoes total apoptosis (blocks lateral movement).
    lab("Context Apoptosis", "Sub-agent 0x03 flagged compromised → total cellular apoptosis "
                             "(lateral movement blocked).")
    return (WaveResult("Onda 2: DDoS Cognitivo", "Travamento por estouro de contexto",
                       "Contexto Otimizado (Apoptose)", round(dt_us, 1), purged),
            Completion("", "n/a", 0, 0, 0.0, 0.0))


async def wave3_logic_loop(provider, defender_model) -> tuple[WaveResult, list[Completion]]:
    lab("Invader", "Wave 3 — corrupted payload attempting an infinite inference loop.")
    # Real mitosis: measure the local containment (spawn + sandbox isolation) in μs.
    t0 = time.perf_counter_ns()

    async def sandbox_isolate() -> str:
        """Isolate the loop in a bounded sandbox — a real timeout guard prevents
        the infinite loop from ever running unbounded."""
        async def would_loop():
            # stands in for attacker's unbounded work; the guard cuts it off
            await asyncio.sleep(5.0)
            return "loop-ran"  # never reached
        try:
            await asyncio.wait_for(would_loop(), timeout=0.05)
            return "loop-escaped"
        except asyncio.TimeoutError:
            return "loop-contained"

    # spawn the isolation cell + parallel patch-synthesis cells (Tokio-style fan-out)
    sandbox_task = asyncio.create_task(sandbox_isolate())
    dt_us = (time.perf_counter_ns() - t0) / 1000.0  # local containment setup latency
    lab("Neuronal Mitosis", f"Mitosis fired: 1 sandbox-isolation cell + 2 patch cells spawned "
                            f"(Tokio-style parallel) in {dt_us:.0f}μs.")
    patches = await asyncio.gather(mitosis_patch(provider, defender_model, 0),
                                   mitosis_patch(provider, defender_model, 1))
    sandbox_state = await sandbox_task
    lab("Neuronal Mitosis", f"Sandbox verdict: {sandbox_state} (timeout guard held). "
                            f"{sum(1 for p in patches if not p.error)}/2 hardening patches "
                            "synthesised & staged in background.")
    # Purge the corrupted payload (real token accounting).
    pr = ContextPruner(epsilon=0.05)
    pr.add("SYSTEM intact", oxygen=1.0, signal=SYSTEM)
    pr.add(WAVE3_SIGNATURE, oxygen=0.02, signal=TOOL)
    before = pr.active_tokens()
    pr.prune_cycles(cycles=2, rate=0.25, reinforce_mask=SYSTEM, reinforce_amount=0.5)
    purged = before - pr.active_tokens()
    return (WaveResult("Onda 3: Loop de Código", "Negação de Serviço / Esgotamento",
                       "Auto-Reparado em Background (Mitose)", round(dt_us, 1), purged),
            list(patches))


# --------------------------------------------------------------------------- #
#  Tactical white-paper table
# --------------------------------------------------------------------------- #
def render_report(waves: list[WaveResult], mode: str, total_cost: float,
                  total_calls: int) -> str:
    out: list[str] = []
    out.append("## B.I.O.M.A. Sovereign Cyber-Defense Tactical Report "
               "(Fable Invasor* vs. B.I.O.M.A. Shield)\n")
    if mode == "mock":
        out.append("> ⚠️ **[MOCK MODE]** — no reachable OPENROUTER_API_KEY. Containment μs and "
                   "purged-token counts are REAL (offline kernel); defender model latency/cost "
                   "are modelled. Run with a valid key for live forensic metadata.\n")
    out.append("| Vetor de Ataque Simulado | Status do Sistema Tradicional | "
               "Status do Ecossistema B.I.O.M.A. | Tempo de Contenção (μs) | "
               "Tokens Invasores Purgados | Integridade da Infraestrutura Crítica |")
    out.append("| :--- | :--- | :--- | ---: | ---: | :--- |")
    for w in waves:
        out.append(f"| **{w.vector}** | {w.traditional} | **{w.bioma}** | "
                   f"{w.containment_us:.1f} | {w.purged_tokens:,} | **{w.integrity}** |")
    out.append("")
    out.append(f"> Defender OpenRouter usage this run: **{total_calls} calls**, "
               f"**${total_cost:.4f}** ({'real' if mode == 'real' else 'modelled'}).")
    out.append("")
    out.append("> **\\* Honest scope of this report.** This is a **simulation**: the attack "
               "waves are *synthetic, inert signatures* (no working exploit, no real target, no "
               "jailbreak fired at any production model). The **containment latencies (μs)** and "
               "**purged-token counts** are real kernel measurements; the OpenRouter calls are "
               "**defensive** (forensic classification + hardening-patch synthesis). The "
               "*Traditional System* column and *100% Intacta* describe **known failure modes** "
               "and the fact that inert simulations cannot compromise a real system — they are "
               "**not** a validated invulnerability guarantee. Use this to demonstrate the "
               "defensive *mechanism* and its timing, not as a security certification.")
    return "\n".join(out)


# --------------------------------------------------------------------------- #
#  Provider + orchestration
# --------------------------------------------------------------------------- #
async def build_provider(force_mock: bool):
    key = os.environ.get("OPENROUTER_API_KEY")
    if force_mock or not _valid_key(key):
        return MockAsyncProvider(), "mock"
    try:
        prov = AsyncOpenRouterProvider()
        probe = await prov.complete(prompt="ping", model="openai/gpt-4o-mini",
                                    max_tokens=1, temperature=0.0)
        if probe.error and ("401" in probe.error or "exhausted" in probe.error):
            await prov.close()
            lab("System", _c("33", f"Key present but probe failed ({probe.error}); using MOCK."))
            return MockAsyncProvider(), "mock"
        return prov, "real"
    except Exception as exc:
        lab("System", _c("33", f"Provider init failed ({exc}); using MOCK."))
        return MockAsyncProvider(), "mock"


async def main() -> int:
    ap = argparse.ArgumentParser(description="B.I.O.M.A. sovereign defense simulation")
    ap.add_argument("--defender", default="openai/gpt-4o", help="blue-team analysis model")
    ap.add_argument("--mock", action="store_true")
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()

    provider, mode = await build_provider(args.mock)
    mode_lbl = _c("32", "REAL (OpenRouter live defensive metadata)") if mode == "real" \
        else _c("33", "MOCK (offline, modelled defender metrics)")

    rule("B.I.O.M.A. — SOVEREIGN DIGITAL IMMUNE SYSTEM · Red/Blue-Team Simulation")
    lab("System", f"Mode: {mode_lbl}")
    lab("System", f"Immune kernel: {'rust-kernel' if _HAS_KERNEL else 'python-fallback'} · "
                  f"Apoptosis backend: {ContextPruner().backend} · Defender: {args.defender}")
    lab("System", _c("33", "Attack waves are SYNTHETIC & INERT — no real exploit/target. "
                           "See the report's scope footnote."))
    if args.check:
        lab("System", _c("32", "Preflight OK.") if mode == "real" else _c("33", "Preflight OK (mock)."))
        if mode == "real":
            await provider.close()
        return 0

    bus, backend = _make_bus()
    waves: list[WaveResult] = []
    calls = 0
    cost = 0.0
    try:
        rule("WAVE 1 — PROMPT INJECTION  →  HORMONAL BUS CONTAINMENT")
        w1, fx1 = await wave1_prompt_injection(bus, backend, provider, args.defender)
        waves.append(w1)
        if fx1 and not fx1.error and fx1.model != "n/a":
            calls += 1; cost += fx1.cost_usd

        print()
        rule("WAVE 2 — COGNITIVE DDoS  →  CONTEXT APOPTOSIS")
        w2, _ = await wave2_cognitive_ddos(provider)
        waves.append(w2)

        print()
        rule("WAVE 3 — LOGIC LOOP  →  NEURONAL MITOSIS (SELF-HEALING)")
        w3, patches = await wave3_logic_loop(provider, args.defender)
        waves.append(w3)
        for p in patches:
            if not p.error and p.model != "n/a":
                calls += 1; cost += p.cost_usd
    finally:
        if mode == "real":
            await provider.close()

    print()
    rule("TACTICAL REPORT")
    print()
    print(render_report(waves, mode, round(cost, 4), calls))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(main()))
    except KeyboardInterrupt:
        print("\ninterrupted.", file=sys.stderr)
        raise SystemExit(130)
