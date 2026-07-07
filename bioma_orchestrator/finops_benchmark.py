"""
finops_benchmark.py — end-to-end token/cost savings from context apoptosis.

Wires the Rust kernel's apoptosis (via `ContextPruner`) into the orchestrator's
context layer and measures the REAL input-token reduction it produces, then turns
that into a FinOps figure at a stated price tier.

Two scenarios:
  1. **Single window** — one realistic agent context (system + recent turns +
     verbose tool logs); apoptosis evicts the low-relevance noise.  This is the
     "30–40%" product claim.
  2. **Multi-turn session** — a bounded, self-pruning window vs. re-sending the
     full history every turn; the savings compound over the session.

Honesty: token counts are REAL (the kernel actually removes items); the reduction
depends on how noisy the context is (stated per scenario).  The `$` is an honest
calculation from a stated input price — **no external model is called** (offline).

Run:  python -m bioma_orchestrator.finops_benchmark
"""

from __future__ import annotations

import json
import os
import time

from .context import ContextPruner, est_tokens, SYSTEM, USER, ASSISTANT, TOOL

PRICE_IN_PER_M = 3.0     # USD / 1M input tokens (illustrative frontier tier)
_PKG = os.path.dirname(os.path.abspath(__file__))


def _pad(prefix: str, target_tokens: int) -> str:
    """Build content of ~`target_tokens` tokens (~4 chars/token)."""
    filler = "trace stack frame json blob detail context log entry value "
    s = prefix + " :: "
    while est_tokens(s) < target_tokens:
        s += filler
    return s


# --------------------------------------------------------------------------- #
#  Scenario 1 — single-window pruning (the 30–40% headline)
# --------------------------------------------------------------------------- #
def single_window(n: int = 500) -> dict:
    full_total = saved_total = 0
    for _ in range(n):
        p = ContextPruner()
        p.add(_pad("SYSTEM: production engineering assistant; spec + rules", 400),
              oxygen=50.0, signal=SYSTEM)
        for i in range(6):                       # recent, relevant turns/facts → keep
            p.add(_pad(f"[recent {i}] relevant user+assistant exchange", 240),
                  oxygen=2.2, signal=USER)
        for i in range(8):                       # verbose tool logs / scratchpad → NOISE
            p.add(_pad(f"[tool {i}] verbose trace dump", 150), oxygen=0.5, signal=TOOL)
        full_t = p.full_tokens()
        p.prune_cycles(3, rate=0.4, reinforce_mask=SYSTEM | USER, reinforce_amount=0.35)
        saved_total += full_t - p.active_tokens()
        full_total += full_t
    avg_full = full_total / n
    avg_saved = saved_total / n
    reduction = saved_total / full_total
    return {
        "scenario": "single_window",
        "requests": n,
        "avg_context_tokens": round(avg_full, 1),
        "avg_tokens_saved": round(avg_saved, 1),
        "reduction_pct": round(reduction * 100, 1),
        "usd_saved_per_request": round(avg_saved / 1e6 * PRICE_IN_PER_M, 6),
        "usd_saved_per_1M_requests": round(avg_saved * PRICE_IN_PER_M, 2),
        "composition": "system(400t) + 6 recent(240t) + 8 tool-logs(150t, noise)",
    }


# --------------------------------------------------------------------------- #
#  Scenario 2 — multi-turn session (compounding savings)
# --------------------------------------------------------------------------- #
def multi_turn(sessions: int = 200, turns: int = 20) -> dict:
    full_total = pruned_total = 0
    for _ in range(sessions):
        p = ContextPruner()
        p.add(_pad("SYSTEM: durable instructions", 400), oxygen=50.0, signal=SYSTEM)
        for _turn in range(turns):
            p.add(_pad("user turn", 120), oxygen=2.0, signal=USER)
            p.add(_pad("assistant answer", 180), oxygen=1.6, signal=ASSISTANT)
            p.add(_pad("tool log verbose", 250), oxygen=0.5, signal=TOOL)   # noise
            full_total += p.full_tokens()                                   # naive: resend all
            p.prune(rate=0.34, reinforce_mask=SYSTEM, reinforce_amount=0.5)
            pruned_total += p.active_tokens()
    reduction = 1.0 - pruned_total / full_total
    saved = full_total - pruned_total
    per_call_full = full_total / (sessions * turns)
    per_call_saved = saved / (sessions * turns)
    return {
        "scenario": "multi_turn_session",
        "sessions": sessions, "turns": turns,
        "avg_full_context_per_call": round(per_call_full, 1),
        "avg_tokens_saved_per_call": round(per_call_saved, 1),
        "reduction_pct": round(reduction * 100, 1),
        "usd_saved_per_1M_calls": round(per_call_saved * PRICE_IN_PER_M, 2),
    }


