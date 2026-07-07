#!/usr/bin/env python3
"""
bioma_kernel_loadtest.py — industrial-scale resilience benchmark for the Rust kernel
====================================================================================
Hardens the "resilient at industrial level" claim with GROUND TRUTH, no API cost.

Sweeps 1k → 10k concurrent Tokio micro-agents flooding the lock-free hormonal bus
(with live apoptosis running on a CPU-pinned collector core) and measures, per load:
  • throughput  — signals processed per second
  • latency     — avg / p99 / max of the measured hormone round-trip (μs)
  • apoptosis   — memory-apoptosis events + tokens freed under load

HONEST SCOPE: this measures the KERNEL primitive (in-memory concurrent signalling +
apoptosis), NOT an end-to-end LLM system. The defensible claim it supports is narrow
and true: "the Rust kernel sustains N-thousand concurrent agents at BOUNDED μs
latency." Resilience = latency stays bounded (does not blow up) as load scales.
"""
from __future__ import annotations

import sys
import time

try:
    import bioma_kernel
except Exception as exc:  # pragma: no cover
    print(f"bioma_kernel not importable ({exc}). Build it: cd bioma_kernel && maturin develop --release")
    raise SystemExit(2)

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

if not hasattr(bioma_kernel, "StressTester"):
    print("This kernel build has no StressTester.")
    raise SystemExit(2)

import os
CORES = os.cpu_count() or 0
LOADS = [1000, 2500, 5000, 10000]
DURATION = 2.0

print("=" * 84)
print("  B.I.O.M.A. Rust Kernel — Industrial Resilience Load Test (ground truth)")
print("=" * 84)
print(f"  host cores: {CORES}  ·  workers = cores-1 (1 core pinned for telemetry)  ·  "
      f"{DURATION:.0f}s per load\n")

rows = []
for n in LOADS:
    st = bioma_kernel.StressTester(num_signals=16, max_agents=10000)  # fresh → clean metrics
    t0 = time.perf_counter()
    m = st.run(n, DURATION)          # floods the bus with n concurrent agents
    wall = time.perf_counter() - t0
    signals = m.get("sinais_processados", 0.0)
    thr = signals / wall if wall > 0 else 0.0
    rows.append({
        "agents": n, "wall": wall, "signals": signals, "thr": thr,
        "avg_us": m.get("latencia_comunicacao_us", 0.0),
        "p99_us": m.get("latencia_p99_us", 0.0),
        "max_us": m.get("latencia_max_us", 0.0),
        "apop": m.get("apoptosis_events", 0.0),
        "tok_saved": m.get("tokens_salvos_apoptose", 0.0),
    })
    print(f"  {n:>6,} agents │ {thr/1e6:6.2f} M sig/s │ avg {m.get('latencia_comunicacao_us',0):6.3f}μs "
          f"│ p99 {m.get('latencia_p99_us',0):7.2f}μs │ max {m.get('latencia_max_us',0):8.1f}μs "
          f"│ apoptose {int(m.get('apoptosis_events',0)):>7,} eventos")

print("\n" + "=" * 84)
print("## B.I.O.M.A. Kernel — Resiliência sob carga (ground truth, sem API)\n")
print("| Agentes concorrentes | Throughput (sinais/s) | Latência média (μs) | Latência p99 (μs) | Apoptose (eventos) | Tokens liberados |")
print("| ---: | ---: | ---: | ---: | ---: | ---: |")
for r in rows:
    print(f"| {r['agents']:,} | {r['thr']/1e6:.2f} M | {r['avg_us']:.3f} | {r['p99_us']:.2f} "
          f"| {int(r['apop']):,} | {int(r['tok_saved']):,} |")

# --- resilience verdict: does latency stay bounded as load scales 10×? ---
avg0, avg1 = rows[0]["avg_us"], rows[-1]["avg_us"]
p99_0, p99_1 = rows[0]["p99_us"], rows[-1]["p99_us"]
scale = rows[-1]["agents"] / rows[0]["agents"]
avg_growth = (avg1 / avg0) if avg0 > 0 else float("inf")
p99_growth = (p99_1 / p99_0) if p99_0 > 0 else float("inf")
print(f"\n**Veredito de resiliência (carga {scale:.0f}× maior, de {rows[0]['agents']:,} → {rows[-1]['agents']:,} agentes):**")
print(f"- Latência média: {avg0:.3f}μs → {avg1:.3f}μs  (**{avg_growth:.1f}×**)")
print(f"- Latência p99:   {p99_0:.2f}μs → {p99_1:.2f}μs  (**{p99_growth:.1f}×**)")
bounded = avg_growth <= scale * 0.5 and rows[-1]["avg_us"] < 50
print(f"- **Latência {'PERMANECE LIMITADA' if bounded else 'CRESCE'} sob {scale:.0f}× de carga** — "
      f"{'resiliência confirmada (μs, sub-linear)' if bounded else 'revisar sob carga'}.")
print("\n> Escopo honesto: mede a primitiva do KERNEL (sinalização concorrente + apoptose em "
      "memória), não um sistema LLM ponta-a-ponta. Afirmação defensável: 'o kernel sustenta "
      "N mil agentes concorrentes com latência de μs limitada'.")
