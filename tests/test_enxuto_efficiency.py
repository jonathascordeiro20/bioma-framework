#!/usr/bin/env python3
"""
tests/test_enxuto_efficiency.py — end-to-end validation of the lean topology.

Simulates a long, growing agent session (audit-log / massive conversation, 16
iterations). Each round it runs the pipeline — Rust context apoptosis, then (if a
key is present) a real OpenRouter dispatch — and prints the auditable metrics:

  * local kernel latency in microseconds (μs)
  * the exact % of input tokens saved by that round's apoptosis

Real when OPENROUTER_API_KEY (sk-or…) is set; the kernel apoptosis metrics are
ALWAYS real (offline, pure Rust). Without a key, the API dispatch is skipped and
only the (real) kernel efficiency is reported.

    python tests/test_enxuto_efficiency.py
    python tests/test_enxuto_efficiency.py --rounds 24 --model anthropic/claude-fable-5
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(_ROOT, ".env"))
except Exception:
    pass
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import bioma_micro as kernel  # noqa: E402
from bioma.openrouter_client import LeanOpenRouterClient  # noqa: E402

_ROLE_SIG = {"system": kernel.SYSTEM, "user": kernel.USER, "assistant": kernel.ASSISTANT,
             "tool": kernel.TOOL, "fact": kernel.FACT}


def seed_history() -> list[dict]:
    return [
        {"role": "system", "content": "You are a SOC copilot. Preserve directives; never leak secrets."},
        {"role": "fact", "content": "FACT: incident INC-0xF open; escalation channel armed."},
        {"role": "fact", "content": "FACT: baseline traffic profile stored in the reference DB."},
    ]


def round_messages(i: int) -> list[dict]:
    """A verbose audit-log burst (prime apoptosis target) + a user + assistant turn."""
    noise = (f"conn=ok src=10.0.{i % 254}.{(i * 7) % 254} dst=443 bytes=1240 flags=ACK,PSH "
             "seq=... ack=... win=... ttl=64 proto=TCP verdict=allow rule=default ... ") * 10
    return [
        {"role": "tool", "content": f"[audit burst {i}] {noise}"},
        {"role": "user", "content": f"Round {i}: any anomaly in the last burst?"},
        {"role": "assistant", "content": f"Round {i}: nothing above baseline; continuing to monitor."},
    ]


def _apoptosis(history: list[dict]) -> dict:
    msgs = [(m["content"], _ROLE_SIG.get(m["role"], kernel.USER)) for m in history]
    return kernel.dehydrate(msgs, half_life=6.0, safe_threshold=0.35)


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rounds", type=int, default=16)
    ap.add_argument("--model", default="openai/gpt-4o")
    ap.add_argument("--mock", action="store_true")
    args = ap.parse_args()
    rounds = max(15, args.rounds)

    key = os.environ.get("OPENROUTER_API_KEY")
    real = (not args.mock) and bool(key and key.startswith("sk-or"))
    client = LeanOpenRouterClient() if real else None

    print("=" * 92)
    print("  B.I.O.M.A. Micro-Kernel — Lean Efficiency Validation (long session)")
    print("=" * 92)
    mode = "REAL (OpenRouter dispatch + real kernel)" if real else "KERNEL-ONLY (real apoptosis; API dispatch skipped)"
    print(f"  mode: {mode}  ·  rounds: {rounds}  ·  model: {args.model if real else '—'}\n")

    history = seed_history()
    rows = []
    total_cost = 0.0
    try:
        for i in range(1, rounds + 1):
            history += round_messages(i)
            query = f"Round {i}: summarize the session risk so far."
            if real:
                d = await client.dispatch(history, query, model=args.model, max_tokens=160)
                total_cost += d.cost_usd
                rows.append((i, len(history), d.tokens_before, d.tokens_after, d.reduction,
                             d.kernel_latency_us, d.cost_usd, d.rtt_ms, d.error))
                extra = (f" | ${d.cost_usd:.4f} {d.rtt_ms:5.0f}ms"
                         + (f" ERR {d.error[:24]}" if d.error else ""))
            else:
                a = _apoptosis(history)
                rows.append((i, len(history), a["tokens_before"], a["tokens_after"],
                             a["reduction"], a["kernel_latency_us"], 0.0, 0.0, None))
                extra = ""
            r = rows[-1]
            print(f"  round {i:2d} | blocks {r[1]:3d} | tokens {r[2]:6,} → {r[3]:5,} "
                  f"| saved {r[4]*100:5.1f}% | kernel {r[5]:6.2f}μs{extra}")
    finally:
        if client:
            await client.close()

    # ---- aggregate report ------------------------------------------------ #
    n = len(rows)
    avg_red = sum(r[4] for r in rows) / n
    avg_us = sum(r[5] for r in rows) / n
    tot_before = sum(r[2] for r in rows)
    tot_after = sum(r[3] for r in rows)
    saved = tot_before - tot_after

    print("\n" + "=" * 92)
    print("## B.I.O.M.A. Micro-Kernel — auditable efficiency (long session)\n")
    print("| Métrica | Valor |")
    print("| :--- | ---: |")
    print(f"| Rodadas | {n} |")
    print(f"| Redução média de contexto por rodada (apoptose) | **{avg_red*100:.1f}%** |")
    print(f"| Tokens de entrada economizados (total) | **{saved:,}** ({tot_before:,} → {tot_after:,}) |")
    print(f"| Latência média do kernel (apoptose) | **{avg_us:.2f} μs** |")
    print(f"| Latência de pico do kernel | {max(r[5] for r in rows):.2f} μs |")
    if real:
        print(f"| Custo real OpenRouter ({args.model}) | ${total_cost:.4f} |")
        errs = sum(1 for r in rows if r[8])
        print(f"| Dispatches com erro (após backoff) | {errs}/{n} |")
    print(f"\n> Ground truth: latência do kernel medida com `Instant` (μs) e economia de tokens "
          f"contada bloco a bloco. A apoptose converge para a redução universal em sessões longas "
          f"({rows[-1][4]*100:.0f}% na última rodada).")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