def run() -> dict:
    t0 = time.time()
    sw = single_window()
    mt = multi_turn()
    return {
        "benchmark": "B.I.O.M.A. — context-apoptosis FinOps (kernel → orchestrator)",
        "backend": ContextPruner().backend,
        "price_in_usd_per_1M": PRICE_IN_PER_M,
        "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "elapsed_s": round(time.time() - t0, 2),
        "single_window": sw,
        "multi_turn": mt,
        "honesty": [
            "Token counts are REAL (the kernel removes items); reduction depends on context noise.",
            "USD is a calculation from a stated input price — no external model was called (offline).",
            "Savings apply to INPUT tokens; output tokens are unaffected by pruning.",
        ],
    }


def _write_md(rep: dict, path: str) -> None:
    sw, mt = rep["single_window"], rep["multi_turn"]
    L = [f"# {rep['benchmark']}", "",
         f"_backend: **{rep['backend']}** · price: ${rep['price_in_usd_per_1M']}/1M input · {rep['generated_utc']}_", "",
         "## 1 · Single window (the product claim)", "",
         f"- Context composition: {sw['composition']}",
         f"- **Reduction: {sw['reduction_pct']}%** — {sw['avg_tokens_saved']:.0f} of "
         f"{sw['avg_context_tokens']:.0f} tokens pruned per request",
         f"- **${sw['usd_saved_per_1M_requests']:,} saved per 1M requests** "
         f"(${sw['usd_saved_per_request']}/request)", "",
         "## 2 · Multi-turn session (compounding)", "",
         f"- {mt['sessions']} sessions × {mt['turns']} turns",
         f"- **Reduction: {mt['reduction_pct']}%** vs. re-sending full history "
         f"({mt['avg_tokens_saved_per_call']:.0f} tokens/call)",
         f"- **${mt['usd_saved_per_1M_calls']:,} saved per 1M calls**", "",
         "## Honesty", ""] + [f"- {h}" for h in rep["honesty"]]
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(L) + "\n")


def main() -> int:
    rep = run()
    with open(os.path.join(_PKG, "FINOPS_REPORT.json"), "w", encoding="utf-8") as fh:
        json.dump(rep, fh, indent=2, ensure_ascii=False)
    _write_md(rep, os.path.join(_PKG, "FINOPS_REPORT.md"))

    sw, mt = rep["single_window"], rep["multi_turn"]
    w = 70
    print("=" * w)
    print(" B.I.O.M.A. — CONTEXT-APOPTOSIS FinOps (kernel → orchestrator) ".center(w, "="))
    print("=" * w)
    print(f"  backend: {rep['backend']}   ·   price: ${PRICE_IN_PER_M}/1M input tokens")
    print("-" * w)
    print("  [1] SINGLE WINDOW (product claim)")
    print(f"      contexto médio ...... {sw['avg_context_tokens']:.0f} tokens/request")
    print(f"      REDUÇÃO ............. {sw['reduction_pct']}%  "
          f"({sw['avg_tokens_saved']:.0f} tokens podados/request)")
    print(f"      $$ economizado ...... ${sw['usd_saved_per_1M_requests']:,} por 1M requests")
    print("  [2] MULTI-TURN SESSION (compounding)")
    print(f"      REDUÇÃO ............. {mt['reduction_pct']}%  vs. reenviar histórico completo")
    print(f"      $$ economizado ...... ${mt['usd_saved_per_1M_calls']:,} por 1M calls")
    print("-" * w)
    print("  written: FINOPS_REPORT.json, FINOPS_REPORT.md")
    print("=" * w)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
